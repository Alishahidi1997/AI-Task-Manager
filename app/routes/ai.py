from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.auth import get_current_user
from app.models import User
from app.services.ai_parse import parse_task_text, plan_task_text

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


@router.post("/parse-task")
def parse_task(payload: ParseTaskIn, current_user: User = Depends(get_current_user)):
    _ = current_user
    return parse_task_text(payload.text, payload.timezone)


@router.post("/plan-task")
def plan_task(payload: PlanTaskIn, current_user: User = Depends(get_current_user)):
    _ = current_user
    return plan_task_text(payload.text, payload.timezone, payload.horizon_days)
