"""Workspace quotas (Phase 3.7 production hardening)."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.models import Task


def _max_tasks_per_user() -> int:
    return max(0, int(os.getenv("WORKSPACE_MAX_TASKS_PER_USER", "0")))


def _max_open_tasks_per_user() -> int:
    return max(0, int(os.getenv("WORKSPACE_MAX_OPEN_TASKS_PER_USER", "0")))


def assert_can_create_task(db: Session, user_id: int) -> None:
    """Raise PermissionError when per-user workspace task quotas are exceeded."""
    max_total = _max_tasks_per_user()
    if max_total > 0:
        total = db.query(Task).filter(Task.user_id == user_id).count()
        if total >= max_total:
            raise PermissionError(
                f"workspace task limit reached ({max_total} tasks per user)"
            )

    max_open = _max_open_tasks_per_user()
    if max_open > 0:
        open_count = (
            db.query(Task)
            .filter(Task.user_id == user_id, Task.status != "done")
            .count()
        )
        if open_count >= max_open:
            raise PermissionError(
                f"workspace open-task limit reached ({max_open} non-done tasks per user)"
            )
