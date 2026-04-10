from __future__ import annotations

from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional, TypeVar

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import OutboxStatus, SchedulerSyncJobStatus
from app.models.coverage import OutboxEvent
from app.models.integrations import ProviderCallbackLog, SchedulerSyncJob

_CLAIM_SCAN_MULTIPLIER = 5
_OUTBOX_STALE_LOCK_AFTER = timedelta(minutes=5)
_CALLBACK_STALE_LOCK_AFTER = timedelta(minutes=5)
_SCHEDULER_JOB_STALE_AFTER = timedelta(minutes=15)
_DEFAULT_OUTBOX_RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
)

T = TypeVar("T")
BusinessResolver = Callable[[AsyncSession, list[T]], Awaitable[dict[object, Optional[object]]]]


def retry_delay_for_attempt(
    attempt_count: int,
    *,
    schedule: tuple[timedelta, ...] = _DEFAULT_OUTBOX_RETRY_DELAYS,
) -> timedelta:
    index = max(0, min(max(attempt_count, 1) - 1, len(schedule) - 1))
    return schedule[index]


async def _apply_business_isolation(
    session: AsyncSession,
    entries: list[T],
    *,
    limit: int,
    key_fn: Callable[[T], object],
    resolver: BusinessResolver[T] | None = None,
) -> list[T]:
    if not entries:
        return []
    if resolver is None:
        return entries[:limit]

    resolved = await resolver(session, entries)
    selected: list[T] = []
    seen_business_keys: set[str] = set()

    for entry in entries:
        business_key = resolved.get(key_fn(entry))
        dedupe_key = str(business_key) if business_key is not None else f"row:{key_fn(entry)}"
        if business_key is not None and dedupe_key in seen_business_keys:
            continue
        seen_business_keys.add(dedupe_key)
        selected.append(entry)
        if len(selected) >= limit:
            break

    return selected


async def claim_outbox_events(
    session: AsyncSession,
    *,
    now: datetime,
    limit: int,
    topic: str,
    business_resolver: BusinessResolver[OutboxEvent] | None = None,
) -> list[OutboxEvent]:
    due_filter = or_(OutboxEvent.available_at.is_(None), OutboxEvent.available_at <= now)
    stale_filter = and_(
        OutboxEvent.status == OutboxStatus.processing,
        OutboxEvent.locked_at.is_not(None),
        OutboxEvent.locked_at <= now - _OUTBOX_STALE_LOCK_AFTER,
    )
    result = await session.execute(
        select(OutboxEvent)
        .where(
            OutboxEvent.topic == topic,
            or_(
                and_(OutboxEvent.status.in_([OutboxStatus.pending, OutboxStatus.failed]), due_filter),
                stale_filter,
            ),
        )
        .order_by(OutboxEvent.available_at.asc(), OutboxEvent.created_at.asc())
        .limit(max(limit, 1) * _CLAIM_SCAN_MULTIPLIER)
        .with_for_update(skip_locked=True)
    )
    events = list(result.scalars().all())
    selected = await _apply_business_isolation(
        session,
        events,
        limit=limit,
        key_fn=lambda event: event.id,
        resolver=business_resolver,
    )
    for event in selected:
        event.status = OutboxStatus.processing
        event.locked_at = now
        event.attempt_count = int(event.attempt_count or 0) + 1
    await session.flush()
    return selected


def mark_outbox_event_sent(
    event: OutboxEvent,
    *,
    now: datetime,
    result_payload: dict | None = None,
) -> None:
    event.status = OutboxStatus.sent
    event.processed_at = now
    event.locked_at = None
    event.result_payload = result_payload or {}
    event.error_message = None


def mark_outbox_event_retry(
    event: OutboxEvent,
    *,
    now: datetime,
    next_attempt_at: datetime,
    error_message: str,
    result_payload: dict | None = None,
) -> None:
    event.status = OutboxStatus.failed
    event.available_at = next_attempt_at
    event.processed_at = now
    event.locked_at = None
    event.error_message = error_message
    event.result_payload = result_payload or {}


