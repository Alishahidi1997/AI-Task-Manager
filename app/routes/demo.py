import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.demo_seed import (
    SCENARIOS,
    list_demo_scenarios,
    load_demo_scenario,
    reset_demo_dataset,
)

router = APIRouter(prefix="/demo", tags=["demo"])

DEMO_EMAIL = "demo@smarttracker.local"


def _assert_demo_access(current_user: User):
    demo_mode = os.getenv("DEMO_MODE", "false").strip().lower() == "true"
    if not demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="demo mode is disabled",
        )
    if current_user.email != DEMO_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only demo account can manage demo data",
        )


@router.get("/scenarios")
def get_demo_scenarios(current_user: User = Depends(get_current_user)):
    _assert_demo_access(current_user)
    return {"ok": True, "scenarios": list_demo_scenarios()}


@router.post("/load/{scenario_id}")
def load_demo_scenario_data(
    scenario_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _assert_demo_access(current_user)
    if scenario_id not in SCENARIOS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown demo scenario '{scenario_id}'",
        )

    result = load_demo_scenario(db, current_user, scenario_id)
    return {"ok": True, **result}


@router.post("/reset")
def reset_demo_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _assert_demo_access(current_user)
    result = reset_demo_dataset(db, current_user)
    return {"ok": True, **result}
