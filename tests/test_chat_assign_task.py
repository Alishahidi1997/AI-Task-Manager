"""Phase 3.6 — assign_task on /chat."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Task, User
from app.services.chat_orchestrator import PlannerOutput
from tests.conftest import auth_headers_with_role


@pytest.fixture(autouse=True)
def _openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def test_manager_assign_task_via_chat(client, monkeypatch):
    mgr_email = "mgr-chat-assign@corp.com"
    dev_email = "dev-chat-assign@corp.com"
    headers = auth_headers_with_role(
        client,
        mgr_email,
        "secret123",
        role="manager",
        tenant_id="corp-chat-assign",
    )

    db = SessionLocal()
    try:
        db.add(
            User(
                email=dev_email,
                password_hash=hash_password("secret123"),
                role="employee",
                tenant_id="corp-chat-assign",
            )
        )
        user = db.query(User).filter(User.email == mgr_email).first()
        task = Task(
            title="Ops handoff",
            status="todo",
            user_id=user.id,
            due_date=datetime.now(timezone.utc) + timedelta(days=2),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
    finally:
        db.close()

    async def plan_assign(_client, _message, _identity, _registry, _source, _conv, _ctx=None):
        parsed = {
            "tool_name": "assign_task",
            "arguments": {"task_id": task_id, "assignee": "dev"},
            "confidence": 0.95,
            "missing_required": [],
            "clarification_question": None,
        }
        return PlannerOutput(**parsed), parsed

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", plan_assign)

    response = client.post(
        "/chat",
        headers=headers,
        json={"message": f"assign task {task_id} to dev", "source": "pytest"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "executed"
    assert body["result"]["assignee"] == dev_email
    assert body["planner_output"]["arguments"]["assignee"] == dev_email

    listed = client.get("/tasks", headers=headers).json()
    row = next(t for t in listed if t["id"] == task_id)
    assert row["assignee"] == dev_email


def test_employee_chat_registry_excludes_assign_task():
    from app.services.chat_orchestrator import _chat_tool_registry_for_user

    class _User:
        role = "employee"

    assert "assign_task" not in _chat_tool_registry_for_user(_User())
    assert "assign_task" in _chat_tool_registry_for_user(type("_Mgr", (), {"role": "manager"})())
