from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.llm_jobs import get_llm_job, job_to_response

router = APIRouter(prefix="/jobs", tags=["jobs"])


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
