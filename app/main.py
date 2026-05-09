from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import hash_password
from app.database import Base, SessionLocal, engine, migrate_sqlite
from app.models import Task, User
from app.routes.ai import router as ai_router
from app.routes.analytics import router as analytics_router
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.demo import router as demo_router
from app.routes.insights import router as insights_router
from app.routes.slack import router as slack_router
from app.routes.summary import router as summary_router
from app.routes.tasks import router as tasks_router
from app.services.category_guess import guess_category
from app.services.demo_seed import reset_demo_dataset
from app.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # import models so sqlalchemy knows about the tables
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_sqlite(engine)

    # Backfill legacy rows so smart grouping is stored on each task.
    db = SessionLocal()
    try:
        demo = db.query(User).filter(User.email == "demo@smarttracker.local").first()
        if not demo:
            demo = User(
                email="demo@smarttracker.local",
                password_hash=hash_password("demo1234"),
            )
            db.add(demo)
            db.commit()
            db.refresh(demo)

        # Ensure existing rows are owned by demo user after migration.
        orphan_tasks = db.query(Task).filter(Task.user_id.is_(None)).all()
        for task in orphan_tasks:
            task.user_id = demo.id

        uncategorized = db.query(Task).filter(Task.category.is_(None)).all()
        for task in uncategorized:
            task.category = guess_category(task.title, task.description or "", task.due_date)
        demo_task_count = db.query(Task).filter(Task.user_id == demo.id).count()
        if demo_task_count == 0:
            reset_demo_dataset(db, demo)

        if uncategorized or orphan_tasks:
            db.commit()
    finally:
        db.close()

    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(tasks_router)
app.include_router(summary_router)
app.include_router(insights_router)
app.include_router(auth_router)
app.include_router(demo_router)
app.include_router(ai_router)
app.include_router(analytics_router)
app.include_router(chat_router)
app.include_router(slack_router)


@app.get("/")
def root():
    return {"status": "ok"}
