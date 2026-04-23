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
                "email VARCHAR(255) NOT NULL UNIQUE, "
                "password_hash VARCHAR(255) NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )

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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
