"""add platform event notify trigger

Revision ID: 20260413_0016
Revises: 20260412_0015
Create Date: 2026-04-13 10:30:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "20260413_0016"
down_revision = "20260412_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION notify_backfill_platform_event() RETURNS trigger AS $$
        DECLARE
            payload json;
        BEGIN
            payload := json_build_object(
                'platform_event_id', NEW.id::text,
                'business_id', NEW.business_id::text,
                'location_id', CASE WHEN NEW.location_id IS NULL THEN NULL ELSE NEW.location_id::text END,
                'event_type', NEW.event_type,
                'entity_type', NEW.entity_type,
                'entity_id', CASE WHEN NEW.entity_id IS NULL THEN NULL ELSE NEW.entity_id::text END,
                'trace_id', NEW.trace_id,
                'occurred_at', NEW.occurred_at
            );
            PERFORM pg_notify('backfill_platform_events', payload::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS tr_notify_backfill_platform_event ON platform_events;
        CREATE TRIGGER tr_notify_backfill_platform_event
        AFTER INSERT ON platform_events
        FOR EACH ROW
        EXECUTE FUNCTION notify_backfill_platform_event();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tr_notify_backfill_platform_event ON platform_events;")
    op.execute("DROP FUNCTION IF EXISTS notify_backfill_platform_event();")
