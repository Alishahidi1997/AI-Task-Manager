import os
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal
from app.models import DailySummary, Task, User
from app.services.ai_summary import build_daily_summary


def run_daily_summary_job():
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.id.asc()).all()
        for user in users:
            try:
                done_tasks = (
                    db.query(Task)
                    .filter(Task.status == "done", Task.user_id == user.id)
                    .order_by(Task.id.desc())
                    .limit(50)
                    .all()
                )
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

                now = datetime.now(timezone.utc).isoformat()
                print(
                    f"[scheduler] {now} user={user.id} mode={mode} tasks={len(done_tasks)}"
                )
            except Exception as e:
                db.rollback()
                row = DailySummary(
                    summary_text="ERROR: " + str(e),
                    mode="openai",
                    task_count=0,
                    is_error=1,
                    user_id=user.id,
                )
                db.add(row)
                db.commit()
                print(f"[scheduler] daily summary failed for user={user.id}: {e}")
    except Exception as e:
        db.rollback()
        print(f"[scheduler] daily summary failed: {e}")
    finally:
        db.close()


def _minutes_from_env():
    raw = os.getenv("SUMMARY_EVERY_MINUTES", "").strip()
    if not raw:
        return None
    try:
        n = int(raw)
        if n > 0:
            return n
    except ValueError:
        pass
    
    return None


def start_scheduler():
    scheduler = BackgroundScheduler()
    every_minutes = _minutes_from_env()
    if every_minutes is not None:
        scheduler.add_job(
            run_daily_summary_job,
            "interval",
            minutes=every_minutes,
            id="daily-summary",
            replace_existing=True,
        )
    else:
        
        scheduler.add_job(
            run_daily_summary_job,
            "cron",
            hour=0,
            minute=0,
            id="daily-summary",
            replace_existing=True,
        )

    scheduler.start()
    return scheduler
