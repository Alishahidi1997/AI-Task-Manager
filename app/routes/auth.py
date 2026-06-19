from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models import User
from app.services.user_directory import serialize_user_profile

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        value = v.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("invalid email format")
        return value


class LoginIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        value = v.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("invalid email format")
        return value


class ProfilePatchIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str | None = Field(default=None, max_length=128)


class UserProfileOut(BaseModel):
    id: int
    email: str
    role: str
    tenant_id: str
    display_name: str


@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="email already exists")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": serialize_user_profile(user),
    }


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password")
    token = create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": serialize_user_profile(user),
    }


@router.get("/me", response_model=UserProfileOut)
def me(current_user: User = Depends(get_current_user)):
    return serialize_user_profile(current_user)


@router.patch("/me", response_model=UserProfileOut)
def update_me(
    payload: ProfilePatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if "display_name" in payload.model_fields_set:
        name = payload.display_name
        current_user.display_name = name.strip() if name and name.strip() else None
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
    return serialize_user_profile(current_user)
