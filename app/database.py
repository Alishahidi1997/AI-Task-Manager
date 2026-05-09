from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# sqlite file lives next to requirements.txt (repo root)
ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "db.sqlite3"

DATABASE_URL = f"sqlite:///{DB_FILE.as_posix()}"


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def migrate_sqlite(engine):
    # sqlite has no real migrations in this repo — add missing cols by hand
    with engine.begin() as conn:
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

        # old demo used backend/frontend buckets — fold into daily-style labels
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
                "created_at DATETIME NOT NULL)"
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
