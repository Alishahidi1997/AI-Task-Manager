"""Queued /ai/* routes on the batch LLM queue (Epic 1.2 optional)."""

from unittest.mock import patch

from app.database import SessionLocal
from app.models import LLMJob, User
from app.queue.config import JOB_AI_PARSE, JOB_AI_PLAN, is_batch_job
from app.services.llm_jobs import create_llm_job
from app.worker.handlers import process_llm_job_message
from tests.conftest import auth_headers


def test_batch_job_types_include_ai_routes():
    assert is_batch_job(JOB_AI_PARSE)
    assert is_batch_job(JOB_AI_PLAN)


@patch("app.services.llm_queue_enqueue.publish_llm_job")
def test_parse_task_returns_202_when_queue_enabled(mock_publish, client, monkeypatch):
    monkeypatch.setenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    monkeypatch.setenv("LLM_QUEUE_ENABLED", "true")
    headers = auth_headers(client, "ai-parse-queue@example.com", "secret123")
    response = client.post(
        "/ai/parse-task",
        headers=headers,
        json={"text": "Review budget deck tomorrow at 3pm"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "accepted"
    assert body["job_id"]
    mock_publish.assert_called_once()
    _, kwargs = mock_publish.call_args
    assert kwargs["job_type"] == JOB_AI_PARSE

    db = SessionLocal()
    try:
        row = db.query(LLMJob).filter(LLMJob.job_id == body["job_id"]).first()
        assert row is not None
        assert row.job_type == JOB_AI_PARSE
        assert row.channel == "api"
    finally:
        db.close()


def test_worker_processes_ai_parse_job():
    db = SessionLocal()
    try:
        user = User(email="ai-worker@example.com", password_hash="x", role="employee")
        db.add(user)
        db.commit()
        db.refresh(user)

        row = create_llm_job(
            db,
            job_type=JOB_AI_PARSE,
            user_id=user.id,
            tenant_id=f"user-{user.id}",
            request_text="Ship docs tomorrow",
            channel="api",
            payload={"text": "Ship docs tomorrow", "timezone": "UTC"},
            idempotency_key="ai:parse:test",
        )
        message = {
            "job_id": row.job_id,
            "job_type": JOB_AI_PARSE,
            "user_id": user.id,
            "tenant_id": row.tenant_id,
            "request_text": row.request_text,
            "payload": {"text": "Ship docs tomorrow", "timezone": "UTC"},
        }

        with patch(
            "app.worker.handlers.parse_task_text",
            return_value={"title": "Ship docs", "due_date": None, "mode": "fallback"},
        ):
            process_llm_job_message(message)

        db.refresh(row)
        assert row.status == "completed"
        import json

        result = json.loads(row.result_json)
        assert result["title"] == "Ship docs"
    finally:
        db.close()
