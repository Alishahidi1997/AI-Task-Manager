"""Demo mode defaults for local development."""

from __future__ import annotations

import pytest

from app.services.production import demo_mode_enabled


def test_demo_mode_enabled_by_default_in_dev(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert demo_mode_enabled() is True


def test_demo_mode_disabled_in_production(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    assert demo_mode_enabled() is False


def test_demo_mode_explicit_override(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEMO_MODE", "true")
    assert demo_mode_enabled() is True


def test_demo_routes_work_without_explicit_env(client, monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)

    from app.auth import hash_password
    from app.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "demo@smarttracker.local").first()
        if not user:
            user = User(
                email="demo@smarttracker.local",
                password_hash=hash_password("demo1234"),
                role="manager",
                tenant_id="default",
            )
            db.add(user)
            db.commit()
    finally:
        db.close()

    login = client.post(
        "/auth/login",
        json={"email": "demo@smarttracker.local", "password": "demo1234"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    scenarios = client.get("/demo/scenarios", headers=headers)
    assert scenarios.status_code == 200, scenarios.text
    assert scenarios.json()["scenarios"]
