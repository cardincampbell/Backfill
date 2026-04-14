"""add employee schedule access links

Revision ID: 20260413_0017
Revises: 20260413_0016
Create Date: 2026-04-13 15:15:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260413_0017"
down_revision = "20260413_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_schedule_access_links",
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "link_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", name="uq_employee_schedule_access_links_employee_id"),
    )
    op.create_index(
        "ix_employee_schedule_access_links_business_id",
        "employee_schedule_access_links",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        "ix_employee_schedule_access_links_revoked_at",
        "employee_schedule_access_links",
        ["revoked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_employee_schedule_access_links_revoked_at", table_name="employee_schedule_access_links")
    op.drop_index("ix_employee_schedule_access_links_business_id", table_name="employee_schedule_access_links")
    op.drop_table("employee_schedule_access_links")
