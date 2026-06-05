"""Phase 3.5 — Task.assignee column persisted by API and Slack execution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Task, User
from app.services.slack_execution import execute_slack_tool
from tests.conftest import auth_headers_with_role


def test_rest_create_and_update_assignee(client):
    email = "assignee-col@corp.com"
    headers = auth_headers_with_role(
        client,
        email,
        "secret123",
        role="employee",
        tenant_id="corp-assignee",
    )
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    created = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "With assignee",
            "description": "note",
            "due_date": due,
            "assignee": "peer@corp.com",
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert created.json()["assignee"] == "peer@corp.com"

    updated = client.put(
        f"/tasks/{task_id}",
        headers=headers,
        json={"assignee": "other@corp.com"},
    )
    assert updated.status_code == 200
    assert updated.json()["assignee"] == "other@corp.com"


def test_slack_create_and_assign_task_set_assignee_column(client):
    mgr_email = "mgr-assign-col@corp.com"
    headers = auth_headers_with_role(
        client,
        mgr_email,
        "secret123",
        role="manager",
        tenant_id="corp-assignee-col",
    )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == mgr_email).first()
        assert user is not None
        due = datetime.now(timezone.utc) + timedelta(days=3)
        result = execute_slack_tool(
            tool="create_task",
            arguments={
                "title": "Slack assignee task",
                "assignee": "ops@corp.com",
                "due_date": due.isoformat(),
            },
            user=user,
            db=db,
        )
        task = db.query(Task).filter(Task.id == result["task_id"]).first()
        assert task is not None
        assert task.assignee == "ops@corp.com"
        assert task.description is None

        execute_slack_tool(
            tool="assign_task",
            arguments={"task_id": task.id, "assignee": "dev@corp.com"},
            user=user,
            db=db,
        )
        db.refresh(task)
        assert task.assignee == "dev@corp.com"
    finally:
        db.close()

    # smoke: authenticated list still works
    listed = client.get("/tasks", headers=headers)
    assert listed.status_code == 200
