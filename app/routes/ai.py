from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.queue.config import llm_queue_enabled
from app.services.ai_agent import run_agent_command
from app.services.ai_parse import parse_task_text, plan_task_text
from app.services.llm_queue_enqueue import enqueue_ai_agent, enqueue_ai_parse, enqueue_ai_plan

router = APIRouter(prefix="/ai", tags=["ai"])


class ParseTaskIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=3, max_length=2000)
    timezone: str | None = Field(default=None, max_length=100)


class PlanTaskIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=3, max_length=3000)
    timezone: str | None = Field(default=None, max_length=100)
    horizon_days: int = Field(default=7, ge=1, le=30)


class AgentCommandIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=3, max_length=3000)
    timezone: str | None = Field(default=None, max_length=100)
    dry_run: bool = True


def _queued_response(job_id: str, *, label: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "status": "accepted",
            "job_id": job_id,
            "poll_url": f"/jobs/{job_id}",
            "message": f"{label} queued; poll GET /jobs/{{job_id}} for result.",
        },
    )


@router.post("/parse-task")
async def parse_task(
    payload: ParseTaskIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if llm_queue_enabled():
        try:
            job_id = await enqueue_ai_parse(
                db,
                user=current_user,
                text=payload.text,
                timezone=payload.timezone,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"could not enqueue parse job: {exc}",
            ) from exc
        return _queued_response(job_id, label="Task parse")

    return parse_task_text(payload.text, payload.timezone)


@router.post("/plan-task")
async def plan_task(
    payload: PlanTaskIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if llm_queue_enabled():
        try:
            job_id = await enqueue_ai_plan(
                db,
                user=current_user,
                text=payload.text,
                timezone=payload.timezone,
                horizon_days=payload.horizon_days,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"could not enqueue plan job: {exc}",
            ) from exc
        return _queued_response(job_id, label="Task plan")

    return plan_task_text(payload.text, payload.timezone, payload.horizon_days)


@router.post("/agent-command")
async def agent_command(
    payload: AgentCommandIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if llm_queue_enabled():
        try:
            job_id = await enqueue_ai_agent(
                db,
                user=current_user,
                query=payload.query,
                timezone=payload.timezone,
                dry_run=payload.dry_run,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"could not enqueue agent job: {exc}",
            ) from exc
        return _queued_response(job_id, label="Agent command")

    return run_agent_command(
        payload.query,
        current_user=current_user,
        db=db,
        timezone_name=payload.timezone,
        dry_run=payload.dry_run,
    )
