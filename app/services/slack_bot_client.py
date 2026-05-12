"""Slack Bot API helpers for Layer 9 — post orchestration results to the channel (or thread)."""

from __future__ import annotations

import os
from typing import Any

import httpx

CHAT_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"


def slack_bot_token() -> str:
    return os.getenv("SLACK_BOT_TOKEN", "").strip()


async def chat_post_message(
    client: httpx.AsyncClient,
    *,
    token: str,
    channel: str,
    text: str,
    thread_ts: str | None = None,
) -> dict[str, Any]:
    """Call chat.postMessage. Returns Slack JSON plus http_status."""
    body: dict[str, Any] = {"channel": channel, "text": text}
    if thread_ts:
        body["thread_ts"] = thread_ts
    resp = await client.post(
        CHAT_POST_MESSAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json=body,
    )
    try:
        data = resp.json()
    except Exception:
        data = {"ok": False, "error": "invalid_json_response", "raw": resp.text[:500]}
    if isinstance(data, dict):
        data = {**data, "http_status": resp.status_code}
        return data
    return {"ok": False, "error": "unexpected_response_shape", "http_status": resp.status_code}
