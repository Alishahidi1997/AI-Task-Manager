from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Task, User, utcnow
from app.schemas import Status, TaskCreate, TaskOut, TaskUpdate
from app.services.category_guess import guess_category
from app.services.task_workflow import assert_status_transition
from app.services.workspace_limits import assert_can_create_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _check_status_transition(current_status: str, next_status: str):
    try:
        assert_status_transition(current_status, next_status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        assert_can_create_task(db, current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    cat = payload.category
    if cat is None:
        cat = guess_category(payload.title, payload.description or "", payload.due_date)

    done_at = None
    if payload.status == "done":
        done_at = utcnow()

    task = Task(
        title=payload.title,
        description=payload.description,
        status=payload.status,
        due_date=payload.due_date,
        category=cat,
        completed_at=done_at,
        assignee=payload.assignee,
        user_id=current_user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("", response_model=list[TaskOut])
def list_tasks(
    
    status_filter: Status | None = Query(default=None, alias="status"),
    due_before: datetime | None = Query(default=None),
    
    due_after: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Task).filter(Task.user_id == current_user.id)
    if status_filter is not None:
        q = q.filter(Task.status == status_filter)
    if due_before is not None:
        q = q.filter(Task.due_date.is_not(None))
        q = q.filter(Task.due_date <= due_before)

    if due_after is not None:
        q = q.filter(Task.due_date.is_not(None))
        q = q.filter(Task.due_date >= due_after)

    return q.order_by(Task.id.desc()).all()


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    old_status = task.status
    updates = payload.model_dump(exclude_unset=True)
    next_status = updates.get("status")
    if next_status is not None:
        _check_status_transition(old_status, next_status)

    for key, value in updates.items():
        setattr(task, key, value)

    if (
        ("title" in updates or "description" in updates or "due_date" in updates)
        and "category" not in updates
    ):
        task.category = guess_category(task.title, task.description or "", task.due_date)

    new_status = task.status
    if new_status == "done" and old_status != "done":
        task.completed_at = utcnow()
    elif old_status == "done" and new_status != "done":
        task.completed_at = None

    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    db.delete(task)
    db.commit()
    return None
