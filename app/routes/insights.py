from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Task, User
from app.services.category_guess import guess_category
from app.services.insights import (
    build_insight_explanation,
    build_priority_suggestions,
    build_productivity_insights,
)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/productivity")
def productivity_insights(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    done = (
        db.query(Task)
        .filter(Task.status == "done", Task.user_id == current_user.id)
        .order_by(Task.id.desc())
        .limit(200)
        .all()
    )
    return build_productivity_insights(done, guess_category)


@router.get("/priority")
def priority_suggestions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pending = (
        db.query(Task)
        .filter(Task.status != "done", Task.user_id == current_user.id)
        .filter(Task.due_date.is_not(None))
        .order_by(Task.due_date.asc())
        .limit(500)
        .all()
    )
    return build_priority_suggestions(pending, guess_category)


@router.get("/explain/{insight_id}")
def explain_insight(
    insight_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    done = (
        db.query(Task)
        .filter(Task.status == "done", Task.user_id == current_user.id)
        .order_by(Task.id.desc())
        .limit(300)
        .all()
    )
    pending = (
        db.query(Task)
        .filter(Task.status != "done", Task.user_id == current_user.id)
        .filter(Task.due_date.is_not(None))
        .order_by(Task.due_date.asc())
        .limit(500)
        .all()
    )
    explanation = build_insight_explanation(insight_id, done, pending, guess_category)
    if explanation is None:
        raise HTTPException(status_code=404, detail=f"unknown insight_id '{insight_id}'")
    return explanation
