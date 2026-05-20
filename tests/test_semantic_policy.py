"""Epic 3 semantic policy rules (pytest per rule)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Task, User
from app.services.chat_orchestrator import PlannerOutput
from app.validation.policy_engine import enforce_policies
from tests.conftest import auth_headers, auth_headers_with_role


def test_delete_task_requires_manager_or_admin():
    with pytest.raises(PermissionError, match="delete"):
        enforce_policies(
            {"role": "employee", "tenant": "t1", "user_id": 1},
            "delete_task",
            {"task_id": 1},
        )


def test_assignee_must_belong_to_tenant():
    db = SessionLocal()
    try:
        user = User(
            email="tenant-a@example.com",
            password_hash=hash_password("secret123"),
            role="manager",
            tenant_id="tenant-a",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        with pytest.raises(PermissionError, match="tenant"):
            enforce_policies(
                {"role": "manager", "tenant": "tenant-a", "user_id": user.id},
                "create_task",
                {
                    "title": "x",
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                    "assignee": "nobody@other.com",
                },
                db=db,
            )
    finally:
        db.close()


def test_due_date_slip_capped_for_employee(client, monkeypatch):
    headers = auth_headers_with_role(
        client,
        "slip-emp@example.com",
        "secret123",
        role="employee",
        tenant_id="tenant-slip",
    )
    due = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    created = client.post(
        "/tasks",
        headers=headers,
        json={"title": "Slip task", "description": "", "due_date": due},
    )
    task_id = created.json()["id"]
    far = (datetime.now(timezone.utc) + timedelta(days=40)).isoformat()

    async def fake_plan(
        client, message, identity_ctx, tool_registry, source, conversation_id, thread_context=None
    ):
        parsed = {
            "tool_name": "update_task",
            "arguments": {"task_id": task_id, "due_date": far},
            "confidence": 0.95,
            "missing_required": [],
            "clarification_question": None,
        }
        return PlannerOutput(**parsed), parsed

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", fake_plan)
    response = client.post(
        "/chat",
        headers=headers,
        json={"message": "push due date", "source": "pytest"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "policy_rejected"
    assert "extended" in body["reason"].lower() or "days" in body["reason"].lower()


def test_manager_can_delete_via_chat(client, monkeypatch):
    headers = auth_headers_with_role(
        client, "mgr-del@example.com", "secret123", role="manager", tenant_id="tenant-mgr"
    )
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    created = client.post(
        "/tasks",
        headers=headers,
        json={"title": "To delete", "description": "", "due_date": due},
    )
    task_id = created.json()["id"]

    async def fake_plan(
        client, message, identity_ctx, tool_registry, source, conversation_id, thread_context=None
    ):
        parsed = {
            "tool_name": "delete_task",
            "arguments": {"task_id": task_id},
            "confidence": 0.95,
            "missing_required": [],
            "clarification_question": None,
        }
        return PlannerOutput(**parsed), parsed

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", fake_plan)
    response = client.post(
        "/chat",
        headers=headers,
        json={"message": "delete that task", "source": "pytest"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
