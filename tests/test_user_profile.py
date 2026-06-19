"""Phase 4.3 — enriched user profile API."""

from __future__ import annotations

from app.auth import hash_password
from app.database import SessionLocal
from app.models import User
from tests.conftest import auth_headers, auth_headers_with_role


def test_me_returns_profile_fields(client):
    headers = auth_headers(client, "profile-me@corp.com", "secret123")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "profile-me@corp.com").first()
        assert user is not None
        user.display_name = "Profile User"
        user.role = "employee"
        user.tenant_id = "corp-profile"
        db.commit()
    finally:
        db.close()

    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "profile-me@corp.com"
    assert body["role"] == "employee"
    assert body["tenant_id"] == "corp-profile"
    assert body["display_name"] == "Profile User"


def test_patch_me_updates_display_name(client):
    headers = auth_headers(client, "profile-patch@corp.com", "secret123")

    response = client.patch(
        "/auth/me",
        headers=headers,
        json={"display_name": "Patched Name"},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Patched Name"

    me = client.get("/auth/me", headers=headers)
    assert me.json()["display_name"] == "Patched Name"


def test_patch_me_clear_display_name(client):
    headers = auth_headers(client, "profile-clear@corp.com", "secret123")
    client.patch("/auth/me", headers=headers, json={"display_name": "Temp"})
    response = client.patch("/auth/me", headers=headers, json={"display_name": ""})
    assert response.status_code == 200
    assert response.json()["display_name"] == "profile-clear"


def test_login_returns_profile(client):
    email = "profile-login@corp.com"
    client.post("/auth/register", json={"email": email, "password": "secret123"})
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        user.display_name = "Login Name"
        db.commit()
    finally:
        db.close()

    response = client.post("/auth/login", json={"email": email, "password": "secret123"})
    assert response.status_code == 200
    user = response.json()["user"]
    assert user["display_name"] == "Login Name"
    assert user["role"] == "employee"


def test_manager_sees_workspace_directory_for_assignee_picker(client):
    mgr_headers = auth_headers_with_role(
        client,
        "profile-mgr@corp.com",
        "secret123",
        role="manager",
        tenant_id="corp-picker",
    )
    db = SessionLocal()
    try:
        db.add(
            User(
                email="picker-dev@corp.com",
                password_hash=hash_password("secret123"),
                role="employee",
                tenant_id="corp-picker",
                display_name="Dev Pick",
            )
        )
        db.commit()
    finally:
        db.close()

    directory = client.get("/workspace/directory", headers=mgr_headers)
    assert directory.status_code == 200
    names = {row["display_name"] for row in directory.json()["users"]}
    assert "Dev Pick" in names
