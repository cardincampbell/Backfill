from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from typing import Any

import psycopg

from app.config import settings

logger = logging.getLogger(__name__)

PLATFORM_EVENT_NOTIFY_CHANNEL = "backfill_platform_events"


@dataclass(frozen=True)
class RealtimePlatformEvent:
    platform_event_id: str
    business_id: str | None
    location_id: str | None
    event_type: str
    entity_type: str
    entity_id: str | None
    trace_id: str
    occurred_at: str | None
    source: str = "platform_event"

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _SubscriberScope:
    business_id: str
    location_id: str | None


class RealtimeEventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[int, tuple[_SubscriberScope, asyncio.Queue[RealtimePlatformEvent]]] = {}
        self._next_subscriber_id = 1
        self._lock = asyncio.Lock()
        self._listen_task: asyncio.Task[None] | None = None
        self._stop_requested = False

    async def ensure_started(self) -> None:
        async with self._lock:
            if self._listen_task is not None and not self._listen_task.done():
                return
            self._stop_requested = False
            self._listen_task = asyncio.create_task(
                self._listen_forever(),
                name="backfill-realtime-events-listener",
            )

    async def stop(self) -> None:
        async with self._lock:
            self._stop_requested = True
            task = self._listen_task
            self._listen_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @asynccontextmanager
    async def subscribe(
        self,
        *,
        business_id: str,
        location_id: str | None = None,
    ) -> AsyncIterator[asyncio.Queue[RealtimePlatformEvent]]:
        queue: asyncio.Queue[RealtimePlatformEvent] = asyncio.Queue(maxsize=100)
        async with self._lock:
            subscriber_id = self._next_subscriber_id
            self._next_subscriber_id += 1
            self._subscribers[subscriber_id] = (
                _SubscriberScope(business_id=business_id, location_id=location_id),
                queue,
            )
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.pop(subscriber_id, None)

    async def publish_local(self, event: RealtimePlatformEvent) -> None:
        async with self._lock:
            subscribers = list(self._subscribers.items())
        for _, (scope, queue) in subscribers:
            if scope.business_id != (event.business_id or ""):
                continue
            if scope.location_id is not None and scope.location_id != event.location_id:
                continue
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("Dropping realtime event because subscriber queue is saturated")

    async def _listen_forever(self) -> None:
        while not self._stop_requested:
            try:
                await self._listen_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Realtime platform event listener crashed; retrying")
                await asyncio.sleep(1)

    async def _listen_once(self) -> None:
        async with await psycopg.AsyncConnection.connect(
            settings.advisory_lock_database_url,
            autocommit=True,
        ) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(f"LISTEN {PLATFORM_EVENT_NOTIFY_CHANNEL}")
            logger.info("Realtime listener subscribed to Postgres channel %s", PLATFORM_EVENT_NOTIFY_CHANNEL)
            while not self._stop_requested:
                async for notification in connection.notifies(timeout=15):
                    event = _parse_notification_payload(notification.payload)
                    if event is None:
                        continue
                    await self.publish_local(event)


def _parse_notification_payload(payload: str) -> RealtimePlatformEvent | None:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Ignoring malformed realtime notification payload")
        return None
    if not isinstance(raw, dict):
        return None
    business_id = raw.get("business_id")
    event_type = raw.get("event_type")
    entity_type = raw.get("entity_type")
    trace_id = raw.get("trace_id")
    platform_event_id = raw.get("platform_event_id")
    if not all(isinstance(value, str) and value for value in (platform_event_id, business_id, event_type, entity_type, trace_id)):
        return None
    location_id = raw.get("location_id")
    entity_id = raw.get("entity_id")
    occurred_at = raw.get("occurred_at")
    return RealtimePlatformEvent(
        platform_event_id=platform_event_id,
        business_id=business_id,
        location_id=location_id if isinstance(location_id, str) and location_id else None,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id if isinstance(entity_id, str) and entity_id else None,
        trace_id=trace_id,
        occurred_at=occurred_at if isinstance(occurred_at, str) and occurred_at else None,
    )


_broker: RealtimeEventBroker | None = None


def get_realtime_event_broker() -> RealtimeEventBroker:
    global _broker
    if _broker is None:
        _broker = RealtimeEventBroker()
    return _broker

