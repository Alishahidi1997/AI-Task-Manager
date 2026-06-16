"""Phase 4.1 — workspace display-name directory."""

from __future__ import annotations

from app.auth import hash_password
from app.database import SessionLocal
from app.models import User
from app.services.entity_resolution import apply_assignee_resolution
from app.services.user_directory import (
    effective_display_name,
    find_assignee_candidates,
    list_workspace_directory,
)
from tests.conftest import auth_headers


def test_effective_display_name_falls_back_to_email_local():
    user = User(email="ali@corp.com", password_hash="x")
    assert effective_display_name(user) == "ali"

    user.display_name = "Ali Shah"
    assert effective_display_name(user) == "Ali Shah"


def test_find_assignee_candidates_by_display_name():
    db = SessionLocal()
    try:
        db.add(
            User(
                email="ali@corp.com",
                password_hash=hash_password("secret123"),
                role="employee",
                tenant_id="corp",
                display_name="Ali",
            )
        )
        db.add(
            User(
                email="bob@corp.com",
                password_hash=hash_password("secret123"),
                role="employee",
                tenant_id="corp",
                display_name="Bob",
            )
        )
        db.commit()

        matches = find_assignee_candidates(db, "corp", "Ali")
        assert len(matches) == 1
        assert matches[0].email == "ali@corp.com"

        prefix = find_assignee_candidates(db, "corp", "al")
        assert len(prefix) == 1
        assert prefix[0].email == "ali@corp.com"
    finally:
        db.close()


def test_apply_assignee_resolution_uses_display_name():
    db = SessionLocal()
    try:
        db.add(
            User(
                email="dev@corp.com",
                password_hash=hash_password("secret123"),
                role="employee",
                tenant_id="corp",
                display_name="Devon",
            )
        )
        db.commit()

        args, question = apply_assignee_resolution(
            db,
            "corp",
            {"assignee": "Devon"},
            "assign to Devon",
        )
        assert question is None
        assert args["assignee"] == "dev@corp.com"
    finally:
        db.close()


def test_workspace_directory_endpoint(client):
    headers = auth_headers(client, "dir-mgr@corp.com", "secret123")
    db = SessionLocal()
    try:
        mgr = db.query(User).filter(User.email == "dir-mgr@corp.com").first()
        assert mgr is not None
        mgr.tenant_id = "corp-dir"
        mgr.role = "manager"
        db.add(
            User(
                email="teammate@corp.com",
                password_hash=hash_password("secret123"),
                role="employee",
                tenant_id="corp-dir",
                display_name="Teammate",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/workspace/directory", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "corp-dir"
    emails = {row["email"] for row in body["users"]}
    assert "teammate@corp.com" in emails
    teammate = next(row for row in body["users"] if row["email"] == "teammate@corp.com")
    assert teammate["display_name"] == "Teammate"


def test_list_workspace_directory_sorted_by_email():
    db = SessionLocal()
    try:
        db.add(
            User(
                email="zoe@corp.com",
                password_hash="x",
                role="employee",
                tenant_id="sort-corp",
                display_name="Zoe",
            )
        )
        db.add(
            User(
                email="amy@corp.com",
                password_hash="x",
                role="employee",
                tenant_id="sort-corp",
                display_name="Amy",
            )
        )
        db.commit()

        rows = list_workspace_directory(db, "sort-corp")
        assert [row["email"] for row in rows] == ["amy@corp.com", "zoe@corp.com"]
    finally:
        db.close()
