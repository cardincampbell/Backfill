from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import PlatformEvent
from app.models.projections import FeedProjection, ProjectionCursor
from app.schemas.events import PlatformEventRead
from app.services import platform_events

DEFAULT_FEED_PROJECTION_NAME = "dashboard_activity_feed"
_READ_CONTRACT_NAME = "PlatformEventRead"


@dataclass(frozen=True)
class _FeedReadItem:
    event: PlatformEventRead
    source_created_at: datetime


def _normalized_limit(limit: int, *, max_limit: int = 250) -> int:
    return max(1, min(limit, max_limit))


def _cursor_clause(
    *,
    created_at_column: Any,
    id_column: Any,
    last_source_created_at: datetime | None,
    last_source_event_id: UUID | None,
):
    if last_source_created_at is None or last_source_event_id is None:
        return None
    return or_(
        created_at_column > last_source_created_at,
        and_(
            created_at_column == last_source_created_at,
            id_column > last_source_event_id,
        ),
    )


def _feed_read_from_projection(row: FeedProjection) -> PlatformEventRead:
    return PlatformEventRead(
        id=row.source_event_id,
        business_id=row.business_id,
        location_id=row.location_id,
        schema_version=row.schema_version,
        event_type=row.event_type,
        compatibility_event_name=row.compatibility_event_name,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        actor_type=row.actor_type,
        actor_user_id=row.actor_user_id,
        actor_membership_id=row.actor_membership_id,
        trace_id=row.trace_id,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        payload=dict(row.payload or {}),
        event_metadata=dict(row.event_metadata or {}),
        error_message=row.error_message,
        occurred_at=row.occurred_at,
    )


def _feed_read_from_platform_event(row: PlatformEvent) -> PlatformEventRead:
    return PlatformEventRead(
        id=row.id,
        business_id=row.business_id,
        location_id=row.location_id,
        schema_version=row.schema_version,
        event_type=row.event_type,
        compatibility_event_name=row.compatibility_event_name,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        actor_type=row.actor_type,
        actor_user_id=row.actor_user_id,
        actor_membership_id=row.actor_membership_id,
        trace_id=row.trace_id,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        payload=dict(row.payload or {}),
        event_metadata=dict(row.event_metadata or {}),
        error_message=row.error_message,
        occurred_at=row.occurred_at,
    )


def _feed_item_sort_key(item: _FeedReadItem) -> tuple[datetime, datetime, str]:
    return (
        item.event.occurred_at,
        item.source_created_at,
        str(item.event.id),
    )


async def _ensure_projection_cursor(
    session: AsyncSession,
    *,
    projection_name: str,
) -> None:
    await session.execute(
        pg_insert(ProjectionCursor)
        .values(projection_name=projection_name)
        .on_conflict_do_nothing(index_elements=[ProjectionCursor.projection_name])
    )
    await session.flush()


async def _load_projection_cursor(
    session: AsyncSession,
    *,
    projection_name: str,
) -> ProjectionCursor | None:
    return await session.scalar(
        select(ProjectionCursor).where(ProjectionCursor.projection_name == projection_name)
    )


async def _lock_projection_cursor(
    session: AsyncSession,
    *,
    projection_name: str,
    skip_locked: bool,
) -> ProjectionCursor | None:
    result = await session.execute(
        select(ProjectionCursor)
        .where(ProjectionCursor.projection_name == projection_name)
        .with_for_update(skip_locked=skip_locked)
    )
    return result.scalar_one_or_none()


async def _claim_projection_cursor(
    session: AsyncSession,
    *,
    projection_name: str,
    now: datetime,
) -> ProjectionCursor | None:
    await _ensure_projection_cursor(session, projection_name=projection_name)
    cursor = await _lock_projection_cursor(
        session,
        projection_name=projection_name,
        skip_locked=True,
    )
    if cursor is None:
        return None
    cursor.cursor_status = "processing"
    cursor.last_run_started_at = now
    cursor.last_error = None
    await session.flush()
    return cursor


