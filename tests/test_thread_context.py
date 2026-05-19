from datetime import datetime, timedelta, timezone

import pytest

from app.services.chat_orchestrator import PlannerOutput
from tests.conftest import auth_headers


@pytest.fixture
def mock_chat_planner(monkeypatch):
    async def fake_llm_plan(
        client, message, identity_ctx, tool_registry, source, conversation_id, thread_context=None
    ):
        due = datetime.now(timezone.utc) + timedelta(days=2)
        parsed = {
            "tool_name": "create_task",
            "arguments": {
                "title": "Thread context task",
                "due_date": due.isoformat(),
            },
            "confidence": 0.95,
            "missing_required": [],
            "clarification_question": None,
        }
        return PlannerOutput(**parsed), parsed

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", fake_llm_plan)


def test_followup_resolves_last_task_without_second_llm_call(client, mock_chat_planner, monkeypatch):
    headers = auth_headers(client, "thread-user@example.com", "secret123")
    conversation_id = "conv-followup-1"

    create_resp = client.post(
        "/chat",
        headers=headers,
        json={
            "message": "Create a task called Thread context task",
            "source": "pytest",
            "conversation_id": conversation_id,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    created = create_resp.json()
    assert created["status"] == "executed"
    task_id = created["result"]["task_id"]

    async def should_not_run(*_args, **_kwargs):
        raise AssertionError("LLM planner should not run for deterministic follow-up")

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", should_not_run)

    followup_resp = client.post(
        "/chat",
        headers=headers,
        json={
            "message": "mark that done",
            "source": "pytest",
            "conversation_id": conversation_id,
        },
    )
    assert followup_resp.status_code == 200, followup_resp.text
    body = followup_resp.json()
    assert body["status"] == "executed"
    assert body["result"]["task_id"] == task_id
    assert body["result"]["status"] == "done"
    assert body["planner_output"]["tool_name"] == "update_task"


def test_clarify_resumes_pending_create(client, monkeypatch):
    async def low_confidence_plan(
        client, message, identity_ctx, tool_registry, source, conversation_id, thread_context=None
    ):
        parsed = {
            "tool_name": "create_task",
            "arguments": {"title": "Needs due date"},
            "confidence": 0.2,
            "missing_required": ["due_date"],
            "clarification_question": "When is this due?",
        }
        return PlannerOutput(**parsed), parsed

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", low_confidence_plan)

    headers = auth_headers(client, "clarify-user@example.com", "secret123")
    conversation_id = "conv-clarify-1"

    first = client.post(
        "/chat",
        headers=headers,
        json={
            "message": "Create a task called Needs due date",
            "source": "pytest",
            "conversation_id": conversation_id,
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "clarification_required"

    due = datetime.now(timezone.utc) + timedelta(days=3)
    second = client.post(
        "/clarify",
        headers=headers,
        json={"conversation_id": conversation_id, "answer": due.isoformat()},
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["status"] == "executed"
    assert body["result"]["tool_name"] == "create_task"
    assert body["result"]["task_id"] > 0
