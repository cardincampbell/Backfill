"""add predictive demand contracts

Revision ID: 20260420_0025
Revises: 20260418_0024
Create Date: 2026-04-20 10:15:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260420_0025"
down_revision = "20260418_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_run_inputs",
        sa.Column(
            "fixed_shift_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "schedule_run_inputs",
        sa.Column(
            "generated_demand_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_table(
        "schedule_run_proposed_shifts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("applied_shift_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("demand_key", sa.String(length=255), nullable=False),
        sa.Column("optimizer_shift_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False, server_default=sa.text("'historical_pattern'")),
        sa.Column("generation_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("headcount", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("premium_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("requires_manager_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "generation_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["schedule_run_id"], ["schedule_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["applied_shift_id"], ["shifts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_run_proposed_shifts"),
        sa.UniqueConstraint("schedule_run_id", "demand_key", name="uq_schedule_run_proposed_shifts_run_demand_key"),
        sa.UniqueConstraint(
            "schedule_run_id",
            "optimizer_shift_id",
            name="uq_schedule_run_proposed_shifts_run_optimizer_shift_id",
        ),
    )
    op.create_index(
        "ix_schedule_run_proposed_shifts_schedule_run_id_starts_at",
        "schedule_run_proposed_shifts",
        ["schedule_run_id", "starts_at"],
        unique=False,
    )

    op.add_column(
        "schedule_run_assignments",
        sa.Column("proposed_shift_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_schedule_run_assignments_proposed_shift_id",
        "schedule_run_assignments",
        "schedule_run_proposed_shifts",
        ["proposed_shift_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "schedule_run_rejections",
        sa.Column("proposed_shift_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_schedule_run_rejections_proposed_shift_id",
        "schedule_run_rejections",
        "schedule_run_proposed_shifts",
        ["proposed_shift_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_schedule_run_rejections_proposed_shift_id",
        "schedule_run_rejections",
        type_="foreignkey",
    )
    op.drop_column("schedule_run_rejections", "proposed_shift_id")

    op.drop_constraint(
        "fk_schedule_run_assignments_proposed_shift_id",
        "schedule_run_assignments",
        type_="foreignkey",
    )
    op.drop_column("schedule_run_assignments", "proposed_shift_id")

    op.drop_index(
        "ix_schedule_run_proposed_shifts_schedule_run_id_starts_at",
        table_name="schedule_run_proposed_shifts",
    )
    op.drop_table("schedule_run_proposed_shifts")

    op.drop_column("schedule_run_inputs", "generated_demand_payload")
    op.drop_column("schedule_run_inputs", "fixed_shift_payload")
