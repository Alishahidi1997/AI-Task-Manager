"""Trusted execution for Slack-orchestrated tools (Layer 7). LLM output is never executed raw — only validated/coerced args."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.models import Task, User
from app.services.category_guess import guess_category

VALID_STATUS = {"todo", "in_progress", "done"}
VALID_CATEGORY = {"today", "this_week", "routine", "backlog"}


def _parse_datetime(v) -> datetime:
    if isinstance(v, datetime):
        dt = v
    else:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _coerce_int(v) -> int:
    if isinstance(v, bool):
        raise ValueError("invalid integer")
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    return int(str(v).strip())


class SlackCreateTaskArgs(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    assignee: str = Field(min_length=1, max_length=255)
    due_date: datetime
    priority: str | None = Field(default=None, max_length=32)

    @field_validator("due_date", mode="before")
    @classmethod
    def parse_due(cls, v):
        return _parse_datetime(v)


class SlackUpdateTaskArgs(BaseModel):
    task_id: int
    status: str | None = None
    assignee: str | None = Field(default=None, max_length=255)
    due_date: datetime | None = None
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=8000)

    @field_validator("task_id", mode="before")
    @classmethod
    def coerce_task_id(cls, v):
        return _coerce_int(v)

    @field_validator("due_date", mode="before")
    @classmethod
    def parse_due(cls, v):
        if v is None:
            return None
        return _parse_datetime(v)


class SlackDeleteTaskArgs(BaseModel):
    task_id: int

    @field_validator("task_id", mode="before")
    @classmethod
    def coerce_task_id(cls, v):
        return _coerce_int(v)


class SlackAssignTaskArgs(BaseModel):
    task_id: int
    assignee: str = Field(min_length=1, max_length=255)

    @field_validator("task_id", mode="before")
    @classmethod
    def coerce_task_id(cls, v):
        return _coerce_int(v)


def execute_slack_tool(*, tool: str, arguments: dict, user: User, db: Session) -> dict:
    """Execute one validated tool call for the mapped Slack user. Raises ValueError / PermissionError on failure."""
    if tool == "create_task":
        try:
            args = SlackCreateTaskArgs(**arguments)
        except ValidationError as exc:
            raise ValueError(f"invalid create_task arguments: {exc}") from exc
        if args.due_date < datetime.now(timezone.utc):
            raise PermissionError("due_date cannot be in the past")
        lines = [f"Assignee: {args.assignee}"]
        if args.priority:
            lines.append(f"Priority: {args.priority}")
        description = "\n".join(lines)
        category = guess_category(args.title, description, args.due_date)
        task = Task(
            title=args.title,
            description=description,
            due_date=args.due_date,
            status="todo",
            category=category if category in VALID_CATEGORY else None,
            user_id=user.id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return {"tool_name": tool, "task_id": task.id, "status": task.status}

    if tool == "update_task":
        try:
            args = SlackUpdateTaskArgs(**arguments)
        except ValidationError as exc:
            raise ValueError(f"invalid update_task arguments: {exc}") from exc
        task = db.query(Task).filter(Task.id == args.task_id, Task.user_id == user.id).first()
        if not task:
            raise ValueError("task not found")
        if args.status is not None:
            if args.status not in VALID_STATUS:
                raise ValueError("invalid status")
            task.status = args.status
            if args.status == "done":
                task.completed_at = datetime.now(timezone.utc)
            elif task.completed_at is not None:
                task.completed_at = None
        if args.title is not None:
            task.title = args.title
        if args.description is not None:
            task.description = args.description
        if args.due_date is not None:
            if args.due_date < datetime.now(timezone.utc):
                raise PermissionError("due_date cannot be in the past")
            task.due_date = args.due_date
        if args.assignee is not None:
            base = task.description or ""
            note = f"Assignee: {args.assignee}"
            task.description = f"{base}\n{note}".strip() if base else note
        db.add(task)
        db.commit()
        db.refresh(task)
        return {"tool_name": tool, "task_id": task.id, "status": task.status}

    if tool == "delete_task":
        try:
            args = SlackDeleteTaskArgs(**arguments)
        except ValidationError as exc:
            raise ValueError(f"invalid delete_task arguments: {exc}") from exc
        task = db.query(Task).filter(Task.id == args.task_id, Task.user_id == user.id).first()
        if not task:
            raise ValueError("task not found")
        db.delete(task)
        db.commit()
        return {"tool_name": tool, "task_id": args.task_id, "status": "deleted"}

    if tool == "assign_task":
        try:
            args = SlackAssignTaskArgs(**arguments)
        except ValidationError as exc:
            raise ValueError(f"invalid assign_task arguments: {exc}") from exc
        task = db.query(Task).filter(Task.id == args.task_id, Task.user_id == user.id).first()
        if not task:
            raise ValueError("task not found")
        base = task.description or ""
        note = f"Assignee: {args.assignee}"
        task.description = f"{base}\n{note}".strip() if base else note
        db.add(task)
        db.commit()
        db.refresh(task)
        return {"tool_name": tool, "task_id": task.id, "status": task.status}

    if tool == "admin_tools":
        raise ValueError("admin_tools is not executable in this build")

    raise ValueError(f"unknown tool '{tool}'")
