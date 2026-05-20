import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
import httpx

from app.auth import get_current_user
from app.database import get_db
from app.deps import get_http_client, get_redis
from app.models import AuditLog, User
from app.queue.config import llm_queue_enabled
from app.services.chat_orchestrator import orchestrate_chat, orchestrate_chat_stream, orchestrate_clarify
from app.services.llm_queue_enqueue import enqueue_chat_orchestration
from app.services.audit_utils import audit_validation_result
from app.services.rate_limit import bump_stat, enforce_chat_rate_limit

router = APIRouter(tags=["chat"])


class ChatIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=3, max_length=4000)
    source: str = Field(default="api", min_length=2, max_length=50)
    conversation_id: str | None = Field(default=None, max_length=255)


class ClarifyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    conversation_id: str = Field(min_length=1, max_length=255)
    answer: str = Field(min_length=1, max_length=2000)


@router.post("/chat")
async def chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    redis=Depends(get_redis),
):
    tenant_id = f"user-{current_user.id}"
    await bump_stat(redis, "stats:chat_requests")
    await enforce_chat_rate_limit(redis, current_user.id)

    if llm_queue_enabled():
        try:
            job_id = await enqueue_chat_orchestration(
                db,
                user=current_user,
                message=payload.message,
                source=payload.source,
                conversation_id=payload.conversation_id,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"could not enqueue chat job: {exc}",
            ) from exc
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "accepted",
                "job_id": job_id,
                "poll_url": f"/jobs/{job_id}",
                "message": "Chat orchestration queued; poll GET /jobs/{job_id} for result.",
            },
        )

    try:
        result = await orchestrate_chat(
            payload.message,
            source=payload.source,
            conversation_id=payload.conversation_id,
            current_user=current_user,
            db=db,
            http_client=http_client,
        )
        planner = result.get("planner_output") or {}
        row = AuditLog(
            request_text=payload.message,
            tool_name=planner.get("tool_name"),
            arguments=json.dumps(planner.get("arguments", {}), ensure_ascii=True),
            validation_result=audit_validation_result(result.get("status", "unknown")),
            execution_result=result.get("status", "unknown"),
            user_id=current_user.id,
            tenant_id=tenant_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"audit_id": row.id, **result}
    except Exception as exc:
        row = AuditLog(
            request_text=payload.message,
            tool_name=None,
            arguments=None,
            validation_result="failed",
            execution_result="failed",
            user_id=current_user.id,
            tenant_id=tenant_id,
        )
        db.add(row)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    redis=Depends(get_redis),
):
    """Server-sent events: planner tokens streamed, then a final `result` event (same shape as `/chat`)."""
    tenant_id = f"user-{current_user.id}"
    await bump_stat(redis, "stats:chat_stream_requests")
    await enforce_chat_rate_limit(redis, current_user.id)

    async def event_generator():
        final_result = None
        try:
            async for evt in orchestrate_chat_stream(
                payload.message,
                source=payload.source,
                conversation_id=payload.conversation_id,
                current_user=current_user,
                db=db,
                http_client=http_client,
            ):
                if evt.get("event") == "result":
                    final_result = evt
                yield f"data: {json.dumps(evt, default=str)}\n\n"
        except PermissionError as exc:
            row = AuditLog(
                request_text=payload.message,
                tool_name=None,
                arguments=None,
                validation_result="failed",
                execution_result="denied",
                user_id=current_user.id,
                tenant_id=tenant_id,
            )
            db.add(row)
            db.commit()
            yield f"data: {json.dumps({'event': 'error', 'detail': str(exc), 'code': 403})}\n\n"
            return
        except Exception as exc:
            row = AuditLog(
                request_text=payload.message,
                tool_name=None,
                arguments=None,
                validation_result="failed",
                execution_result="failed",
                user_id=current_user.id,
                tenant_id=tenant_id,
            )
            db.add(row)
            db.commit()
            yield f"data: {json.dumps({'event': 'error', 'detail': str(exc), 'code': 400})}\n\n"
            return

        if not final_result:
            return
        # Strip wrapper keys for audit alignment with non-streaming `/chat`
        inner = {k: v for k, v in final_result.items() if k != "event"}
        planner = inner.get("planner_output") or {}
        try:
            row = AuditLog(
                request_text=payload.message,
                tool_name=planner.get("tool_name"),
                arguments=json.dumps(planner.get("arguments", {}), ensure_ascii=True),
                validation_result=audit_validation_result(inner.get("status", "unknown")),
                execution_result=inner.get("status", "unknown"),
                user_id=current_user.id,
                tenant_id=tenant_id,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            yield f"data: {json.dumps({'event': 'audit', 'audit_id': row.id})}\n\n"
        except Exception:
            db.rollback()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/clarify")
def clarify(
    payload: ClarifyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = f"user-{current_user.id}"
    try:
        result = orchestrate_clarify(
            payload.conversation_id,
            payload.answer,
            current_user=current_user,
            db=db,
        )
        planner = result.get("planner_output") or {}
        row = AuditLog(
            request_text=f"[clarify:{payload.conversation_id}] {payload.answer}",
            tool_name=planner.get("tool_name"),
            arguments=json.dumps(planner.get("arguments", {}), ensure_ascii=True, default=str),
            validation_result=audit_validation_result(result.get("status", "unknown")),
            execution_result=result.get("status", "unknown"),
            user_id=current_user.id,
            tenant_id=tenant_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"audit_id": row.id, **result}
    except ValueError as exc:
        row = AuditLog(
            request_text=f"[clarify:{payload.conversation_id}] {payload.answer}",
            tool_name=None,
            arguments=None,
            validation_result="failed",
            execution_result="failed",
            user_id=current_user.id,
            tenant_id=tenant_id,
        )
        db.add(row)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
