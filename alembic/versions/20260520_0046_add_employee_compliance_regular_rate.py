"""add employee compliance regular rate

Revision ID: 20260520_0046
Revises: 20260520_0045
Create Date: 2026-05-20 21:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260520_0046"
down_revision = "20260520_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("compliance_regular_rate_cents", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employees", "compliance_regular_rate_cents")
