from unittest.mock import patch

from app.database import SessionLocal
from app.models import LLMJob, User
from app.queue.config import JOB_CHAT_ORCHESTRATION
from app.services.llm_jobs import create_llm_job, get_llm_job, job_to_response
from tests.conftest import auth_headers


def test_create_and_get_llm_job_record():
    db = SessionLocal()
    try:
        user = User(email="llm-row@example.com", password_hash="x", role="employee")
        db.add(user)
        db.commit()
        db.refresh(user)
        row = create_llm_job(
            db,
            job_type=JOB_CHAT_ORCHESTRATION,
            user_id=user.id,
            tenant_id=f"user-{user.id}",
            request_text="hello",
            channel="api",
            payload={"message": "hello", "source": "pytest"},
            idempotency_key="chat:test",
        )
        assert row.job_id
        assert row.status == "pending"
        fetched = get_llm_job(db, row.job_id, user_id=user.id)
        assert fetched is not None
        body = job_to_response(fetched)
        assert body["job_type"] == JOB_CHAT_ORCHESTRATION
        assert body["status"] == "pending"
    finally:
        db.close()


@patch("app.services.llm_queue_enqueue.publish_llm_job")
def test_chat_returns_202_when_queue_enabled(mock_publish, client, monkeypatch):
    monkeypatch.setenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    monkeypatch.setenv("LLM_QUEUE_ENABLED", "true")
    headers = auth_headers(client, "queue-chat@example.com", "secret123")
    response = client.post(
        "/chat",
        headers=headers,
        json={"message": "Create a task due tomorrow", "source": "pytest"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "accepted"
    assert body["job_id"]
    mock_publish.assert_called_once()
    db = SessionLocal()
    try:
        row = db.query(LLMJob).filter(LLMJob.job_id == body["job_id"]).first()
        assert row is not None
        assert row.status == "pending"
    finally:
        db.close()


def test_get_job_endpoint(client):
    headers = auth_headers(client, "job-get@example.com", "secret123")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "job-get@example.com").first()
        row = create_llm_job(
            db,
            job_type=JOB_CHAT_ORCHESTRATION,
            user_id=user.id,
            tenant_id=f"user-{user.id}",
            request_text="poll me",
            channel="api",
            payload={"message": "poll me"},
        )
        job_id = row.job_id
    finally:
        db.close()

    poll = client.get(f"/jobs/{job_id}", headers=headers)
    assert poll.status_code == 200
    assert poll.json()["job_id"] == job_id
    assert poll.json()["status"] == "pending"


def test_worker_processes_chat_orchestration_job():
    """Epic 1.2 acceptance: worker completes a queued chat orchestration job."""
    from datetime import datetime, timedelta, timezone

    from app.auth import hash_password
    from app.services.llm_jobs import create_llm_job
    from app.worker.handlers import process_llm_job_message

    db = SessionLocal()
    try:
        user = User(email="worker-chat@example.com", password_hash=hash_password("secret123"))
        db.add(user)
        db.commit()
        db.refresh(user)

        row = create_llm_job(
            db,
            job_type=JOB_CHAT_ORCHESTRATION,
            user_id=user.id,
            tenant_id=f"user-{user.id}",
            request_text="Create a queued chat task",
            channel="api",
            payload={
                "message": "Create a queued chat task",
                "source": "pytest",
                "conversation_id": None,
            },
            idempotency_key="chat-worker:test",
        )
        message = {
            "job_id": row.job_id,
            "job_type": JOB_CHAT_ORCHESTRATION,
            "user_id": user.id,
            "tenant_id": row.tenant_id,
            "request_text": row.request_text,
            "payload": {
                "message": "Create a queued chat task",
                "source": "pytest",
                "conversation_id": None,
            },
        }

        due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        async def fake_orchestrate(*_args, **_kwargs):
            return {
                "status": "executed",
                "result": {"tool_name": "create_task", "task_id": 99, "status": "todo"},
                "planner_output": {
                    "tool_name": "create_task",
                    "arguments": {"title": "Queued", "due_date": due},
                },
            }

        with patch("app.worker.handlers.orchestrate_chat", side_effect=fake_orchestrate):
            process_llm_job_message(message)

        db.refresh(row)
        assert row.status == "completed"
        assert row.result_json is not None
        assert "executed" in row.result_json
    finally:
        db.close()
