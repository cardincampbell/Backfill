"""add auto scheduler tables

Revision ID: 20260418_0022
Revises: 20260417_0021
Create Date: 2026-04-18 09:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260418_0022"
down_revision = "20260417_0021"
branch_labels = None
depends_on = None


schedule_run_type = postgresql.ENUM(
    "draft_generate",
    "replay",
    "shadow_compare",
    "publish_candidate",
    name="schedule_run_type",
)
schedule_run_status = postgresql.ENUM(
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="schedule_run_status",
)
schedule_apply_status = postgresql.ENUM(
    "queued",
    "applied",
    "stale_rejected",
    "failed",
    "no_op",
    name="schedule_apply_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    schedule_run_type.create(bind, checkfirst=True)
    schedule_run_status.create(bind, checkfirst=True)
    schedule_apply_status.create(bind, checkfirst=True)

    op.create_table(
        "schedule_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("planning_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planning_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "run_type",
            postgresql.ENUM(
                "draft_generate",
                "replay",
                "shadow_compare",
                "publish_candidate",
                name="schedule_run_type",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'draft_generate'"),
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
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
        sa.Column("optimizer_engine", sa.String(length=64), nullable=False, server_default=sa.text("'ortools_cp_sat_v1'")),
        sa.Column("objective_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("constraints_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("policy_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("input_snapshot_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("input_snapshot_hash", sa.String(length=255), nullable=False),
        sa.Column("run_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_runs"),
    )
    op.create_index("ix_schedule_runs_business_id_created_at", "schedule_runs", ["business_id", "created_at"], unique=False)
    op.create_index("ix_schedule_runs_location_id_created_at", "schedule_runs", ["location_id", "created_at"], unique=False)
    op.create_index("ix_schedule_runs_status_created_at", "schedule_runs", ["status", "created_at"], unique=False)

    op.create_table(
        "schedule_run_inputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("employee_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("availability_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("policy_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("labor_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reliability_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reliability_snapshot_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reliability_snapshot_hash", sa.String(length=255), nullable=True),
        sa.Column("reliability_snapshot_version", sa.String(length=64), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["schedule_run_id"], ["schedule_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_run_inputs"),
        sa.UniqueConstraint("schedule_run_id", name="uq_schedule_run_inputs_schedule_run_id"),
    )

    op.create_table(
        "schedule_run_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_score", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("decision_rank", sa.Integer(), nullable=False),
        sa.Column("assignment_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["schedule_run_id"], ["schedule_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_run_assignments"),
    )
    op.create_index(
        "ix_schedule_run_assignments_schedule_run_id_decision_rank",
        "schedule_run_assignments",
        ["schedule_run_id", "decision_rank"],
        unique=False,
    )

    op.create_table(
        "schedule_run_rejections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_rank", sa.Integer(), nullable=False),
        sa.Column("rejection_reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("score_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("constraint_failure_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["schedule_run_id"], ["schedule_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_run_rejections"),
    )
    op.create_index(
        "ix_schedule_run_rejections_schedule_run_id_candidate_rank",
        "schedule_run_rejections",
        ["schedule_run_id", "candidate_rank"],
        unique=False,
    )

    op.create_table(
        "schedule_run_explanations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("fairness_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("overtime_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("coverage_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("unassigned_shift_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["schedule_run_id"], ["schedule_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_run_explanations"),
        sa.UniqueConstraint("schedule_run_id", name="uq_schedule_run_explanations_schedule_run_id"),
    )

    op.create_table(
        "schedule_run_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("assigned_shift_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unassigned_shift_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("candidate_considered_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("overtime_assignment_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("fairness_spread_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("solver_runtime_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("objective_value", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["schedule_run_id"], ["schedule_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_run_metrics"),
        sa.UniqueConstraint("schedule_run_id", name="uq_schedule_run_metrics_schedule_run_id"),
    )

    op.create_table(
        "schedule_run_applies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("planning_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planning_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "queued",
                "applied",
                "stale_rejected",
                "failed",
                "no_op",
                name="schedule_apply_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("target_snapshot_hash", sa.String(length=255), nullable=False),
        sa.Column("current_snapshot_hash", sa.String(length=255), nullable=False),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("apply_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["schedule_run_id"], ["schedule_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_run_applies"),
    )
    op.create_index(
        "ix_schedule_run_applies_schedule_run_id_created_at",
        "schedule_run_applies",
        ["schedule_run_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_schedule_run_applies_status_created_at",
        "schedule_run_applies",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_run_applies_status_created_at", table_name="schedule_run_applies")
    op.drop_index("ix_schedule_run_applies_schedule_run_id_created_at", table_name="schedule_run_applies")
    op.drop_table("schedule_run_applies")

    op.drop_table("schedule_run_metrics")
    op.drop_table("schedule_run_explanations")

    op.drop_index("ix_schedule_run_rejections_schedule_run_id_candidate_rank", table_name="schedule_run_rejections")
    op.drop_table("schedule_run_rejections")

    op.drop_index("ix_schedule_run_assignments_schedule_run_id_decision_rank", table_name="schedule_run_assignments")
    op.drop_table("schedule_run_assignments")

    op.drop_table("schedule_run_inputs")

    op.drop_index("ix_schedule_runs_status_created_at", table_name="schedule_runs")
    op.drop_index("ix_schedule_runs_location_id_created_at", table_name="schedule_runs")
    op.drop_index("ix_schedule_runs_business_id_created_at", table_name="schedule_runs")
    op.drop_table("schedule_runs")

    bind = op.get_bind()
    schedule_apply_status.drop(bind, checkfirst=True)
    schedule_run_status.drop(bind, checkfirst=True)
    schedule_run_type.drop(bind, checkfirst=True)
