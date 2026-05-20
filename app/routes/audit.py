"""Admin audit views: list orchestration outcomes and unified Slack trace chains."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import AuditLog, SlackOrchestrationTrace, User
from app.services.rbac import is_manager_or_admin

router = APIRouter(prefix="/audit", tags=["audit"])


def _require_audit_viewer(user: User) -> None:
    if not is_manager_or_admin(user.role):
        raise HTTPException(status_code=403, detail="manager or admin role required")


def _audit_row_dict(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "request_text": row.request_text,
        "tool_name": row.tool_name,
        "arguments": row.arguments,
        "validation_result": row.validation_result,
        "execution_result": row.execution_result,
        "user_id": row.user_id,
        "tenant_id": row.tenant_id,
        "slack_event_id": row.slack_event_id,
        "created_at": row.created_at,
    }


def _trace_dict(row: SlackOrchestrationTrace) -> dict:
    return {
        "trace_id": row.trace_id,
        "audit_log_id": row.audit_log_id,
        "outcome": row.outcome,
        "total_duration_ms": row.total_duration_ms,
        "slack_channel_id": row.slack_channel_id,
        "slack_message_ts": row.slack_message_ts,
        "slack_user_id": row.slack_user_id,
        "tenant_id": row.tenant_id,
        "spans": json.loads(row.spans_json) if row.spans_json else [],
        "metrics": json.loads(row.metrics_json) if row.metrics_json else {},
        "created_at": row.created_at,
    }


@router.get("")
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List audit rows for the tenant (manager/admin). Optional filter by user_id."""
    _require_audit_viewer(current_user)
    tenant = current_user.tenant_id or f"user-{current_user.id}"
    query = db.query(AuditLog).filter(AuditLog.tenant_id == tenant)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    rows = query.order_by(AuditLog.id.desc()).limit(limit).all()
    return {"items": [_audit_row_dict(row) for row in rows], "count": len(rows)}


@router.get("/{audit_id}")
def get_audit_detail(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Unified audit detail: validation + execution + linked Slack trace when present.
    Managers/admins see any row in their tenant; others only their own rows.
    """
    row = db.query(AuditLog).filter(AuditLog.id == audit_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="audit log not found")

    tenant = current_user.tenant_id or f"user-{current_user.id}"
    if row.user_id != current_user.id:
        if not is_manager_or_admin(current_user.role) or row.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="audit log not found")

    trace = (
        db.query(SlackOrchestrationTrace)
        .filter(SlackOrchestrationTrace.audit_log_id == audit_id)
        .order_by(SlackOrchestrationTrace.id.desc())
        .first()
    )
    body = _audit_row_dict(row)
    body["trace"] = _trace_dict(trace) if trace else None
    return body
