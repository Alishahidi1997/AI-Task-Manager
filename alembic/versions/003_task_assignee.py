"""Add tasks.assignee column (Phase 3.5).

Revision ID: 003_assignee
Revises: 002_threads
Create Date: 2026-05-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_assignee"
down_revision: Union[str, None] = "002_threads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("assignee", sa.String(length=255), nullable=True))
    op.create_index("ix_tasks_assignee", "tasks", ["assignee"])


def downgrade() -> None:
    op.drop_index("ix_tasks_assignee", table_name="tasks")
    op.drop_column("tasks", "assignee")
