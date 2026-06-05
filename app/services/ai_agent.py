import json
import os
import re
from datetime import datetime

import httpx

from app.models import Task
from app.services.category_guess import guess_category
from app.services.entity_resolution import resolve_task_id_for_agent_query
from app.services.rbac import allowed_tools_for_role
from app.validation.policy_engine import enforce_policies

VALID_STATUS = {"todo", "in_progress", "done"}
VALID_CATEGORY = {"today", "this_week", "routine", "backlog"}
_DELETE_WORDS = re.compile(r"\b(delete|remove|drop)\b", re.IGNORECASE)
_UPDATE_WORDS = re.compile(r"\b(update|mark|complete|finish|set\s+status)\b", re.IGNORECASE)
_CREATE_WORDS = re.compile(r"\b(create|add|new\s+task)\b", re.IGNORECASE)


def detect_agent_intent(query: str) -> str:
    """Primary operation implied by the user request (used to keep one tool per command)."""
    low = query.lower()
    delete_hit = bool(_DELETE_WORDS.search(low))
    create_hit = bool(_CREATE_WORDS.search(low))
    update_hit = bool(_UPDATE_WORDS.search(low))
    if delete_hit and not create_hit:
        return "delete"
    if create_hit and not delete_hit:
        return "create"
    if update_hit and not create_hit:
        return "update"
    if delete_hit:
        return "delete"
    if update_hit:
        return "update"
    if create_hit:
        return "create"
    return "unknown"


def _tool_name_from_call(call: dict) -> str | None:
    return (call.get("function") or {}).get("name")


def filter_tool_calls_for_intent(tool_calls: list[dict], intent: str) -> list[dict]:
    """Keep only the single most relevant tool call for the detected intent."""
    if not tool_calls:
        return []
    if intent == "delete":
        matched = [c for c in tool_calls if _tool_name_from_call(c) == "delete_task"]
        return matched[:1]
    if intent == "create":
        matched = [c for c in tool_calls if _tool_name_from_call(c) == "create_task"]
        return matched[:1]
    if intent == "update":
        matched = [c for c in tool_calls if _tool_name_from_call(c) == "update_task"]
        return matched[:1]
    return tool_calls[:1]


def _identity_context(current_user) -> dict:
    return {
        "user_id": current_user.id,
        "role": current_user.role,
        "tenant": current_user.tenant_id,
    }


def _parse_iso_datetime(value: str | None):
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _allowed_transition(current_status: str, next_status: str):
    allowed = {
        "todo": {"todo", "in_progress"},
        "in_progress": {"in_progress", "done", "todo"},
        "done": {"done", "in_progress"},
    }
    return next_status in allowed.get(current_status, set())


def _tool_spec_for_role(role: str):
    allowed = set(allowed_tools_for_role(role))
    tools = [
        {
            "type": "function",
            "function": {
                "name": "create_task",
                "description": "Create a new task for the authenticated user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": ["string", "null"]},
                        "due_date": {"type": ["string", "null"]},
                        "category": {
                            "type": "string",
                            "enum": ["today", "this_week", "routine", "backlog"],
                        },
                    },
                    "required": ["title"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_task",
                "description": "Update a task that belongs to the authenticated user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"},
                        "title": {"type": ["string", "null"]},
                        "description": {"type": ["string", "null"]},
                        "status": {"type": "string", "enum": ["todo", "in_progress", "done"]},
                        "due_date": {"type": ["string", "null"]},
                        "category": {
                            "type": "string",
                            "enum": ["today", "this_week", "routine", "backlog"],
                        },
                    },
                    "required": ["task_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_task",
                "description": "Delete a task that belongs to the authenticated user.",
                "parameters": {
                    "type": "object",
                    "properties": {"task_id": {"type": "integer"}},
                    "required": ["task_id"],
                },
            },
        },
    ]
    return [tool for tool in tools if tool["function"]["name"] in allowed]


