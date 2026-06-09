"""Live OpenAI smoke tests for all AI surfaces (opt-in: RUN_AI_LIVE=1 + OPENAI_API_KEY)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth_headers_with_role

pytestmark = [
    pytest.mark.skipif(
        os.getenv("RUN_AI_LIVE", "").strip().lower() not in {"1", "true", "yes", "on"},
        reason="set RUN_AI_LIVE=1 to run live OpenAI smoke tests",
    ),
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY", "").strip(),
        reason="OPENAI_API_KEY required for live smoke tests",
    ),
]


@pytest.fixture
def mgr_headers(client):
    return auth_headers_with_role(
        client,
        "live-mgr@example.com",
        "secret123",
        role="manager",
        tenant_id="live-tenant",
    )


@pytest.fixture
def emp_headers(client):
    return auth_headers_with_role(
        client,
        "live-emp@example.com",
        "secret123",
        role="employee",
        tenant_id="live-tenant",
    )


def test_live_parse_task(client, mgr_headers):
    response = client.post(
        "/ai/parse-task",
        headers=mgr_headers,
        json={"text": "Review budget deck by tomorrow at 3pm", "timezone": "UTC"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("title")
    assert body.get("mode") == "openai"


def test_live_plan_task(client, mgr_headers):
    response = client.post(
        "/ai/plan-task",
        headers=mgr_headers,
        json={"text": "Prepare for product launch next week", "timezone": "UTC", "horizon_days": 7},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body.get("tasks", [])) >= 1


def test_live_agent_command_dry_run(client, mgr_headers):
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    client.post(
        "/tasks",
        headers=mgr_headers,
        json={"title": "Live agent target", "description": "", "due_date": due},
    )
    response = client.post(
        "/ai/agent-command",
        headers=mgr_headers,
        json={
            "query": "create a task called Live smoke follow-up due in 3 days",
            "dry_run": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True
    assert body.get("tool_calls_count", 0) >= 1


def test_live_chat_create(client, mgr_headers):
    due = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    response = client.post(
        "/chat",
        headers=mgr_headers,
        json={
            "message": f"Create a task titled Live chat smoke test due {due}",
            "source": "live-smoke",
            "conversation_id": "live-smoke-1",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] in {"executed", "clarification_required"}
    if body["status"] == "executed":
        assert body["result"]["task_id"]


def test_live_daily_summary(client, mgr_headers):
    due = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    created = client.post(
        "/tasks",
        headers=mgr_headers,
        json={"title": "Completed live item", "description": "", "due_date": due, "status": "done"},
    )
    assert created.status_code == 201
    response = client.get("/summary/daily", headers=mgr_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("summary")
    assert body.get("mode") == "openai"


def test_live_employee_delete_rejected(client, emp_headers):
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    created = client.post(
        "/tasks",
        headers=emp_headers,
        json={"title": "Emp owned task", "description": "", "due_date": due},
    )
    task_id = created.json()["id"]
    response = client.post(
        "/chat",
        headers=emp_headers,
        json={
            "message": f"delete task {task_id}",
            "source": "live-smoke",
            "conversation_id": "live-smoke-emp",
        },
    )
    # RBAC: delete_task is not in employee chat tool registry (400) or policy blocks (200).
    if response.status_code == 400:
        assert "not allowed" in response.json().get("detail", "").lower()
        return
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "policy_rejected"
    assert "delete" in body.get("reason", "").lower()
