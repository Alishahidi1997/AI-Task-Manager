import json
import os
from collections.abc import AsyncIterator

import httpx

from app.llm.openai_transport import OPENAI_CHAT_URL, post_chat_completion_async, post_chat_completion_sync


def _planner_payload(system_prompt: str, user_text: str) -> dict:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.1,
        "max_tokens": 320,
        "response_format": {"type": "json_object"},
    }


def _parse_planner_content(data: dict) -> dict:
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON from planner") from exc


def plan_tool_call(system_prompt: str, user_text: str) -> dict:
    """Synchronous planner call (standalone scripts / tests). Prefer plan_tool_call_async in routes."""
    data = post_chat_completion_sync(_planner_payload(system_prompt, user_text))
    return _parse_planner_content(data)


async def plan_tool_call_async(
    client: httpx.AsyncClient, system_prompt: str, user_text: str
) -> dict:
    """Planner call using the shared AsyncClient from app.state (dependency injection)."""
    data = await post_chat_completion_async(client, _planner_payload(system_prompt, user_text))
    return _parse_planner_content(data)


async def stream_chat_completion_text(
    client: httpx.AsyncClient, payload: dict
) -> AsyncIterator[str]:
    """Yield assistant content deltas from OpenAI streaming chat completions."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    stream_body = {**payload, "stream": True}
    async with client.stream(
        "POST",
        OPENAI_CHAT_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=stream_body,
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line or line.startswith(":"):
                continue
            if line.startswith("data: "):
                chunk = line[6:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {}).get("content")
                if delta:
                    yield delta
