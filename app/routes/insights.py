from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import NextActionFeedback, Task, User
from app.services.action_outcomes import build_next_action_outcomes_dashboard
from app.services.analytics import detect_kpi_anomalies
from app.services.category_guess import guess_category
from app.services.insights import (
    build_anomalies_explanation,
    build_insight_explanation,
    build_next_actions,
    build_priority_suggestions,
    build_productivity_insights,
)

router = APIRouter(prefix="/insights", tags=["insights"])

VALID_OUTCOMES = {"accepted", "dismissed", "completed"}


class NextActionOutcomeIn(BaseModel):
    feedback_key: str
    outcome: str


class NextActionApplyIn(BaseModel):
    feedback_key: str


def _parse_feedback_key(feedback_key: str) -> tuple[str, int]:
    raw = feedback_key.strip()
    if ":" not in raw:
        raise HTTPException(status_code=400, detail="feedback_key must include action_type:task_id")
    action_type, task_id_text = raw.split(":", 1)
    action_type = action_type.strip()
    if not action_type:
        raise HTTPException(status_code=400, detail="feedback_key missing action_type")
    try:
        task_id = int(task_id_text.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="feedback_key task_id must be an integer") from exc
    return action_type, task_id


def _apply_next_action(action_type: str, task: Task):
    now = datetime.now(timezone.utc)
    if action_type == "reschedule":
        base = task.due_date or now
        task.due_date = base + timedelta(days=2)
    elif action_type == "split_task":
        note = "Split suggestion: break this item into smaller deliverables with concrete subtask owners."
        task.description = f"{(task.description or '').strip()}\n\n{note}".strip()
        if task.status == "todo":
            task.status = "in_progress"
    elif action_type == "escalate_risk":
        if not task.title.startswith("[ESCALATED] "):
            task.title = f"[ESCALATED] {task.title}"
        task.status = "in_progress"
        note = "Risk escalated due to prolonged overdue duration."
        task.description = f"{(task.description or '').strip()}\n\n{note}".strip()
    elif action_type == "contact_owner":
        note = "Action taken: owner contacted to confirm recovery ETA."
        task.description = f"{(task.description or '').strip()}\n\n{note}".strip()
        if task.status == "todo":
            task.status = "in_progress"
    else:
        raise HTTPException(status_code=400, detail=f"unsupported action_type '{action_type}'")


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


@router.get("/anomalies")
def kpi_anomalies(
    days: int = Query(default=30, ge=8, le=120),
    baseline_days: int = Query(default=7, ge=3, le=21),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if baseline_days >= days:
        raise HTTPException(
            status_code=400,
            detail="baseline_days must be smaller than days so each day has a prior window",
        )
    tasks = (
        db.query(Task)
        .filter(Task.user_id == current_user.id)
        .order_by(Task.created_at.asc(), Task.id.asc())
        .limit(3000)
        .all()
    )
    return detect_kpi_anomalies(tasks, window_days=days, baseline_days=baseline_days)


@router.get("/next-actions")
def next_actions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pending = (
        db.query(Task)
        .filter(Task.status != "done", Task.user_id == current_user.id)
        .filter(Task.due_date.is_not(None))
        .order_by(Task.due_date.asc())
        .limit(800)
        .all()
    )
    feedback = (
        db.query(NextActionFeedback)
        .filter(NextActionFeedback.user_id == current_user.id)
        .order_by(NextActionFeedback.id.desc())
        .limit(2000)
        .all()
    )
    return build_next_actions(pending, feedback, guess_category)


@router.post("/next-actions/outcome")
def record_next_action_outcome(
    payload: NextActionOutcomeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    outcome = payload.outcome.strip().lower()
    if outcome not in VALID_OUTCOMES:
        raise HTTPException(
            status_code=400,
            detail="outcome must be one of: accepted, dismissed, completed",
        )
    feedback_key = payload.feedback_key.strip()
    action_type, _ = _parse_feedback_key(feedback_key)

    row = NextActionFeedback(
        user_id=current_user.id,
        feedback_key=feedback_key,
        action_type=action_type,
        outcome=outcome,
    )
    db.add(row)
    db.commit()
    return {"ok": True, "feedback_id": row.id, "feedback_key": feedback_key, "outcome": outcome}


@router.post("/next-actions/apply")
def apply_next_action(
    payload: NextActionApplyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    feedback_key = payload.feedback_key.strip()
    action_type, task_id = _parse_feedback_key(feedback_key)
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status == "done":
        raise HTTPException(status_code=400, detail="cannot apply next action to a done task")

    _apply_next_action(action_type, task)
    db.add(task)
    row = NextActionFeedback(
        user_id=current_user.id,
        feedback_key=feedback_key,
        action_type=action_type,
        outcome="completed",
    )
    db.add(row)
    db.commit()
    db.refresh(task)
    return {
        "ok": True,
        "action_type": action_type,
        "feedback_key": feedback_key,
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "due_date": task.due_date.isoformat() if task.due_date else None,
        },
    }


@router.get("/next-actions/outcomes")
def next_action_outcomes(
    days: int = Query(default=90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate accepted/dismissed/completed feedback used to tune next-action ranking."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(NextActionFeedback)
        .filter(
            NextActionFeedback.user_id == current_user.id,
            NextActionFeedback.created_at >= since,
        )
        .order_by(NextActionFeedback.created_at.desc())
        .limit(5000)
        .all()
    )
    return build_next_action_outcomes_dashboard(rows, window_days=days)


@router.get("/explain/{insight_id}")
def explain_insight(
    insight_id: str,
    days: int = Query(default=30, ge=8, le=120),
    baseline_days: int = Query(default=7, ge=3, le=21),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    key = insight_id.strip().lower()
    if key == "anomalies":
        if baseline_days >= days:
            raise HTTPException(
                status_code=400,
                detail="baseline_days must be smaller than days so each day has a prior window",
            )
        tasks = (
            db.query(Task)
            .filter(Task.user_id == current_user.id)
            .order_by(Task.created_at.asc(), Task.id.asc())
            .limit(3000)
            .all()
        )
        return build_anomalies_explanation(tasks, window_days=days, baseline_days=baseline_days)

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
