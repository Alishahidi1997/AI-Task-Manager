import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Task
from app.services.ai_summary import build_daily_summary
from app.services.category_guess import guess_category
from app.services.insights import build_weekly_retro

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("/daily")
def daily_summary(db: Session = Depends(get_db)):
    tasks = (
        db.query(Task).filter(Task.status == "done")
        .order_by(Task.id.desc()).limit(20).all()
    )

    try:
        text, mode = build_daily_summary(tasks)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail="openai returned an error: " + str(e.response.status_code),
        ) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail="summary failed: " + str(e)) from e
    return {
        "summary": text,
        "task_count": len(tasks),
        "mode": mode,
    }


@router.get("/weekly-retro")
def weekly_retro(db: Session = Depends(get_db)):
    done = db.query(Task).filter(Task.status == "done").order_by(Task.id.desc()).limit(400).all()
    open_tasks = db.query(Task).filter(Task.status != "done").order_by(Task.id.desc()).limit(400).all()
    return build_weekly_retro(done, open_tasks, guess_category)
