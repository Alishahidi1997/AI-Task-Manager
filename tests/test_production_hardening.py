"""Phase 3.7 — workspace limits, webhooks, production guards."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Task, User
from app.services.chat_orchestrator import PlannerOutput
from app.services.production import validate_production_settings
from app.services.webhooks import build_execution_payload, emit_execution_webhook
from app.services.workspace_limits import assert_can_create_task
from tests.conftest import auth_headers


def test_workspace_open_task_limit(monkeypatch):
    monkeypatch.setenv("WORKSPACE_MAX_OPEN_TASKS_PER_USER", "2")
    db = SessionLocal()
    try:
        user = User(email="limit@corp.com", password_hash="x", role="employee", tenant_id="corp")
        db.add(user)
        db.commit()
        db.refresh(user)
        for i in range(2):
            db.add(Task(title=f"T{i}", status="todo", user_id=user.id))
        db.commit()
        with pytest.raises(PermissionError, match="open-task limit"):
            assert_can_create_task(db, user.id)
    finally:
        db.close()


def test_chat_create_blocked_at_workspace_limit(client, monkeypatch):
    monkeypatch.setenv("WORKSPACE_MAX_TASKS_PER_USER", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    headers = auth_headers(client, "ws-limit@corp.com", "secret123")
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    created = client.post(
        "/tasks",
        headers=headers,
        json={"title": "Only task", "description": "", "due_date": due},
    )
    assert created.status_code == 201

    async def plan_create(_c, _m, _i, _r, _s, _conv, _ctx=None):
        parsed = {
            "tool_name": "create_task",
            "arguments": {"title": "Second", "due_date": due},
            "confidence": 0.95,
            "missing_required": [],
            "clarification_question": None,
        }
        return PlannerOutput(**parsed), parsed

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", plan_create)
    response = client.post(
        "/chat",
        headers=headers,
        json={"message": "create another task", "source": "pytest"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "policy_rejected"
    assert "limit" in response.json()["reason"].lower()


def test_emit_execution_webhook_posts_signed_payload(monkeypatch):
    import asyncio

    monkeypatch.setenv("WEBHOOK_URL", "https://example.com/hook")
    monkeypatch.setenv("WEBHOOK_SECRET", "signing-secret")
    captured: dict = {}

    class _Resp:
        def raise_for_status(self):
            return None

    class _Client:
        async def post(self, url, content=None, headers=None, timeout=None):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return _Resp()

    payload = build_execution_payload(
        event="orchestration.executed",
        channel="chat",
        user_id=1,
        tenant_id="corp",
        request_text="hello",
        tool_name="create_task",
        arguments={"title": "x"},
        result={"task_id": 9},
        audit_id=3,
    )
    asyncio.run(emit_execution_webhook(_Client(), payload))
    assert captured["url"] == "https://example.com/hook"
    assert json.loads(captured["content"])["event"] == "orchestration.executed"
    assert captured["headers"]["X-SmartTask-Signature"].startswith("sha256=")


def test_production_requires_strong_jwt(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me-in-production")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validate_production_settings()
