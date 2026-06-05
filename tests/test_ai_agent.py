"""AI agent command — single-tool intent, RBAC, policy, and task resolution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Task, User
from app.services.ai_agent import (
    detect_agent_intent,
    filter_tool_calls_for_intent,
    run_agent_command,
)
from app.services.entity_resolution import resolve_task_id_for_agent_query
from tests.conftest import auth_headers_with_role


def test_detect_agent_intent_prefers_delete_over_pasted_create_text():
    query = (
        "delete the task for operational manager, this one:\n"
        "Add a task for operational manager\n"
        "todo\n"
        "category: this_week | due: 2026-06-07T01:00:00"
    )
    assert detect_agent_intent(query) == "delete"


def test_filter_tool_calls_keeps_only_delete_for_delete_intent():
    calls = [
        {"function": {"name": "delete_task", "arguments": '{"task_id": 99}'}},
        {
            "function": {
                "name": "create_task",
                "arguments": '{"title": "Add a task for operational manager"}',
            }
        },
    ]
    filtered = filter_tool_calls_for_intent(calls, "delete")
    assert len(filtered) == 1
    assert filtered[0]["function"]["name"] == "delete_task"


def test_resolve_task_id_from_pasted_agent_block():
    db = SessionLocal()
    try:
        user = User(
            email="agent-resolve@corp.com",
            password_hash="x",
            role="manager",
            tenant_id="corp-agent",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        due = datetime(2026, 6, 7, 1, 0, tzinfo=timezone.utc)
        task = Task(
            title="Add a task for operational manager",
            status="todo",
            category="this_week",
            due_date=due,
            assignee="ops-mgr@corp.com",
            user_id=user.id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        query = (
            "delete the task for operational manager, this one:\n"
            "Add a task for operational manager\n"
            "todo\n"
            "category: this_week | due: 2026-06-07T01:00:00"
        )
        resolved = resolve_task_id_for_agent_query(db, user.id, query, {"task_id": 999})
        assert resolved == task.id
    finally:
        db.close()


def test_employee_delete_blocked_by_policy(client, monkeypatch):
    headers = auth_headers_with_role(
        client,
        "emp-agent@corp.com",
        "secret123",
        role="employee",
        tenant_id="corp-agent",
    )

    def fake_openai(*_args, **_kwargs):
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "delete_task",
                        "arguments": '{"task_id": 1}',
                    }
                }
            ],
            "content": "",
        }

    monkeypatch.setattr("app.services.ai_agent._ask_openai_for_tools", fake_openai)

    response = client.post(
        "/ai/agent-command",
        headers=headers,
        json={"query": "delete task 1", "dry_run": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "delete"
    assert body["actions"][0]["ok"] is False
    assert body["actions"][0]["detail"]
    assert body["actions"][0]["ok"] is False


def test_manager_delete_does_not_create_task(client, monkeypatch):
    headers = auth_headers_with_role(
        client,
        "mgr-agent@corp.com",
        "secret123",
        role="manager",
        tenant_id="corp-agent",
    )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "mgr-agent@corp.com").first()
        due = datetime.now(timezone.utc) + timedelta(days=2)
        task = Task(
            title="Add a task for operational manager",
            status="todo",
            category="this_week",
            due_date=due,
            assignee="ops-mgr@corp.com",
            user_id=user.id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
    finally:
        db.close()

    query = (
        "delete the task for operational manager, this one:\n"
        "Add a task for operational manager\n"
        "todo\n"
        f"category: this_week | due: {due.isoformat()}"
    )

    def fake_openai(*_args, **_kwargs):
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "delete_task",
                        "arguments": '{"task_id": 999}',
                    }
                },
                {
                    "function": {
                        "name": "create_task",
                        "arguments": '{"title": "Add a task for operational manager"}',
                    }
                },
            ],
            "content": "",
        }

    monkeypatch.setattr("app.services.ai_agent._ask_openai_for_tools", fake_openai)

    before = client.get("/tasks", headers=headers).json()
    assert any(row["id"] == task_id for row in before)

    response = client.post(
        "/ai/agent-command",
        headers=headers,
        json={"query": query, "dry_run": False},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "delete"
    assert len(body["actions"]) == 1
    assert body["actions"][0]["tool"] == "delete_task"
    assert body["actions"][0]["ok"] is True
    assert body["actions"][0]["task_id"] == task_id

    after = client.get("/tasks", headers=headers).json()
    assert not any(row["id"] == task_id for row in after)
