"""Process queued LLM / orchestration jobs — reuses existing orchestration code."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import AuditLog, User
from app.queue.config import (
    JOB_CHAT_ORCHESTRATION,
    JOB_CHAT_STREAM,
    JOB_DAILY_SUMMARY,
    JOB_SLACK_ORCHESTRATION,
)
from app.services.chat_stream_buffer import append_stream_event, set_stream_status
from app.services.chat_orchestrator import orchestrate_chat_stream
from app.services.daily_summary_job import run_daily_summary_for_user
from app.services.audit_utils import audit_validation_result
from app.services.chat_orchestrator import orchestrate_chat
from app.services.llm_jobs import mark_job_completed, mark_job_failed, mark_job_running
from app.services.slack_idempotency import fail_stuck_processing_claim
from app.services.slack_observability import SlackTraceRecorder

logger = logging.getLogger(__name__)


def _save_chat_audit(db, *, user_id: int, tenant_id: str, request_text: str, result: dict) -> int:
    planner = result.get("planner_output") or {}
    row = AuditLog(
        request_text=request_text,
        tool_name=planner.get("tool_name"),
        arguments=json.dumps(planner.get("arguments", {}), ensure_ascii=True),
        validation_result=audit_validation_result(result.get("status", "unknown")),
        execution_result=result.get("status", "unknown"),
        user_id=user_id,
        tenant_id=tenant_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


def _save_chat_denied_audit(db, *, user_id: int, tenant_id: str, request_text: str) -> int:
    row = AuditLog(
        request_text=request_text,
        tool_name=None,
        arguments=None,
        validation_result="failed",
        execution_result="denied",
        user_id=user_id,
        tenant_id=tenant_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


async def _run_chat_job(message: dict) -> dict:
    job_id = message["job_id"]
    user_id = message["user_id"]
    tenant_id = message["tenant_id"]
    inner = message.get("payload") or {}
    request_text = message.get("request_text", "")
    db = SessionLocal()
    job_row = None
    try:
        row = db.query(User).filter(User.id == user_id).first()
        if row is None:
            raise ValueError(f"user {user_id} not found")
        from app.models import LLMJob

        job_row = db.query(LLMJob).filter(LLMJob.job_id == job_id).first()
        if job_row:
            mark_job_running(db, job_row)

        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0)) as client:
            result = await orchestrate_chat(
                inner.get("message", request_text),
                source=inner.get("source", "api"),
                conversation_id=inner.get("conversation_id"),
                current_user=row,
                db=db,
                http_client=client,
            )
        if result.get("status") == "policy_rejected":
            audit_id = _save_chat_audit(
                db,
                user_id=user_id,
                tenant_id=tenant_id,
                request_text=request_text,
                result=result,
            )
            if job_row:
                mark_job_completed(
                    db,
                    job_row,
                    result={**result, "audit_id": audit_id},
                    audit_log_id=audit_id,
                )
            return {**result, "audit_id": audit_id}

        audit_id = _save_chat_audit(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            request_text=request_text,
            result=result,
        )
        if job_row:
            mark_job_completed(db, job_row, result={**result, "audit_id": audit_id}, audit_log_id=audit_id)
        return {**result, "audit_id": audit_id}
    except PermissionError as exc:
        audit_id = _save_chat_denied_audit(
            db, user_id=user_id, tenant_id=tenant_id, request_text=request_text
        )
        if job_row:
            mark_job_failed(
                db,
                job_row,
                error=str(exc),
                result={"status": "denied", "audit_id": audit_id},
            )
        raise
    except Exception as exc:
        if job_row:
            mark_job_failed(db, job_row, error=str(exc))
        raise
    finally:
        db.close()


async def _run_slack_job(message: dict) -> dict:
    from app.routes.slack import _orchestrate_slack_message_after_user_map, _post_slack_user_message

    job_id = message["job_id"]
    user_id = message["user_id"]
    inner = message.get("payload") or {}
    slack_event_id = inner.get("slack_event_id")
    trace_id = inner.get("trace_id")

    db = SessionLocal()
    recorder = SlackTraceRecorder(trace_id=trace_id) if trace_id else SlackTraceRecorder()
    job_row = None
    try:
        user = db.get(User, user_id)
        if user is None:
            raise ValueError(f"user {user_id} not found")

        from app.models import LLMJob

        job_row = db.query(LLMJob).filter(LLMJob.job_id == job_id).first()
        if job_row:
            mark_job_running(db, job_row)

        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0)) as client:
            try:
                body = await _orchestrate_slack_message_after_user_map(
                    client,
                    recorder,
                    db,
                    user,
                    event=inner.get("event") or {},
                    slack_user_id=inner.get("slack_user_id", ""),
                    text=inner.get("text", message.get("request_text", "")),
                    channel_id=inner.get("channel_id", ""),
                    ts=inner.get("ts"),
                    slack_event_id=slack_event_id,
                )
            except HTTPException as exc:
                fail_stuck_processing_claim(db, slack_event_id)
                if job_row:
                    mark_job_failed(db, job_row, error=str(exc.detail))
                raw = exc.detail
                msg = raw.get("detail", str(raw)) if isinstance(raw, dict) else str(raw)
                await _post_slack_user_message(
                    client,
                    recorder,
                    channel_id=inner.get("channel_id", ""),
                    event=inner.get("event") or {},
                    text=f"I couldn't process that request: {msg[:3500]}",
                )
                raise
            except Exception as exc:
                fail_stuck_processing_claim(db, slack_event_id)
                if job_row:
                    mark_job_failed(db, job_row, error=str(exc))
                raise

        if job_row:
            audit_id = body.get("audit_id")
            mark_job_completed(db, job_row, result=body, audit_log_id=audit_id)
        return body
    finally:
        db.close()


async def _run_chat_stream_job_async(message: dict) -> dict:
    import os

    import redis.asyncio as redis_async

    job_id = message["job_id"]
    user_id = message["user_id"]
    tenant_id = message["tenant_id"]
    inner = message.get("payload") or {}
    request_text = message.get("request_text", "")

    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        raise RuntimeError("REDIS_URL is required for chat stream jobs")

    redis = redis_async.from_url(redis_url, decode_responses=True)
    db = SessionLocal()
    job_row = None
    final_result = None
    try:
        from app.models import LLMJob

        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise ValueError(f"user {user_id} not found")

        job_row = db.query(LLMJob).filter(LLMJob.job_id == job_id).first()
        if job_row:
            mark_job_running(db, job_row)

        await set_stream_status(redis, job_id, "running")

        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0)) as client:
            async for evt in orchestrate_chat_stream(
                inner.get("message", request_text),
                source=inner.get("source", "api"),
                conversation_id=inner.get("conversation_id"),
                current_user=user,
                db=db,
                http_client=client,
            ):
                await append_stream_event(redis, job_id, evt)
                if evt.get("event") == "result":
                    final_result = evt

        await append_stream_event(redis, job_id, {"event": "stream_end"})
        await set_stream_status(redis, job_id, "completed")

        if final_result is None:
            raise ValueError("stream ended without result event")

        planner = final_result.get("planner_output") or {}
        audit_id = _save_chat_audit(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            request_text=request_text,
            result={k: v for k, v in final_result.items() if k != "event"},
        )
        if job_row:
            mark_job_completed(
                db,
                job_row,
                result={**{k: v for k, v in final_result.items() if k != "event"}, "audit_id": audit_id},
                audit_log_id=audit_id,
            )
        return {**{k: v for k, v in final_result.items() if k != "event"}, "audit_id": audit_id}
    except Exception as exc:
        await append_stream_event(redis, job_id, {"event": "error", "detail": str(exc)[:2000]})
        await append_stream_event(redis, job_id, {"event": "stream_end"})
        await set_stream_status(redis, job_id, "failed")
        if job_row:
            mark_job_failed(db, job_row, error=str(exc))
        raise
    finally:
        await redis.aclose()
        db.close()


def _run_chat_stream_job(message: dict) -> dict:
    return asyncio.run(_run_chat_stream_job_async(message))


def _run_daily_summary_job(message: dict) -> dict:
    job_id = message["job_id"]
    user_id = message["user_id"]
    db = SessionLocal()
    job_row = None
    try:
        from app.models import LLMJob

        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise ValueError(f"user {user_id} not found")

        job_row = db.query(LLMJob).filter(LLMJob.job_id == job_id).first()
        if job_row:
            mark_job_running(db, job_row)

        result = run_daily_summary_for_user(db, user)
        if job_row:
            mark_job_completed(db, job_row, result=result)
        return result
    except Exception as exc:
        if job_row:
            mark_job_failed(db, job_row, error=str(exc))
        raise
    finally:
        db.close()


def process_llm_job_message(message: dict) -> None:
    """Sync entrypoint for the RabbitMQ consumer."""
    job_type = message.get("job_type")
    logger.info("processing job_id=%s type=%s", message.get("job_id"), job_type)
    try:
        if job_type == JOB_CHAT_ORCHESTRATION:
            asyncio.run(_run_chat_job(message))
        elif job_type == JOB_CHAT_STREAM:
            _run_chat_stream_job(message)
        elif job_type == JOB_SLACK_ORCHESTRATION:
            asyncio.run(_run_slack_job(message))
        elif job_type == JOB_DAILY_SUMMARY:
            _run_daily_summary_job(message)
        else:
            raise ValueError(f"unsupported job_type '{job_type}'")
        logger.info("completed job_id=%s", message.get("job_id"))
    except Exception as exc:
        logger.exception("failed job_id=%s: %s", message.get("job_id"), exc)
        db = SessionLocal()
        try:
            from app.models import LLMJob

            job_row = db.query(LLMJob).filter(LLMJob.job_id == message.get("job_id")).first()
            if job_row and job_row.status not in {"completed", "failed"}:
                mark_job_failed(db, job_row, error=str(exc))
        finally:
            db.close()
        raise
