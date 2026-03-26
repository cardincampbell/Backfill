"""
Queue-first integration sync orchestration.

This layer assumes partner-level rate limits may apply, so every platform uses
shared durable job queues with explicit priority and retry policy.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import aiosqlite

from app.db import queries
from app.services import scheduling

ROLLING_RECONCILE_INTERVAL = timedelta(minutes=30)
WRITEBACK_STABILIZATION_WINDOW = timedelta(minutes=5)

PLATFORM_POLICIES = {
    "7shifts": {
        "shared_budget_rps": 10,
        "supports_webhooks": True,
        "default_mode": "webhook_first",
    },
    "deputy": {
        "shared_budget_rps": 3,
        "supports_webhooks": True,
        "default_mode": "webhook_first",
    },
    "wheniwork": {
        "shared_budget_rps": 2,
        "supports_webhooks": True,
        "default_mode": "webhook_first",
    },
    "homebase": {
        "shared_budget_rps": 1,
        "supports_webhooks": False,
        "default_mode": "scheduled_companion",
    },
    "backfill_native": {
        "shared_budget_rps": 0,
        "supports_webhooks": False,
        "default_mode": "native",
    },
}

JOB_PRIORITIES = {
    "event_reconcile": 10,
    "writeback": 15,
    "repair_reconcile": 20,
    "rolling_reconcile": 40,
    "daily_reconcile": 80,
    "connect_bootstrap": 90,
}

RETRY_BACKOFFS = {
    "event_reconcile": [timedelta(minutes=1), timedelta(minutes=5)],
    "writeback": [timedelta(minutes=1), timedelta(minutes=5)],
    "repair_reconcile": [timedelta(minutes=5), timedelta(minutes=20)],
    "rolling_reconcile": [timedelta(minutes=10), timedelta(minutes=30)],
    "daily_reconcile": [timedelta(minutes=30), timedelta(hours=2)],
    "connect_bootstrap": [timedelta(minutes=5), timedelta(minutes=30)],
}


def platform_policy(platform: str | None) -> dict:
    return PLATFORM_POLICIES.get(platform or "backfill_native", PLATFORM_POLICIES["backfill_native"])


def job_priority(job_type: str) -> int:
    return JOB_PRIORITIES.get(job_type, 50)


def _retry_delay(job_type: str, attempt_count: int) -> Optional[timedelta]:
    delays = RETRY_BACKOFFS.get(job_type, [timedelta(minutes=5), timedelta(minutes=30)])
    index = max(attempt_count - 1, 0)
    if index >= len(delays):
        return None
    return delays[index]


def _coerce_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _window_for_job(job_type: str, reference: Optional[datetime] = None) -> tuple[str | None, str | None]:
    current = reference or datetime.utcnow()
    if job_type == "event_reconcile":
        start = current - timedelta(days=1)
        end = current + timedelta(days=3)
        return start.date().isoformat(), end.date().isoformat()
    if job_type == "rolling_reconcile":
        start = current - timedelta(days=1)
        end = current + timedelta(days=2)
        return start.date().isoformat(), end.date().isoformat()
    if job_type in {"daily_reconcile", "connect_bootstrap", "repair_reconcile"}:
        start = current - timedelta(days=1)
        end = current + timedelta(days=14)
        return start.date().isoformat(), end.date().isoformat()
    return None, None


def _parse_shift_start(shift: dict) -> Optional[datetime]:
    shift_date = shift.get("date")
    shift_start = shift.get("start_time")
    if not shift_date or not shift_start:
        return None
    try:
        return datetime.fromisoformat(f"{shift_date}T{shift_start}")
    except ValueError:
        return None


def _should_hold_writeback_until(shift: dict, *, now: Optional[datetime] = None) -> datetime:
    current = now or datetime.utcnow()
    target = current + WRITEBACK_STABILIZATION_WINDOW
    shift_start = _parse_shift_start(shift)
    if shift_start is None or shift_start <= target:
        return current
    return target


def _is_recent(value: str | None, *, now: datetime, window: timedelta) -> bool:
    if not value:
        return False
    parsed = _coerce_datetime(value)
    if parsed is None:
        return False
    return now - parsed <= window


async def enqueue_sync_job(
    db: aiosqlite.Connection,
    *,
    platform: str,
    location_id: Optional[int],
    job_type: str,
    integration_event_id: Optional[int] = None,
    scope: Optional[str] = None,
    scope_ref: Optional[str] = None,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
    next_run_at: Optional[str] = None,
    max_attempts: int = 3,
    idempotency_key: Optional[str] = None,
) -> int:
    start, end = (window_start, window_end)
    if start is None and end is None:
        start, end = _window_for_job(job_type)

    return await queries.insert_sync_job(
        db,
        {
            "platform": platform,
            "location_id": location_id,
            "integration_event_id": integration_event_id,
            "job_type": job_type,
            "priority": job_priority(job_type),
            "scope": scope,
            "scope_ref": scope_ref,
            "window_start": start,
            "window_end": end,
            "next_run_at": next_run_at or datetime.utcnow().isoformat(),
            "max_attempts": max_attempts,
            "idempotency_key": idempotency_key,
        },
    )


async def enqueue_event_reconcile(
    db: aiosqlite.Connection,
    *,
    platform: str,
    payload: dict,
    location_id: Optional[int],
    event_type: Optional[str],
    event_scope: Optional[str],
    scope_ref: Optional[str],
    source_event_id: Optional[str],
) -> dict:
    event_id = await queries.insert_integration_event(
        db,
        {
            "platform": platform,
            "location_id": location_id,
            "source_event_id": source_event_id,
            "event_type": event_type,
            "event_scope": event_scope,
            "payload": payload,
            "received_at": datetime.utcnow().isoformat(),
            "status": "queued",
        },
    )
    event = await queries.get_integration_event(db, event_id)

    job_id = await enqueue_sync_job(
        db,
        platform=platform,
        location_id=location_id,
        integration_event_id=event_id,
        job_type="event_reconcile",
        scope=event_scope,
        scope_ref=scope_ref,
        idempotency_key=(f"{platform}:event_reconcile:{source_event_id}" if source_event_id else None),
    )
    return {
        "event": event,
        "job": await queries.get_sync_job(db, job_id),
    }


async def enqueue_rolling_reconcile(
    db: aiosqlite.Connection,
    *,
    location_id: int,
) -> dict:
    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError(f"Location {location_id} not found")
    job_id = await enqueue_sync_job(
        db,
        platform=location.get("scheduling_platform") or "backfill_native",
        location_id=location_id,
        job_type="rolling_reconcile",
        scope="location",
        scope_ref=str(location_id),
        idempotency_key=f"rolling:{location_id}:{datetime.utcnow().strftime('%Y%m%d%H%M')}",
    )
    return await queries.get_sync_job(db, job_id)


async def enqueue_daily_reconcile(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    for_date: Optional[date] = None,
) -> dict:
    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError(f"Location {location_id} not found")
    run_date = for_date or date.today()
    job_id = await enqueue_sync_job(
        db,
        platform=location.get("scheduling_platform") or "backfill_native",
        location_id=location_id,
        job_type="daily_reconcile",
        scope="location",
        scope_ref=str(location_id),
        idempotency_key=f"daily:{location_id}:{run_date.isoformat()}",
    )
    return await queries.get_sync_job(db, job_id)


async def enqueue_daily_reconcile_for_all(
    db: aiosqlite.Connection,
    *,
    for_date: Optional[date] = None,
) -> list[dict]:
    jobs = []
    for location in await queries.list_locations(db):
        if (location.get("scheduling_platform") or "backfill_native") == "backfill_native":
            continue
        jobs.append(await enqueue_daily_reconcile(db, location_id=int(location["id"]), for_date=for_date))
    return jobs


async def enqueue_writeback(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
) -> dict:
    shift = await queries.get_shift(db, shift_id)
    if shift is None:
        raise ValueError(f"Shift {shift_id} not found")

    location_id = shift.get("location_id")
    if not location_id:
        return {"status": "skipped", "reason": "location_not_found", "shift_id": shift_id}

    location = await queries.get_location(db, int(location_id))
    if location is None:
        return {"status": "skipped", "reason": "location_not_found", "shift_id": shift_id}

    if not scheduling.writeback_is_enabled(location):
        return {"status": "skipped", "reason": "writeback_disabled", "shift_id": shift_id}

    platform = location.get("scheduling_platform") or "backfill_native"
    next_run_at = _should_hold_writeback_until(shift).isoformat()
    existing = await queries.find_pending_sync_job_for_scope(
        db,
        location_id=int(location_id),
        job_type="writeback",
        scope_ref=str(shift_id),
    )
    if existing is not None:
        if existing.get("status") == "queued":
            existing_next = _coerce_datetime(existing.get("next_run_at"))
            if existing_next is None or existing_next > datetime.fromisoformat(next_run_at):
                await queries.update_sync_job(
                    db,
                    int(existing["id"]),
                    {"next_run_at": next_run_at, "last_error": None},
                )
                existing = await queries.get_sync_job(db, int(existing["id"]))
            return existing or {"status": "queued", "shift_id": shift_id}

    job_id = await enqueue_sync_job(
        db,
        platform=platform,
        location_id=int(location_id),
        job_type="writeback",
        scope="shift",
        scope_ref=str(shift_id),
        next_run_at=next_run_at,
    )
    return await queries.get_sync_job(db, job_id)


async def enqueue_rolling_reconcile_for_due_locations(
    db: aiosqlite.Connection,
    *,
    now: Optional[datetime] = None,
) -> list[dict]:
    current = now or datetime.utcnow()
    queued: list[dict] = []
    for location in await queries.list_locations(db):
        platform = location.get("scheduling_platform") or "backfill_native"
        if platform == "backfill_native":
            continue

        location_id = int(location["id"])
        open_rolling = await queries.find_pending_sync_job_for_scope(
            db,
            location_id=location_id,
            job_type="rolling_reconcile",
            scope_ref=str(location_id),
        )
        if open_rolling is not None:
            continue

        last_rolling = location.get("last_rolling_sync_at")
        if _is_recent(last_rolling, now=current, window=ROLLING_RECONCILE_INTERVAL):
            continue

        healthy = (location.get("integration_state") or "healthy") == "healthy"
        recent_event = _is_recent(
            location.get("last_event_sync_at"),
            now=current,
            window=ROLLING_RECONCILE_INTERVAL,
        )
        recent_writeback = _is_recent(
            location.get("last_writeback_at"),
            now=current,
            window=ROLLING_RECONCILE_INTERVAL,
        )
        if healthy and (recent_event or recent_writeback):
            continue

        queued.append(await enqueue_rolling_reconcile(db, location_id=location_id))
    return queued


async def enqueue_daily_reconcile_for_due_locations(
    db: aiosqlite.Connection,
    *,
    for_date: Optional[date] = None,
) -> list[dict]:
    run_date = for_date or date.today()
    queued: list[dict] = []
    for location in await queries.list_locations(db):
        platform = location.get("scheduling_platform") or "backfill_native"
        if platform == "backfill_native":
            continue

        location_id = int(location["id"])
        open_daily = await queries.find_pending_sync_job_for_scope(
            db,
            location_id=location_id,
            job_type="daily_reconcile",
            scope_ref=str(location_id),
        )
        if open_daily is not None:
            continue

        last_daily = location.get("last_daily_sync_at")
        if last_daily:
            parsed = _coerce_datetime(last_daily)
            if parsed and parsed.date() >= run_date:
                continue

        queued.append(await enqueue_daily_reconcile(db, location_id=location_id, for_date=run_date))
    return queued


def _rollup_counts(results: list[dict]) -> tuple[int, int, int]:
    created = sum(int(result.get("created", 0) or 0) for result in results)
    updated = sum(int(result.get("updated", 0) or 0) for result in results)
    skipped = sum(int(result.get("skipped", 0) or 0) for result in results)
    return created, updated, skipped


async def _mark_location_sync_state(
    db: aiosqlite.Connection,
    location_id: int,
    *,
    state: str,
    error: Optional[str] = None,
    event_stamp: bool = False,
    rolling_stamp: bool = False,
    daily_stamp: bool = False,
    writeback_stamp: bool = False,
) -> None:
    now = datetime.utcnow().isoformat()
    updates: dict[str, object] = {
        "integration_state": state,
        "last_sync_error": error,
    }
    if event_stamp:
        updates["last_event_sync_at"] = now
    if rolling_stamp:
        updates["last_rolling_sync_at"] = now
    if daily_stamp:
        updates["last_daily_sync_at"] = now
    if writeback_stamp:
        updates["last_writeback_at"] = now
    await queries.update_location(db, location_id, updates)


async def process_sync_job(db: aiosqlite.Connection, job_id: int) -> dict:
    job = await queries.get_sync_job(db, job_id)
    if job is None:
        raise ValueError(f"Sync job {job_id} not found")
    if job["status"] == "queued":
        claimed = await queries.claim_sync_job(db, job_id)
        if claimed is None:
            refreshed = await queries.get_sync_job(db, job_id)
            return {"status": refreshed["status"] if refreshed else "missing", "job_id": job_id}
        job = claimed
    if job["status"] != "running":
        return {"status": job["status"], "job_id": job_id}

    started_at = _coerce_datetime(job.get("started_at")) or datetime.utcnow()
    completed_at = datetime.utcnow()
    attempt_number = int(job.get("attempt_count") or 1)
    created = updated = skipped = 0

    try:
        location_id = job.get("location_id")
        location = await queries.get_location(db, int(location_id)) if location_id else None
        platform = job.get("platform") or (location.get("scheduling_platform") if location else "backfill_native")

        if platform == "backfill_native":
            if location_id:
                await _mark_location_sync_state(
                    db,
                    int(location_id),
                    state="healthy",
                    event_stamp=job["job_type"] == "event_reconcile",
                    rolling_stamp=job["job_type"] == "rolling_reconcile",
                    daily_stamp=job["job_type"] in {"daily_reconcile", "connect_bootstrap"},
                    writeback_stamp=job["job_type"] == "writeback",
                )
            await queries.update_sync_job(
                db,
                job_id,
                {"status": "completed", "completed_at": completed_at.isoformat(), "last_error": None},
            )
            await queries.insert_sync_run(
                db,
                {
                    "sync_job_id": job_id,
                    "attempt_number": attempt_number,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "status": "completed",
                    "latency_ms": int((completed_at - started_at).total_seconds() * 1000),
                },
            )
            return {"status": "completed", "job_id": job_id, "platform": platform}

        if location is None:
            raise ValueError(f"Location {location_id} not found")

        results: list[dict] = []
        if job["job_type"] in {"daily_reconcile", "connect_bootstrap", "repair_reconcile"}:
            results.append(await scheduling.sync_roster(db, int(location_id)))

        if job["job_type"] in {"event_reconcile", "rolling_reconcile", "daily_reconcile", "connect_bootstrap", "repair_reconcile"}:
            start_value = job.get("window_start")
            end_value = job.get("window_end")
            start_date = date.fromisoformat(start_value) if start_value else date.today()
            end_date = date.fromisoformat(end_value) if end_value else (date.today() + timedelta(days=14))
            results.append(await scheduling.sync_schedule(db, int(location_id), start_date, end_date))

        if job["job_type"] == "writeback":
            scope_ref = job.get("scope_ref")
            if not scope_ref:
                raise ValueError("Writeback job missing scope_ref")
            await scheduling.push_fill_update(db, int(scope_ref))

        created, updated, skipped = _rollup_counts(results)
        await queries.update_sync_job(
            db,
            job_id,
            {"status": "completed", "completed_at": completed_at.isoformat(), "last_error": None},
        )
        if job.get("integration_event_id"):
            await queries.update_integration_event(
                db,
                int(job["integration_event_id"]),
                {"status": "processed", "processed_at": completed_at.isoformat(), "error": None},
            )
        await _mark_location_sync_state(
            db,
            int(location_id),
            state="healthy",
            event_stamp=job["job_type"] == "event_reconcile",
            rolling_stamp=job["job_type"] == "rolling_reconcile",
            daily_stamp=job["job_type"] in {"daily_reconcile", "connect_bootstrap"},
            writeback_stamp=job["job_type"] == "writeback",
        )
        await queries.insert_sync_run(
            db,
            {
                "sync_job_id": job_id,
                "attempt_number": attempt_number,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "status": "completed",
                "created_count": created,
                "updated_count": updated,
                "skipped_count": skipped,
                "latency_ms": int((completed_at - started_at).total_seconds() * 1000),
            },
        )
        return {
            "status": "completed",
            "job_id": job_id,
            "platform": platform,
            "created": created,
            "updated": updated,
            "skipped": skipped,
        }
    except Exception as exc:
        retry_delay = _retry_delay(job["job_type"], attempt_number)
        final_failure = attempt_number >= int(job.get("max_attempts") or 3) or retry_delay is None
        next_run_at = None if final_failure else (completed_at + retry_delay).isoformat()
        await queries.update_sync_job(
            db,
            job_id,
            {
                "status": "failed" if final_failure else "queued",
                "completed_at": completed_at.isoformat() if final_failure else None,
                "next_run_at": next_run_at,
                "last_error": str(exc),
            },
        )
        if job.get("integration_event_id"):
            await queries.update_integration_event(
                db,
                int(job["integration_event_id"]),
                {
                    "status": "failed" if final_failure else "retrying",
                    "processed_at": completed_at.isoformat() if final_failure else None,
                    "error": str(exc),
                },
            )
        if job.get("location_id"):
            await _mark_location_sync_state(
                db,
                int(job["location_id"]),
                state="degraded" if final_failure else "repairing",
                error=str(exc),
            )
        await queries.insert_sync_run(
            db,
            {
                "sync_job_id": job_id,
                "attempt_number": attempt_number,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "status": "failed" if final_failure else "retrying",
                "created_count": created,
                "updated_count": updated,
                "skipped_count": skipped,
                "latency_ms": int((completed_at - started_at).total_seconds() * 1000),
                "error": str(exc),
            },
        )
        return {
            "status": "failed" if final_failure else "retrying",
            "job_id": job_id,
            "error": str(exc),
            "next_run_at": next_run_at,
        }


async def process_due_sync_jobs(
    db: aiosqlite.Connection,
    *,
    platform: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    jobs = await queries.claim_due_sync_jobs(db, platform=platform, limit=limit)
    results = []
    for job in jobs:
        results.append(await process_sync_job(db, int(job["id"])))
    return results
