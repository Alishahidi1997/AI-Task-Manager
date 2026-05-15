"""Slack Events API idempotency — duplicate webhooks must not re-run Layer 7 execution."""

from __future__ import annotations

import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditLog, User

# Outcomes that mean this event_id was already handled end-to-end.
_TERMINAL_DUPLICATE = frozenset(
    {
        "executed",
        "clarification_required",
        "policy_rejected",
        "execution_denied",
        "execution_failed",
        "validation_failed",
        "failed",
    }
)


def slack_event_id_from_payload(payload: dict, event: dict) -> str | None:
    """
    Slack's top-level event_id (event_callback) is the primary idempotency key.
    Fallback: channel + message ts when event_id is missing (local tests).
    """
    top = payload.get("event_id")
    if top:
        return str(top).strip()
    channel = event.get("channel")
    ts = event.get("ts")
    if channel and ts:
        return f"{channel}:{ts}"
    return None


def find_duplicate_audit(db: Session, slack_event_id: str) -> AuditLog | None:
    """Return a prior audit row for this event if we should not execute again."""
    row = (
        db.query(AuditLog)
        .filter(AuditLog.slack_event_id == slack_event_id)
        .order_by(AuditLog.id.desc())
        .first()
    )
    if row is None:
        return None
    if row.execution_result in _TERMINAL_DUPLICATE:
        return row
    if row.execution_result == "processing":
        return row
    return None


def claim_slack_event(
    db: Session,
    slack_event_id: str | None,
    *,
    user: User,
    request_text: str,
) -> tuple[str, AuditLog | None]:
    """
    Reserve processing for this Slack delivery.

    Returns:
        ("proceed", audit_row) — new or no key; continue orchestration and update audit_row.
        ("duplicate", audit_row) — already seen; do not call execute_slack_tool.
    """
    if not slack_event_id:
        return "proceed", None

    prior = find_duplicate_audit(db, slack_event_id)
    if prior is not None:
        return "duplicate", prior

    row = AuditLog(
        request_text=request_text,
        tool_name=None,
        arguments=None,
        validation_result="pending",
        execution_result="processing",
        user_id=user.id,
        tenant_id=user.tenant_id or "default",
        slack_event_id=slack_event_id,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return "proceed", row
    except IntegrityError:
        db.rollback()
        prior = find_duplicate_audit(db, slack_event_id)
        return "duplicate", prior


def should_skip_execution(db: Session, slack_event_id: str | None) -> AuditLog | None:
    """Layer 7 gate: block execute_slack_tool if this event_id already reached a terminal state."""
    if not slack_event_id:
        return None
    row = (
        db.query(AuditLog)
        .filter(
            AuditLog.slack_event_id == slack_event_id,
            AuditLog.execution_result == "executed",
        )
        .first()
    )
    return row


def duplicate_slack_response(prior: AuditLog, *, trace_id: str, normalized: dict) -> dict:
    """Safe replay body for Slack retries (no second execution)."""
    args = None
    if prior.arguments:
        try:
            args = json.loads(prior.arguments)
        except json.JSONDecodeError:
            args = prior.arguments
    status = prior.execution_result
    if status == "processing":
        status = "duplicate_inflight"
    body: dict = {
        "ok": True,
        "status": status,
        "duplicate": True,
        "slack_event_id": prior.slack_event_id,
        "audit_id": prior.id,
        "normalized_request": normalized,
        "trace_id": trace_id,
        "message": "This Slack event was already processed; execution skipped.",
    }
    if prior.tool_name:
        body["tool_name"] = prior.tool_name
    if args is not None:
        body["arguments"] = args
    if status == "executed" and isinstance(args, dict):
        body["execution"] = {
            "tool_name": prior.tool_name,
            "note": "replayed from audit log",
        }
    return body
