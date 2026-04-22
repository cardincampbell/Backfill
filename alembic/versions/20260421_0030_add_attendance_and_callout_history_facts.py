"""add attendance and callout history facts

Revision ID: 20260421_0030
Revises: 20260421_0029
Create Date: 2026-04-21 15:05:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421_0030"
down_revision = "20260421_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance_history_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_system", sa.String(length=64), nullable=False, server_default=sa.text("'backfill_native'")),
        sa.Column("source_assignment_id", sa.String(length=255), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_hours", sa.Numeric(10, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("worked_hours", sa.Numeric(10, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("attendance_status", sa.String(length=32), nullable=False),
        sa.Column("late_minutes", sa.Integer(), nullable=True),
        sa.Column("left_early_minutes", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_attendance_history_facts"),
        sa.UniqueConstraint("source_system", "dedupe_key", name="uq_attendance_history_facts_source_system_dedupe_key"),
    )
    op.create_index(
        "ix_attendance_history_facts_location_role_starts_at",
        "attendance_history_facts",
        ["location_id", "role_id", "starts_at"],
        unique=False,
    )
    op.create_index(
        "ix_attendance_history_facts_employee_starts_at",
        "attendance_history_facts",
        ["employee_id", "starts_at"],
        unique=False,
    )

    op.create_table(
        "callout_history_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_system", sa.String(length=64), nullable=False, server_default=sa.text("'backfill_native'")),
        sa.Column("source_case_id", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shift_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shift_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notice_minutes", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("filled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fill_latency_minutes", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_callout_history_facts"),
        sa.UniqueConstraint("source_system", "dedupe_key", name="uq_callout_history_facts_source_system_dedupe_key"),
    )
    op.create_index(
        "ix_callout_history_facts_location_role_occurred_at",
        "callout_history_facts",
        ["location_id", "role_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_callout_history_facts_location_role_shift_starts_at",
        "callout_history_facts",
        ["location_id", "role_id", "shift_starts_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_callout_history_facts_location_role_shift_starts_at", table_name="callout_history_facts")
    op.drop_index("ix_callout_history_facts_location_role_occurred_at", table_name="callout_history_facts")
    op.drop_table("callout_history_facts")

    op.drop_index("ix_attendance_history_facts_employee_starts_at", table_name="attendance_history_facts")
    op.drop_index("ix_attendance_history_facts_location_role_starts_at", table_name="attendance_history_facts")
    op.drop_table("attendance_history_facts")
