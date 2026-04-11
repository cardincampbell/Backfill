from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.models.events import PlatformEvent
from app.models.projections import FeedProjection, ProjectionCursor
from app.services import feed_projections


@pytest.mark.asyncio
async def test_process_feed_projection_batch_round_trips_platform_events_to_feed_query(postgres_sessionmaker):
    sessionmaker = postgres_sessionmaker
    projection_name = f"dashboard_activity_feed_test_{uuid4()}"
    business_id = uuid4()
    location_id = uuid4()
    created_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    first_event_id = None
    second_event_id = None

    try:
        async with sessionmaker() as setup_session:
            latest_existing = await setup_session.scalar(
                select(PlatformEvent).order_by(PlatformEvent.created_at.desc(), PlatformEvent.id.desc()).limit(1)
            )
            if latest_existing is not None:
                setup_session.add(
                    ProjectionCursor(
                        projection_name=projection_name,
                        last_source_created_at=latest_existing.created_at,
                        last_source_event_id=latest_existing.id,
                        cursor_status="idle",
                        cursor_metadata={},
                    )
                )

            first_event = PlatformEvent(
                business_id=business_id,
                location_id=location_id,
                schema_version=1,
                event_type="coverage.phase_1.executed",
                compatibility_event_name="coverage.phase_1.executed",
                entity_type="coverage_case",
                entity_id=uuid4(),
                actor_type="system",
                actor_user_id=None,
                actor_membership_id=None,
                trace_id=f"trace_{uuid4().hex}",
                ip_address=None,
                user_agent=None,
                payload={"phase": 1},
                event_metadata={"channel": "worker"},
                error_message=None,
                occurred_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
            second_event = PlatformEvent(
                business_id=business_id,
                location_id=location_id,
                schema_version=1,
                event_type="coverage.dispatch.executed",
                compatibility_event_name="coverage.dispatch.executed",
                entity_type="coverage_case",
                entity_id=uuid4(),
                actor_type="system",
                actor_user_id=None,
                actor_membership_id=None,
                trace_id=f"trace_{uuid4().hex}",
                ip_address=None,
                user_agent=None,
                payload={"dispatch": True},
                event_metadata={"channel": "worker"},
                error_message=None,
                occurred_at=created_at + timedelta(seconds=5),
                created_at=created_at + timedelta(seconds=5),
                updated_at=created_at + timedelta(seconds=5),
            )
            setup_session.add_all([first_event, second_event])
            await setup_session.commit()
            first_event_id = first_event.id
            second_event_id = second_event.id

        async with sessionmaker() as process_session:
            result = await feed_projections.process_feed_projection_batch(
                process_session,
                limit=20,
                projection_name=projection_name,
            )

        assert str(first_event_id) in result["processed_source_event_ids"]
        assert str(second_event_id) in result["processed_source_event_ids"]

        async with sessionmaker() as read_session:
            rows = await feed_projections.list_feed_events(
                read_session,
                business_id=business_id,
                projection_name=projection_name,
                limit=20,
            )

        assert [item.id for item in rows] == [second_event_id, first_event_id]
    finally:
        async with sessionmaker() as cleanup_session:
            await cleanup_session.execute(
                delete(FeedProjection).where(FeedProjection.projection_name == projection_name)
            )
            await cleanup_session.execute(
                delete(ProjectionCursor).where(ProjectionCursor.projection_name == projection_name)
            )
            if first_event_id is not None and second_event_id is not None:
                await cleanup_session.execute(
                    delete(PlatformEvent).where(PlatformEvent.id.in_([first_event_id, second_event_id]))
                )
            await cleanup_session.commit()
