from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, Column

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="todo")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    due_date = Column(DateTime(timezone=True), nullable=True)
