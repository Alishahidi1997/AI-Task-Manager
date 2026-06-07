import json
import os
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.llm.openai_client import stream_chat_completion_text
from app.llm.openai_transport import post_chat_completion_async
from app.models import Task
from app.services.category_guess import guess_category
from app.services.entity_resolution import (
    apply_assignee_resolution,
    apply_task_id_from_title,
    try_resolve_followup,
)
from app.services.rbac import allowed_tools_for_role
from app.services.task_workflow import assert_status_transition
from app.services.thread_manager import ThreadManager, api_thread_key
from app.validation.json_validator import PlannerOutput, validate_chat_planner_output
from app.validation.policy_engine import enforce_policies

VALID_STATUS = {"todo", "in_progress", "done"}
VALID_CATEGORY = {"today", "this_week", "routine", "backlog"}
CHAT_TOOL_NAMES = frozenset({"create_task", "update_task", "delete_task", "assign_task"})


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


class AssignTaskArgs(BaseModel):
    task_id: int
    assignee: str = Field(min_length=1, max_length=255)


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
        "assign_task": {
            "required": ["task_id", "assignee"],
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
    if payload.tool_name == "assign_task":
        return AssignTaskArgs(**payload.arguments)
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
    message: str,
    identity_ctx: dict,
    tool_registry: dict,
    source: str,
    conversation_id: str | None,
    thread_context: dict | None = None,
) -> dict:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    now_iso = datetime.now(timezone.utc).isoformat()
    system_text = (
        "You are a strict planner. Output JSON only with keys: "
        "tool_name, arguments, confidence, missing_required, clarification_question. "
        "Pick one tool from registry. Do not hallucinate fields. "
        "When thread_context.last_task_id is set and the user refers to 'that task' or 'it', "
        "use update_task or delete_task with that task_id — do not invent a new task."
    )
    user_text = (
        f"now={now_iso}\nsource={source}\nconversation_id={conversation_id}\n"
        f"identity={json.dumps(identity_ctx)}\n"
        f"thread_context={json.dumps(thread_context or {})}\n"
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
    thread_context: dict | None = None,
):
    payload = _chat_planner_openai_payload(
        message, identity_ctx, tool_registry, source, conversation_id, thread_context
    )
    data = await post_chat_completion_async(client, payload)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or "{}"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON from planner") from exc
    validated = validate_chat_planner_output(parsed, tool_registry=tool_registry)
    return validated, parsed


