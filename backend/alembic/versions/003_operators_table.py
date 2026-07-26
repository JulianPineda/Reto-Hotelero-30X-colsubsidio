"""Add operators table — real credential store with a role column.

Replaces the "any operator_id + non-empty pin works" login stopgap.
`role` ('operator' | 'supervisor') is the actual server-side security
boundary between the two modules, enforced via app/api/deps.py's
require_role dependency on every relevant endpoint — not just which
button the frontend happens to show.

Revision ID: 003_operators_table
Revises: 002_count_item_soft_delete
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_operators_table"
down_revision: Union[str, None] = "002_count_item_soft_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("operator_id", sa.String(length=100), nullable=False),
        sa.Column("pin_hash", sa.String(length=60), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('operator', 'supervisor')", name="ck_operators_role"),
        schema="public",
    )
    op.create_unique_constraint("uq_operators_operator_id", "operators", ["operator_id"], schema="public")


def downgrade() -> None:
    op.drop_table("operators", schema="public")
