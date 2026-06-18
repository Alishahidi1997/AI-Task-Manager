"""Shared fixtures: isolated SQLite DB, no scheduler, Slack signature skip for tests."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def test_environment(tmp_path_factory) -> Generator[None, None, None]:
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    db_path = tmp_path_factory.mktemp("db") / "pytest.sqlite3"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["DISABLE_SCHEDULER"] = "1"
    os.environ["JWT_SECRET_KEY"] = "pytest-jwt-secret"
    os.environ["SLACK_SKIP_SIGNATURE_VERIFY"] = "true"
    # Keep API tests on sync /chat unless a test opts in; do not strip RABBITMQ_URL
    # (CI sets it for test_rabbitmq_integration.py — popping caused KeyError in that job).
    os.environ["LLM_QUEUE_ENABLED"] = "false"
    if os.getenv("RUN_AI_LIVE", "").strip().lower() not in {"1", "true", "yes", "on"}:
        os.environ.pop("OPENAI_API_KEY", None)
    # Keep REDIS_URL for CI integration job (test_redis_integration.py).
    yield


@pytest.fixture(scope="session")
def client(test_environment: None) -> Generator[TestClient, None, None]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_tables(client: TestClient) -> Generator[None, None, None]:
    from app.database import SessionLocal
    from app.models import (
        AuditLog,
        ConversationThread,
        DailySummary,
        LLMJob,
        NextActionFeedback,
        SlackOrchestrationTrace,
        Task,
        User,
    )

    db = SessionLocal()
    try:
        db.query(ConversationThread).delete()
        db.query(LLMJob).delete()
        db.query(NextActionFeedback).delete()
        db.query(SlackOrchestrationTrace).delete()
        db.query(AuditLog).delete()
        db.query(DailySummary).delete()
        db.query(Task).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()
    yield


def auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def auth_headers_with_role(
    client: TestClient,
    email: str,
    password: str,
    *,
    role: str = "employee",
    tenant_id: str = "tenant-test",
) -> dict[str, str]:
    headers = auth_headers(client, email, password)
    from app.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None
        user.role = role
        user.tenant_id = tenant_id
        db.add(user)
        db.commit()
    finally:
        db.close()
    return headers
