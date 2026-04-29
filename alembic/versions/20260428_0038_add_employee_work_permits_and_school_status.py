"""add employee work permits and school status

Revision ID: 20260428_0038
Revises: 20260427_0037
Create Date: 2026-04-28 09:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260428_0038"
down_revision = "20260427_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("minor_school_status", sa.String(length=32), nullable=True))
    op.create_table(
        "employee_work_permits",
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("permit_number", sa.String(length=80), nullable=False),
        sa.Column("issuing_authority", sa.String(length=255), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("effective_start_date", sa.Date(), nullable=True),
        sa.Column("effective_end_date", sa.Date(), nullable=True),
        sa.Column(
            "permit_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employee_work_permits")),
        sa.UniqueConstraint(
            "employee_id",
            "permit_number",
            name="uq_employee_work_permits_employee_id_permit_number",
        ),
    )
    op.create_index(
        op.f("ix_employee_work_permits_employee_id"),
        "employee_work_permits",
        ["employee_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_employee_work_permits_effective_end_date"),
        "employee_work_permits",
        ["effective_end_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_employee_work_permits_effective_end_date"), table_name="employee_work_permits")
    op.drop_index(op.f("ix_employee_work_permits_employee_id"), table_name="employee_work_permits")
    op.drop_table("employee_work_permits")
    op.drop_column("employees", "minor_school_status")
