"""conversation_threads for Epic 2 ThreadManager

Revision ID: 002_threads
Revises: 001_initial
Create Date: 2026-05-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_threads"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_threads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_key", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("last_task_id", sa.Integer(), nullable=True),
        sa.Column("turns_json", sa.Text(), nullable=False),
        sa.Column("pending_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_key"),
    )
    op.create_index("ix_conversation_threads_user_id", "conversation_threads", ["user_id"])


def downgrade() -> None:
    op.drop_table("conversation_threads")
