"""add pos sales facts

Revision ID: 20260421_0029
Revises: 20260421_0028
Create Date: 2026-04-21 13:15:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421_0029"
down_revision = "20260421_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pos_sales_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_account_id", sa.String(length=255), nullable=True),
        sa.Column("provider_location_id", sa.String(length=255), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gross_sales_cents", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("net_sales_cents", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("order_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("guest_count", sa.Integer(), nullable=True),
        sa.Column("refund_count", sa.Integer(), nullable=True),
        sa.Column(
            "source_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_pos_sales_facts"),
        sa.UniqueConstraint("provider", "dedupe_key", name="uq_pos_sales_facts_provider_dedupe_key"),
    )
    op.create_index(
        "ix_pos_sales_facts_location_bucket_start",
        "pos_sales_facts",
        ["location_id", "bucket_start"],
        unique=False,
    )
    op.create_index(
        "ix_pos_sales_facts_location_observed_at",
        "pos_sales_facts",
        ["location_id", "observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_pos_sales_facts_provider_location_bucket_start",
        "pos_sales_facts",
        ["provider", "provider_location_id", "bucket_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pos_sales_facts_provider_location_bucket_start", table_name="pos_sales_facts")
    op.drop_index("ix_pos_sales_facts_location_observed_at", table_name="pos_sales_facts")
    op.drop_index("ix_pos_sales_facts_location_bucket_start", table_name="pos_sales_facts")
    op.drop_table("pos_sales_facts")
