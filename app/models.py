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
    category = Column(String(64), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    user_id = Column(Integer, nullable=False, default=1)


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    summary_text = Column(Text, nullable=False)
    mode = Column(String(32), nullable=False, default="openai")
    task_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    is_error = Column(Integer, nullable=False, default=0)
    user_id = Column(Integer, nullable=False, default=1)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slack_user_id = Column(String(64), nullable=True, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(64), nullable=False, default="employee")
    tenant_id = Column(String(128), nullable=False, default="default")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class NextActionFeedback(Base):
    __tablename__ = "next_action_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    feedback_key = Column(String(255), nullable=False)
    action_type = Column(String(64), nullable=False)
    outcome = Column(String(32), nullable=False)  # accepted | dismissed | completed
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_text = Column(Text, nullable=False)
    tool_name = Column(String(64), nullable=True)
    arguments = Column(Text, nullable=True)
    validation_result = Column(String(32), nullable=False, default="unknown")
    execution_result = Column(String(32), nullable=False, default="unknown")
    user_id = Column(Integer, nullable=False, default=1)
    tenant_id = Column(String(128), nullable=False, default="default")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

