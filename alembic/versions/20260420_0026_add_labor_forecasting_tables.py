"""add labor forecasting tables

Revision ID: 20260420_0026
Revises: 20260420_0025
Create Date: 2026-04-20 14:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260420_0026"
down_revision = "20260420_0025"
branch_labels = None
depends_on = None


labor_forecast_run_status_enum = postgresql.ENUM(
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="labor_forecast_run_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    labor_forecast_run_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "labor_forecast_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("planning_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planning_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_model_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("feature_snapshot_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "queued",
                "running",
                "completed",
                "failed",
                "cancelled",
                name="labor_forecast_run_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column(
            "forecast_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_labor_forecast_runs"),
    )
    op.create_index(
        "ix_labor_forecast_runs_business_id_created_at",
        "labor_forecast_runs",
        ["business_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_labor_forecast_runs_location_id_created_at",
        "labor_forecast_runs",
        ["location_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_labor_forecast_runs_status_created_at",
        "labor_forecast_runs",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "labor_forecast_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("labor_forecast_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("predicted_headcount", sa.Numeric(10, 4), nullable=False),
        sa.Column("predicted_labor_hours", sa.Numeric(10, 4), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "forecast_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["labor_forecast_run_id"], ["labor_forecast_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_labor_forecast_points"),
        sa.UniqueConstraint(
            "labor_forecast_run_id",
            "location_id",
            "role_id",
            "window_start",
            "window_end",
            name="uq_labor_forecast_points_run_location_role_window",
        ),
    )
    op.create_index(
        "ix_labor_forecast_points_run_id_window_start",
        "labor_forecast_points",
        ["labor_forecast_run_id", "window_start"],
        unique=False,
    )
    op.create_index(
        "ix_labor_forecast_points_location_role_window_start",
        "labor_forecast_points",
        ["location_id", "role_id", "window_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_labor_forecast_points_location_role_window_start",
        table_name="labor_forecast_points",
    )
    op.drop_index(
        "ix_labor_forecast_points_run_id_window_start",
        table_name="labor_forecast_points",
    )
    op.drop_table("labor_forecast_points")

    op.drop_index(
        "ix_labor_forecast_runs_status_created_at",
        table_name="labor_forecast_runs",
    )
    op.drop_index(
        "ix_labor_forecast_runs_location_id_created_at",
        table_name="labor_forecast_runs",
    )
    op.drop_index(
        "ix_labor_forecast_runs_business_id_created_at",
        table_name="labor_forecast_runs",
    )
    op.drop_table("labor_forecast_runs")

    labor_forecast_run_status_enum.drop(op.get_bind(), checkfirst=True)
