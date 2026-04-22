"""add forecast provenance to proposed shifts

Revision ID: 20260420_0027
Revises: 20260420_0026
Create Date: 2026-04-20 16:05:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260420_0027"
down_revision = "20260420_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_run_proposed_shifts",
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "schedule_run_proposed_shifts",
        sa.Column("source_point_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_srps_source_run",
        "schedule_run_proposed_shifts",
        "labor_forecast_runs",
        ["source_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_srps_source_point",
        "schedule_run_proposed_shifts",
        "labor_forecast_points",
        ["source_point_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_srps_source_point",
        "schedule_run_proposed_shifts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_srps_source_run",
        "schedule_run_proposed_shifts",
        type_="foreignkey",
    )
    op.drop_column("schedule_run_proposed_shifts", "source_point_id")
    op.drop_column("schedule_run_proposed_shifts", "source_run_id")
