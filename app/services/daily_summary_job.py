"""Daily summary execution for scheduler and batch queue worker."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import DailySummary, Task, User
from app.services.ai_summary import build_daily_summary


def run_daily_summary_for_user(db: Session, user: User) -> dict:
    """Build and persist one user's daily summary. Returns result metadata."""
    done_tasks = (
        db.query(Task)
        .filter(Task.status == "done", Task.user_id == user.id)
        .order_by(Task.id.desc())
        .limit(50)
        .all()
    )
    try:
        text, mode = build_daily_summary(done_tasks)
        row = DailySummary(
            summary_text=text,
            mode=mode,
            task_count=len(done_tasks),
            is_error=0,
            user_id=user.id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "status": "completed",
            "user_id": user.id,
            "summary_id": row.id,
            "mode": mode,
            "task_count": len(done_tasks),
        }
    except Exception as exc:
        db.rollback()
        row = DailySummary(
            summary_text="ERROR: " + str(exc),
            mode="openai",
            task_count=0,
            is_error=1,
            user_id=user.id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "status": "failed",
            "user_id": user.id,
            "summary_id": row.id,
            "error": str(exc),
        }


def run_daily_summary_for_all_users(db: Session) -> list[dict]:
    results: list[dict] = []
    users = db.query(User).order_by(User.id.asc()).all()
    for user in users:
        result = run_daily_summary_for_user(db, user)
        results.append(result)
        now = datetime.now(timezone.utc).isoformat()
        print(f"[scheduler] {now} user={user.id} status={result.get('status')}")
    return results
