"""Semantic policy rules beyond JSON schema validation (Epic 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.services.rbac import role_rank

# Max extension of an existing due date (days) by role when updating a task.
DUE_DATE_SLIP_DAYS = {
    "employee": 14,
    "manager": 90,
    "admin": 365,
}


def _parse_due_date(value) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _find_tenant_user(db: Session, tenant: str, assignee: str):
    from app.models import User

    needle = assignee.strip().lower()
    if not needle:
        return None
    rows = db.query(User).filter(User.tenant_id == tenant).all()
    for user in rows:
        if user.email.lower() == needle:
            return user
        if user.slack_user_id and user.slack_user_id.lower() == needle:
            return user
    return None


def _assert_assignee_in_tenant(db: Session, tenant: str, assignee: str) -> None:
    if not assignee.strip():
        raise PermissionError("assignee is required")
    if _find_tenant_user(db, tenant, assignee) is None:
        raise PermissionError("assignee must be a user in your tenant")


def _assert_actor_may_target_assignee(
    db: Session,
    tenant: str,
    actor_role: str,
    assignee: str,
) -> None:
    """Lower-ranked users cannot create/update/delete/assign work for higher-ranked users."""
    if role_rank(actor_role) >= role_rank("admin"):
        return
    target = _find_tenant_user(db, tenant, str(assignee))
    if target is None:
        return
    if role_rank(target.role) > role_rank(actor_role):
        raise PermissionError(
            "cannot modify or assign tasks for users above your role in the organization"
        )


def _assert_actor_may_modify_task(
    db: Session,
    tenant: str,
    actor_role: str,
    user_id: int,
    task_id: int | None,
) -> None:
    from app.models import Task

    if task_id is None:
        return
    task = db.query(Task).filter(Task.id == int(task_id), Task.user_id == user_id).first()
    if task is None or not task.assignee:
        return
    _assert_actor_may_target_assignee(db, tenant, actor_role, task.assignee)


def _assert_due_date_slip(
    db: Session,
    role: str,
    task_id: int,
    new_due_raw,
    user_id: int,
) -> None:
    from app.models import Task

    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if task is None or task.due_date is None:
        return

    new_due = _parse_due_date(new_due_raw)
    current = task.due_date
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if new_due <= current:
        return

    extension_days = (new_due.date() - current.date()).days
    max_slip = DUE_DATE_SLIP_DAYS.get(role, DUE_DATE_SLIP_DAYS["employee"])
    if extension_days > max_slip:
        raise PermissionError(
            f"due date can only be extended by up to {max_slip} days for your role "
            f"(requested extension: {extension_days} days)"
        )


def enforce_policies(
    identity_context: dict,
    tool: str,
    arguments: dict,
    *,
    db: Session | None = None,
):
    role = (identity_context.get("role") or "employee").strip().lower()
    tenant = identity_context.get("tenant")
    user_id = identity_context.get("user_id")
    if not tenant:
        raise PermissionError("tenant context is required")

    assignee = arguments.get("assignee")
    if assignee:
        if role not in {"manager", "admin"}:
            raise PermissionError("only managers/admins can assign tasks")
        if db is not None:
            _assert_assignee_in_tenant(db, tenant, str(assignee))
            _assert_actor_may_target_assignee(db, tenant, role, str(assignee))

    if tool in {"update_task", "delete_task", "assign_task"} and db is not None and user_id is not None:
        task_id = arguments.get("task_id")
        if task_id is not None:
            _assert_actor_may_modify_task(db, tenant, role, int(user_id), int(task_id))

    due_date = arguments.get("due_date")
    if due_date:
        try:
            parsed = _parse_due_date(due_date)
            if parsed < datetime.now(timezone.utc):
                raise PermissionError("due_date cannot be in the past")
        except ValueError as exc:
            raise PermissionError("due_date must be valid ISO datetime") from exc

    if tool in {"update_task", "assign_task"} and due_date and db is not None and user_id is not None:
        task_id = arguments.get("task_id")
        if task_id is not None:
            _assert_due_date_slip(db, role, int(task_id), due_date, int(user_id))

    if tool == "delete_task" and role not in {"manager", "admin"}:
        raise PermissionError("only managers/admins can delete tasks")

    if arguments.get("priority") == "high" and role not in {"manager", "admin"}:
        raise PermissionError("high priority tasks require manager or admin role")

    if tool == "create_task" and db is not None and user_id is not None:
        from app.services.workspace_limits import assert_can_create_task

        assert_can_create_task(db, int(user_id))

    if tool == "admin_tools":
        raise PermissionError("admin_tools is not available in this build")
