"""Live OpenAI planner calls for eval suite (EVAL_LIVE=1 only)."""

from __future__ import annotations

import httpx

from app.evals.models import GoldenCase
from app.llm.openai_client import plan_tool_call
from app.orchestration.prompt_builder import build_planner_system_prompt
from app.orchestration.tool_registry import filter_tools, tool_schema_map
from app.services.chat_orchestrator import _chat_planner_openai_payload, _chat_tool_registry_for_user
from app.services.rbac import allowed_tools_for_role


class _EvalUser:
    def __init__(self, role: str, user_id: int = 1):
        self.id = user_id
        self.role = role
        self.tenant_id = "eval-tenant"


def live_planner(case: GoldenCase) -> dict:
    if case.channel == "chat":
        user = _EvalUser(case.role)
        registry = _chat_tool_registry_for_user(user)
        identity = {
            "user_id": user.id,
            "tenant_id": user.tenant_id,
            "role": case.role,
            "tenant": user.tenant_id,
        }
        payload = _chat_planner_openai_payload(
            case.input,
            identity,
            registry,
            source="eval",
            conversation_id=None,
            thread_context=None,
        )
        with httpx.Client(timeout=45.0) as client:
            api_key = __import__("os").environ.get("OPENAI_API_KEY", "").strip()
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            content = (response.json().get("choices") or [{}])[0].get("message", {}).get("content") or "{}"
        import json

        return json.loads(content)

    tools = filter_tools(allowed_tools_for_role(case.role))
    schemas = tool_schema_map()
    identity = {
        "user_id": 1,
        "tenant_id": "eval-tenant",
        "role": case.role,
        "tenant": "eval-tenant",
    }
    prompt = build_planner_system_prompt(identity, tools)
    raw = plan_tool_call(prompt, case.input)
    if raw.get("tool") not in schemas:
        return raw
    return raw
