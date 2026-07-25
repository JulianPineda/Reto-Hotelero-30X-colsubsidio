"""initial schema - 7 tablas (events, warehouses, catalog_items, count_sessions,
count_items, historical_counts, synonym_embeddings)

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "unaccent"')

    # --- events (append-only event store) ---------------------------------
    op.create_table(
        "events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("sequence_number", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        schema="public",
    )
    op.create_index("idx_events_aggregate", "events", ["aggregate_id", "sequence_number"], schema="public")
    op.create_index(
        "idx_events_type_time", "events", ["event_type", sa.text("occurred_at DESC")], schema="public"
    )
    op.create_index(
        "idx_events_warehouse", "events", ["warehouse_id", sa.text("occurred_at DESC")], schema="public"
    )

    # --- warehouses ---------------------------------------------------------
    op.create_table(
        "warehouses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("location", sa.String(200)),
        sa.Column("timezone", sa.String(50), server_default="America/Bogota"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="public",
    )

    # --- catalog_items --------------------------------------------------------
    op.create_table(
        "catalog_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("oracle_code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("subcategory", sa.String(100)),
        sa.Column("is_perishable", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("default_shelf_days", sa.Integer()),
        sa.Column("synonyms", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'")),
        sa.Column("qdrant_point_id", sa.String(100)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="public",
    )
    op.execute(
        "CREATE INDEX idx_catalog_ft ON public.catalog_items "
        "USING gin(to_tsvector('spanish', name))"
    )
    op.create_index("idx_catalog_active", "catalog_items", ["is_active", "category"], schema="public")

    # --- count_sessions ---------------------------------------------------
    op.create_table(
        "count_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.warehouses.id"),
            nullable=False,
        ),
        sa.Column("operator_id", sa.String(100), nullable=False),
        sa.Column("supervisor_id", sa.String(100)),
        sa.Column("shift", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="in_progress"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("exported_at", sa.DateTime(timezone=True)),
        sa.Column("export_path", sa.Text()),
        sa.Column("total_items", sa.Integer(), server_default=sa.text("0")),
        sa.Column("flagged_items", sa.Integer(), server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="public",
    )
    op.create_index(
        "idx_sessions_warehouse", "count_sessions", ["warehouse_id", sa.text("started_at DESC")], schema="public"
    )
    op.create_index(
        "idx_sessions_status", "count_sessions", ["status", sa.text("started_at DESC")], schema="public"
    )

    # --- count_items --------------------------------------------------------
    op.create_table(
        "count_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.count_sessions.id"),
            nullable=False,
        ),
        sa.Column(
            "catalog_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.catalog_items.id"),
        ),
        sa.Column("oracle_code", sa.String(50)),
        sa.Column("raw_transcript", sa.Text()),
        sa.Column("parsed_article", sa.String(300)),
        sa.Column("parsed_quantity", sa.Numeric(15, 4), nullable=False),
        sa.Column("parsed_unit", sa.String(30)),
        sa.Column("homologated_name", sa.String(300)),
        sa.Column("homologation_score", sa.Float()),
        sa.Column("sin_homologar", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("quantity_confirmed", sa.Numeric(15, 4)),
        sa.Column("unit_confirmed", sa.String(30)),
        sa.Column("is_flagged", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("flag_type", sa.String(50)),
        sa.Column("flag_reason", sa.Text()),
        sa.Column("is_approved", sa.Boolean()),
        sa.Column("approved_by", sa.String(100)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("corrected_quantity", sa.Numeric(15, 4)),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("traffic_light", sa.String(10)),
        sa.Column("is_offline", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("sequence_in_session", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="public",
    )
    op.create_index(
        "idx_items_session", "count_items", ["session_id", "sequence_in_session"], schema="public"
    )
    op.execute(
        "CREATE INDEX idx_items_flagged ON public.count_items (is_flagged, is_approved) "
        "WHERE is_flagged = TRUE"
    )
    op.create_index(
        "idx_items_catalog", "count_items", ["catalog_item_id", sa.text("created_at DESC")], schema="public"
    )

    # --- historical_counts (read model) -------------------------------------
    op.create_table(
        "historical_counts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.warehouses.id"),
            nullable=False,
        ),
        sa.Column(
            "catalog_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.catalog_items.id"),
            nullable=False,
        ),
        sa.Column("oracle_code", sa.String(50), nullable=False),
        sa.Column("count_date", sa.Date(), nullable=False),
        sa.Column("shift", sa.String(20)),
        sa.Column("quantity", sa.Numeric(15, 4), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.count_sessions.id"),
        ),
        sa.Column("is_validated", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="public",
    )
    op.create_index(
        "idx_hist_unique",
        "historical_counts",
        ["warehouse_id", "catalog_item_id", "count_date", "shift"],
        unique=True,
        schema="public",
    )
    op.create_index(
        "idx_hist_lookup",
        "historical_counts",
        ["warehouse_id", "catalog_item_id", sa.text("count_date DESC")],
        schema="public",
    )

    # --- synonym_embeddings --------------------------------------------------
    op.create_table(
        "synonym_embeddings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "catalog_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.catalog_items.id"),
            nullable=False,
        ),
        sa.Column("synonym", sa.String(300), nullable=False),
        sa.Column("qdrant_point_id", sa.String(100)),
        sa.Column("source", sa.String(50), server_default="operator_correction"),
        sa.Column("confidence", sa.Float(), server_default=sa.text("1.0")),
        sa.Column("usage_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("created_by", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("catalog_item_id", "synonym"),
        schema="public",
    )


def downgrade() -> None:
    op.drop_table("synonym_embeddings", schema="public")
    op.drop_table("historical_counts", schema="public")
    op.drop_table("count_items", schema="public")
    op.drop_table("count_sessions", schema="public")
    op.drop_table("catalog_items", schema="public")
    op.drop_table("warehouses", schema="public")
    op.drop_table("events", schema="public")
