import json
import os
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.llm.openai_client import stream_chat_completion_text
from app.models import Task
from app.services.category_guess import guess_category
from app.services.rbac import allowed_tools_for_role
from app.services.task_workflow import assert_status_transition
from app.validation.json_validator import validate_chat_planner_output
from app.validation.policy_engine import enforce_policies

VALID_STATUS = {"todo", "in_progress", "done"}
VALID_CATEGORY = {"today", "this_week", "routine", "backlog"}
CHAT_TOOL_NAMES = frozenset({"create_task", "update_task", "delete_task"})


class CreateTaskArgs(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    due_date: datetime
    priority: str | None = Field(default=None, max_length=32)
    assignee: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    category: str | None = Field(default=None, max_length=64)


class UpdateTaskArgs(BaseModel):
    task_id: int
    status: str | None = None
    assignee: str | None = Field(default=None, max_length=255)
    due_date: datetime | None = None
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=8000)


class DeleteTaskArgs(BaseModel):
    task_id: int


class PlannerOutput(BaseModel):
    tool_name: str
    arguments: dict
    confidence: float = Field(ge=0.0, le=1.0)
    missing_required: list[str] = Field(default_factory=list)
    clarification_question: str | None = None


def _tool_registry() -> dict:
    return {
        "create_task": {
            "required": ["title", "due_date"],
            "optional": ["priority", "assignee", "description", "category"],
        },
        "update_task": {
            "required": ["task_id"],
            "optional": ["status", "assignee", "due_date", "title", "description"],
        },
        "delete_task": {
            "required": ["task_id"],
            "optional": [],
        },
    }


def _chat_tool_registry_for_user(user) -> dict:
    """Role-filtered tool schemas exposed to the chat planner."""
    allowed = set(allowed_tools_for_role(user.role)) & CHAT_TOOL_NAMES
    full = _tool_registry()
    return {name: full[name] for name in allowed if name in full}


def _validate_tool_output(payload: PlannerOutput):
    if payload.tool_name not in _tool_registry():
        raise ValueError(f"unknown tool '{payload.tool_name}'")
    if payload.tool_name == "create_task":
        return CreateTaskArgs(**payload.arguments)
    if payload.tool_name == "update_task":
        parsed = UpdateTaskArgs(**payload.arguments)
        if parsed.status is not None and parsed.status not in VALID_STATUS:
            raise ValueError("invalid status")
        return parsed
    return DeleteTaskArgs(**payload.arguments)


def _build_identity_context(user):
    role = (user.role or "employee").strip().lower()
    return {
        "user_id": user.id,
        "tenant_id": user.tenant_id or f"user-{user.id}",
        "role": role,
        "tenant": user.tenant_id or f"user-{user.id}",
    }


def _policy_context(identity_ctx: dict) -> dict:
    return {
        "user_id": identity_ctx["user_id"],
        "role": identity_ctx["role"],
        "tenant": identity_ctx["tenant"],
    }


def _api_key_header() -> dict[str, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}


def _chat_planner_openai_payload(
    message: str, identity_ctx: dict, tool_registry: dict, source: str, conversation_id: str | None
) -> dict:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    now_iso = datetime.now(timezone.utc).isoformat()
    system_text = (
        "You are a strict planner. Output JSON only with keys: "
        "tool_name, arguments, confidence, missing_required, clarification_question. "
        "Pick one tool from registry. Do not hallucinate fields."
    )
    user_text = (
        f"now={now_iso}\nsource={source}\nconversation_id={conversation_id}\n"
        f"identity={json.dumps(identity_ctx)}\n"
        f"tool_registry={json.dumps(tool_registry)}\n"
        f"request={message}"
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.1,
        "max_tokens": 350,
        "response_format": {"type": "json_object"},
    }


async def _llm_plan_async(
    client: httpx.AsyncClient,
    message: str,
    identity_ctx: dict,
    tool_registry: dict,
    source: str,
    conversation_id: str | None,
):
    payload = _chat_planner_openai_payload(message, identity_ctx, tool_registry, source, conversation_id)
    response = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers=_api_key_header(),
        json=payload,
    )
    response.raise_for_status()
    data = response.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or "{}"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON from planner") from exc
    validated = validate_chat_planner_output(parsed, tool_registry=tool_registry)
    return validated, parsed


