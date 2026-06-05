"""Epic 2 entity resolution — assignee name → tenant user email."""

from datetime import datetime, timedelta, timezone

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Task, User
from app.services.chat_orchestrator import PlannerOutput
from app.services.entity_resolution import (
    apply_assignee_resolution,
    find_assignee_candidates,
)
from tests.conftest import auth_headers_with_role


def test_find_assignee_candidates_by_email_local_part():
    db = SessionLocal()
    try:
        db.add(
            User(
                email="ali@corp.com",
                password_hash=hash_password("secret123"),
                role="employee",
                tenant_id="corp",
            )
        )
        db.add(
            User(
                email="alice@corp.com",
                password_hash=hash_password("secret123"),
                role="employee",
                tenant_id="corp",
            )
        )
        db.commit()

        ali_matches = find_assignee_candidates(db, "corp", "ali")
        assert len(ali_matches) == 1
        assert ali_matches[0].email == "ali@corp.com"

        ambiguous = find_assignee_candidates(db, "corp", "al")
        assert len(ambiguous) == 2
    finally:
        db.close()


def test_apply_assignee_resolution_ambiguous_returns_clarification():
    db = SessionLocal()
    try:
        db.add(
            User(
                email="ali@corp.com",
                password_hash=hash_password("secret123"),
                role="employee",
                tenant_id="corp",
            )
        )
        db.add(
            User(
                email="alice@corp.com",
                password_hash=hash_password("secret123"),
                role="employee",
                tenant_id="corp",
            )
        )
        db.commit()

        args, question = apply_assignee_resolution(
            db,
            "corp",
            {"assignee": "al"},
            "create task assigned to al",
        )
        assert question is not None
        assert "Which assignee" in question
        assert "ali@corp.com" in question
    finally:
        db.close()


def test_chat_resolves_assignee_name_before_policy(client, monkeypatch):
    mgr_email = "mgr-assign-res@corp.com"
    dev_email = "dev-assign-res@corp.com"

    headers = auth_headers_with_role(
        client,
        mgr_email,
        "secret123",
        role="manager",
        tenant_id="corp-assign",
    )

    db = SessionLocal()
    try:
        db.add(
            User(
                email=dev_email,
                password_hash=hash_password("secret123"),
                role="employee",
                tenant_id="corp-assign",
            )
        )
        db.commit()
    finally:
        db.close()
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    async def plan_with_name_hint(
        client, message, identity_ctx, tool_registry, source, conversation_id, thread_context=None
    ):
        parsed = {
            "tool_name": "create_task",
            "arguments": {
                "title": "Budget review",
                "due_date": due,
                "assignee": "dev",
            },
            "confidence": 0.95,
            "missing_required": [],
            "clarification_question": None,
        }
        return PlannerOutput(**parsed), parsed

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", plan_with_name_hint)

    response = client.post(
        "/chat",
        headers=headers,
        json={"message": "Create budget review assigned to dev", "source": "pytest"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "executed"
    assert body["planner_output"]["arguments"]["assignee"] == dev_email

    task_id = body["result"]["task_id"]
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        assert task is not None
        assert task.assignee == dev_email
    finally:
        db.close()
