from __future__ import annotations

from datetime import datetime
from typing import Optional

import aiosqlite

from app.config import settings
from app.db import queries
from app.models.audit import AuditAction
from app.services import audit as audit_svc
from app.services import messaging
from app.services import outreach as outreach_svc
from app.services import retell as retell_svc


async def queue_outreach_delivery(
    db: aiosqlite.Connection,
    *,
    attempt_id: int,
    cascade_id: int,
    shift_id: int,
    worker_id: int,
    tier: int,
    channel: str,
    location_id: Optional[int] = None,
) -> dict:
    if not settings.backfill_ops_worker_enabled:
        result = await process_outreach_job(
            db,
            attempt_id=attempt_id,
            cascade_id=cascade_id,
            shift_id=shift_id,
            worker_id=worker_id,
            tier=tier,
            channel=channel,
        )
        result["delivery_mode"] = "inline"
        return result

    from app.services import ops_queue

    job = await ops_queue.enqueue_job(
        db,
        job_type="send_outreach_delivery",
        location_id=location_id,
        payload={
            "attempt_id": int(attempt_id),
            "cascade_id": int(cascade_id),
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
            "tier": int(tier),
            "channel": str(channel),
        },
        idempotency_key=f"outreach_delivery:{attempt_id}",
        max_attempts=3,
    )
    return {
        "status": "queued",
        "delivery_mode": "queued",
        "job_id": int(job["id"]),
        "attempt_id": int(attempt_id),
        "channel": str(channel),
    }


async def process_outreach_job(
    db: aiosqlite.Connection,
    *,
    attempt_id: int,
    cascade_id: int,
    shift_id: int,
    worker_id: int,
    tier: int,
    channel: str,
) -> dict:
    attempt = await queries.get_outreach_attempt(db, attempt_id)
    if attempt is None:
        return {"status": "missing_attempt", "attempt_id": attempt_id}
    if attempt.get("status") == "sent":
        return {
            "status": "sent",
            "attempt_id": attempt_id,
            "channel": channel,
            "idempotent": True,
        }
    if attempt.get("status") in {"cancelled", "failed"}:
        return {
            "status": str(attempt.get("status")),
            "attempt_id": attempt_id,
            "channel": channel,
            "idempotent": True,
        }

    cascade = await queries.get_cascade(db, cascade_id)
    if cascade is None or cascade.get("status") != "active":
        await queries.update_outreach_attempt(db, attempt_id, status="cancelled")
        return {
            "status": "cancelled",
            "attempt_id": attempt_id,
            "channel": channel,
            "reason": "cascade_inactive",
        }

    shift = await queries.get_shift(db, shift_id)
    worker = await queries.get_worker(db, worker_id)
    if shift is None or worker is None or not worker.get("phone"):
        await queries.update_outreach_attempt(db, attempt_id, status="failed")
        return {
            "status": "failed",
            "attempt_id": attempt_id,
            "channel": channel,
            "reason": "missing_context",
        }

    location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
    metadata = {
        "cascade_id": cascade_id,
        "worker_id": worker_id,
        "shift_id": shift_id,
        "vacancy_kind": outreach_svc.vacancy_kind(shift),
        "role": shift.get("role"),
        "date": shift.get("date"),
        "start_time": shift.get("start_time"),
        "end_time": shift.get("end_time"),
        "pay_rate": shift.get("pay_rate"),
    }

    if channel == "sms":
        message_sid = messaging.send_sms(
            str(worker["phone"]),
            outreach_svc.build_initial_sms(worker, shift, location),
            metadata=metadata,
        )
        await queries.update_outreach_attempt(
            db,
            attempt_id,
            status="sent",
            sent_at=datetime.utcnow().isoformat(),
        )
        await audit_svc.append(
            db,
            AuditAction.outreach_sent,
            entity_type="outreach_attempt",
            entity_id=attempt_id,
            details={
                "worker_id": worker_id,
                "shift_id": shift_id,
                "tier": tier,
                "channel": "sms",
                "message_sid": message_sid,
                "chat_id": message_sid if settings.retell_sms_enabled and str(message_sid).startswith("chat_") else None,
            },
        )
        return {
            "status": "sent",
            "attempt_id": attempt_id,
            "channel": channel,
            "message_sid": message_sid,
        }

    if channel == "voice":
        call_id = await retell_svc.create_phone_call(
            to_number=str(worker["phone"]),
            metadata=metadata,
        )
        await queries.update_outreach_attempt(
            db,
            attempt_id,
            status="sent",
            sent_at=datetime.utcnow().isoformat(),
        )
        await audit_svc.append(
            db,
            AuditAction.outreach_sent,
            entity_type="outreach_attempt",
            entity_id=attempt_id,
            details={
                "worker_id": worker_id,
                "shift_id": shift_id,
                "tier": tier,
                "channel": "voice",
                "call_id": call_id,
            },
        )
        return {
            "status": "sent",
            "attempt_id": attempt_id,
            "channel": channel,
            "call_id": call_id,
        }

    await queries.update_outreach_attempt(db, attempt_id, status="failed")
    raise ValueError(f"Unsupported outreach channel {channel!r}")
