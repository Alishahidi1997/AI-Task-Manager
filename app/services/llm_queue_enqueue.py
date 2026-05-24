"""Create LLM job rows and publish to RabbitMQ."""

from __future__ import annotations

import asyncio
import hashlib

from sqlalchemy.orm import Session

from app.models import LLMJob, User
from app.queue.config import JOB_CHAT_ORCHESTRATION, JOB_DAILY_SUMMARY, JOB_SLACK_ORCHESTRATION
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


def _daily_summary_idempotency_key(user_id: int, day: date | None = None) -> str:
    day = day or date.today()
    return f"daily-summary:{user_id}:{day.isoformat()}"


def enqueue_daily_summary_for_user(db: Session, user: User, *, day: date | None = None) -> str | None:
    """Enqueue one daily summary job on the batch queue. Skips duplicate idempotency keys."""
    tenant_id = user.tenant_id or f"user-{user.id}"
    idempotency_key = _daily_summary_idempotency_key(user.id, day)
    existing = (
        db.query(LLMJob)
        .filter(
            LLMJob.idempotency_key == idempotency_key,
            LLMJob.job_type == JOB_DAILY_SUMMARY,
            LLMJob.status.in_(("pending", "running", "completed")),
        )
        .first()
    )
    if existing is not None:
        return existing.job_id

    payload = {"user_id": user.id, "summary_date": (day or date.today()).isoformat()}
    row = create_llm_job(
        db,
        job_type=JOB_DAILY_SUMMARY,
        user_id=user.id,
        tenant_id=tenant_id,
        request_text=f"daily summary {payload['summary_date']}",
        channel="batch",
        payload=payload,
        idempotency_key=idempotency_key,
    )
    message_body = build_queue_message(row)
    publish_llm_job(message_body, job_type=JOB_DAILY_SUMMARY)
    return row.job_id


def enqueue_daily_summaries_for_all_users(db: Session) -> list[str]:
    users = db.query(User).order_by(User.id.asc()).all()
    job_ids: list[str] = []
    for user in users:
        job_id = enqueue_daily_summary_for_user(db, user)
        if job_id:
            job_ids.append(job_id)
    return job_ids
