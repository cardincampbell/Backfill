"""add phase 0 versioning and provider callback logs

Revision ID: 20260409_0009
Revises: 20260408_0008
Create Date: 2026-04-09 10:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260409_0009"
down_revision = "20260408_0008"
branch_labels = None
depends_on = None


def _column_names(inspector: Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _table_names(inspector: Inspector) -> set[str]:
    return set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "version" not in _column_names(inspector, "coverage_cases"):
        op.add_column(
            "coverage_cases",
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )

    inspector = sa.inspect(bind)
    if "version" not in _column_names(inspector, "shift_assignments"):
        op.add_column(
            "shift_assignments",
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )

    inspector = sa.inspect(bind)
    if "provider_callback_logs" not in _table_names(inspector):
        op.create_table(
            "provider_callback_logs",
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("route_key", sa.String(length=120), nullable=False),
            sa.Column("event_type", sa.String(length=120), nullable=True),
            sa.Column("provider_event_id", sa.String(length=255), nullable=True),
            sa.Column("dedupe_key", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'received'")),
            sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_callback_logs")),
            sa.UniqueConstraint("provider", "dedupe_key", name="uq_provider_callback_logs_provider_dedupe_key"),
        )
        op.create_index(
            "ix_provider_callback_logs_provider_received_at",
            "provider_callback_logs",
            ["provider", "received_at"],
            unique=False,
        )
        op.create_index(
            "ix_provider_callback_logs_status_received_at",
            "provider_callback_logs",
            ["status", "received_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "provider_callback_logs" in _table_names(inspector):
        if "ix_provider_callback_logs_status_received_at" in {index["name"] for index in inspector.get_indexes("provider_callback_logs")}:
            op.drop_index("ix_provider_callback_logs_status_received_at", table_name="provider_callback_logs")
        inspector = sa.inspect(bind)
        if "ix_provider_callback_logs_provider_received_at" in {index["name"] for index in inspector.get_indexes("provider_callback_logs")}:
            op.drop_index("ix_provider_callback_logs_provider_received_at", table_name="provider_callback_logs")
        op.drop_table("provider_callback_logs")

    inspector = sa.inspect(bind)
    if "version" in _column_names(inspector, "shift_assignments"):
        op.drop_column("shift_assignments", "version")

    inspector = sa.inspect(bind)
    if "version" in _column_names(inspector, "coverage_cases"):
        op.drop_column("coverage_cases", "version")