def mark_outbox_event_cancelled(
    event: OutboxEvent,
    *,
    now: datetime,
    error_message: str,
    result_payload: dict | None = None,
) -> None:
    event.status = OutboxStatus.cancelled
    event.processed_at = now
    event.locked_at = None
    event.error_message = error_message
    event.result_payload = result_payload or {}


async def claim_provider_callback_logs(
    session: AsyncSession,
    *,
    limit: int,
    now: datetime,
) -> list[ProviderCallbackLog]:
    stale_filter = and_(
        ProviderCallbackLog.status == "processing",
        ProviderCallbackLog.processed_at.is_not(None),
        ProviderCallbackLog.processed_at <= now - _CALLBACK_STALE_LOCK_AFTER,
    )
    result = await session.execute(
        select(ProviderCallbackLog)
        .where(
            or_(
                ProviderCallbackLog.status.in_(["received", "failed"]),
                stale_filter,
            )
        )
        .order_by(ProviderCallbackLog.received_at.asc(), ProviderCallbackLog.created_at.asc())
        .limit(max(limit, 1) * _CLAIM_SCAN_MULTIPLIER)
        .with_for_update(skip_locked=True)
    )
    entries = list(result.scalars().all())[:limit]
    for entry in entries:
        entry.status = "processing"
        entry.processed_at = now
    await session.flush()
    return entries


async def claim_scheduler_jobs(
    session: AsyncSession,
    *,
    now: datetime,
    limit: int,
) -> list[SchedulerSyncJob]:
    stale_filter = and_(
        SchedulerSyncJob.status == SchedulerSyncJobStatus.running,
        SchedulerSyncJob.started_at.is_not(None),
        SchedulerSyncJob.started_at <= now - _SCHEDULER_JOB_STALE_AFTER,
    )
    result = await session.execute(
        select(SchedulerSyncJob)
        .where(
            or_(
                and_(
                    SchedulerSyncJob.status == SchedulerSyncJobStatus.queued,
                    SchedulerSyncJob.next_run_at <= now,
                ),
                stale_filter,
            )
        )
        .order_by(SchedulerSyncJob.priority.asc(), SchedulerSyncJob.next_run_at.asc())
        .limit(max(limit, 1) * _CLAIM_SCAN_MULTIPLIER)
        .with_for_update(skip_locked=True)
    )
    jobs = list(result.scalars().all())
    selected = await _apply_business_isolation(
        session,
        jobs,
        limit=limit,
        key_fn=lambda job: job.id,
        resolver=_scheduler_job_business_keys,
    )
    for job in selected:
        mark_scheduler_job_claimed(job, now=now)
    await session.flush()
    return selected


async def _scheduler_job_business_keys(
    _session: AsyncSession,
    jobs: list[SchedulerSyncJob],
) -> dict[object, object | None]:
    return {
        job.id: job.business_id
        for job in jobs
    }


def mark_scheduler_job_claimed(
    job: SchedulerSyncJob,
    *,
    now: datetime,
) -> None:
    job.status = SchedulerSyncJobStatus.running
    job.started_at = now
    job.attempt_count += 1


def mark_scheduler_job_completed(
    job: SchedulerSyncJob,
    *,
    completed_at: datetime,
) -> None:
    job.status = SchedulerSyncJobStatus.completed
    job.completed_at = completed_at
    job.last_error = None


def mark_scheduler_job_retry(
    job: SchedulerSyncJob,
    *,
    next_run_at: datetime,
    error_message: str,
) -> None:
    job.status = SchedulerSyncJobStatus.queued
    job.completed_at = None
    job.next_run_at = next_run_at
    job.last_error = error_message


def mark_scheduler_job_failed(
    job: SchedulerSyncJob,
    *,
    completed_at: datetime,
    error_message: str,
) -> None:
    job.status = SchedulerSyncJobStatus.failed
    job.completed_at = completed_at
    job.last_error = error_message
