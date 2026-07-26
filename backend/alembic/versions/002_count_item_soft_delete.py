"""Add soft-delete columns to count_items.

Operators had no way to undo a mis-dictated item — the ItemDeleted event
type/payload (app/schemas/events.py) existed from the start but nothing
ever emitted it, and count_items had no column to record the deletion on
the read-model side. count_items is already a mutable read-model (is_approved,
corrected_quantity etc. are updated in place) — CLAUDE.md 3.7's append-only
rule is specifically about the `events` table, not this one — so a soft-
delete flag here, paired with an ItemDeleted event for the audit trail, is
consistent with the existing pattern rather than a new one.

Revision ID: 002_count_item_soft_delete
Revises: 001_initial_schema
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_count_item_soft_delete"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "count_items",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="public",
    )
    op.add_column(
        "count_items",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.add_column(
        "count_items",
        sa.Column("deleted_by", sa.String(length=100), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("count_items", "deleted_by", schema="public")
    op.drop_column("count_items", "deleted_at", schema="public")
    op.drop_column("count_items", "is_deleted", schema="public")
