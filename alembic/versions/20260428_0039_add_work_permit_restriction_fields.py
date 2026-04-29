"""add work permit restriction fields

Revision ID: 20260428_0039
Revises: 20260428_0038
Create Date: 2026-04-28 12:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0039"
down_revision = "20260428_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("work_permit_effective_start_on", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("work_permit_max_daily_minutes", sa.Integer(), nullable=True))
    op.add_column("employees", sa.Column("work_permit_max_weekly_minutes", sa.Integer(), nullable=True))
    op.add_column("employees", sa.Column("work_permit_earliest_start_local_time", sa.Time(), nullable=True))
    op.add_column("employees", sa.Column("work_permit_latest_end_local_time", sa.Time(), nullable=True))

    op.add_column("employee_work_permits", sa.Column("max_daily_minutes", sa.Integer(), nullable=True))
    op.add_column("employee_work_permits", sa.Column("max_weekly_minutes", sa.Integer(), nullable=True))
    op.add_column("employee_work_permits", sa.Column("earliest_start_local_time", sa.Time(), nullable=True))
    op.add_column("employee_work_permits", sa.Column("latest_end_local_time", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("employee_work_permits", "latest_end_local_time")
    op.drop_column("employee_work_permits", "earliest_start_local_time")
    op.drop_column("employee_work_permits", "max_weekly_minutes")
    op.drop_column("employee_work_permits", "max_daily_minutes")

    op.drop_column("employees", "work_permit_latest_end_local_time")
    op.drop_column("employees", "work_permit_earliest_start_local_time")
    op.drop_column("employees", "work_permit_max_weekly_minutes")
    op.drop_column("employees", "work_permit_max_daily_minutes")
    op.drop_column("employees", "work_permit_effective_start_on")
