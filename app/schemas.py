# pydantic shapes for request/response bodies (validation lives here)
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# matches what we store in sqlite
Status = Literal["todo", "in_progress", "done"]
# daily planning style, not tech stack
Category = Literal["today", "this_week", "routine", "backlog"]


class TaskCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    status: Status = "todo"
    due_date: datetime | None = None
    category: Category | None = None
    assignee: str | None = Field(default=None, max_length=255)


class TaskUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    status: Status | None = None
    due_date: datetime | None = None
    category: Category | None = None
    assignee: str | None = Field(default=None, max_length=255)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: str
    created_at: datetime
    due_date: datetime | None
    category: str | None
    completed_at: datetime | None
    assignee: str | None = None
