"""add v2 scheduler and retell tables

Revision ID: 20260402_0003
Revises: 20260402_0002
Create Date: 2026-04-02 16:25:00.000000
"""
from __future__ import annotations

from alembic import op

from app.models.integrations import (
    RetellConversation,
    SchedulerConnection,
    SchedulerEvent,
    SchedulerSyncJob,
    SchedulerSyncRun,
)


revision = "20260402_0003"
down_revision = "20260402_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SchedulerConnection.__table__.create(bind=bind)
    SchedulerEvent.__table__.create(bind=bind)
    SchedulerSyncJob.__table__.create(bind=bind)
    SchedulerSyncRun.__table__.create(bind=bind)
    RetellConversation.__table__.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    RetellConversation.__table__.drop(bind=bind)
    SchedulerSyncRun.__table__.drop(bind=bind)
    SchedulerSyncJob.__table__.drop(bind=bind)
    SchedulerEvent.__table__.drop(bind=bind)
    SchedulerConnection.__table__.drop(bind=bind)
