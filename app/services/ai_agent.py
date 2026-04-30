import json
import os
from datetime import datetime

import httpx

from app.models import Task
from app.services.category_guess import guess_category

VALID_STATUS = {"todo", "in_progress", "done"}
VALID_CATEGORY = {"today", "this_week", "routine", "backlog"}


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


def _tool_spec():
    return [
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


def _ask_openai_for_tools(query: str, timezone_name: str | None, api_key: str):
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    now = datetime.now().isoformat()
    tz_label = timezone_name or "unknown"
    messages = [
        {
            "role": "system",
            "content": (
                "You are a task operations planner. Decide which tool(s) to call for the user request. "
                "Use tools only for task create/update/delete operations. Keep arguments minimal and valid."
            ),
        },
        {"role": "user", "content": f"Now: {now}\nTimezone: {tz_label}\nRequest: {query}"},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "tools": _tool_spec(),
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
    message = data["choices"][0]["message"]
    return message


def run_agent_command(query: str, current_user, db, timezone_name: str | None = None, dry_run: bool = False):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {
            "ok": False,
            "mode": "no_openai_key",
            "assistant_message": "OPENAI_API_KEY is not set.",
            "actions": [],
        }

    message = _ask_openai_for_tools(query, timezone_name, api_key)
    tool_calls = message.get("tool_calls") or []
    actions = []

    for call in tool_calls:
        fn = call.get("function", {})
        fn_name = fn.get("name")
        raw_args = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            actions.append({"tool": fn_name, "ok": False, "detail": "invalid JSON arguments"})
            continue

        if fn_name == "create_task":
            title = str(args.get("title") or "").strip()[:255]
            if not title:
                actions.append({"tool": fn_name, "ok": False, "detail": "title is required"})
                continue
            description = args.get("description")
            if description is not None:
                description = str(description)[:8000]
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

    return {
        "ok": True,
        "mode": "openai_tools",
        "assistant_message": message.get("content") or "",
        "actions": actions,
        "tool_calls_count": len(tool_calls),
        "dry_run": dry_run,
    }