async def _mark_projection_cursor_failure(
    session: AsyncSession,
    *,
    projection_name: str,
    now: datetime,
    error_message: str,
) -> None:
    await _ensure_projection_cursor(session, projection_name=projection_name)
    cursor = await _lock_projection_cursor(
        session,
        projection_name=projection_name,
        skip_locked=False,
    )
    if cursor is None:
        return
    cursor.cursor_status = "failed"
    cursor.last_run_completed_at = now
    cursor.last_error = error_message.strip() or "feed_projection_failed"
    cursor.cursor_metadata = {
        **(cursor.cursor_metadata or {}),
        "last_failure_at": now.isoformat(),
    }
    await session.commit()


async def _list_projection_source_events(
    session: AsyncSession,
    *,
    cursor: ProjectionCursor,
    limit: int,
) -> list[PlatformEvent]:
    stmt = select(PlatformEvent).order_by(PlatformEvent.created_at.asc(), PlatformEvent.id.asc())
    clause = _cursor_clause(
        created_at_column=PlatformEvent.created_at,
        id_column=PlatformEvent.id,
        last_source_created_at=cursor.last_source_created_at,
        last_source_event_id=cursor.last_source_event_id,
    )
    if clause is not None:
        stmt = stmt.where(clause)
    stmt = stmt.limit(_normalized_limit(limit, max_limit=500))
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _projection_record(
    event: PlatformEvent,
    *,
    projection_name: str,
) -> dict[str, Any]:
    actor_type = getattr(event.actor_type, "value", event.actor_type)
    return {
        "id": uuid.uuid4(),
        "source_event_id": event.id,
        "projection_name": projection_name,
        "business_id": event.business_id,
        "location_id": event.location_id,
        "schema_version": event.schema_version,
        "event_type": event.event_type,
        "compatibility_event_name": event.compatibility_event_name,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "actor_type": str(actor_type),
        "actor_user_id": event.actor_user_id,
        "actor_membership_id": event.actor_membership_id,
        "trace_id": event.trace_id,
        "ip_address": event.ip_address,
        "user_agent": event.user_agent,
        "payload": dict(event.payload or {}),
        "metadata": dict(event.event_metadata or {}),
        "error_message": event.error_message,
        "occurred_at": event.occurred_at,
        "source_created_at": event.created_at,
        "projection_metadata": {
            "projection_contract": _READ_CONTRACT_NAME,
            "source_table": "platform_events",
        },
    }


async def _upsert_feed_projection_rows(
    session: AsyncSession,
    *,
    projection_name: str,
    events: list[PlatformEvent],
) -> None:
    if not events:
        return
    values = [
        _projection_record(event, projection_name=projection_name)
        for event in events
    ]
    insert_stmt = pg_insert(FeedProjection).values(values)
    await session.execute(
        insert_stmt.on_conflict_do_update(
            index_elements=[FeedProjection.projection_name, FeedProjection.source_event_id],
            set_={
                "business_id": insert_stmt.excluded.business_id,
                "location_id": insert_stmt.excluded.location_id,
                "schema_version": insert_stmt.excluded.schema_version,
                "event_type": insert_stmt.excluded.event_type,
                "compatibility_event_name": insert_stmt.excluded.compatibility_event_name,
                "entity_type": insert_stmt.excluded.entity_type,
                "entity_id": insert_stmt.excluded.entity_id,
                "actor_type": insert_stmt.excluded.actor_type,
                "actor_user_id": insert_stmt.excluded.actor_user_id,
                "actor_membership_id": insert_stmt.excluded.actor_membership_id,
                "trace_id": insert_stmt.excluded.trace_id,
                "ip_address": insert_stmt.excluded.ip_address,
                "user_agent": insert_stmt.excluded.user_agent,
                "payload": insert_stmt.excluded.payload,
                "metadata": insert_stmt.excluded["metadata"],
                "error_message": insert_stmt.excluded.error_message,
                "occurred_at": insert_stmt.excluded.occurred_at,
                "source_created_at": insert_stmt.excluded.source_created_at,
                "projection_metadata": insert_stmt.excluded.projection_metadata,
            },
        )
    )
    await session.flush()


