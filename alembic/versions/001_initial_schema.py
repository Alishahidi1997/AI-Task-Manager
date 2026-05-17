"""Initial schema from app.models (PostgreSQL / Alembic source of truth).

Revision ID: 001_initial
Revises:
Create Date: 2026-05-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slack_user_id", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=64), server_default="employee", nullable=False),
        sa.Column("tenant_id", sa.String(length=128), server_default="default", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("slack_user_id"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="todo", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "daily_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=32), server_default="openai", nullable=False),
        sa.Column("task_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_error", sa.Integer(), server_default="0", nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "next_action_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("feedback_key", sa.String(length=255), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_next_action_feedback_user_id", "next_action_feedback", ["user_id"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=True),
        sa.Column("arguments", sa.Text(), nullable=True),
        sa.Column("validation_result", sa.String(length=32), server_default="unknown", nullable=False),
        sa.Column("execution_result", sa.String(length=32), server_default="unknown", nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), server_default="default", nullable=False),
        sa.Column("slack_event_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slack_event_id"),
    )
    op.create_table(
        "llm_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), server_default="default", nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("channel", sa.String(length=32), server_default="api", nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("audit_log_id", sa.Integer(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_llm_jobs_user_id", "llm_jobs", ["user_id"])
    op.create_index("ix_llm_jobs_idempotency_key", "llm_jobs", ["idempotency_key"])
    op.create_table(
        "slack_orchestration_traces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("audit_log_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.String(length=128), server_default="default", nullable=False),
        sa.Column("slack_channel_id", sa.String(length=64), nullable=True),
        sa.Column("slack_message_ts", sa.String(length=32), nullable=True),
        sa.Column("slack_user_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("total_duration_ms", sa.Integer(), nullable=False),
        sa.Column("spans_json", sa.Text(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trace_id"),
    )
    op.create_index("ix_slack_orchestration_traces_trace_id", "slack_orchestration_traces", ["trace_id"])


def downgrade() -> None:
    op.drop_table("slack_orchestration_traces")
    op.drop_table("llm_jobs")
    op.drop_table("audit_logs")
    op.drop_table("next_action_feedback")
    op.drop_table("daily_summaries")
    op.drop_table("tasks")
    op.drop_table("users")
