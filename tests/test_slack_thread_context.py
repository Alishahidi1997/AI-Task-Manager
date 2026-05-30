"""Epic 2.1 — Slack thread context and follow-up resolution."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Task, User
from app.services.entity_resolution import apply_task_id_from_title, try_resolve_slack_followup
from app.services.thread_manager import ThreadManager, slack_thread_key
from tests.test_slack_idempotency import _seed_slack_user


@patch("app.routes.slack.plan_tool_call_async")
def test_slack_followup_uses_thread_without_second_llm(mock_plan, client, monkeypatch):
    monkeypatch.setenv("SLACK_EVENTS_ASYNC", "false")
    _seed_slack_user(client)

    due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    mock_plan.return_value = {
        "tool_name": "create_task",
        "arguments": {
            "title": "Slack thread task",
            "assignee": "idempotency@example.com",
            "due_date": due,
        },
        "confidence": 0.95,
        "missing_required": [],
        "clarification_question": None,
    }

    payload = {
        "type": "event_callback",
        "event_id": "Ev_slack_thread_1",
        "event": {
            "type": "message",
            "user": "U_IDEMPOTENCY_TEST",
            "text": "create a task titled Slack thread task",
            "channel": "C_THREAD",
            "ts": "100.001",
            "thread_ts": "100.000",
        },
    }
    headers = {"Content-Type": "application/json"}

    first = client.post("/slack/events", content=json.dumps(payload), headers=headers)
    assert first.status_code == 200, first.text
    assert first.json().get("status") == "executed"
    task_id = first.json()["execution"]["task_id"]

    async def should_not_run(*_args, **_kwargs):
        raise AssertionError("planner should not run for deterministic follow-up")

    mock_plan.side_effect = should_not_run

    payload["event_id"] = "Ev_slack_thread_2"
    payload["event"]["text"] = "mark that done"
    payload["event"]["ts"] = "100.002"
    payload["event"]["thread_ts"] = "100.000"

    second = client.post("/slack/events", content=json.dumps(payload), headers=headers)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body.get("status") == "executed"
    assert body["execution"]["task_id"] == task_id
    assert body["execution"]["status"] == "done"


def test_try_resolve_slack_followup_returns_slack_shape():
    raw = try_resolve_slack_followup("mark that done", 42)
    assert raw is not None
    assert raw["tool_name"] == "update_task"
    assert raw["arguments"]["task_id"] == 42


def test_apply_task_id_from_title():
    db = SessionLocal()
    try:
        user = User(email="title-res@example.com", password_hash=hash_password("secret123"))
        db.add(user)
        db.commit()
        db.refresh(user)
        task = Task(title="Budget review", description="", status="todo", user_id=user.id)
        db.add(task)
        db.commit()

        args = apply_task_id_from_title(
            db,
            user.id,
            "update_task",
            {},
            "please update task called Budget review to done",
        )
        assert args["task_id"] == task.id
    finally:
        db.close()


def test_slack_thread_key_stored_last_task_id():
    db = SessionLocal()
    try:
        user = User(email="thread-key@example.com", password_hash=hash_password("secret123"))
        db.add(user)
        db.commit()
        db.refresh(user)

        mgr = ThreadManager(db, user.id)
        row = mgr.load(slack_thread_key(user.id, "C1", thread_ts="1.0", message_ts="1.1"))
        mgr.record_execution_result(row, {"status": "executed", "task_id": 99})
        db.refresh(row)
        assert row.last_task_id == 99
    finally:
        db.close()
