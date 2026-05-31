"""Resolve follow-up references using session focus (last_task_id) before LLM planning."""

from __future__ import annotations

import re

_FOLLOWUP_PHRASES = (
    "that task",
    "that one",
    "this task",
    "the task",
    "mark it",
    "mark that",
    "complete it",
    "complete that",
    "finish it",
    "finish that",
    "delete it",
    "delete that",
    "remove it",
    "remove that",
)

_DONE_WORDS = ("done", "complete", "finish", "close")
_PROGRESS_WORDS = ("in progress", "start", "started", "working on")
_DELETE_WORDS = ("delete", "remove", "drop")


def message_references_session_task(message: str) -> bool:
    low = message.lower()
    return any(phrase in low for phrase in _FOLLOWUP_PHRASES)


def try_resolve_followup(message: str, last_task_id: int | None):
    """
    Deterministic follow-up when the user refers to the thread's last task.
    Returns a PlannerOutput ready for validation/execution, or None to use the LLM.
    """
    from app.validation.json_validator import PlannerOutput

    if last_task_id is None or not message_references_session_task(message):
        return None

    low = message.lower()
    if any(word in low for word in _DELETE_WORDS):
        return PlannerOutput(
            tool_name="delete_task",
            arguments={"task_id": last_task_id},
            confidence=0.9,
            missing_required=[],
            clarification_question=None,
        )
    if any(word in low for word in _DONE_WORDS):
        return PlannerOutput(
            tool_name="update_task",
            arguments={"task_id": last_task_id, "status": "done"},
            confidence=0.9,
            missing_required=[],
            clarification_question=None,
        )
    if any(word in low for word in _PROGRESS_WORDS):
        return PlannerOutput(
            tool_name="update_task",
            arguments={"task_id": last_task_id, "status": "in_progress"},
            confidence=0.88,
            missing_required=[],
            clarification_question=None,
        )
    return PlannerOutput(
        tool_name="update_task",
        arguments={"task_id": last_task_id},
        confidence=0.75,
        missing_required=[],
        clarification_question=None,
    )


def try_resolve_slack_followup(message: str, last_task_id: int | None) -> dict | None:
    """Planner JSON for Slack deterministic thread follow-ups (canonical ``tool_name``)."""
    chat_plan = try_resolve_followup(message, last_task_id)
    if chat_plan is None:
        return None
    return chat_plan.model_dump()


def apply_task_id_from_title(
    db,
    user_id: int,
    tool_name: str,
    arguments: dict,
    message: str,
) -> dict:
    """Fill task_id on update/delete when the user names a task title in the message."""
    if tool_name not in {"update_task", "delete_task", "assign_task"}:
        return arguments
    if arguments.get("task_id") is not None:
        return arguments
    low = message.lower()
    for prefix in ("task called ", "task titled ", "task "):
        if prefix in low:
            fragment = message[low.index(prefix) + len(prefix) :].strip().strip('"').strip("'")
            for stop in (" to done", " as done", " done", ".", ","):
                stop_low = stop.strip()
                if stop_low and stop_low in fragment.lower():
                    fragment = fragment[: fragment.lower().index(stop_low)].strip()
            fragment = fragment.split(".")[0].split(",")[0].strip()
            task_id = resolve_task_id_from_title(db, user_id, fragment)
            if task_id is not None:
                merged = dict(arguments)
                merged["task_id"] = task_id
                return merged
    return arguments


def resolve_task_id_from_title(db, user_id: int, title_fragment: str) -> int | None:
    """Lightweight title search for entity resolution (tenant-scoped by user_id)."""
    from app.models import Task

    fragment = title_fragment.strip()
    if len(fragment) < 3:
        return None
    row = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.title.ilike(f"%{fragment}%"))
        .order_by(Task.id.desc())
        .first()
    )
    return row.id if row else None


def _looks_like_email(value: str) -> bool:
    return "@" in value.strip()


def _email_local(email: str) -> str:
    return email.split("@", 1)[0].lower()


def extract_assignee_from_message(message: str) -> str | None:
    """Pull assignee hint from natural language when the planner omitted it."""
    patterns = (
        r"\bassign(?:ed)?\s+to\s+([^\n,.;]+)",
        r"\bassignee\s+([^\n,.;]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            hint = match.group(1).strip().strip('"').strip("'")
            if hint:
                return hint
    return None


def find_assignee_candidates(db, tenant_id: str, hint: str):
    """Match assignee hints against tenant users by email local-part or slack id."""
    from app.models import User

    needle = hint.strip().lower()
    if not needle:
        return []

    rows = db.query(User).filter(User.tenant_id == tenant_id).all()
    if _looks_like_email(needle):
        return [user for user in rows if user.email.lower() == needle]

    exact: list = []
    prefix: list = []
    for user in rows:
        if user.slack_user_id and user.slack_user_id.lower() == needle:
            exact.append(user)
            continue
        local = _email_local(user.email)
        if local == needle:
            exact.append(user)
        elif local.startswith(needle):
            prefix.append(user)

    if exact:
        return list({user.id: user for user in exact}.values())
    return list({user.id: user for user in prefix}.values())


def apply_assignee_resolution(
    db,
    tenant_id: str,
    arguments: dict,
    message: str,
) -> tuple[dict, str | None]:
    """
    Resolve assignee name fragments to tenant user emails before policy/execute.
    Returns updated arguments and an optional clarification question when ambiguous.
    """
    merged = dict(arguments)
    hint = merged.get("assignee")
    if not hint:
        hint = extract_assignee_from_message(message)
        if hint:
            merged["assignee"] = hint

    assignee = merged.get("assignee")
    if not assignee:
        return merged, None

    assignee_str = str(assignee).strip()
    if _looks_like_email(assignee_str):
        from app.models import User

        row = (
            db.query(User)
            .filter(User.tenant_id == tenant_id, User.email.ilike(assignee_str))
            .first()
        )
        if row is not None:
            merged["assignee"] = row.email
        return merged, None

    candidates = find_assignee_candidates(db, tenant_id, assignee_str)
    if len(candidates) == 1:
        merged["assignee"] = candidates[0].email
        return merged, None
    if len(candidates) > 1:
        options = ", ".join(sorted(user.email for user in candidates))
        return merged, f"Which assignee did you mean? Options: {options}"
    return merged, f"I couldn't find a user matching '{assignee_str}' in your workspace."
