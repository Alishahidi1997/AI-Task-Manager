from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.user_directory import list_workspace_directory

router = APIRouter(prefix="/workspace", tags=["workspace"])


class DirectoryUser(BaseModel):
    id: int
    email: str
    display_name: str
    role: str


class WorkspaceDirectoryOut(BaseModel):
    tenant_id: str
    users: list[DirectoryUser]


@router.get("/directory", response_model=WorkspaceDirectoryOut)
def workspace_directory(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant_id = current_user.tenant_id or "default"
    return {
        "tenant_id": tenant_id,
        "users": list_workspace_directory(db, tenant_id),
    }
