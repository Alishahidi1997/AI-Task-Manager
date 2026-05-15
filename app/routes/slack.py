import json
import os
from datetime import datetime

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import SessionLocal, get_db
from app.deps import get_http_client
from app.llm.openai_client import plan_tool_call_async
from app.models import AuditLog, SlackOrchestrationTrace, User
from app.orchestration.prompt_builder import build_planner_system_prompt
from app.orchestration.tool_registry import filter_tools, tool_schema_map
from app.services.rbac import allowed_tools_for_role
from app.services.slack_bot_client import chat_post_message, slack_bot_token
from app.services.slack_execution import execute_slack_tool
from app.services.slack_idempotency import (
    claim_slack_event,
    duplicate_slack_response,
    should_skip_execution,
    slack_event_id_from_payload,
)
from app.services.slack_observability import (
    SlackTraceRecorder,
    persist_slack_trace,
    trace_response_summary,
)
from app.services.slack_security import verify_slack_signature
from app.validation.json_validator import validate_planner_output
from app.validation.policy_engine import enforce_policies

router = APIRouter(prefix="/slack", tags=["slack"])


def _slack_thread_ts_for_reply(event: dict) -> str | None:
    """Thread to post under: same thread if user was in a thread, else start a thread on their message."""
    ts = event.get("ts")
    if ts is None:
        return None
    root = event.get("thread_ts")
    return str(root) if root else str(ts)


async def _post_slack_user_message(
    http_client: httpx.AsyncClient,
    recorder: SlackTraceRecorder,
    *,
    channel_id: str,
    event: dict,
    text: str,
) -> dict | None:
    token = slack_bot_token()
    if not token:
        return None
    thread_ts = _slack_thread_ts_for_reply(event)
    with recorder.span("slack_post_message"):
        try:
            return await chat_post_message(
                http_client,
                token=token,
                channel=channel_id,
                text=text[:4000],
                thread_ts=thread_ts,
            )
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "error": f"http_{type(exc).__name__}",
                "detail": str(exc)[:500],
            }


