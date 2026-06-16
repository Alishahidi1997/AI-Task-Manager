"""Add users.display_name for workspace directory (Phase 4.1).

Revision ID: 004_display_name
Revises: 003_assignee
Create Date: 2026-05-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_display_name"
down_revision: Union[str, None] = "003_assignee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")
