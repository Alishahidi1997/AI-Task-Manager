import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import httpx

from app.database import get_db
from app.deps import get_http_client
from app.llm.openai_client import plan_tool_call_async
from app.models import AuditLog, User
from app.orchestration.prompt_builder import build_planner_system_prompt
from app.orchestration.tool_registry import filter_tools, tool_schema_map
from app.services.rbac import allowed_tools_for_role
from app.services.slack_execution import execute_slack_tool
from app.services.slack_security import verify_slack_signature
from app.validation.json_validator import validate_planner_output
from app.validation.policy_engine import enforce_policies

router = APIRouter(prefix="/slack", tags=["slack"])


def _audit_row(
    db: Session,
    *,
    request_text: str,
    user: User,
    tool_name: str | None,
    arguments: dict | None,
    validation_result: str,
    execution_result: str,
) -> AuditLog:
    row = AuditLog(
        request_text=request_text,
        tool_name=tool_name,
        arguments=json.dumps(arguments, ensure_ascii=True) if arguments is not None else None,
        validation_result=validation_result,
        execution_result=execution_result,
        user_id=user.id,
        tenant_id=user.tenant_id or "default",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/events")
async def slack_events(
    request: Request,
    db: Session = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
):
    raw = await request.body()
    verify_slack_signature(
        timestamp=request.headers.get("X-Slack-Request-Timestamp"),
        signature=request.headers.get("X-Slack-Signature"),
        raw_body=raw,
    )
    payload = await request.json()

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    event = payload.get("event") or {}
    if event.get("type") != "message":
        return {"ok": True, "ignored": True}

    slack_user_id = event.get("user")
    text = event.get("text")
    channel_id = event.get("channel")
    ts = event.get("ts")
    if not slack_user_id or not text or not channel_id:
        raise HTTPException(status_code=400, detail="malformed slack event payload")

    user = db.query(User).filter(User.slack_user_id == slack_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="slack user is not mapped to an internal user")

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
    try:
        planner_raw = await plan_tool_call_async(http_client, planner_prompt, text)
        validated_plan = validate_planner_output(
            planner_raw,
            tool_schemas=tool_schema_map(),
            allowed_tools=allowed,
        )
        if validated_plan.missing_required or validated_plan.confidence < 0.35:
            row = _audit_row(
                db,
                request_text=text,
                user=user,
                tool_name=validated_plan.tool,
                arguments=validated_plan.arguments,
                validation_result="clarification",
                execution_result="clarification_required",
            )
            return {
                "ok": True,
                "normalized_request": normalized,
                "identity_context": identity_context,
                "allowed_tools": tools,
                "status": "clarification_required",
                "clarification_question": validated_plan.clarification_question
                or f"Missing required: {', '.join(validated_plan.missing_required)}",
                "planner_output": validated_plan.model_dump(),
                "audit_id": row.id,
            }
        enforce_policies(identity_context, validated_plan.tool, validated_plan.arguments)
    except PermissionError as exc:
        row = _audit_row(
            db,
            request_text=text,
            user=user,
            tool_name=None,
            arguments=None,
            validation_result="failed",
            execution_result="policy_rejected",
        )
        return {
            "ok": False,
            "normalized_request": normalized,
            "identity_context": identity_context,
            "status": "policy_rejected",
            "reason": str(exc),
            "audit_id": row.id,
        }
    except Exception as exc:
        try:
            _audit_row(
                db,
                request_text=text,
                user=user,
                tool_name=None,
                arguments=None,
                validation_result="failed",
                execution_result="failed",
            )
        except Exception:
            db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        exec_result = execute_slack_tool(
            tool=validated_plan.tool,
            arguments=validated_plan.arguments,
            user=user,
            db=db,
        )
    except PermissionError as exc:
        row = _audit_row(
            db,
            request_text=text,
            user=user,
            tool_name=validated_plan.tool,
            arguments=validated_plan.arguments,
            validation_result="passed",
            execution_result="denied",
        )
        return {
            "ok": False,
            "normalized_request": normalized,
            "identity_context": identity_context,
            "status": "execution_denied",
            "reason": str(exc),
            "planner_output": validated_plan.model_dump(),
            "audit_id": row.id,
        }
    except ValueError as exc:
        row = _audit_row(
            db,
            request_text=text,
            user=user,
            tool_name=validated_plan.tool,
            arguments=validated_plan.arguments,
            validation_result="passed",
            execution_result="failed",
        )
        return {
            "ok": False,
            "normalized_request": normalized,
            "identity_context": identity_context,
            "status": "execution_failed",
            "reason": str(exc),
            "planner_output": validated_plan.model_dump(),
            "audit_id": row.id,
        }

    row = _audit_row(
        db,
        request_text=text,
        user=user,
        tool_name=validated_plan.tool,
        arguments=validated_plan.arguments,
        validation_result="passed",
        execution_result="executed",
    )

    return {
        "ok": True,
        "normalized_request": normalized,
        "identity_context": identity_context,
        "allowed_tools": tools,
        "planner_prompt": planner_prompt,
        "planner_output": validated_plan.model_dump(),
        "status": "executed",
        "execution": exec_result,
        "audit_id": row.id,
    }
