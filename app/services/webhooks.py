"""Outbound webhooks for AI/orchestration execution events (Phase 3.7)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


def webhooks_enabled() -> bool:
    return bool(os.getenv("WEBHOOK_URL", "").strip())


def build_execution_payload(
    *,
    event: str,
    channel: str,
    user_id: int,
    tenant_id: str,
    request_text: str,
    tool_name: str | None,
    arguments: dict | None,
    result: dict | None,
    audit_id: int | None = None,
) -> dict:
    return {
        "event": event,
        "channel": channel,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "request_text": request_text,
        "tool_name": tool_name,
        "arguments": arguments or {},
        "result": result,
        "audit_id": audit_id,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
    }


async def emit_execution_webhook(http_client: httpx.AsyncClient, payload: dict) -> None:
    """Best-effort POST; never raises to callers."""
    url = os.getenv("WEBHOOK_URL", "").strip()
    if not url:
        return
    body = json.dumps(payload, default=str, ensure_ascii=True)
    headers = {"Content-Type": "application/json", "User-Agent": "SmartTaskTracker/1.0"}
    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if secret:
        digest = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
        headers["X-SmartTask-Signature"] = f"sha256={digest}"
    try:
        response = await http_client.post(url, content=body, headers=headers, timeout=5.0)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("webhook delivery failed: %s", exc)
