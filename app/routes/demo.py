from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Task, User
from app.services.demo_seed import (
    SCENARIOS,
    list_demo_scenarios,
    load_demo_scenario,
    reset_demo_dataset,
)
from app.services.persona_dashboard import build_persona_dashboard
from app.services.production import demo_mode_enabled

VALID_PERSONA_ROLES = frozenset({"manager", "analyst", "executive"})

router = APIRouter(prefix="/demo", tags=["demo"])

DEMO_EMAIL = "demo@smarttracker.local"


def _assert_demo_access(current_user: User):
    if not demo_mode_enabled():
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


@router.get("/personas/{role}/dashboard")
def get_persona_dashboard(
    role: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Role-aware dashboard over the demo user's task dataset (shared across personas)."""
    _assert_demo_access(current_user)
    key = role.strip().lower()
    if key not in VALID_PERSONA_ROLES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown persona role '{role}'",
        )
    tasks = (
        db.query(Task)
        .filter(Task.user_id == current_user.id)
        .order_by(Task.id.asc())
        .limit(3000)
        .all()
    )
    try:
        return build_persona_dashboard(key, tasks)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
