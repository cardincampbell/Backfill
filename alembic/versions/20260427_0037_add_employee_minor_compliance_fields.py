"""add employee minor compliance fields

Revision ID: 20260427_0037
Revises: 20260424_0036
Create Date: 2026-04-27 10:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260427_0037"
down_revision = "20260424_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("work_permit_number", sa.String(length=80), nullable=True))
    op.add_column("employees", sa.Column("work_permit_expires_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "work_permit_expires_on")
    op.drop_column("employees", "work_permit_number")
    op.drop_column("employees", "date_of_birth")
