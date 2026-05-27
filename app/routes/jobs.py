import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.deps import get_redis
from app.models import User
from app.queue.config import JOB_CHAT_STREAM
from app.services.chat_stream_buffer import iter_stream_events
from app.services.llm_jobs import get_llm_job, job_to_response

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}/stream")
async def stream_job_events(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    """SSE stream of planner tokens + result for queued chat_planner_stream jobs."""
    if redis is None:
        raise HTTPException(status_code=503, detail="REDIS_URL is required for job streaming")

    row = get_llm_job(db, job_id.strip(), user_id=current_user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    if row.job_type != JOB_CHAT_STREAM:
        raise HTTPException(status_code=400, detail="job is not a chat stream job")

    async def event_generator():
        async for evt in iter_stream_events(redis, job_id.strip()):
            yield f"data: {json.dumps(evt, default=str)}\n\n"
            if evt.get("event") in {"stream_end", "result", "error"}:
                if evt.get("event") == "result" and row.audit_log_id:
                    yield f"data: {json.dumps({'event': 'audit', 'audit_id': row.audit_log_id})}\n\n"
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{job_id}")
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Poll async LLM orchestration result (when RABBITMQ_URL + LLM queue enabled)."""
    row = get_llm_job(db, job_id.strip(), user_id=current_user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job_to_response(row)
