"""add mask_url to tasks (image editing)

Revision ID: 0003_mask_url
Revises: 0002_multi_reference
Create Date: 2026-01-03 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_mask_url"
down_revision: Union[str, None] = "0002_multi_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("mask_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "mask_url")