async def _load_projected_rows(
    session: AsyncSession,
    *,
    business_id: UUID,
    projection_name: str,
    location_id: UUID | None,
    entity_type: str | None,
    event_type: str | None,
    limit: int,
) -> list[FeedProjection]:
    stmt = (
        select(FeedProjection)
        .where(
            FeedProjection.projection_name == projection_name,
            FeedProjection.business_id == business_id,
        )
        .order_by(
            FeedProjection.occurred_at.desc(),
            FeedProjection.source_created_at.desc(),
            FeedProjection.source_event_id.desc(),
        )
        .limit(_normalized_limit(limit))
    )
    if location_id is not None:
        stmt = stmt.where(FeedProjection.location_id == location_id)
    if entity_type is not None:
        stmt = stmt.where(FeedProjection.entity_type == entity_type)
    if event_type is not None:
        stmt = stmt.where(FeedProjection.event_type == event_type)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _load_raw_tail_events(
    session: AsyncSession,
    *,
    business_id: UUID,
    projection_name: str,
    location_id: UUID | None,
    entity_type: str | None,
    event_type: str | None,
    limit: int,
) -> list[PlatformEvent]:
    cursor = await _load_projection_cursor(session, projection_name=projection_name)
    if cursor is None or cursor.last_source_created_at is None or cursor.last_source_event_id is None:
        return []

    stmt = (
        select(PlatformEvent)
        .where(PlatformEvent.business_id == business_id)
        .order_by(
            PlatformEvent.occurred_at.desc(),
            PlatformEvent.created_at.desc(),
            PlatformEvent.id.desc(),
        )
        .limit(_normalized_limit(limit))
    )
    clause = _cursor_clause(
        created_at_column=PlatformEvent.created_at,
        id_column=PlatformEvent.id,
        last_source_created_at=cursor.last_source_created_at,
        last_source_event_id=cursor.last_source_event_id,
    )
    if clause is not None:
        stmt = stmt.where(clause)
    if location_id is not None:
        stmt = stmt.where(PlatformEvent.location_id == location_id)
    if entity_type is not None:
        stmt = stmt.where(PlatformEvent.entity_type == entity_type)
    if event_type is not None:
        stmt = stmt.where(PlatformEvent.event_type == event_type)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _merge_feed_reads(
    projected_rows: list[FeedProjection],
    raw_tail_events: list[PlatformEvent],
    *,
    limit: int,
) -> list[PlatformEventRead]:
    items: list[_FeedReadItem] = [
        _FeedReadItem(
            event=_feed_read_from_projection(row),
            source_created_at=row.source_created_at,
        )
        for row in projected_rows
    ]
    items.extend(
        _FeedReadItem(
            event=_feed_read_from_platform_event(row),
            source_created_at=row.created_at,
        )
        for row in raw_tail_events
    )
    deduped: dict[str, _FeedReadItem] = {}
    for item in items:
        deduped[str(item.event.id)] = item
    ordered = sorted(
        deduped.values(),
        key=_feed_item_sort_key,
        reverse=True,
    )
    return [item.event for item in ordered[: _normalized_limit(limit)]]


async def list_feed_events(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None = None,
    entity_type: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
    projection_name: str = DEFAULT_FEED_PROJECTION_NAME,
) -> list[PlatformEventRead]:
    projected_rows = await _load_projected_rows(
        session,
        business_id=business_id,
        projection_name=projection_name,
        location_id=location_id,
        entity_type=entity_type,
        event_type=event_type,
        limit=limit,
    )
    if not projected_rows:
        raw_rows = await platform_events.list_events(
            session,
            business_id=business_id,
            location_id=location_id,
            entity_type=entity_type,
            event_type=event_type,
            limit=limit,
        )
        return [_feed_read_from_platform_event(row) for row in raw_rows]

    raw_tail_events = await _load_raw_tail_events(
        session,
        business_id=business_id,
        projection_name=projection_name,
        location_id=location_id,
        entity_type=entity_type,
        event_type=event_type,
        limit=limit,
    )
    return _merge_feed_reads(projected_rows, raw_tail_events, limit=limit)


