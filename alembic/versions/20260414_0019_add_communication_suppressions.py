"""add communication suppressions

Revision ID: 20260414_0019
Revises: 20260414_0018
Create Date: 2026-04-14 16:40:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260414_0019"
down_revision = "20260414_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "communication_suppressions",
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("destination", sa.String(length=320), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False, server_default="global"),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column(
            "suppressed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "suppression_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_communication_suppressions_destination",
        "communication_suppressions",
        ["channel", "destination"],
        unique=False,
    )
    op.create_index(
        "ix_communication_suppressions_revoked_at",
        "communication_suppressions",
        ["revoked_at"],
        unique=False,
    )
    op.create_index(
        "uq_communication_suppressions_active_destination",
        "communication_suppressions",
        ["channel", "destination", "scope"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_communication_suppressions_active_destination",
        table_name="communication_suppressions",
    )
    op.drop_index("ix_communication_suppressions_revoked_at", table_name="communication_suppressions")
    op.drop_index("ix_communication_suppressions_destination", table_name="communication_suppressions")
    op.drop_table("communication_suppressions")