def _audit_row(
    db: Session,
    *,
    request_text: str,
    user: User,
    tool_name: str | None,
    arguments: dict | None,
    validation_result: str,
    execution_result: str,
    slack_event_id: str | None = None,
) -> AuditLog:
    row = AuditLog(
        request_text=request_text,
        tool_name=tool_name,
        arguments=json.dumps(arguments, ensure_ascii=True) if arguments is not None else None,
        validation_result=validation_result,
        execution_result=execution_result,
        user_id=user.id,
        tenant_id=user.tenant_id or "default",
        slack_event_id=slack_event_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _save_audit(
    db: Session,
    claim_row: AuditLog | None,
    *,
    request_text: str,
    user: User,
    tool_name: str | None,
    arguments: dict | None,
    validation_result: str,
    execution_result: str,
    slack_event_id: str | None = None,
) -> AuditLog:
    """Update the idempotency claim row when present; otherwise insert a new audit row."""
    if claim_row is not None:
        claim_row.request_text = request_text
        claim_row.tool_name = tool_name
        claim_row.arguments = (
            json.dumps(arguments, ensure_ascii=True) if arguments is not None else None
        )
        claim_row.validation_result = validation_result
        claim_row.execution_result = execution_result
        db.add(claim_row)
        db.commit()
        db.refresh(claim_row)
        return claim_row
    return _audit_row(
        db,
        request_text=request_text,
        user=user,
        tool_name=tool_name,
        arguments=arguments,
        validation_result=validation_result,
        execution_result=execution_result,
        slack_event_id=slack_event_id,
    )


def _slack_events_async_enabled() -> bool:
    """When true (default), acknowledge Slack quickly and run orchestration in a background task."""
    val = os.getenv("SLACK_EVENTS_ASYNC", "true").strip().lower()
    return val not in {"0", "false", "no", "off"}


async def _slack_orchestration_background(
    http_client: httpx.AsyncClient,
    recorder: SlackTraceRecorder,
    user_id: int,
    event: dict,
    slack_user_id: str,
    text: str,
    channel_id: str,
    ts,
    slack_event_id: str | None,
) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return
        try:
            await _orchestrate_slack_message_after_user_map(
                http_client,
                recorder,
                db,
                user,
                event=event,
                slack_user_id=slack_user_id,
                text=text,
                channel_id=channel_id,
                ts=ts,
                slack_event_id=slack_event_id,
            )
        except HTTPException as exc:
            raw = exc.detail
            msg = raw.get("detail", str(raw)) if isinstance(raw, dict) else str(raw)
            await _post_slack_user_message(
                http_client,
                recorder,
                channel_id=channel_id,
                event=event,
                text=f"I couldn't process that request: {msg[:3500]}",
            )
    finally:
        db.close()


async def _orchestrate_slack_message_after_user_map(
    http_client: httpx.AsyncClient,
    recorder: SlackTraceRecorder,
    db: Session,
    user: User,
    *,
    event: dict,
    slack_user_id: str,
    text: str,
    channel_id: str,
    ts,
    slack_event_id: str | None,
) -> dict:
    tenant_id = user.tenant_id or "default"
    allowed = allowed_tools_for_role(user.role)
    tools = filter_tools(allowed)
    identity_context = {
        "user_id": user.id,
        "role": user.role,
        "tenant": user.tenant_id,
        "allowed_tools": allowed,
    }
    planner_prompt = build_planner_system_prompt(identity_context, tools)
    normalized = {
        "slack_user_id": slack_user_id,
        "text": text,
        "channel_id": channel_id,
        "timestamp": ts or datetime.utcnow().timestamp(),
    }

    claim_status, claim_row = claim_slack_event(
        db, slack_event_id, user=user, request_text=text
    )
    if claim_status == "duplicate" and claim_row is not None:
        outcome = (
            "duplicate_executed"
            if claim_row.execution_result == "executed"
            else "duplicate_replay"
        )
        persist_slack_trace(
            db,
            recorder,
            user=user,
            tenant_id=tenant_id,
            slack_channel_id=channel_id,
            slack_message_ts=str(ts) if ts is not None else None,
            slack_user_id=slack_user_id,
            outcome=outcome,
            audit_log_id=claim_row.id,
        )
        return duplicate_slack_response(
            claim_row, trace_id=recorder.trace_id, normalized=normalized
        )

    try:
        with recorder.span("planner_llm"):
            planner_raw = await plan_tool_call_async(http_client, planner_prompt, text)
        with recorder.span("validation"):
            validated_plan = validate_planner_output(
                planner_raw,
                tool_schemas=tool_schema_map(),
                allowed_tools=allowed,
            )
        if validated_plan.missing_required or validated_plan.confidence < 0.35:
            clarify_q = validated_plan.clarification_question or (
                f"Missing required: {', '.join(validated_plan.missing_required)}"
            )
            slack_delivery = await _post_slack_user_message(
                http_client,
                recorder,
                channel_id=channel_id,
                event=event,
                text=f"I need a bit more detail:\n{clarify_q}",
            )
            row = _save_audit(
                db,
                claim_row,
                request_text=text,
                user=user,
                tool_name=validated_plan.tool,
                arguments=validated_plan.arguments,
                validation_result="clarification",
                execution_result="clarification_required",
                slack_event_id=slack_event_id,
            )
            persist_slack_trace(
                db,
                recorder,
                user=user,
                tenant_id=tenant_id,
                slack_channel_id=channel_id,
                slack_message_ts=str(ts) if ts is not None else None,
                slack_user_id=slack_user_id,
                outcome="clarification_required",
                audit_log_id=row.id,
            )
            body = {
                "ok": True,
                "normalized_request": normalized,
                "identity_context": identity_context,
                "allowed_tools": tools,
                "status": "clarification_required",
                "clarification_question": clarify_q,
                "planner_output": validated_plan.model_dump(),
                "audit_id": row.id,
                "trace": trace_response_summary(recorder),
            }
            if slack_delivery is not None:
                body["slack_delivery"] = slack_delivery
            return body
        with recorder.span("policy"):
            enforce_policies(identity_context, validated_plan.tool, validated_plan.arguments)
    except PermissionError as exc:
        slack_delivery = await _post_slack_user_message(
            http_client,
            recorder,
            channel_id=channel_id,
            event=event,
            text=f"I can't run that (policy): {str(exc)[:3500]}",
        )
        row = _save_audit(
            db,
            claim_row,
            request_text=text,
            user=user,
            tool_name=None,
            arguments=None,
            validation_result="failed",
            execution_result="policy_rejected",
            slack_event_id=slack_event_id,
        )
        persist_slack_trace(
            db,
            recorder,
            user=user,
            tenant_id=tenant_id,
            slack_channel_id=channel_id,
            slack_message_ts=str(ts) if ts is not None else None,
            slack_user_id=slack_user_id,
            outcome="policy_rejected",
            audit_log_id=row.id,
        )
        body = {
            "ok": False,
            "normalized_request": normalized,
            "identity_context": identity_context,
            "status": "policy_rejected",
            "reason": str(exc),
            "audit_id": row.id,
            "trace": trace_response_summary(recorder),
        }
        if slack_delivery is not None:
            body["slack_delivery"] = slack_delivery
        return body
    except Exception as exc:
        try:
            row = _save_audit(
                db,
                claim_row,
                request_text=text,
                user=user,
                tool_name=None,
                arguments=None,
                validation_result="failed",
                execution_result="failed",
                slack_event_id=slack_event_id,
            )
            persist_slack_trace(
                db,
                recorder,
                user=user,
                tenant_id=tenant_id,
                slack_channel_id=channel_id,
                slack_message_ts=str(ts) if ts is not None else None,
                slack_user_id=slack_user_id,
                outcome="validation_failed",
                audit_log_id=row.id,
            )
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                "detail": str(exc),
                "trace_id": recorder.trace_id,
            },
        ) from exc

    prior_executed = should_skip_execution(db, slack_event_id)
    if prior_executed is not None:
        persist_slack_trace(
            db,
            recorder,
            user=user,
            tenant_id=tenant_id,
            slack_channel_id=channel_id,
            slack_message_ts=str(ts) if ts is not None else None,
            slack_user_id=slack_user_id,
            outcome="duplicate_executed",
            audit_log_id=prior_executed.id,
        )
        return duplicate_slack_response(
            prior_executed, trace_id=recorder.trace_id, normalized=normalized
        )

    try:
        with recorder.span("execution"):
            exec_result = execute_slack_tool(
                tool=validated_plan.tool,
                arguments=validated_plan.arguments,
                user=user,
                db=db,
            )
    except PermissionError as exc:
        slack_delivery = await _post_slack_user_message(
            http_client,
            recorder,
            channel_id=channel_id,
            event=event,
            text=f"I can't complete that (permission): {str(exc)[:3500]}",
        )
        row = _save_audit(
            db,
            claim_row,
            request_text=text,
            user=user,
            tool_name=validated_plan.tool,
            arguments=validated_plan.arguments,
            validation_result="passed",
            execution_result="denied",
            slack_event_id=slack_event_id,
        )
        persist_slack_trace(
            db,
            recorder,
            user=user,
            tenant_id=tenant_id,
            slack_channel_id=channel_id,
            slack_message_ts=str(ts) if ts is not None else None,
            slack_user_id=slack_user_id,
            outcome="execution_denied",
            audit_log_id=row.id,
        )
        body = {
            "ok": False,
            "normalized_request": normalized,
            "identity_context": identity_context,
            "status": "execution_denied",
            "reason": str(exc),
            "planner_output": validated_plan.model_dump(),
            "audit_id": row.id,
            "trace": trace_response_summary(recorder),
        }
        if slack_delivery is not None:
            body["slack_delivery"] = slack_delivery
        return body
    except ValueError as exc:
        slack_delivery = await _post_slack_user_message(
            http_client,
            recorder,
            channel_id=channel_id,
            event=event,
            text=f"I couldn't complete that: {str(exc)[:3500]}",
        )
        row = _save_audit(
            db,
            claim_row,
            request_text=text,
            user=user,
            tool_name=validated_plan.tool,
            arguments=validated_plan.arguments,
            validation_result="passed",
            execution_result="failed",
            slack_event_id=slack_event_id,
        )
        persist_slack_trace(
            db,
            recorder,
            user=user,
            tenant_id=tenant_id,
            slack_channel_id=channel_id,
            slack_message_ts=str(ts) if ts is not None else None,
            slack_user_id=slack_user_id,
            outcome="execution_failed",
            audit_log_id=row.id,
        )
        body = {
            "ok": False,
            "normalized_request": normalized,
            "identity_context": identity_context,
            "status": "execution_failed",
            "reason": str(exc),
            "planner_output": validated_plan.model_dump(),
            "audit_id": row.id,
            "trace": trace_response_summary(recorder),
        }
        if slack_delivery is not None:
            body["slack_delivery"] = slack_delivery
        return body

    tool = validated_plan.tool
    tid = exec_result.get("task_id")
    st = exec_result.get("status")
    success_bits = [f"Done — executed `{tool}`."]
    if tid is not None:
        success_bits.append(f"Task #{tid} (status: `{st}`).")
    slack_delivery = await _post_slack_user_message(
        http_client,
        recorder,
        channel_id=channel_id,
        event=event,
        text=" ".join(success_bits),
    )

    row = _save_audit(
        db,
        claim_row,
        request_text=text,
        user=user,
        tool_name=validated_plan.tool,
        arguments=validated_plan.arguments,
        validation_result="passed",
        execution_result="executed",
        slack_event_id=slack_event_id,
    )
    persist_slack_trace(
        db,
        recorder,
        user=user,
        tenant_id=tenant_id,
        slack_channel_id=channel_id,
        slack_message_ts=str(ts) if ts is not None else None,
        slack_user_id=slack_user_id,
        outcome="executed",
        audit_log_id=row.id,
    )

    body = {
        "ok": True,
        "normalized_request": normalized,
        "identity_context": identity_context,
        "allowed_tools": tools,
        "planner_prompt": planner_prompt,
        "planner_output": validated_plan.model_dump(),
        "status": "executed",
        "execution": exec_result,
        "audit_id": row.id,
        "trace": trace_response_summary(recorder),
    }
    if slack_delivery is not None:
        body["slack_delivery"] = slack_delivery
    return body


