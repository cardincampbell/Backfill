from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.events import PlatformEvent
from app.models.projections import FeedProjection
from app.services import feed_projections


class DummyProjectionSession:
    pass


def test_feed_read_from_projection_uses_source_event_id_not_projection_row_id():
    projection_row_id = uuid4()
    source_event_id = uuid4()
    business_id = uuid4()
    occurred_at = datetime(2026, 4, 10, 21, 0, tzinfo=timezone.utc)
    source_created_at = datetime(2026, 4, 10, 21, 1, tzinfo=timezone.utc)

    projection = FeedProjection(
        id=projection_row_id,
        source_event_id=source_event_id,
        projection_name="dashboard_activity_feed",
        business_id=business_id,
        location_id=None,
        schema_version=1,
        event_type="coverage.dispatch.executed",
        compatibility_event_name="coverage.dispatch.executed",
        entity_type="coverage_case",
        entity_id=uuid4(),
        actor_type="system",
        actor_user_id=None,
        actor_membership_id=None,
        trace_id="trace_projection_1",
        ip_address=None,
        user_agent=None,
        payload={"shift_id": "shift_123"},
        event_metadata={"channel": "worker"},
        error_message=None,
        occurred_at=occurred_at,
        source_created_at=source_created_at,
        projection_metadata={"source_table": "platform_events"},
    )

    result = feed_projections._feed_read_from_projection(projection)

    assert result.id == source_event_id
    assert result.id != projection_row_id
    assert result.trace_id == "trace_projection_1"


@pytest.mark.asyncio
async def test_list_feed_events_falls_back_to_raw_platform_events_when_projection_is_empty(monkeypatch):
    session = DummyProjectionSession()
    business_id = uuid4()
    location_id = uuid4()
    event_id = uuid4()
    occurred_at = datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc)
    created_at = datetime(2026, 4, 10, 18, 31, tzinfo=timezone.utc)

    async def fake_load_projected_rows(*args, **kwargs):
        return []

    async def fake_list_events(_session, **kwargs):
        assert kwargs["business_id"] == business_id
        assert kwargs["location_id"] == location_id
        return [
            PlatformEvent(
                id=event_id,
                business_id=business_id,
                location_id=location_id,
                schema_version=1,
                event_type="billing.fill.charged",
                compatibility_event_name="billing.fill.charged",
                entity_type="coverage_case",
                entity_id=uuid4(),
                actor_type="system",
                actor_user_id=None,
                actor_membership_id=None,
                trace_id="trace_123",
                ip_address=None,
                user_agent=None,
                payload={"amount_cents": 2000},
                event_metadata={"channel": "system"},
                error_message=None,
                occurred_at=occurred_at,
                created_at=created_at,
                updated_at=created_at,
            )
        ]

    monkeypatch.setattr(feed_projections, "_load_projected_rows", fake_load_projected_rows)
    monkeypatch.setattr(feed_projections.platform_events, "list_events", fake_list_events)

    result = await feed_projections.list_feed_events(
        session,
        business_id=business_id,
        location_id=location_id,
    )

    assert len(result) == 1
    assert result[0].id == event_id
    assert result[0].event_type == "billing.fill.charged"


@pytest.mark.asyncio
async def test_list_feed_events_merges_projected_rows_with_newer_raw_tail(monkeypatch):
    session = DummyProjectionSession()
    business_id = uuid4()
    projection_row_id = uuid4()
    source_event_id = uuid4()
    raw_event_id = uuid4()
    projected_occurred_at = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
    projected_created_at = datetime(2026, 4, 10, 18, 1, tzinfo=timezone.utc)
    raw_occurred_at = datetime(2026, 4, 10, 18, 5, tzinfo=timezone.utc)
    raw_created_at = datetime(2026, 4, 10, 18, 6, tzinfo=timezone.utc)

    projection_row = FeedProjection(
        id=projection_row_id,
        source_event_id=source_event_id,
        projection_name="dashboard_activity_feed",
        business_id=business_id,
        location_id=None,
        schema_version=1,
        event_type="coverage.phase_1.executed",
        compatibility_event_name="coverage.phase_1.executed",
        entity_type="coverage_case",
        entity_id=uuid4(),
        actor_type="system",
        actor_user_id=None,
        actor_membership_id=None,
        trace_id="trace_projection",
        ip_address=None,
        user_agent=None,
        payload={"phase": 1},
        event_metadata={"channel": "worker"},
        error_message=None,
        occurred_at=projected_occurred_at,
        source_created_at=projected_created_at,
        projection_metadata={"source_table": "platform_events"},
    )
    raw_event = PlatformEvent(
        id=raw_event_id,
        business_id=business_id,
        location_id=None,
        schema_version=1,
        event_type="coverage.dispatch.executed",
        compatibility_event_name="coverage.dispatch.executed",
        entity_type="coverage_case",
        entity_id=uuid4(),
        actor_type="system",
        actor_user_id=None,
        actor_membership_id=None,
        trace_id="trace_raw",
        ip_address=None,
        user_agent=None,
        payload={"dispatch": True},
        event_metadata={"channel": "worker"},
        error_message=None,
        occurred_at=raw_occurred_at,
        created_at=raw_created_at,
        updated_at=raw_created_at,
    )

    async def fake_load_projected_rows(*args, **kwargs):
        return [projection_row]

    async def fake_load_raw_tail_events(*args, **kwargs):
        return [raw_event]

    monkeypatch.setattr(feed_projections, "_load_projected_rows", fake_load_projected_rows)
    monkeypatch.setattr(feed_projections, "_load_raw_tail_events", fake_load_raw_tail_events)

    result = await feed_projections.list_feed_events(
        session,
        business_id=business_id,
    )

    assert [item.id for item in result] == [raw_event_id, source_event_id]


@pytest.mark.asyncio
async def test_process_feed_projection_batch_returns_busy_when_cursor_is_locked(monkeypatch):
    session = DummyProjectionSession()

    async def fake_claim_cursor(*args, **kwargs):
        return None

    monkeypatch.setattr(feed_projections, "_claim_projection_cursor", fake_claim_cursor)

    result = await feed_projections.process_feed_projection_batch(session, limit=15)

    assert result == {
        "projection_name": feed_projections.DEFAULT_FEED_PROJECTION_NAME,
        "status": "busy",
        "claimed": False,
        "cursor_status": "processing",
        "processed_count": 0,
        "processed_source_event_ids": [],
        "latest_source_event_id": None,
        "latest_source_created_at": None,
    }


@pytest.mark.asyncio
async def test_rebuild_feed_projection_returns_busy_when_cursor_is_locked(monkeypatch):
    session = DummyProjectionSession()

    async def fake_claim_cursor(*args, **kwargs):
        return None

    monkeypatch.setattr(feed_projections, "_claim_projection_cursor", fake_claim_cursor)

    result = await feed_projections.rebuild_feed_projection(session, limit=15)

    assert result == {
        "projection_name": feed_projections.DEFAULT_FEED_PROJECTION_NAME,
        "status": "busy",
        "claimed": False,
        "cursor_status": "processing",
        "deleted_count": 0,
        "processed_count": 0,
        "processed_source_event_ids": [],
        "latest_source_event_id": None,
        "latest_source_created_at": None,
    }
