"""create v2 core schema

Revision ID: 20260331_0001
Revises:
Create Date: 2026-03-31 18:30:00.000000
"""
from __future__ import annotations

from alembic import op

from app.db.base import Base
import app.models  # noqa: F401


# revision identifiers, used by Alembic.
revision = "20260331_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
