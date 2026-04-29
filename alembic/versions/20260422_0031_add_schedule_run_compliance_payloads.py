"""add schedule run compliance payloads

Revision ID: 20260422_0031
Revises: 20260421_0030
Create Date: 2026-04-22 09:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260422_0031"
down_revision = "20260421_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_run_inputs",
        sa.Column(
            "compliance_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "schedule_run_explanations",
        sa.Column(
            "compliance_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("schedule_run_explanations", "compliance_payload")
    op.drop_column("schedule_run_inputs", "compliance_payload")
