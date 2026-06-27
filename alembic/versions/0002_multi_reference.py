"""add reference_urls and driving_url to tasks (multi-character + motion)

Revision ID: 0002_multi_reference
Revises: 0001_initial
Create Date: 2026-01-02 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_multi_reference"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("reference_urls", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column("tasks", sa.Column("driving_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "driving_url")
    op.drop_column("tasks", "reference_urls")