@router.post("/events")
async def slack_events(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
):
    raw = await request.body()
    recorder = SlackTraceRecorder()
    try:
        with recorder.span("signature_verify"):
            verify_slack_signature(
                timestamp=request.headers.get("X-Slack-Request-Timestamp"),
                signature=request.headers.get("X-Slack-Signature"),
                raw_body=raw,
            )
        with recorder.span("parse_payload"):
            payload = json.loads(raw.decode("utf-8"))
    except HTTPException:
        raise

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    event = payload.get("event") or {}
    if event.get("type") != "message":
        return {"ok": True, "ignored": True}

    if event.get("subtype") is not None:
        return {"ok": True, "ignored": True, "reason": "skipped_non_plain_message"}

    slack_user_id = event.get("user")
    text = event.get("text")
    channel_id = event.get("channel")
    ts = event.get("ts")
    tenant_fallback = "default"

    if not slack_user_id or not text or not channel_id:
        persist_slack_trace(
            db,
            recorder,
            user=None,
            tenant_id=tenant_fallback,
            slack_channel_id=channel_id,
            slack_message_ts=str(ts) if ts is not None else None,
            slack_user_id=slack_user_id,
            outcome="malformed_event",
        )
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "malformed slack event payload",
                "trace_id": recorder.trace_id,
            },
        )

    with recorder.span("user_resolve"):
        user = db.query(User).filter(User.slack_user_id == slack_user_id).first()

    if not user:
        persist_slack_trace(
            db,
            recorder,
            user=None,
            tenant_id=tenant_fallback,
            slack_channel_id=channel_id,
            slack_message_ts=str(ts) if ts is not None else None,
            slack_user_id=slack_user_id,
            outcome="user_not_mapped",
        )
        raise HTTPException(
            status_code=404,
            detail={
                "detail": "slack user is not mapped to an internal user",
                "trace_id": recorder.trace_id,
            },
        )

    slack_event_id = slack_event_id_from_payload(payload, event)

    if _slack_events_async_enabled():
        background_tasks.add_task(
            _slack_orchestration_background,
            http_client,
            recorder,
            user.id,
            dict(event),
            slack_user_id,
            text,
            channel_id,
            ts,
            slack_event_id,
        )
        return {"ok": True, "accepted": True, "trace_id": recorder.trace_id}

    return await _orchestrate_slack_message_after_user_map(
        http_client,
        recorder,
        db,
        user,
        event=event,
        slack_user_id=slack_user_id,
        text=text,
        channel_id=channel_id,
        ts=ts,
        slack_event_id=slack_event_id,
    )


@router.get("/traces/{trace_id}")
def get_slack_trace(
    trace_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(SlackOrchestrationTrace)
        .filter(SlackOrchestrationTrace.trace_id == trace_id)
        .first()
    )
    if row is None or row.user_id is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="trace not found")

    spans = json.loads(row.spans_json) if row.spans_json else []
    metrics = json.loads(row.metrics_json) if row.metrics_json else {}

    return {
        "trace_id": row.trace_id,
        "audit_log_id": row.audit_log_id,
        "outcome": row.outcome,
        "total_duration_ms": row.total_duration_ms,
        "slack_channel_id": row.slack_channel_id,
        "slack_message_ts": row.slack_message_ts,
        "slack_user_id": row.slack_user_id,
        "tenant_id": row.tenant_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "spans": spans,
        "metrics": metrics,
    }
