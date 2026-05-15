from datetime import datetime, timedelta, timezone

import pytest

from app.services.chat_orchestrator import PlannerOutput
from tests.conftest import auth_headers


@pytest.fixture
def mock_chat_planner(monkeypatch):
    async def fake_llm_plan(client, message, identity_ctx, source, conversation_id):
        due = datetime.now(timezone.utc) + timedelta(days=2)
        parsed = {
            "tool_name": "create_task",
            "arguments": {
                "title": "Chat planned task",
                "due_date": due.isoformat(),
            },
            "confidence": 0.95,
            "missing_required": [],
            "clarification_question": None,
        }
        return PlannerOutput(**parsed), parsed

    monkeypatch.setattr("app.services.chat_orchestrator._llm_plan_async", fake_llm_plan)


def test_chat_executes_mocked_planner(client, mock_chat_planner):
    headers = auth_headers(client, "chat-user@example.com", "secret123")
    response = client.post(
        "/chat",
        headers=headers,
        json={"message": "Create a task due tomorrow called Chat planned task", "source": "pytest"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "executed"
    assert "audit_id" in body
    assert body["result"]["tool_name"] == "create_task"
    assert body["result"]["task_id"] > 0

    audit = client.get(f"/audit/{body['audit_id']}", headers=headers)
    assert audit.status_code == 200
    assert audit.json()["tool_name"] == "create_task"
