"""Resolve follow-up references using session focus (last_task_id) before LLM planning."""

from __future__ import annotations

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
    from app.services.chat_orchestrator import PlannerOutput

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
