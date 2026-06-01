import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.auth import hash_password
from app.database import SessionLocal
from app.models import AuditLog, SlackOrchestrationTrace, User
from app.services.slack_idempotency import claim_slack_event, slack_event_id_from_payload
from app.validation.json_validator import PlannerOutput


def _seed_slack_user(client, slack_user_id: str = "U_IDEMPOTENCY_TEST"):
    db = SessionLocal()
    try:
        user = User(
            email="idempotency@example.com",
            password_hash=hash_password("secret123"),
            slack_user_id=slack_user_id,
            role="manager",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def test_slack_event_id_prefers_payload_event_id():
    payload = {"type": "event_callback", "event_id": "Ev123"}
    event = {"channel": "C1", "ts": "1.0"}
    assert slack_event_id_from_payload(payload, event) == "Ev123"


def test_claim_slack_event_duplicate_after_executed():
    db = SessionLocal()
    try:
        user = User(
            email="claim-dup@example.com",
            password_hash=hash_password("secret123"),
            role="employee",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        key = "Ev_claim_test_1"
        status, row = claim_slack_event(db, key, user=user, request_text="hello")
        assert status == "proceed"
        assert row is not None
        row.execution_result = "executed"
        row.validation_result = "passed"
        db.commit()

        status2, row2 = claim_slack_event(db, key, user=user, request_text="hello again")
        assert status2 == "duplicate"
        assert row2.id == row.id
    finally:
        db.close()


@patch("app.routes.slack.plan_tool_call_async")
def test_slack_duplicate_delivery_skips_second_execution(mock_plan, client, monkeypatch):
    monkeypatch.setenv("SLACK_EVENTS_ASYNC", "false")
    _seed_slack_user(client)

    due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    mock_plan.return_value = {
        "tool_name": "create_task",
        "arguments": {
            "title": "Idempotent task",
            "assignee": "idempotency@example.com",
            "due_date": due,
        },
        "confidence": 0.95,
        "missing_required": [],
        "clarification_question": None,
    }

    payload = {
        "type": "event_callback",
        "event_id": "Ev_idempotency_integration",
        "event": {
            "type": "message",
            "user": "U_IDEMPOTENCY_TEST",
            "text": "create a task for idempotency@example.com",
            "channel": "C_IDEM",
            "ts": "999.001",
        },
    }
    headers = {"Content-Type": "application/json"}

    first = client.post("/slack/events", content=json.dumps(payload), headers=headers)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body.get("status") == "executed"
    assert first_body.get("duplicate") is not True

    second = client.post("/slack/events", content=json.dumps(payload), headers=headers)
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body.get("duplicate") is True
    assert second_body.get("slack_event_id") == "Ev_idempotency_integration"
    assert mock_plan.call_count == 1

    db = SessionLocal()
    try:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.slack_event_id == "Ev_idempotency_integration")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].execution_result == "executed"
        trace = (
            db.query(SlackOrchestrationTrace)
            .filter(SlackOrchestrationTrace.audit_log_id == rows[0].id)
            .first()
        )
        assert trace is not None
        assert trace.outcome == "executed"
        assert first_body.get("audit_id") == rows[0].id
        assert first_body.get("trace", {}).get("trace_id") == trace.trace_id
    finally:
        db.close()


@patch("app.services.llm_queue_enqueue.publish_llm_job")
def test_slack_queue_skips_enqueue_on_duplicate(mock_publish, client, monkeypatch):
    """Queued path must not publish a second job when event_id was already executed."""
    monkeypatch.setenv("SLACK_EVENTS_ASYNC", "true")
    monkeypatch.setenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    monkeypatch.setenv("LLM_QUEUE_ENABLED", "true")
    _seed_slack_user(client)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.slack_user_id == "U_IDEMPOTENCY_TEST").first()
        key = "Ev_queue_dup"
        status, row = claim_slack_event(db, key, user=user, request_text="first")
        assert status == "proceed"
        row.execution_result = "executed"
        row.validation_result = "passed"
        db.commit()
    finally:
        db.close()

    payload = {
        "type": "event_callback",
        "event_id": "Ev_queue_dup",
        "event": {
            "type": "message",
            "user": "U_IDEMPOTENCY_TEST",
            "text": "hello again",
            "channel": "C_IDEM",
            "ts": "999.002",
        },
    }
    response = client.post(
        "/slack/events",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("duplicate") is True
    mock_publish.assert_not_called()
