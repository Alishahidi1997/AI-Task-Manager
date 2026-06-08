"""Role hierarchy — lower rank cannot modify tasks assigned to higher rank."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Task, User
from app.services.chat_orchestrator import PlannerOutput
from app.validation.policy_engine import enforce_policies
from tests.conftest import auth_headers_with_role


def test_employee_cannot_update_task_assigned_to_manager():
    db = SessionLocal()
    try:
        mgr = User(
            email="mgr-hier@corp.com",
            password_hash=hash_password("x"),
            role="manager",
            tenant_id="corp-hier",
        )
        emp = User(
            email="emp-hier@corp.com",
            password_hash=hash_password("x"),
            role="employee",
            tenant_id="corp-hier",
        )
        db.add_all([mgr, emp])
        db.commit()
        db.refresh(emp)
        task = Task(
            title="Ops handoff",
            status="todo",
            assignee=mgr.email,
            user_id=emp.id,
            due_date=datetime.now(timezone.utc) + timedelta(days=2),
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        with pytest.raises(PermissionError, match="above your role"):
            enforce_policies(
                {"role": "employee", "tenant": "corp-hier", "user_id": emp.id},
                "update_task",
                {"task_id": task.id, "status": "done"},
                db=db,
            )
    finally:
        db.close()


def test_employee_cannot_assign_to_manager_via_chat(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    mgr_email = "mgr-hier-chat@corp.com"
    headers = auth_headers_with_role(
        client,
        "emp-hier-chat@corp.com",
        "secret123",
        role="employee",
        tenant_id="corp-hier-chat",
    )
    db = SessionLocal()
    try:
        db.add(
            User(
                email=mgr_email,
                password_hash=hash_password("secret123"),
                role="manager",
                tenant_id="corp-hier-chat",
            )
        )
        db.commit()
    finally:
        db.close()

    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    async def plan_create_for_manager(
        _c, _m, _i, _r, _s, _conv, _ctx=None
    ):
        parsed = {
            "tool_name": "create_task",
            "arguments": {
                "title": "Work for manager",
                "due_date": due,
                "assignee": mgr_email,
            },
            "confidence": 0.95,
            "missing_required": [],
            "clarification_question": None,
        }
        return PlannerOutput(**parsed), parsed

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", plan_create_for_manager)
    response = client.post(
        "/chat",
        headers=headers,
        json={"message": f"create task for {mgr_email} due tomorrow", "source": "pytest"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "policy_rejected"
    assert "assign" in body["reason"].lower() or "role" in body["reason"].lower()
