import json
import os
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.models import Task
from app.services.category_guess import guess_category

VALID_STATUS = {"todo", "in_progress", "done"}
VALID_CATEGORY = {"today", "this_week", "routine", "backlog"}


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
    role = "manager" if str(user.email).startswith("demo@") else "member"
    permissions = {"task:create", "task:update", "task:delete"}
    if role == "manager":
        permissions.add("task:assign")
        permissions.add("task:high_priority")
    return {
        "user_id": str(user.id),
        "tenant_id": f"user-{user.id}",
        "role": role,
        "permissions": sorted(list(permissions)),
    }


def _authorize(identity_ctx: dict, tool_name: str, args):
    perms = set(identity_ctx["permissions"])
    if tool_name == "create_task" and "task:create" not in perms:
        raise PermissionError("missing permission task:create")
    if tool_name == "update_task" and "task:update" not in perms:
        raise PermissionError("missing permission task:update")
    if tool_name == "delete_task" and "task:delete" not in perms:
        raise PermissionError("missing permission task:delete")

    assignee = getattr(args, "assignee", None)
    if assignee and "task:assign" not in perms:
        raise PermissionError("assigning tasks requires manager role")
    if getattr(args, "priority", None) == "high" and "task:high_priority" not in perms:
        raise PermissionError("high priority tasks require manager role")
    due_date = getattr(args, "due_date", None)
    if due_date is not None and due_date < datetime.now(timezone.utc):
        raise PermissionError("due_date cannot be in the past")


def _llm_plan(message: str, identity_ctx: dict, source: str, conversation_id: str | None):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    registry = _tool_registry()
    now_iso = datetime.now(timezone.utc).isoformat()
    system_text = (
        "You are a strict planner. Output JSON only with keys: "
        "tool_name, arguments, confidence, missing_required, clarification_question. "
        "Pick one tool from registry. Do not hallucinate fields."
    )
    user_text = (
        f"now={now_iso}\nsource={source}\nconversation_id={conversation_id}\n"
        f"identity={json.dumps(identity_ctx)}\n"
        f"tool_registry={json.dumps(registry)}\n"
        f"request={message}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.1,
        "max_tokens": 350,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=45.0) as client:
        resp = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or "{}"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON from planner") from exc
    return PlannerOutput(**parsed), parsed


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
            task.status = args.status
            if args.status == "done":
                task.completed_at = datetime.now(timezone.utc)
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


def orchestrate_chat(message: str, source: str, conversation_id: str | None, current_user, db):
    identity_ctx = _build_identity_context(current_user)
    planner_output, raw_output = _llm_plan(message, identity_ctx, source, conversation_id)
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
    _authorize(identity_ctx, planner_output.tool_name, validated_args)
    result = _execute(planner_output.tool_name, validated_args, current_user, db)
    return {
        "status": "executed",
        "result": result,
        "planner_output": planner_output.model_dump(),
        "identity": identity_ctx,
        "raw_planner_output": raw_output,
    }