def _format_tasks_for_prompt(db, user_id: int) -> str:
    rows = (
        db.query(Task)
        .filter(Task.user_id == user_id)
        .order_by(Task.id.desc())
        .limit(30)
        .all()
    )
    if not rows:
        return "(no tasks)"
    lines = []
    for task in rows:
        due = task.due_date.isoformat() if task.due_date else "none"
        lines.append(
            f"- id={task.id} title={task.title!r} status={task.status} "
            f"assignee={task.assignee or 'none'} due={due} category={task.category or 'none'}"
        )
    return "\n".join(lines)


def _ask_openai_for_tools(
    query: str,
    timezone_name: str | None,
    api_key: str,
    *,
    role: str,
    task_catalog: str,
    intent: str,
):
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    now = datetime.now().isoformat()
    tz_label = timezone_name or "unknown"
    intent_rule = (
        "The user wants to DELETE a task. Call delete_task only. "
        "Pick task_id from the task catalog. Never call create_task."
        if intent == "delete"
        else "The user wants to CREATE a task. Call create_task only."
        if intent == "create"
        else "The user wants to UPDATE a task. Call update_task only. "
        "Pick task_id from the task catalog."
        if intent == "update"
        else "Call exactly one tool that best matches the request."
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a task operations planner. Choose exactly ONE tool call per request. "
                "Use task_id values from the user's task catalog when deleting or updating. "
                "Do not invent tasks from pasted descriptions; pasted blocks describe an existing task. "
                f"{intent_rule}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Now: {now}\nTimezone: {tz_label}\n"
                f"User role: {role}\n"
                f"Task catalog:\n{task_catalog}\n\n"
                f"Request: {query}"
            ),
        },
    ]
    tools = _tool_spec_for_role(role)
    if not tools:
        return {"tool_calls": [], "content": "No tools allowed for this role."}

    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.1,
        "max_tokens": 300,
    }
    with httpx.Client(timeout=45.0) as client:
        response = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    return data["choices"][0]["message"]


