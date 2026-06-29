"""partner billing: api_keys balance/overrides, tasks.price_credits, billing_ledger

Revision ID: 0004_billing
Revises: 0003_mask_url
Create Date: 2026-06-29 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_billing"
down_revision: Union[str, None] = "0003_mask_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("balance_credits", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "api_keys",
        sa.Column("price_overrides", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column("tasks", sa.Column("price_credits", sa.Integer(), nullable=True))

    op.create_table(
        "billing_ledger",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("api_key_id", sa.String(length=32), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("task_id", sa.String(length=32), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("amount_credits", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "entry_type", name="uq_ledger_task_entry"),
    )
    op.create_index("ix_billing_ledger_api_key_id", "billing_ledger", ["api_key_id"])
    op.create_index("ix_billing_ledger_created_at", "billing_ledger", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_billing_ledger_created_at", table_name="billing_ledger")
    op.drop_index("ix_billing_ledger_api_key_id", table_name="billing_ledger")
    op.drop_table("billing_ledger")
    op.drop_column("tasks", "price_credits")
    op.drop_column("api_keys", "price_overrides")
    op.drop_column("api_keys", "balance_credits")
