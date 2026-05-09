import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import AuditLog, User
from app.services.chat_orchestrator import orchestrate_chat

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
def chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = f"user-{current_user.id}"
    try:
        result = orchestrate_chat(
            payload.message,
            source=payload.source,
            conversation_id=payload.conversation_id,
            current_user=current_user,
            db=db,
        )
        planner = result.get("planner_output") or {}
        row = AuditLog(
            request_text=payload.message,
            tool_name=planner.get("tool_name"),
            arguments=json.dumps(planner.get("arguments", {}), ensure_ascii=True),
            validation_result="passed" if result.get("status") == "executed" else "clarification",
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
