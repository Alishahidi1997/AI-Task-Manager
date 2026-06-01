"""RabbitMQ broker integration (Epic 1.2). Skipped unless RABBITMQ_URL is set."""

from __future__ import annotations

import json
import os
import time
from unittest.mock import patch

import pika
import pytest

from app.auth import hash_password
from app.database import SessionLocal
from app.models import LLMJob, User
from app.queue.config import JOB_CHAT_ORCHESTRATION, QUEUE_ORCHESTRATION, rabbitmq_url
from app.queue.publisher import _ensure_topology, publish_llm_job
from app.services.llm_jobs import build_queue_message, create_llm_job
from app.worker.handlers import process_llm_job_message

pytestmark = pytest.mark.skipif(
    not os.getenv("RABBITMQ_URL", "").strip(),
    reason="set RABBITMQ_URL to run RabbitMQ integration tests",
)


def _blocking_connection(url: str, *, attempts: int = 12, delay_sec: float = 1.0) -> pika.BlockingConnection:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return pika.BlockingConnection(pika.URLParameters(url))
        except Exception as exc:  # noqa: BLE001 — broker may be starting
            last_error = exc
            time.sleep(delay_sec)
    raise RuntimeError(f"could not connect to RabbitMQ at {url}") from last_error


def test_broker_delivers_chat_job_to_worker_handler(monkeypatch):
    """Publish to llm.orchestration.high and process one message end-to-end."""
    broker_url = os.environ["RABBITMQ_URL"].strip()
    monkeypatch.setenv("RABBITMQ_URL", broker_url)

    db = SessionLocal()
    try:
        user = User(email="rmq-int@example.com", password_hash=hash_password("secret123"))
        db.add(user)
        db.commit()
        db.refresh(user)

        row = create_llm_job(
            db,
            job_type=JOB_CHAT_ORCHESTRATION,
            user_id=user.id,
            tenant_id=f"user-{user.id}",
            request_text="broker roundtrip",
            channel="api",
            payload={"message": "broker roundtrip", "source": "pytest"},
            idempotency_key="rmq:roundtrip",
        )
        body = build_queue_message(row)
        job_id = row.job_id
    finally:
        db.close()

    connection = _blocking_connection(rabbitmq_url())
    try:
        channel = connection.channel()
        _ensure_topology(channel)
        channel.queue_purge(QUEUE_ORCHESTRATION)
        publish_llm_job(body, job_type=JOB_CHAT_ORCHESTRATION)
        method, _props, raw = channel.basic_get(QUEUE_ORCHESTRATION, auto_ack=True)
        assert method is not None, "expected one message on orchestration queue"
        message = json.loads(raw.decode("utf-8"))
        assert message["job_id"] == job_id
    finally:
        connection.close()

    async def fake_orchestrate(*_args, **_kwargs):
        return {
            "status": "executed",
            "result": {"tool_name": "create_task", "task_id": 1, "status": "todo"},
            "planner_output": {"tool_name": "create_task", "arguments": {}},
        }

    with patch("app.worker.handlers.orchestrate_chat", side_effect=fake_orchestrate):
        process_llm_job_message(message)

    db = SessionLocal()
    try:
        updated = db.query(LLMJob).filter(LLMJob.job_id == job_id).first()
        assert updated is not None
        assert updated.status == "completed"
    finally:
        db.close()
