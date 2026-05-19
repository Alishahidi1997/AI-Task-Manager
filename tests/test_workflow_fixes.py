from datetime import datetime, timedelta, timezone

import pytest

from app.auth import hash_password
from app.database import SessionLocal
from app.models import AuditLog, Task, User
from app.services.slack_idempotency import (
    claim_slack_event,
    fail_stuck_processing_claim,
    is_stale_processing,
)
from app.services.task_workflow import assert_status_transition
from tests.conftest import auth_headers


def test_assert_status_transition_blocks_todo_to_done():
    with pytest.raises(ValueError, match="invalid status workflow"):
        assert_status_transition("todo", "done")


def test_stale_processing_detected():
    db = SessionLocal()
    try:
        user = User(
            email="stale@example.com",
            password_hash=hash_password("secret123"),
            role="employee",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        status, row = claim_slack_event(db, "Ev_stale", user=user, request_text="hi")
        assert status == "proceed"
        assert row is not None
        row.created_at = datetime.now(timezone.utc) - timedelta(seconds=400)
        db.commit()
        db.refresh(row)
        assert is_stale_processing(row) is True

        status2, row2 = claim_slack_event(db, "Ev_stale", user=user, request_text="retry")
        assert status2 == "proceed"
        assert row2.id == row.id
    finally:
        db.close()


def test_abandoned_claim_is_reclaimed_on_retry():
    db = SessionLocal()
    try:
        user = User(
            email="abandon@example.com",
            password_hash=hash_password("secret123"),
            role="employee",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        key = "Ev_abandon"
        status, row = claim_slack_event(db, key, user=user, request_text="first")
        assert status == "proceed"
        fail_stuck_processing_claim(db, key)
        db.refresh(row)
        assert row.execution_result == "abandoned"

        status2, row2 = claim_slack_event(db, key, user=user, request_text="retry")
        assert status2 == "proceed"
        assert row2.id == row.id
        assert row2.execution_result == "processing"
    finally:
        db.close()


def test_chat_employee_cannot_delete(client, monkeypatch):
    async def fake_plan(
        client, message, identity_ctx, tool_registry, source, conversation_id, thread_context=None
    ):
        from app.services.chat_orchestrator import PlannerOutput

        due = datetime.now(timezone.utc) + timedelta(days=2)
        parsed = {
            "tool_name": "delete_task",
            "arguments": {"task_id": 1},
            "confidence": 0.95,
            "missing_required": [],
            "clarification_question": None,
        }
        return PlannerOutput(**parsed), parsed

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", fake_plan)
    headers = auth_headers(client, "emp-delete@example.com", "secret123")
    response = client.post(
        "/chat",
        headers=headers,
        json={"message": "delete task 1", "source": "pytest"},
    )
    assert response.status_code == 403


def test_insights_snapshot_empty_user(client):
    headers = auth_headers(client, "snap@example.com", "secret123")
    response = client.get("/insights/snapshot", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "productivity" in body
    assert "anomalies" in body
    assert "next_actions" in body


def test_insights_explain_anomalies(client):
    headers = auth_headers(client, "explain@example.com", "secret123")
    response = client.get("/insights/explain/anomalies", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["insight_id"] == "anomalies"
    assert isinstance(body.get("why"), list)


def test_chat_update_respects_status_workflow(client, monkeypatch):
    headers = auth_headers(client, "wf@example.com", "secret123")
    due = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    create = client.post(
        "/tasks",
        headers=headers,
        json={"title": "Workflow task", "description": "x", "due_date": due},
    )
    task_id = create.json()["id"]

    async def fake_plan(
        client, message, identity_ctx, tool_registry, source, conversation_id, thread_context=None
    ):
        from app.services.chat_orchestrator import PlannerOutput

        parsed = {
            "tool_name": "update_task",
            "arguments": {"task_id": task_id, "status": "done"},
            "confidence": 0.95,
            "missing_required": [],
            "clarification_question": None,
        }
        return PlannerOutput(**parsed), parsed

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", fake_plan)
    bad = client.post(
        "/chat",
        headers=headers,
        json={"message": "mark done", "source": "pytest"},
    )
    assert bad.status_code == 400
    assert "invalid status workflow" in bad.json()["detail"]