def _complete_after_plan(
    planner_output: PlannerOutput,
    raw_output: dict,
    identity_ctx: dict,
    current_user,
    db,
    *,
    allow_compact_done_transition: bool = False,
    message: str = "",
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

    if db is not None:
        merged_args = apply_task_id_from_title(
            db,
            current_user.id,
            planner_output.tool_name,
            planner_output.arguments,
            message,
        )
        if merged_args != planner_output.arguments:
            planner_output = planner_output.model_copy(update={"arguments": merged_args})
            raw_output = planner_output.model_dump()

    tenant = identity_ctx.get("tenant")
    if db is not None and tenant:
        merged_args, assignee_clarify = apply_assignee_resolution(
            db, tenant, planner_output.arguments, message
        )
        if assignee_clarify:
            return {
                "status": "clarification_required",
                "question": assignee_clarify,
                "planner_output": planner_output.model_dump(),
                "identity": identity_ctx,
                "raw_planner_output": raw_output,
            }
        if merged_args != planner_output.arguments:
            planner_output = planner_output.model_copy(update={"arguments": merged_args})
            raw_output = planner_output.model_dump()

    try:
        validated_args = _validate_tool_output(planner_output)
    except (ValidationError, ValueError) as exc:
        raise ValueError(f"validation failed: {exc}") from exc
    try:
        enforce_policies(
            _policy_context(identity_ctx),
            planner_output.tool_name,
            planner_output.arguments,
            db=db,
        )
    except PermissionError as exc:
        return {
            "status": "policy_rejected",
            "reason": str(exc),
            "planner_output": planner_output.model_dump(),
            "identity": identity_ctx,
            "raw_planner_output": raw_output,
        }
    result = _execute(
        planner_output.tool_name,
        validated_args,
        current_user,
        db,
        allow_compact_done_transition=allow_compact_done_transition,
    )
    return {
        "status": "executed",
        "result": result,
        "planner_output": planner_output.model_dump(),
        "identity": identity_ctx,
        "raw_planner_output": raw_output,
    }


def _execute(tool_name: str, args, current_user, db, *, allow_compact_done_transition: bool = False):
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
            assignee=args.assignee,
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
        if args.assignee is not None:
            task.assignee = args.assignee
        if args.status is not None:
            target = args.status
            if allow_compact_done_transition and target == "done" and task.status == "todo":
                assert_status_transition(task.status, "in_progress")
                task.status = "in_progress"
            assert_status_transition(task.status, target)
            task.status = target
            if target == "done":
                task.completed_at = datetime.now(timezone.utc)
            elif task.completed_at is not None:
                task.completed_at = None
        db.add(task)
        db.commit()
        db.refresh(task)
        return {"tool_name": tool_name, "task_id": task.id, "status": task.status}

    if tool_name == "assign_task":
        task = db.query(Task).filter(Task.id == args.task_id, Task.user_id == current_user.id).first()
        if not task:
            raise ValueError("task not found")
        task.assignee = args.assignee
        db.add(task)
        db.commit()
        db.refresh(task)
        return {
            "tool_name": tool_name,
            "task_id": task.id,
            "status": task.status,
            "assignee": task.assignee,
        }

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

    thread_row = None
    thread_mgr = None
    if conversation_id:
        thread_mgr = ThreadManager(db, current_user.id)
        thread_row = thread_mgr.load(api_thread_key(current_user.id, conversation_id))
        thread_mgr.add_turn(thread_row, "user", message)

    thread_context = thread_mgr.planner_context(thread_row) if thread_mgr else None
    last_task_id = thread_context.get("last_task_id") if thread_context else None

    followup = try_resolve_followup(message, last_task_id)
    if followup is not None:
        raw_output = followup.model_dump()
        result = _complete_after_plan(
            followup,
            raw_output,
            identity_ctx,
            current_user,
            db,
            allow_compact_done_transition=True,
            message=message,
        )
    else:
        planner_output, raw_output = await _llm_plan_async(
            http_client,
            message,
            identity_ctx,
            tool_registry,
            source,
            conversation_id,
            thread_context,
        )
        result = _complete_after_plan(
            planner_output, raw_output, identity_ctx, current_user, db, message=message
        )

    if thread_mgr and thread_row is not None:
        thread_mgr.record_execution_result(thread_row, result)
        thread_mgr.add_turn(thread_row, "assistant", json.dumps(result, default=str)[:2000])

    return result


def orchestrate_clarify(
    conversation_id: str,
    answer: str,
    current_user,
    db,
):
    """Resume a thread after clarification_required using stored pending_json."""
    thread_mgr = ThreadManager(db, current_user.id)
    thread_row = thread_mgr.load(api_thread_key(current_user.id, conversation_id))
    pending = thread_mgr.get_pending(thread_row)
    if not pending:
        raise ValueError("no pending clarification for this conversation")

    planner_data = dict(pending.get("planner_output") or {})
    tool_name = planner_data.get("tool_name")
    if not tool_name:
        raise ValueError("pending clarification is missing tool_name")

    arguments = dict(planner_data.get("arguments") or {})
    missing = list(planner_data.get("missing_required") or [])
    identity_ctx = _build_identity_context(current_user)
    if missing:
        field = missing.pop(0)
        value = answer.strip()
        if field == "due_date":
            try:
                normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
                arguments[field] = datetime.fromisoformat(normalized)
            except ValueError as exc:
                raise ValueError(f"invalid due_date: {value}") from exc
        else:
            arguments[field] = value
        if field == "assignee":
            merged, clarify = apply_assignee_resolution(
                db, identity_ctx.get("tenant") or f"user-{current_user.id}", arguments, answer
            )
            if clarify:
                raise ValueError(clarify)
            arguments = merged

    planner_output = PlannerOutput(
        tool_name=tool_name,
        arguments=arguments,
        confidence=max(float(planner_data.get("confidence", 0.5)), 0.7),
        missing_required=missing,
        clarification_question=None,
    )
    raw_output = planner_output.model_dump()
    result = _complete_after_plan(planner_output, raw_output, identity_ctx, current_user, db)
    thread_mgr.add_turn(thread_row, "user", f"[clarify] {answer}")
    thread_mgr.record_execution_result(thread_row, result)
    thread_mgr.add_turn(thread_row, "assistant", json.dumps(result, default=str)[:2000])
    return result


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
    thread_row = None
    thread_mgr = None
    if conversation_id:
        thread_mgr = ThreadManager(db, current_user.id)
        thread_row = thread_mgr.load(api_thread_key(current_user.id, conversation_id))
        thread_mgr.add_turn(thread_row, "user", message)
    thread_context = thread_mgr.planner_context(thread_row) if thread_mgr else None

    yield {"event": "start", "identity": identity_ctx}
    followup = try_resolve_followup(message, (thread_context or {}).get("last_task_id"))
    if followup is not None:
        result = _complete_after_plan(
            followup,
            followup.model_dump(),
            identity_ctx,
            current_user,
            db,
            allow_compact_done_transition=True,
        )
        if thread_mgr and thread_row is not None:
            thread_mgr.record_execution_result(thread_row, result)
        yield {"event": "result", **result}
        return

    payload = _chat_planner_openai_payload(
        message, identity_ctx, tool_registry, source, conversation_id, thread_context
    )
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
    if thread_mgr and thread_row is not None:
        thread_mgr.record_execution_result(thread_row, result)
        thread_mgr.add_turn(thread_row, "assistant", json.dumps(result, default=str)[:2000])
    yield {"event": "result", **result}
