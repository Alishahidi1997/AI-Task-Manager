from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine, migrate_sqlite
from app.routes.insights import router as insights_router
from app.routes.summary import router as summary_router
from app.routes.tasks import router as tasks_router
from app.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # import models so sqlalchemy knows about the tables
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_sqlite(engine)
    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)
app.include_router(tasks_router)
app.include_router(summary_router)
app.include_router(insights_router)


@app.get("/")
def root():
    return {"status": "ok"}
