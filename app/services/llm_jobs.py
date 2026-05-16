"""Persisted LLM / orchestration job records for queue workers and polling."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import LLMJob, utcnow


def _new_job_id() -> str:
    return str(uuid.uuid4())


def create_llm_job(
    db: Session,
    *,
    job_type: str,
    user_id: int,
    tenant_id: str,
    request_text: str,
    channel: str,
    payload: dict,
    idempotency_key: str | None = None,
) -> LLMJob:
    row = LLMJob(
        job_id=_new_job_id(),
        job_type=job_type,
        status="pending",
        user_id=user_id,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        channel=channel,
        request_text=request_text,
        payload_json=json.dumps(payload, ensure_ascii=True),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_llm_job(db: Session, job_id: str, *, user_id: int | None = None) -> LLMJob | None:
    q = db.query(LLMJob).filter(LLMJob.job_id == job_id)
    if user_id is not None:
        q = q.filter(LLMJob.user_id == user_id)
    return q.first()


def mark_job_running(db: Session, row: LLMJob) -> None:
    row.status = "running"
    row.updated_at = utcnow()
    db.add(row)
    db.commit()


def mark_job_completed(
    db: Session,
    row: LLMJob,
    *,
    result: dict,
    audit_log_id: int | None = None,
) -> None:
    row.status = "completed"
    row.result_json = json.dumps(result, ensure_ascii=True, default=str)
    row.audit_log_id = audit_log_id
    row.error_text = None
    row.updated_at = utcnow()
    db.add(row)
    db.commit()


def mark_job_failed(db: Session, row: LLMJob, *, error: str, result: dict | None = None) -> None:
    row.status = "failed"
    row.error_text = error[:4000]
    if result is not None:
        row.result_json = json.dumps(result, ensure_ascii=True, default=str)
    row.updated_at = utcnow()
    db.add(row)
    db.commit()


def job_to_response(row: LLMJob) -> dict:
    result = None
    if row.result_json:
        try:
            result = json.loads(row.result_json)
        except json.JSONDecodeError:
            result = {"raw": row.result_json}
    return {
        "job_id": row.job_id,
        "job_type": row.job_type,
        "status": row.status,
        "channel": row.channel,
        "request_text": row.request_text,
        "user_id": row.user_id,
        "tenant_id": row.tenant_id,
        "audit_log_id": row.audit_log_id,
        "error": row.error_text,
        "result": result,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def build_queue_message(row: LLMJob) -> dict:
    payload = json.loads(row.payload_json) if row.payload_json else {}
    return {
        "job_id": row.job_id,
        "job_type": row.job_type,
        "user_id": row.user_id,
        "tenant_id": row.tenant_id,
        "idempotency_key": row.idempotency_key,
        "channel": row.channel,
        "request_text": row.request_text,
        "payload": payload,
    }