def run_agent_command(query: str, current_user, db, timezone_name: str | None = None, dry_run: bool = False):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {
            "ok": False,
            "mode": "no_openai_key",
            "assistant_message": "OPENAI_API_KEY is not set.",
            "actions": [],
        }

    intent = detect_agent_intent(query)
    identity = _identity_context(current_user)
    task_catalog = _format_tasks_for_prompt(db, current_user.id)

    message = _ask_openai_for_tools(
        query,
        timezone_name,
        api_key,
        role=current_user.role,
        task_catalog=task_catalog,
        intent=intent,
    )
    tool_calls = filter_tool_calls_for_intent(message.get("tool_calls") or [], intent)
    actions = []

    if intent == "delete" and not tool_calls:
        return {
            "ok": False,
            "mode": "openai_tools",
            "assistant_message": "Delete request could not be mapped to a task. Check task_id or title in your catalog.",
            "actions": [{"tool": "delete_task", "ok": False, "detail": "no delete tool call returned"}],
            "tool_calls_count": 0,
            "dry_run": dry_run,
            "intent": intent,
        }

    for call in tool_calls:
        fn = call.get("function", {})
        fn_name = fn.get("name")
        raw_args = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            actions.append({"tool": fn_name, "ok": False, "detail": "invalid JSON arguments"})
            continue

        if fn_name not in allowed_tools_for_role(current_user.role):
            actions.append({"tool": fn_name, "ok": False, "detail": "tool not allowed for your role"})
            continue

        if fn_name in {"update_task", "delete_task"}:
            resolved_id = resolve_task_id_for_agent_query(db, current_user.id, query, args)
            if resolved_id is not None:
                args["task_id"] = resolved_id
            elif args.get("task_id") is None:
                detail = "task not found; could not resolve from request"
                actions.append({"tool": fn_name, "ok": False, "detail": detail})
                continue

        try:
            enforce_policies(identity, fn_name, args, db=db)
        except PermissionError as exc:
            actions.append({"tool": fn_name, "ok": False, "detail": str(exc)})
            continue

        if fn_name == "create_task":
            title = str(args.get("title") or "").strip()[:255]
            if not title:
                actions.append({"tool": fn_name, "ok": False, "detail": "title is required"})
                continue
            description = args.get("description")
            if description is not None:
                description = str(description)[:8000]
            assignee_raw = args.get("assignee")
            assignee = str(assignee_raw).strip()[:255] if assignee_raw else None
            due_date = _parse_iso_datetime(args.get("due_date"))
            category = args.get("category")
            if category not in VALID_CATEGORY:
                category = guess_category(title, description or "", due_date)
            if dry_run:
                actions.append(
                    {
                        "tool": fn_name,
                        "ok": True,
                        "dry_run": True,
                        "task_preview": {
                            "title": title,
                            "description": description,
                            "due_date": due_date.isoformat() if due_date else None,
                            "category": category,
                        },
                    }
                )
                continue

            task = Task(
                title=title,
                description=description,
                due_date=due_date,
                category=category,
                status="todo",
                assignee=assignee,
                user_id=current_user.id,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            actions.append({"tool": fn_name, "ok": True, "task_id": task.id})
            continue

        if fn_name == "update_task":
            task_id = args.get("task_id")
            if not isinstance(task_id, int):
                actions.append({"tool": fn_name, "ok": False, "detail": "task_id must be an integer"})
                continue
            task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
            if not task:
                actions.append({"tool": fn_name, "ok": False, "detail": "task not found or not owned"})
                continue
            next_status = args.get("status")
            if next_status is not None:
                if next_status not in VALID_STATUS:
                    actions.append({"tool": fn_name, "ok": False, "detail": "invalid status"})
                    continue
                if not _allowed_transition(task.status, next_status):
                    actions.append({"tool": fn_name, "ok": False, "detail": "invalid status transition"})
                    continue

            next_title = args.get("title")
            next_description = args.get("description")
            next_due_date = _parse_iso_datetime(args.get("due_date"))
            next_category = args.get("category")
            if next_category is not None and next_category not in VALID_CATEGORY:
                next_category = None

            if dry_run:
                actions.append({"tool": fn_name, "ok": True, "dry_run": True, "task_id": task_id})
                continue

            if next_title is not None:
                task.title = str(next_title).strip()[:255]
            if next_description is not None:
                task.description = str(next_description)[:8000] if next_description else None
            if "due_date" in args:
                task.due_date = next_due_date
            if next_status is not None:
                task.status = next_status
            if next_category is not None:
                task.category = next_category
            elif any(k in args for k in ("title", "description", "due_date")):
                task.category = guess_category(task.title, task.description or "", task.due_date)

            db.add(task)
            db.commit()
            db.refresh(task)
            actions.append({"tool": fn_name, "ok": True, "task_id": task.id})
            continue

        if fn_name == "delete_task":
            task_id = args.get("task_id")
            if not isinstance(task_id, int):
                actions.append({"tool": fn_name, "ok": False, "detail": "task_id must be an integer"})
                continue
            task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
            if not task:
                actions.append({"tool": fn_name, "ok": False, "detail": "task not found or not owned"})
                continue
            if dry_run:
                actions.append({"tool": fn_name, "ok": True, "dry_run": True, "task_id": task_id})
                continue
            db.delete(task)
            db.commit()
            actions.append({"tool": fn_name, "ok": True, "task_id": task_id})
            continue

        actions.append({"tool": fn_name or "unknown", "ok": False, "detail": "unsupported tool"})

    ok = bool(actions) and all(action.get("ok") for action in actions)
    return {
        "ok": ok,
        "mode": "openai_tools",
        "assistant_message": message.get("content") or "",
        "actions": actions,
        "tool_calls_count": len(tool_calls),
        "dry_run": dry_run,
        "intent": intent,
    }
