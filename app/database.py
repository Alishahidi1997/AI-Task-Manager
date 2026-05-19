import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# sqlite file lives next to requirements.txt (repo root)
ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "db.sqlite3"

_env_url = os.getenv("DATABASE_URL", "").strip()
DATABASE_URL = _env_url if _env_url else f"sqlite:///{DB_FILE.as_posix()}"


class Base(DeclarativeBase):
    pass


def is_sqlite() -> bool:
    return DATABASE_URL.startswith("sqlite")


def is_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql")


def _engine_kwargs() -> dict:
    kwargs: dict = {}
    if is_sqlite():
        kwargs["connect_args"] = {"check_same_thread": False}
    elif is_postgres():
        kwargs["pool_pre_ping"] = True
    return kwargs


engine = create_engine(DATABASE_URL, **_engine_kwargs())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def run_alembic_upgrade() -> None:
    """Apply Alembic migrations (PostgreSQL and any env using Alembic as source of truth)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(cfg, "head")


def migrate_sqlite(bind: Engine) -> None:
    """Legacy SQLite bootstrap — add missing columns on existing dev DBs."""
    if not str(bind.url).startswith("sqlite"):
        return
    with bind.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS users ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "slack_user_id VARCHAR(64), "
                "email VARCHAR(255) NOT NULL UNIQUE, "
                "password_hash VARCHAR(255) NOT NULL, "
                "role VARCHAR(64) NOT NULL DEFAULT 'employee', "
                "tenant_id VARCHAR(128) NOT NULL DEFAULT 'default', "
                "created_at DATETIME NOT NULL)"
            )
        )
        user_rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
        user_cols = {r[1] for r in user_rows}
        if "slack_user_id" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN slack_user_id VARCHAR(64)"))
        if "role" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(64)"))
            conn.execute(text("UPDATE users SET role = 'employee' WHERE role IS NULL OR role = ''"))
        if "tenant_id" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN tenant_id VARCHAR(128)"))
            conn.execute(text("UPDATE users SET tenant_id = 'default' WHERE tenant_id IS NULL OR tenant_id = ''"))

        rows = conn.execute(text("PRAGMA table_info(tasks)")).fetchall()
        col_names = {r[1] for r in rows}
        if "category" not in col_names:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN category VARCHAR(64)"))
        if "completed_at" not in col_names:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN completed_at DATETIME"))
        if "user_id" not in col_names:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN user_id INTEGER"))
            conn.execute(text("UPDATE tasks SET user_id = 1 WHERE user_id IS NULL"))

        conn.execute(
            text(
                "UPDATE tasks SET category = 'backlog' "
                "WHERE category IN ('backend','frontend','admin','general')"
            )
        )

        summary_rows = conn.execute(text("PRAGMA table_info(daily_summaries)")).fetchall()
        summary_col_names = {r[1] for r in summary_rows}
        if "user_id" not in summary_col_names:
            conn.execute(text("ALTER TABLE daily_summaries ADD COLUMN user_id INTEGER"))
            conn.execute(text("UPDATE daily_summaries SET user_id = 1 WHERE user_id IS NULL"))

        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS next_action_feedback ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id INTEGER NOT NULL, "
                "feedback_key VARCHAR(255) NOT NULL, "
                "action_type VARCHAR(64) NOT NULL, "
                "outcome VARCHAR(32) NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )

        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS audit_logs ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "request_text TEXT NOT NULL, "
                "tool_name VARCHAR(64), "
                "arguments TEXT, "
                "validation_result VARCHAR(32) NOT NULL, "
                "execution_result VARCHAR(32) NOT NULL, "
                "user_id INTEGER NOT NULL, "
                "tenant_id VARCHAR(128) NOT NULL, "
                "slack_event_id VARCHAR(128), "
                "created_at DATETIME NOT NULL)"
            )
        )
        audit_rows = conn.execute(text("PRAGMA table_info(audit_logs)")).fetchall()
        audit_cols = {r[1] for r in audit_rows}
        if "slack_event_id" not in audit_cols:
            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN slack_event_id VARCHAR(128)"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_audit_logs_slack_event_id "
                "ON audit_logs (slack_event_id) WHERE slack_event_id IS NOT NULL"
            )
        )

        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS conversation_threads ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "thread_key VARCHAR(255) NOT NULL UNIQUE, "
                "user_id INTEGER NOT NULL, "
                "last_task_id INTEGER, "
                "turns_json TEXT NOT NULL, "
                "pending_json TEXT, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL)"
            )
        )

        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS llm_jobs ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "job_id VARCHAR(36) NOT NULL UNIQUE, "
                "job_type VARCHAR(64) NOT NULL, "
                "status VARCHAR(32) NOT NULL, "
                "user_id INTEGER NOT NULL, "
                "tenant_id VARCHAR(128) NOT NULL, "
                "idempotency_key VARCHAR(255), "
                "channel VARCHAR(32) NOT NULL, "
                "request_text TEXT NOT NULL, "
                "payload_json TEXT NOT NULL, "
                "result_json TEXT, "
                "audit_log_id INTEGER, "
                "error_text TEXT, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL)"
            )
        )

        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS slack_orchestration_traces ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "trace_id VARCHAR(36) NOT NULL UNIQUE, "
                "audit_log_id INTEGER, "
                "user_id INTEGER, "
                "tenant_id VARCHAR(128) NOT NULL, "
                "slack_channel_id VARCHAR(64), "
                "slack_message_ts VARCHAR(32), "
                "slack_user_id VARCHAR(64), "
                "outcome VARCHAR(64) NOT NULL, "
                "total_duration_ms INTEGER NOT NULL, "
                "spans_json TEXT NOT NULL, "
                "metrics_json TEXT, "
                "created_at DATETIME NOT NULL)"
            )
        )


def init_db(bind: Engine | None = None) -> None:
    """
    SQLite: metadata.create_all + legacy migrate_sqlite (local dev compatibility).
    PostgreSQL: Alembic upgrade head (schema from app.models).
    """
    from app import models  # noqa: F401

    db_engine = bind or engine
    if is_postgres():
        run_alembic_upgrade()
        return
    Base.metadata.create_all(bind=db_engine)
    migrate_sqlite(db_engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
