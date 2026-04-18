"""add reliability and replay tables

Revision ID: 20260418_0023
Revises: 20260418_0022
Create Date: 2026-04-18 13:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260418_0023"
down_revision = "20260418_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reliability_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("event_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_reliability_events"),
    )
    op.create_index(
        "ix_reliability_events_business_id_occurred_at",
        "reliability_events",
        ["business_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_reliability_events_employee_id_occurred_at",
        "reliability_events",
        ["employee_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_reliability_events_event_type_occurred_at",
        "reliability_events",
        ["event_type", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "reliability_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False, server_default=sa.text("0")),
        sa.Column("attendance_score", sa.Numeric(precision=5, scale=4), nullable=False, server_default=sa.text("0.7000")),
        sa.Column("punctuality_score", sa.Numeric(precision=5, scale=4), nullable=False, server_default=sa.text("0.7000")),
        sa.Column("commitment_score", sa.Numeric(precision=5, scale=4), nullable=False, server_default=sa.text("0.7000")),
        sa.Column("response_behavior_score", sa.Numeric(precision=5, scale=4), nullable=False, server_default=sa.text("0.7000")),
        sa.Column("coverage_reliability_score", sa.Numeric(precision=5, scale=4), nullable=False, server_default=sa.text("0.7000")),
        sa.Column("overall_reliability_score", sa.Numeric(precision=5, scale=4), nullable=False, server_default=sa.text("0.7000")),
        sa.Column("snapshot_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("payload_hash", sa.String(length=255), nullable=False),
        sa.Column("snapshot_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_reliability_snapshots"),
    )
    op.create_index(
        "ix_reliability_snapshots_business_id_snapshot_at",
        "reliability_snapshots",
        ["business_id", "snapshot_at"],
        unique=False,
    )
    op.create_index(
        "ix_reliability_snapshots_employee_id_snapshot_at",
        "reliability_snapshots",
        ["employee_id", "snapshot_at"],
        unique=False,
    )

    op.create_table(
        "replay_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("planning_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planning_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "completed",
                "failed",
                "cancelled",
                name="schedule_run_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("comparison_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("target_snapshot_hash", sa.String(length=255), nullable=False),
        sa.Column("actual_snapshot_hash", sa.String(length=255), nullable=False),
        sa.Column("actual_assignment_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actual_outcome_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("replay_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["schedule_run_id"], ["schedule_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_replay_runs"),
    )
    op.create_index(
        "ix_replay_runs_schedule_run_id_created_at",
        "replay_runs",
        ["schedule_run_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_replay_runs_business_id_created_at",
        "replay_runs",
        ["business_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_replay_runs_status_created_at",
        "replay_runs",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_replay_runs_status_created_at", table_name="replay_runs")
    op.drop_index("ix_replay_runs_business_id_created_at", table_name="replay_runs")
    op.drop_index("ix_replay_runs_schedule_run_id_created_at", table_name="replay_runs")
    op.drop_table("replay_runs")

    op.drop_index("ix_reliability_snapshots_employee_id_snapshot_at", table_name="reliability_snapshots")
    op.drop_index("ix_reliability_snapshots_business_id_snapshot_at", table_name="reliability_snapshots")
    op.drop_table("reliability_snapshots")

    op.drop_index("ix_reliability_events_event_type_occurred_at", table_name="reliability_events")
    op.drop_index("ix_reliability_events_employee_id_occurred_at", table_name="reliability_events")
    op.drop_index("ix_reliability_events_business_id_occurred_at", table_name="reliability_events")
    op.drop_table("reliability_events")
