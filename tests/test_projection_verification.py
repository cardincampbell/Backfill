from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.models.events import PlatformEvent
from app.models.projections import FeedProjection, ProjectionCursor
from app.services import feed_projections


@pytest.mark.asyncio
async def test_rebuild_feed_projection_from_empty_state(postgres_sessionmaker):
    sessionmaker = postgres_sessionmaker
    projection_name = f"verification_feed_test_{uuid4()}"
    business_id = uuid4()
    created_at = datetime.now(timezone.utc)
    event_ids = []

    try:
        async with sessionmaker() as setup_session:
            # 1. Create platform events
            for i in range(5):
                event = PlatformEvent(
                    business_id=business_id,
                    location_id=None,
                    schema_version=1,
                    event_type=f"test.event.{i}",
                    compatibility_event_name=f"test.event.{i}",
                    entity_type="test_entity",
                    entity_id=uuid4(),
                    actor_type="system",
                    actor_user_id=None,
                    actor_membership_id=None,
                    trace_id=f"trace_{uuid4().hex}",
                    ip_address=None,
                    user_agent=None,
                    payload={"i": i},
                    event_metadata={"test": True},
                    error_message=None,
                    occurred_at=created_at + timedelta(seconds=i),
                    created_at=created_at + timedelta(seconds=i),
                    updated_at=created_at + timedelta(seconds=i),
                )
                setup_session.add(event)
                await setup_session.flush()
                event_ids.append(event.id)
            await setup_session.commit()

        async with sessionmaker() as process_session:
            # 2. Rebuild the projection
            result = await feed_projections.rebuild_feed_projection(
                process_session,
                projection_name=projection_name,
                limit=10,
            )

        assert result["status"] == "processed"
        assert result["processed_count"] == 5
        assert len(result["processed_source_event_ids"]) == 5

        async with sessionmaker() as read_session:
            # 3. Verify feed_projections table
            projections = (
                (
                    await read_session.execute(
                        select(FeedProjection).where(FeedProjection.projection_name == projection_name)
                    )
                )
                .scalars()
                .all()
            )
            assert len(projections) == 5
            assert {p.source_event_id for p in projections} == set(event_ids)

            # 4. Verify ProjectionCursor
            cursor = await read_session.scalar(
                select(ProjectionCursor).where(ProjectionCursor.projection_name == projection_name)
            )
            assert cursor is not None
            assert cursor.last_source_event_id == event_ids[-1]
            assert cursor.cursor_status == "idle"

    finally:
        async with sessionmaker() as cleanup_session:
            await cleanup_session.execute(
                delete(FeedProjection).where(FeedProjection.projection_name == projection_name)
            )
            await cleanup_session.execute(
                delete(ProjectionCursor).where(ProjectionCursor.projection_name == projection_name)
            )
            if event_ids:
                await cleanup_session.execute(delete(PlatformEvent).where(PlatformEvent.id.in_(event_ids)))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_process_feed_projection_in_multiple_batches(postgres_sessionmaker):
    sessionmaker = postgres_sessionmaker
    projection_name = f"verification_feed_test_{uuid4()}"
    business_id = uuid4()
    created_at = datetime.now(timezone.utc)
    event_ids = []

    try:
        async with sessionmaker() as setup_session:
            # 1. Create platform events
            for i in range(15):
                event = PlatformEvent(
                    business_id=business_id,
                    location_id=None,
                    schema_version=1,
                    event_type=f"test.event.{i}",
                    compatibility_event_name=f"test.event.{i}",
                    entity_type="test_entity",
                    entity_id=uuid4(),
                    actor_type="system",
                    actor_user_id=None,
                    actor_membership_id=None,
                    trace_id=f"trace_{uuid4().hex}",
                    ip_address=None,
                    user_agent=None,
                    payload={"i": i},
                    event_metadata={"test": True},
                    error_message=None,
                    occurred_at=created_at + timedelta(seconds=i),
                    created_at=created_at + timedelta(seconds=i),
                    updated_at=created_at + timedelta(seconds=i),
                )
                setup_session.add(event)
                await setup_session.flush()
                event_ids.append(event.id)
            await setup_session.commit()

        # 2. Process events in multiple batches
        for i in range(3):
            async with sessionmaker() as process_session:
                result = await feed_projections.process_feed_projection_batch(
                    process_session,
                    projection_name=projection_name,
                    limit=5,
                )
                assert result["processed_count"] == 5

            async with sessionmaker() as read_session:
                # 3. Verify feed_projections table
                projections = (
                    (
                        await read_session.execute(
                            select(FeedProjection).where(FeedProjection.projection_name == projection_name)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(projections) == (i + 1) * 5

                # 4. Verify ProjectionCursor
                cursor = await read_session.scalar(
                    select(ProjectionCursor).where(ProjectionCursor.projection_name == projection_name)
                )
                assert cursor is not None
                assert cursor.last_source_event_id == event_ids[((i + 1) * 5) - 1]
                assert cursor.cursor_status == "idle"

    finally:
        async with sessionmaker() as cleanup_session:
            await cleanup_session.execute(
                delete(FeedProjection).where(FeedProjection.projection_name == projection_name)
            )
            await cleanup_session.execute(
                delete(ProjectionCursor).where(ProjectionCursor.projection_name == projection_name)
            )
            if event_ids:
                await cleanup_session.execute(delete(PlatformEvent).where(PlatformEvent.id.in_(event_ids)))
            await cleanup_session.commit()



@pytest.mark.asyncio
async def test_projection_cursor_catch_up(postgres_sessionmaker):
    sessionmaker = postgres_sessionmaker
    projection_name = f"verification_feed_test_{uuid4()}"
    business_id = uuid4()
    created_at = datetime.now(timezone.utc)
    event_ids = []

    try:
        async with sessionmaker() as setup_session:
            # 1. Create first batch of platform events
            for i in range(5):
                event = PlatformEvent(
                    business_id=business_id,
                    location_id=None,
                    schema_version=1,
                    event_type=f"test.event.{i}",
                    compatibility_event_name=f"test.event.{i}",
                    entity_type="test_entity",
                    entity_id=uuid4(),
                    actor_type="system",
                    actor_user_id=None,
                    actor_membership_id=None,
                    trace_id=f"trace_{uuid4().hex}",
                    ip_address=None,
                    user_agent=None,
                    payload={"i": i},
                    event_metadata={"test": True},
                    error_message=None,
                    occurred_at=created_at + timedelta(seconds=i),
                    created_at=created_at + timedelta(seconds=i),
                    updated_at=created_at + timedelta(seconds=i),
                )
                setup_session.add(event)
                await setup_session.flush()
                event_ids.append(event.id)
            await setup_session.commit()

        # 2. Process first batch
        async with sessionmaker() as process_session:
            result = await feed_projections.process_feed_projection_batch(
                process_session,
                projection_name=projection_name,
                limit=10,
            )
            assert result["processed_count"] == 5

        async with sessionmaker() as setup_session:
            # 3. Create second batch of platform events
            for i in range(5, 10):
                event = PlatformEvent(
                    business_id=business_id,
                    location_id=None,
                    schema_version=1,
                    event_type=f"test.event.{i}",
                    compatibility_event_name=f"test.event.{i}",
                    entity_type="test_entity",
                    entity_id=uuid4(),
                    actor_type="system",
                    actor_user_id=None,
                    actor_membership_id=None,
                    trace_id=f"trace_{uuid4().hex}",
                    ip_address=None,
                    user_agent=None,
                    payload={"i": i},
                    event_metadata={"test": True},
                    error_message=None,
                    occurred_at=created_at + timedelta(seconds=i),
                    created_at=created_at + timedelta(seconds=i),
                    updated_at=created_at + timedelta(seconds=i),
                )
                setup_session.add(event)
                await setup_session.flush()
                event_ids.append(event.id)
            await setup_session.commit()

        # 4. Process second batch
        async with sessionmaker() as process_session:
            result = await feed_projections.process_feed_projection_batch(
                process_session,
                projection_name=projection_name,
                limit=10,
            )
            assert result["processed_count"] == 5

        async with sessionmaker() as read_session:
            # 5. Verify feed_projections table
            projections = (
                (
                    await read_session.execute(
                        select(FeedProjection).where(FeedProjection.projection_name == projection_name)
                    )
                )
                .scalars()
                .all()
            )
            assert len(projections) == 10

            # 6. Verify ProjectionCursor
            cursor = await read_session.scalar(
                select(ProjectionCursor).where(ProjectionCursor.projection_name == projection_name)
            )
            assert cursor is not None
            assert cursor.last_source_event_id == event_ids[-1]
            assert cursor.cursor_status == "idle"

    finally:
        async with sessionmaker() as cleanup_session:
            await cleanup_session.execute(
                delete(FeedProjection).where(FeedProjection.projection_name == projection_name)
            )
            await cleanup_session.execute(
                delete(ProjectionCursor).where(ProjectionCursor.projection_name == projection_name)
            )
            if event_ids:
                await cleanup_session.execute(delete(PlatformEvent).where(PlatformEvent.id.in_(event_ids)))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_projection_vs_raw_parity(postgres_sessionmaker):
    sessionmaker = postgres_sessionmaker
    projection_name = f"verification_feed_test_{uuid4()}"
    business_id = uuid4()
    created_at = datetime.now(timezone.utc)
    event_ids = []

    try:
        async with sessionmaker() as setup_session:
            # 1. Create platform events
            for i in range(5):
                event = PlatformEvent(
                    business_id=business_id,
                    location_id=None,
                    schema_version=1,
                    event_type=f"test.event.{i}",
                    compatibility_event_name=f"test.event.{i}",
                    entity_type="test_entity",
                    entity_id=uuid4(),
                    actor_type="system",
                    actor_user_id=None,
                    actor_membership_id=None,
                    trace_id=f"trace_{uuid4().hex}",
                    ip_address=None,
                    user_agent=None,
                    payload={"i": i},
                    event_metadata={"test": True},
                    error_message=None,
                    occurred_at=created_at + timedelta(seconds=i),
                    created_at=created_at + timedelta(seconds=i),
                    updated_at=created_at + timedelta(seconds=i),
                )
                setup_session.add(event)
                await setup_session.flush()
                event_ids.append(event.id)
            await setup_session.commit()

        # 2. Process events
        async with sessionmaker() as process_session:
            result = await feed_projections.process_feed_projection_batch(
                process_session,
                projection_name=projection_name,
                limit=10,
            )
            assert result["processed_count"] == 5

        async with sessionmaker() as read_session:
            # 3. Read from both tables
            projections = (
                (
                    await read_session.execute(
                        select(FeedProjection)
                        .where(FeedProjection.projection_name == projection_name)
                        .order_by(FeedProjection.occurred_at)
                    )
                )
                .scalars()
                .all()
            )
            raw_events = (
                (
                    await read_session.execute(
                        select(PlatformEvent)
                        .where(PlatformEvent.id.in_(event_ids))
                        .order_by(PlatformEvent.occurred_at)
                    )
                )
                .scalars()
                .all()
            )

            # 4. Verify parity
            assert len(projections) == len(raw_events)
            for proj, raw in zip(projections, raw_events):
                assert proj.source_event_id == raw.id
                assert proj.business_id == raw.business_id
                assert proj.location_id == raw.location_id
                assert proj.schema_version == raw.schema_version
                assert proj.event_type == raw.event_type
                assert proj.compatibility_event_name == raw.compatibility_event_name
                assert proj.entity_type == raw.entity_type
                assert proj.entity_id == raw.entity_id
                assert proj.actor_type == raw.actor_type.value
                assert proj.actor_user_id == raw.actor_user_id
                assert proj.actor_membership_id == raw.actor_membership_id
                assert proj.trace_id == raw.trace_id
                assert proj.ip_address == raw.ip_address
                assert proj.user_agent == raw.user_agent
                assert proj.payload == raw.payload
                assert proj.event_metadata == raw.event_metadata
                assert proj.error_message == raw.error_message
                assert proj.occurred_at.strftime("%Y-%m-%d %H:%M:%S") == raw.occurred_at.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

    finally:
        async with sessionmaker() as cleanup_session:
            await cleanup_session.execute(
                delete(FeedProjection).where(FeedProjection.projection_name == projection_name)
            )
            await cleanup_session.execute(
                delete(ProjectionCursor).where(ProjectionCursor.projection_name == projection_name)
            )
            if event_ids:
                await cleanup_session.execute(delete(PlatformEvent).where(PlatformEvent.id.in_(event_ids)))
            await cleanup_session.commit()
