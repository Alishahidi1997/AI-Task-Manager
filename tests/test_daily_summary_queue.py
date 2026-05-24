"""Daily summary batch queue (Epic 1.2)."""

from datetime import date
from unittest.mock import patch

from app.auth import hash_password
from app.database import SessionLocal
from app.models import DailySummary, LLMJob, Task, User
from app.queue.config import JOB_DAILY_SUMMARY
from app.services.daily_summary_job import run_daily_summary_for_user
from app.services.llm_queue_enqueue import enqueue_daily_summary_for_user
from app.worker.handlers import process_llm_job_message


def test_run_daily_summary_for_user_persists_summary():
    db = SessionLocal()
    try:
        user = User(email="sum@example.com", password_hash=hash_password("secret123"))
        db.add(user)
        db.commit()
        db.refresh(user)

        task = Task(title="Done item", description="", status="done", user_id=user.id)
        db.add(task)
        db.commit()

        with patch("app.services.daily_summary_job.build_daily_summary", return_value=("Great day", "openai")):
            result = run_daily_summary_for_user(db, user)

        assert result["status"] == "completed"
        assert result["task_count"] == 1
        row = db.query(DailySummary).filter(DailySummary.user_id == user.id).first()
        assert row is not None
        assert row.summary_text == "Great day"
    finally:
        db.close()


@patch("app.services.llm_queue_enqueue.publish_llm_job")
def test_enqueue_daily_summary_uses_batch_queue(mock_publish):
    db = SessionLocal()
    try:
        user = User(email="batch-sum@example.com", password_hash=hash_password("secret123"))
        db.add(user)
        db.commit()
        db.refresh(user)

        job_id = enqueue_daily_summary_for_user(db, user, day=date(2026, 5, 19))
        assert job_id
        mock_publish.assert_called_once()
        _, kwargs = mock_publish.call_args
        assert kwargs["job_type"] == JOB_DAILY_SUMMARY

        row = db.query(LLMJob).filter(LLMJob.job_id == job_id).first()
        assert row.job_type == JOB_DAILY_SUMMARY
        assert row.channel == "batch"

        duplicate = enqueue_daily_summary_for_user(db, user, day=date(2026, 5, 19))
        assert duplicate == job_id
        assert mock_publish.call_count == 1
    finally:
        db.close()


def test_worker_processes_daily_summary_job():
    db = SessionLocal()
    try:
        user = User(email="worker-sum@example.com", password_hash=hash_password("secret123"))
        db.add(user)
        db.commit()
        db.refresh(user)

        task = Task(title="Shipped", description="", status="done", user_id=user.id)
        db.add(task)
        db.commit()

        from app.services.llm_jobs import create_llm_job

        row = create_llm_job(
            db,
            job_type=JOB_DAILY_SUMMARY,
            user_id=user.id,
            tenant_id=f"user-{user.id}",
            request_text="daily summary",
            channel="batch",
            payload={"user_id": user.id},
            idempotency_key="daily-summary:test",
        )
        message = {
            "job_id": row.job_id,
            "job_type": JOB_DAILY_SUMMARY,
            "user_id": user.id,
            "tenant_id": row.tenant_id,
            "request_text": row.request_text,
            "payload": {"user_id": user.id},
        }

        with patch("app.services.daily_summary_job.build_daily_summary", return_value=("Queued summary", "openai")):
            process_llm_job_message(message)

        db.refresh(row)
        assert row.status == "completed"
        summary = db.query(DailySummary).filter(DailySummary.user_id == user.id).first()
        assert summary is not None
        assert summary.summary_text == "Queued summary"
    finally:
        db.close()
