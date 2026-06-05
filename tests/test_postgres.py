"""Optional Postgres + Alembic smoke test (skipped unless POSTGRES_TEST_URL is set)."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL", "").strip(),
    reason="set POSTGRES_TEST_URL to run PostgreSQL integration tests",
)


@pytest.fixture(scope="module")
def postgres_engine():
    os.environ["DATABASE_URL"] = os.environ["POSTGRES_TEST_URL"]
    # Rebuild engine after URL change
    from importlib import reload

    import app.database as dbmod

    reload(dbmod)
    from app.database import init_db, engine

    init_db(engine)
    yield engine
    engine.dispose()


def test_postgres_task_crud(postgres_engine):
    from fastapi.testclient import TestClient
    from importlib import reload
    import app.main as mainmod

    reload(mainmod)
    from app.main import app

    with TestClient(app) as client:
        from tests.conftest import auth_headers

        headers = auth_headers(client, "pg-user@example.com", "secret123")
        from datetime import datetime, timedelta, timezone

        due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        created = client.post(
            "/tasks",
            headers=headers,
            json={
                "title": "Postgres task",
                "description": "via alembic",
                "due_date": due,
                "assignee": "assignee@example.com",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["title"] == "Postgres task"
        assert created.json()["assignee"] == "assignee@example.com"
