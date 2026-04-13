from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # import models so sqlalchemy knows about the tables
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
def root():
    return {"status": "ok"}
