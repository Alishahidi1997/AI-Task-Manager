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
        rows = conn.execute(text("PRAGMA table_info(tasks)")).fetchall()
        col_names = {r[1] for r in rows}
        if "category" not in col_names:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN category VARCHAR(64)"))
        if "completed_at" not in col_names:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN completed_at DATETIME"))

        # old demo used backend/frontend buckets — fold into daily-style labels
        conn.execute(
            text(
                "UPDATE tasks SET category = 'backlog' "
                "WHERE category IN ('backend','frontend','admin','general')"
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