def _complete_after_plan(
    planner_output: PlannerOutput, raw_output: dict, identity_ctx: dict, current_user, db
):
    if planner_output.missing_required:
        return {
            "status": "clarification_required",
            "question": planner_output.clarification_question
            or f"Missing required fields: {', '.join(planner_output.missing_required)}",
            "planner_output": planner_output.model_dump(),
            "identity": identity_ctx,
            "raw_planner_output": raw_output,
        }
    if planner_output.confidence < 0.35:
        return {
            "status": "clarification_required",
            "question": planner_output.clarification_question
            or "I need more detail before I can execute this request safely.",
            "planner_output": planner_output.model_dump(),
            "identity": identity_ctx,
            "raw_planner_output": raw_output,
        }
    try:
        validated_args = _validate_tool_output(planner_output)
    except (ValidationError, ValueError) as exc:
        raise ValueError(f"validation failed: {exc}") from exc
    enforce_policies(_policy_context(identity_ctx), planner_output.tool_name, planner_output.arguments)
    result = _execute(planner_output.tool_name, validated_args, current_user, db)
    return {
        "status": "executed",
        "result": result,
        "planner_output": planner_output.model_dump(),
        "identity": identity_ctx,
        "raw_planner_output": raw_output,
    }


def _execute(tool_name: str, args, current_user, db):
    if tool_name == "create_task":
        category = args.category if args.category in VALID_CATEGORY else None
        if category is None:
            category = guess_category(args.title, args.description or "", args.due_date)
        task = Task(
            title=args.title,
            description=args.description,
            due_date=args.due_date,
            status="todo",
            category=category,
            user_id=current_user.id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return {"tool_name": tool_name, "task_id": task.id, "status": task.status}

    if tool_name == "update_task":
        task = db.query(Task).filter(Task.id == args.task_id, Task.user_id == current_user.id).first()
        if not task:
            raise ValueError("task not found")
        if args.title is not None:
            task.title = args.title
        if args.description is not None:
            task.description = args.description
        if args.due_date is not None:
            task.due_date = args.due_date
        if args.status is not None:
            assert_status_transition(task.status, args.status)
            task.status = args.status
            if args.status == "done":
                task.completed_at = datetime.now(timezone.utc)
            elif task.completed_at is not None:
                task.completed_at = None
        db.add(task)
        db.commit()
        db.refresh(task)
        return {"tool_name": tool_name, "task_id": task.id, "status": task.status}

    task = db.query(Task).filter(Task.id == args.task_id, Task.user_id == current_user.id).first()
    if not task:
        raise ValueError("task not found")
    db.delete(task)
    db.commit()
    return {"tool_name": tool_name, "task_id": args.task_id, "status": "deleted"}


async def orchestrate_chat(
    message: str,
    source: str,
    conversation_id: str | None,
    current_user,
    db,
    http_client: httpx.AsyncClient,
):
    identity_ctx = _build_identity_context(current_user)
    tool_registry = _chat_tool_registry_for_user(current_user)
    planner_output, raw_output = await _llm_plan_async(
        http_client, message, identity_ctx, tool_registry, source, conversation_id
    )
    return _complete_after_plan(planner_output, raw_output, identity_ctx, current_user, db)


async def orchestrate_chat_stream(
    message: str,
    source: str,
    conversation_id: str | None,
    current_user,
    db,
    http_client: httpx.AsyncClient,
):
    """SSE-style stream: start → planner_token chunks → final result object."""
    identity_ctx = _build_identity_context(current_user)
    tool_registry = _chat_tool_registry_for_user(current_user)
    yield {"event": "start", "identity": identity_ctx}
    payload = _chat_planner_openai_payload(message, identity_ctx, tool_registry, source, conversation_id)
    buf: list[str] = []
    async for delta in stream_chat_completion_text(http_client, payload):
        buf.append(delta)
        yield {"event": "planner_token", "text": delta}
    content = "".join(buf)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        yield {"event": "error", "detail": "invalid JSON from planner"}
        raise ValueError("invalid JSON from planner") from exc
    planner_output = validate_chat_planner_output(parsed, tool_registry=tool_registry)
    result = _complete_after_plan(planner_output, parsed, identity_ctx, current_user, db)
    yield {"event": "result", **result}
