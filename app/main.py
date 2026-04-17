from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.routes.summary import router as summary_router
from app.routes.tasks import router as tasks_router
from app.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # import models so sqlalchemy knows about the tables
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)
app.include_router(tasks_router)
app.include_router(summary_router)


@app.get("/")
def root():
    return {"status": "ok"}
