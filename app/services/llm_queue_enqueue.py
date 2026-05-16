"""Create LLM job rows and publish to RabbitMQ."""

from __future__ import annotations

import asyncio
import hashlib

from sqlalchemy.orm import Session

from app.models import User
from app.queue.config import JOB_CHAT_ORCHESTRATION, JOB_SLACK_ORCHESTRATION
from app.queue.publisher import publish_llm_job
from app.services.llm_jobs import build_queue_message, create_llm_job


def _chat_idempotency_key(conversation_id: str | None, message: str) -> str:
    base = f"{conversation_id or 'none'}:{message.strip()}"
    return "chat:" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


async def enqueue_chat_orchestration(
    db: Session,
    *,
    user: User,
    message: str,
    source: str,
    conversation_id: str | None,
) -> str:
    tenant_id = f"user-{user.id}"
    payload = {
        "message": message,
        "source": source,
        "conversation_id": conversation_id,
    }
    row = create_llm_job(
        db,
        job_type=JOB_CHAT_ORCHESTRATION,
        user_id=user.id,
        tenant_id=tenant_id,
        request_text=message,
        channel="api",
        payload=payload,
        idempotency_key=_chat_idempotency_key(conversation_id, message),
    )
    message_body = build_queue_message(row)
    await asyncio.to_thread(publish_llm_job, message_body, job_type=JOB_CHAT_ORCHESTRATION)
    return row.job_id


async def enqueue_slack_orchestration(
    db: Session,
    *,
    user: User,
    trace_id: str,
    event: dict,
    slack_user_id: str,
    text: str,
    channel_id: str,
    ts,
    slack_event_id: str | None,
) -> str:
    tenant_id = user.tenant_id or "default"
    payload = {
        "trace_id": trace_id,
        "event": event,
        "slack_user_id": slack_user_id,
        "text": text,
        "channel_id": channel_id,
        "ts": ts,
        "slack_event_id": slack_event_id,
    }
    row = create_llm_job(
        db,
        job_type=JOB_SLACK_ORCHESTRATION,
        user_id=user.id,
        tenant_id=tenant_id,
        request_text=text,
        channel="slack",
        payload=payload,
        idempotency_key=slack_event_id,
    )
    message_body = build_queue_message(row)
    await asyncio.to_thread(publish_llm_job, message_body, job_type=JOB_SLACK_ORCHESTRATION)
    return row.job_id
