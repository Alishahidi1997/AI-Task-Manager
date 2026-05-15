import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
import httpx

from app.auth import get_current_user
from app.database import get_db
from app.deps import get_http_client, get_redis
from app.models import AuditLog, User
from app.services.chat_orchestrator import orchestrate_chat, orchestrate_chat_stream

router = APIRouter(tags=["chat"])


def _audit_validation_result(execution_status: str) -> str:
    if execution_status == "executed":
        return "passed"
    if execution_status == "clarification_required":
        return "clarification"
    return "failed"


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
    if redis is not None:
        await redis.incr("stats:chat_requests")
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
            validation_result=_audit_validation_result(result.get("status", "unknown")),
            execution_result=result.get("status", "unknown"),
            user_id=current_user.id,
            tenant_id=tenant_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"audit_id": row.id, **result}
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
        raise HTTPException(status_code=403, detail=str(exc)) from exc
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
    if redis is not None:
        await redis.incr("stats:chat_stream_requests")

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
                validation_result=_audit_validation_result(inner.get("status", "unknown")),
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


@router.get("/audit/{audit_id}")
def get_audit_log(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(AuditLog)
        .filter(AuditLog.id == audit_id, AuditLog.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="audit log not found")
    return {
        "id": row.id,
        "request_text": row.request_text,
        "tool_name": row.tool_name,
        "arguments": row.arguments,
        "validation_result": row.validation_result,
        "execution_result": row.execution_result,
        "user_id": row.user_id,
        "tenant_id": row.tenant_id,
        "created_at": row.created_at,
    }


@router.post("/clarify")
def clarify(
    payload: ClarifyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Simple placeholder endpoint for clarification loop orchestration.
    row = AuditLog(
        request_text=f"[clarify:{payload.conversation_id}] {payload.answer}",
        tool_name="clarify",
        arguments=json.dumps({"conversation_id": payload.conversation_id, "answer": payload.answer}),
        validation_result="passed",
        execution_result="received",
        user_id=current_user.id,
        tenant_id=f"user-{current_user.id}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "clarification_received", "audit_id": row.id}
