from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Optional

import aiosqlite

from app.config import settings
from app.db.database import DB_PATH
from app.db import queries

logger = logging.getLogger(__name__)

JOB_PRIORITIES = {
    "send_notification": 15,
    "send_outreach_delivery": 12,
    "run_due_backfill_shifts_automation": 10,
    "send_due_manager_digests": 20,
    "send_shift_confirmation_requests": 20,
    "escalate_unconfirmed_shifts": 20,
    "send_shift_check_in_requests": 20,
    "escalate_missed_check_ins": 20,
    "send_shift_reminders": 20,
}


def _priority_for(job_type: str) -> int:
    return JOB_PRIORITIES.get(job_type, 50)


def _retry_delay(attempt_count: int) -> timedelta:
    minutes = min(max(attempt_count, 1) * 5, 30)
    return timedelta(minutes=minutes)


async def _open_worker_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def enqueue_job(
    db: aiosqlite.Connection,
    *,
    job_type: str,
    payload: dict,
    location_id: Optional[int] = None,
    priority: Optional[int] = None,
    next_run_at: Optional[str] = None,
    max_attempts: int = 3,
    idempotency_key: Optional[str] = None,
) -> dict:
    job_id = await queries.insert_ops_job(
        db,
        {
            "job_type": job_type,
            "location_id": location_id,
            "priority": priority if priority is not None else _priority_for(job_type),
            "payload_json": payload,
            "next_run_at": next_run_at or datetime.utcnow().isoformat(),
            "max_attempts": max_attempts,
            "idempotency_key": idempotency_key,
        },
    )
    job = await queries.get_ops_job(db, job_id)
    assert job is not None
    return job


async def process_ops_job(
    db: aiosqlite.Connection,
    job_id: int,
) -> dict:
    job = await queries.get_ops_job(db, job_id)
    if job is None:
        raise ValueError(f"Ops job {job_id} not found")
    if job["status"] == "queued":
        claimed = await queries.claim_ops_job(db, job_id)
        if claimed is None:
            refreshed = await queries.get_ops_job(db, job_id)
            return {"status": refreshed["status"] if refreshed else "missing", "job_id": job_id}
        job = claimed
    if job["status"] != "running":
        return {"status": job["status"], "job_id": job_id}

    started_at = datetime.utcnow()
    payload = dict(job.get("payload_json") or {})
    job_type = str(job["job_type"])
    try:
        if job_type == "send_notification":
            from app.services import notifications as notifications_svc

            result = await notifications_svc.process_notification_job(
                db,
                notification_type=str(payload.get("notification_type") or ""),
                payload=dict(payload.get("payload") or {}),
            )
        elif job_type == "send_outreach_delivery":
            from app.services import outreach_jobs

            result = await outreach_jobs.process_outreach_job(
                db,
                attempt_id=int(payload["attempt_id"]),
                cascade_id=int(payload["cascade_id"]),
                shift_id=int(payload["shift_id"]),
                worker_id=int(payload["worker_id"]),
                tier=int(payload["tier"]),
                channel=str(payload["channel"]),
            )
        elif job_type == "run_due_backfill_shifts_automation":
            from app.services import backfill_shifts_automation as automation_svc

            result = await automation_svc.run_due_backfill_shifts_automation(
                db,
                **payload,
            )
        elif job_type == "send_due_manager_digests":
            from app.services import backfill_shifts_automation as automation_svc

            result = await automation_svc.send_due_manager_digests(
                db,
                **payload,
            )
        elif job_type == "send_shift_confirmation_requests":
            from app.services import backfill_shifts_automation as automation_svc

            result = await automation_svc.send_shift_confirmation_requests(
                db,
                **payload,
            )
        elif job_type == "escalate_unconfirmed_shifts":
            from app.services import backfill_shifts_automation as automation_svc

            result = await automation_svc.escalate_unconfirmed_shifts(
                db,
                **payload,
            )
        elif job_type == "send_shift_check_in_requests":
            from app.services import backfill_shifts_automation as automation_svc

            result = await automation_svc.send_shift_check_in_requests(
                db,
                **payload,
            )
        elif job_type == "escalate_missed_check_ins":
            from app.services import backfill_shifts_automation as automation_svc

            result = await automation_svc.escalate_missed_check_ins(
                db,
                **payload,
            )
        elif job_type == "send_shift_reminders":
            from app.services import backfill_shifts_automation as automation_svc

            result = await automation_svc.send_shift_reminders(
                db,
                **payload,
            )
        else:
            raise ValueError(f"Unsupported ops job type {job_type!r}")

        await queries.update_ops_job(
            db,
            job_id,
            {
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "last_error": None,
            },
        )
        return {
            "status": "completed",
            "job_id": job_id,
            "job_type": job_type,
            "result": result,
            "latency_ms": int((datetime.utcnow() - started_at).total_seconds() * 1000),
        }
    except Exception as exc:
        refreshed = await queries.get_ops_job(db, job_id)
        attempt_count = int(refreshed.get("attempt_count") or job.get("attempt_count") or 1) if refreshed else int(job.get("attempt_count") or 1)
        max_attempts = int(job.get("max_attempts") or 3)
        if attempt_count < max_attempts:
            await queries.update_ops_job(
                db,
                job_id,
                {
                    "status": "queued",
                    "next_run_at": (datetime.utcnow() + _retry_delay(attempt_count)).isoformat(),
                    "last_error": str(exc),
                    "started_at": None,
                },
            )
            return {
                "status": "queued_for_retry",
                "job_id": job_id,
                "job_type": job_type,
                "error": str(exc),
            }
        await queries.update_ops_job(
            db,
            job_id,
            {
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "last_error": str(exc),
            },
        )
        return {
            "status": "failed",
            "job_id": job_id,
            "job_type": job_type,
            "error": str(exc),
        }


async def process_due_jobs(
    db: aiosqlite.Connection,
    *,
    limit: int = 20,
) -> dict:
    claimed = await queries.claim_due_ops_jobs(db, limit=limit)
    results = []
    for job in claimed:
        results.append(await process_ops_job(db, int(job["id"])))
    return {
        "claimed_count": len(claimed),
        "processed_count": len(results),
        "results": results,
    }


async def worker_loop(
    *,
    stop_event: asyncio.Event,
    poll_seconds: Optional[float] = None,
    batch_limit: Optional[int] = None,
) -> None:
    interval = poll_seconds if poll_seconds is not None else settings.backfill_ops_worker_poll_seconds
    limit = batch_limit if batch_limit is not None else settings.backfill_ops_worker_batch_limit
    while not stop_event.is_set():
        try:
            db = await _open_worker_db()
            try:
                await process_due_jobs(db, limit=limit)
            finally:
                await db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Backfill ops worker loop failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
