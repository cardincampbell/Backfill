"""add v2 webhook subscriptions

Revision ID: 20260402_0002
Revises: 20260331_0001
Create Date: 2026-04-02 12:45:00.000000
"""
from __future__ import annotations

from alembic import op

from app_v2.models.webhooks import WebhookDelivery, WebhookSubscription


revision = "20260402_0002"
down_revision = "20260331_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    WebhookSubscription.__table__.create(bind=bind)
    WebhookDelivery.__table__.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    WebhookDelivery.__table__.drop(bind=bind)
    WebhookSubscription.__table__.drop(bind=bind)
