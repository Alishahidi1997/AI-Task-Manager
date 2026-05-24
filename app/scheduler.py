import os
from datetime import date, datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.models import User
from app.queue.config import llm_queue_enabled
from app.services.daily_summary_job import run_daily_summary_for_all_users


def run_daily_summary_job():
    db = SessionLocal()
    try:
        if llm_queue_enabled():
            from app.services.llm_queue_enqueue import enqueue_daily_summaries_for_all_users

            job_ids = enqueue_daily_summaries_for_all_users(db)
            now = datetime.now(timezone.utc).isoformat()
            print(f"[scheduler] {now} enqueued daily_summary jobs={len(job_ids)}")
            return
        run_daily_summary_for_all_users(db)
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