async def process_feed_projection_batch(
    session: AsyncSession,
    *,
    limit: int = 100,
    projection_name: str = DEFAULT_FEED_PROJECTION_NAME,
) -> dict[str, Any]:
    reference_time = datetime.now(timezone.utc)
    cursor = await _claim_projection_cursor(
        session,
        projection_name=projection_name,
        now=reference_time,
    )
    if cursor is None:
        return {
            "projection_name": projection_name,
            "status": "busy",
            "claimed": False,
            "cursor_status": "processing",
            "processed_count": 0,
            "processed_source_event_ids": [],
            "latest_source_event_id": None,
            "latest_source_created_at": None,
        }

    try:
        events = await _list_projection_source_events(session, cursor=cursor, limit=limit)
        await _upsert_feed_projection_rows(
            session,
            projection_name=projection_name,
            events=events,
        )
        latest_event = events[-1] if events else None
        if latest_event is not None:
            cursor.last_source_created_at = latest_event.created_at
            cursor.last_source_event_id = latest_event.id
        cursor.cursor_status = "idle"
        cursor.last_run_completed_at = reference_time
        cursor.last_error = None
        cursor.cursor_metadata = {
            **(cursor.cursor_metadata or {}),
            "last_processed_count": len(events),
            "last_processed_at": reference_time.isoformat(),
        }
        await session.commit()
        return {
            "projection_name": projection_name,
            "status": "processed" if events else "idle",
            "claimed": True,
            "cursor_status": cursor.cursor_status,
            "processed_count": len(events),
            "processed_source_event_ids": [str(event.id) for event in events],
            "latest_source_event_id": str(latest_event.id) if latest_event is not None else None,
            "latest_source_created_at": latest_event.created_at if latest_event is not None else None,
        }
    except Exception as exc:
        await session.rollback()
        await _mark_projection_cursor_failure(
            session,
            projection_name=projection_name,
            now=reference_time,
            error_message=str(exc),
        )
        raise


async def rebuild_feed_projection(
    session: AsyncSession,
    *,
    limit: int = 100,
    projection_name: str = DEFAULT_FEED_PROJECTION_NAME,
) -> dict[str, Any]:
    reference_time = datetime.now(timezone.utc)
    cursor = await _claim_projection_cursor(
        session,
        projection_name=projection_name,
        now=reference_time,
    )
    if cursor is None:
        return {
            "projection_name": projection_name,
            "status": "busy",
            "claimed": False,
            "cursor_status": "processing",
            "deleted_count": 0,
            "processed_count": 0,
            "processed_source_event_ids": [],
            "latest_source_event_id": None,
            "latest_source_created_at": None,
        }

    try:
        delete_result = await session.execute(
            delete(FeedProjection).where(FeedProjection.projection_name == projection_name)
        )
        deleted_count = int(delete_result.rowcount or 0)
        cursor.last_source_created_at = None
        cursor.last_source_event_id = None
        cursor.cursor_metadata = {
            **(cursor.cursor_metadata or {}),
            "last_rebuild_started_at": reference_time.isoformat(),
        }
        events = await _list_projection_source_events(session, cursor=cursor, limit=limit)
        await _upsert_feed_projection_rows(
            session,
            projection_name=projection_name,
            events=events,
        )
        latest_event = events[-1] if events else None
        if latest_event is not None:
            cursor.last_source_created_at = latest_event.created_at
            cursor.last_source_event_id = latest_event.id
        cursor.cursor_status = "idle"
        cursor.last_run_completed_at = reference_time
        cursor.last_error = None
        cursor.cursor_metadata = {
            **(cursor.cursor_metadata or {}),
            "last_rebuild_completed_at": reference_time.isoformat(),
            "last_rebuild_deleted_count": deleted_count,
            "last_processed_count": len(events),
        }
        await session.commit()
        return {
            "projection_name": projection_name,
            "status": "processed" if events or deleted_count else "idle",
            "claimed": True,
            "cursor_status": cursor.cursor_status,
            "deleted_count": deleted_count,
            "processed_count": len(events),
            "processed_source_event_ids": [str(event.id) for event in events],
            "latest_source_event_id": str(latest_event.id) if latest_event is not None else None,
            "latest_source_created_at": latest_event.created_at if latest_event is not None else None,
        }
    except Exception as exc:
        await session.rollback()
        await _mark_projection_cursor_failure(
            session,
            projection_name=projection_name,
            now=reference_time,
            error_message=str(exc),
        )
        raise
