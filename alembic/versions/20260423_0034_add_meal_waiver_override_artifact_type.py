"""add meal waiver compliance override artifact type

Revision ID: 20260423_0034
Revises: 20260423_0033
Create Date: 2026-04-23 15:10:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "20260423_0034"
down_revision = "20260423_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE compliance_override_artifact_type ADD VALUE IF NOT EXISTS 'meal_waiver'")


def downgrade() -> None:
    # PostgreSQL enum value removal requires a full type rebuild; leave as a no-op.
    return None
