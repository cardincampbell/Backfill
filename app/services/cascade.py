"""
Tiered cascade engine.

Outreach policy:
- Tier 1 targets internal staff ranked by priority.
- Tier 2 targets alumni workers who have worked this restaurant before.
- Only workers who match the shift role and certifications are contacted.
- The worker who called out is never contacted for the same vacancy.
- SMS is always the written offer when consent exists.
- For urgent shifts, voice is layered on immediately after SMS.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
import aiosqlite

from app.db.queries import (
    get_shift,
    get_cascade,
    update_cascade,
    update_outreach_attempt,
    list_workers_for_restaurant,
    list_workers_by_restaurants_worked,
    list_agency_requests,
    insert_outreach_attempt,
    get_restaurant,
)
from app.models.audit import AuditAction
from app.services import agency_router
from app.services import audit as audit_svc
from app.services import messaging
from app.services import notifications
from app.services import outreach as outreach_svc
from app.services import retell as retell_svc

BROADCAST_BATCH_SIZE = 5


async def advance(
    db: aiosqlite.Connection,
    cascade_id: int,
) -> dict:
    """
    Send the next outreach in the cascade. Returns the OutreachAttempt dict
    (or a status dict if the cascade is exhausted).
    """
    cascade = await get_cascade(db, cascade_id)
    if cascade is None:
        raise ValueError(f"Cascade {cascade_id} not found")

    if cascade["status"] != "active":
        return {"status": cascade["status"], "cascade_id": cascade_id}

    shift = await get_shift(db, cascade["shift_id"])
    tier = cascade["current_tier"]
    mode = cascade.get("outreach_mode") or "cascade"

    if tier in {1, 2}:
        workers = await _eligible_workers_for_tier(
            db,
            tier=tier,
            shift=shift,
            exclude_worker_id=shift.get("called_out_by"),
        )
        if _tier_is_exhausted(cascade, workers):
            if tier == 1:
                await _escalate_to_tier2(db, cascade_id, shift)
                return await advance(db, cascade_id)
            return await _mark_exhausted(db, cascade_id, shift, tier)

        if mode == "broadcast":
            return await _advance_broadcast(db, cascade_id, cascade, workers, tier, shift)
        return await _advance_sequential(db, cascade_id, cascade, workers, tier, shift)

    if tier == 3:
        cascade = await get_cascade(db, cascade_id)
        requests = await list_agency_requests(db, cascade_id=cascade_id)
        if requests:
            return {"status": "agency_routed", "cascade_id": cascade_id, "requests": requests}
        if cascade and cascade.get("manager_approved_tier3"):
            return await agency_router.route_to_agencies(db, cascade_id=cascade_id, shift_id=shift["id"])
        return {"status": "awaiting_tier3_approval", "cascade_id": cascade_id}

    return await _mark_exhausted(db, cascade_id, shift, tier)


def _tier_is_exhausted(cascade: dict, workers: list[dict]) -> bool:
    if (cascade.get("outreach_mode") or "cascade") == "broadcast":
        return cascade.get("current_batch", 0) * BROADCAST_BATCH_SIZE >= len(workers)
    return cascade.get("current_position", 0) >= len(workers)


async def _eligible_workers_for_tier(
    db: aiosqlite.Connection,
    tier: int,
    shift: dict,
    exclude_worker_id: Optional[int],
) -> list[dict]:
    if tier == 1:
        return await _eligible_tier1_workers(db, shift, exclude_worker_id=exclude_worker_id)
    if tier == 2:
        return await _eligible_tier2_workers(db, shift, exclude_worker_id=exclude_worker_id)
    return []


async def _escalate_to_tier2(db: aiosqlite.Connection, cascade_id: int, shift: dict) -> None:
    await update_cascade(db, cascade_id, current_tier=2, current_position=0, current_batch=0)
    await audit_svc.append(
        db,
        AuditAction.tier_escalated,
        entity_type="cascade",
        entity_id=cascade_id,
        details={"shift_id": shift["id"], "from_tier": 1, "to_tier": 2},
    )


async def _advance_sequential(
    db: aiosqlite.Connection,
    cascade_id: int,
    cascade: dict,
    workers: list[dict],
    tier: int,
    shift: dict,
) -> dict:
    position = cascade.get("current_position", 0)
    worker = workers[position]
    result = await _send_initial_outreach(db, cascade_id, worker, tier, shift)
    await update_cascade(db, cascade_id, current_position=position + 1)
    return {
        "status": "outreach_sent",
        "mode": "cascade",
        "attempt_ids": result["attempt_ids"],
        "worker_id": worker["id"],
        "channels": result["channels"],
    }


async def _advance_broadcast(
    db: aiosqlite.Connection,
    cascade_id: int,
    cascade: dict,
    workers: list[dict],
    tier: int,
    shift: dict,
) -> dict:
    batch = cascade.get("current_batch", 0)
    start = batch * BROADCAST_BATCH_SIZE
    selected = workers[start:start + BROADCAST_BATCH_SIZE]
    if not selected:
        return await _mark_exhausted(db, cascade_id, shift, tier)

    deliveries = []
    attempt_ids: list[int] = []
    for worker in selected:
        result = await _send_initial_outreach(db, cascade_id, worker, tier, shift)
        attempt_ids.extend(result["attempt_ids"])
        deliveries.append(
            {
                "worker_id": worker["id"],
                "channels": result["channels"],
                "attempt_ids": result["attempt_ids"],
            }
        )

    await update_cascade(db, cascade_id, current_batch=batch + 1)
    payload = {
        "status": "outreach_sent",
        "mode": "broadcast",
        "batch": batch + 1,
        "worker_ids": [worker["id"] for worker in selected],
        "attempt_ids": attempt_ids,
        "deliveries": deliveries,
    }
    if len(selected) == 1:
        payload["worker_id"] = selected[0]["id"]
        payload["channels"] = deliveries[0]["channels"]
    return payload


async def _eligible_tier1_workers(
    db: aiosqlite.Connection,
    shift: dict,
    exclude_worker_id: Optional[int],
) -> list[dict]:
    workers = await list_workers_for_restaurant(
        db, shift["restaurant_id"], active_consent_only=False
    )
    required_certs = set(shift.get("requirements") or [])
    eligible: list[dict] = []
    for worker in workers:
        if exclude_worker_id and worker["id"] == exclude_worker_id:
            continue
        if worker.get("worker_type") != "internal":
            continue
        if shift["role"] not in (worker.get("roles") or []):
            continue
        worker_certs = set(worker.get("certifications") or [])
        if not required_certs.issubset(worker_certs):
            continue
        if worker.get("sms_consent_status") != "granted" and worker.get("voice_consent_status") != "granted":
            continue
        eligible.append(worker)
    return eligible


async def _eligible_tier2_workers(
    db: aiosqlite.Connection,
    shift: dict,
    exclude_worker_id: Optional[int],
) -> list[dict]:
    # Query ALL workers whose restaurants_worked includes this restaurant —
    # alumni may have a different primary restaurant_id so list_workers_for_restaurant
    # would miss them.
    workers = await list_workers_by_restaurants_worked(db, shift["restaurant_id"])
    required_certs = set(shift.get("requirements") or [])
    eligible: list[dict] = []
    for worker in workers:
        if exclude_worker_id and worker["id"] == exclude_worker_id:
            continue
        if worker.get("worker_type") != "alumni":
            continue
        if shift["role"] not in (worker.get("roles") or []):
            continue
        worker_certs = set(worker.get("certifications") or [])
        if not required_certs.issubset(worker_certs):
            continue
        if worker.get("sms_consent_status") != "granted" and worker.get("voice_consent_status") != "granted":
            continue
        eligible.append(worker)
    eligible.sort(key=_tier2_sort_key, reverse=True)
    return eligible


def _tier2_sort_key(worker: dict) -> tuple:
    return (
        float(worker.get("show_up_rate") or 0),
        float(worker.get("acceptance_rate") or 0),
        float(worker.get("response_rate") or 0),
        float(worker.get("rating") or 0),
        int(worker.get("total_shifts_filled") or 0),
        -int(worker.get("priority_rank") or 9999),
    )


async def _send_initial_outreach(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker: dict,
    tier: int,
    shift: dict,
) -> dict:
    restaurant = await get_restaurant(db, shift["restaurant_id"])
    channels = outreach_svc.plan_initial_channels(shift, worker)
    if not channels:
        return {"attempt_ids": [], "channels": []}

    metadata = {
        "cascade_id": cascade_id,
        "worker_id": worker["id"],
        "shift_id": shift["id"],
        "role": shift["role"],
        "date": shift["date"],
        "start_time": shift["start_time"],
        "end_time": shift["end_time"],
        "pay_rate": shift["pay_rate"],
    }
    attempt_ids: list[int] = []

    if "sms" in channels:
        sms_sid = messaging.send_sms(
            worker["phone"],
            outreach_svc.build_initial_sms(worker, shift, restaurant),
        )
        attempt_id = await insert_outreach_attempt(
            db,
            {
                "cascade_id": cascade_id,
                "worker_id": worker["id"],
                "tier": tier,
                "channel": "sms",
                "status": "sent",
                "sent_at": datetime.utcnow().isoformat(),
            },
        )
        attempt_ids.append(attempt_id)
        await audit_svc.append(
            db,
            AuditAction.outreach_sent,
            entity_type="outreach_attempt",
            entity_id=attempt_id,
            details={
                "worker_id": worker["id"],
                "shift_id": shift["id"],
                "tier": tier,
                "channel": "sms",
                "message_sid": sms_sid,
            },
        )

    if "voice" in channels:
        call_id = await retell_svc.create_phone_call(
            to_number=worker["phone"],
            metadata=metadata,
        )
        attempt_id = await insert_outreach_attempt(
            db,
            {
                "cascade_id": cascade_id,
                "worker_id": worker["id"],
                "tier": tier,
                "channel": "voice",
                "status": "sent",
                "sent_at": datetime.utcnow().isoformat(),
            },
        )
        attempt_ids.append(attempt_id)
        await audit_svc.append(
            db,
            AuditAction.outreach_sent,
            entity_type="outreach_attempt",
            entity_id=attempt_id,
            details={
                "worker_id": worker["id"],
                "shift_id": shift["id"],
                "tier": tier,
                "channel": "voice",
                "call_id": call_id,
            },
        )

    return {"attempt_ids": attempt_ids, "channels": channels}


async def _latest_attempt_for_worker(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
):
    async with db.execute(
        """SELECT id, tier, channel, status, outcome, standby_position
           FROM outreach_attempts
           WHERE cascade_id=? AND worker_id=?
           ORDER BY id DESC LIMIT 1""",
        (cascade_id, worker_id),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def _attempt_ids_for_worker(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
) -> list[int]:
    async with db.execute(
        """SELECT id
           FROM outreach_attempts
           WHERE cascade_id=? AND worker_id=?
           ORDER BY id DESC""",
        (cascade_id, worker_id),
    ) as cur:
        rows = await cur.fetchall()
    return [row["id"] for row in rows]


def _fill_tier_for_attempt(tier: int) -> str:
    return "tier2_alumni" if tier == 2 else "tier1_internal"


async def claim_shift(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
    summary: str = "",
) -> dict:
    from app.services.shift_manager import mark_filled

    cascade = await get_cascade(db, cascade_id)
    if cascade is None:
        raise ValueError(f"Cascade {cascade_id} not found")

    shift = await get_shift(db, cascade["shift_id"])
    if shift is None:
        raise ValueError(f"Shift {cascade['shift_id']} not found")

    attempt = await _latest_attempt_for_worker(db, cascade_id, worker_id)
    if attempt is None:
        raise ValueError(f"No outreach attempt found for worker {worker_id} in cascade {cascade_id}")

    now = datetime.utcnow().isoformat()
    confirmed_worker_id = cascade.get("confirmed_worker_id") or shift.get("filled_by")

    if confirmed_worker_id and confirmed_worker_id != worker_id:
        standby_queue = list(cascade.get("standby_queue") or [])
        if worker_id in standby_queue:
            return {
                "status": "standby",
                "worker_id": worker_id,
                "standby_position": standby_queue.index(worker_id) + 1,
                "idempotent": True,
            }

        standby_position = len(standby_queue) + 1
        standby_queue.append(worker_id)
        await update_cascade(db, cascade_id, standby_queue=standby_queue)
        for attempt_id in await _attempt_ids_for_worker(db, cascade_id, worker_id):
            await update_outreach_attempt(
                db,
                attempt_id,
                outcome="standby",
                status="responded",
                standby_position=standby_position,
                responded_at=now,
                conversation_summary=summary,
            )
        await audit_svc.append(
            db,
            AuditAction.outreach_response,
            entity_type="cascade",
            entity_id=cascade_id,
            details={"worker_id": worker_id, "outcome": "standby", "shift_id": shift["id"], "standby_position": standby_position},
        )
        await _update_behavioral_scores(db, worker_id)
        return {"status": "standby", "worker_id": worker_id, "standby_position": standby_position}

    if confirmed_worker_id == worker_id:
        return {"status": "confirmed", "worker_id": worker_id, "idempotent": True}

    for attempt_id in await _attempt_ids_for_worker(db, cascade_id, worker_id):
        await update_outreach_attempt(
            db,
            attempt_id,
            outcome="confirmed",
            status="responded",
            responded_at=now,
            conversation_summary=summary,
        )
    await mark_filled(
        db,
        shift_id=shift["id"],
        filled_by_worker_id=worker_id,
        fill_tier=_fill_tier_for_attempt(attempt["tier"]),
    )
    await update_cascade(db, cascade_id, status="completed", confirmed_worker_id=worker_id)
    await audit_svc.append(
        db,
        AuditAction.outreach_response,
        entity_type="cascade",
        entity_id=cascade_id,
        details={"worker_id": worker_id, "outcome": "confirmed", "shift_id": shift["id"]},
    )
    await _update_behavioral_scores(db, worker_id)
    return {"status": "confirmed", "worker_id": worker_id}


async def decline_shift(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
    summary: str = "",
) -> dict:
    cascade = await get_cascade(db, cascade_id)
    if cascade is None:
        raise ValueError(f"Cascade {cascade_id} not found")

    shift = await get_shift(db, cascade["shift_id"])
    attempt = await _latest_attempt_for_worker(db, cascade_id, worker_id)
    if attempt is None:
        raise ValueError(f"No outreach attempt found for worker {worker_id} in cascade {cascade_id}")

    for attempt_id in await _attempt_ids_for_worker(db, cascade_id, worker_id):
        await update_outreach_attempt(
            db,
            attempt_id,
            outcome="declined",
            status="responded",
            responded_at=datetime.utcnow().isoformat(),
            conversation_summary=summary,
        )
    await audit_svc.append(
        db,
        AuditAction.outreach_response,
        entity_type="cascade",
        entity_id=cascade_id,
        details={"worker_id": worker_id, "outcome": "declined", "shift_id": shift["id"] if shift else None},
    )
    await _update_behavioral_scores(db, worker_id)

    if (cascade.get("outreach_mode") or "cascade") == "cascade" and cascade["status"] == "active":
        return await advance(db, cascade_id)
    if cascade["status"] == "active" and await _broadcast_batch_fully_resolved(db, cascade_id):
        return await advance(db, cascade_id)
    return {"status": "declined", "worker_id": worker_id}


async def cancel_standby(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
    summary: str = "",
) -> dict:
    cascade = await get_cascade(db, cascade_id)
    if cascade is None:
        raise ValueError(f"Cascade {cascade_id} not found")

    standby_queue = list(cascade.get("standby_queue") or [])
    if worker_id not in standby_queue:
        return {"status": "not_on_standby", "worker_id": worker_id}

    standby_queue.remove(worker_id)
    await update_cascade(db, cascade_id, standby_queue=standby_queue)

    attempt = await _latest_attempt_for_worker(db, cascade_id, worker_id)
    if attempt:
        for attempt_id in await _attempt_ids_for_worker(db, cascade_id, worker_id):
            await update_outreach_attempt(
                db,
                attempt_id,
                outcome="standby_expired",
                status="responded",
                standby_position=None,
                responded_at=datetime.utcnow().isoformat(),
                conversation_summary=summary,
            )

    await _resequence_standby_positions(db, cascade_id, standby_queue)
    return {"status": "standby_cancelled", "worker_id": worker_id}


async def promote_standby(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
    summary: str = "",
) -> dict:
    from app.services.shift_manager import mark_filled

    cascade = await get_cascade(db, cascade_id)
    if cascade is None:
        raise ValueError(f"Cascade {cascade_id} not found")

    standby_queue = list(cascade.get("standby_queue") or [])
    if not standby_queue or standby_queue[0] != worker_id:
        return {"status": "promotion_rejected", "worker_id": worker_id}

    shift = await get_shift(db, cascade["shift_id"])
    attempt = await _latest_attempt_for_worker(db, cascade_id, worker_id)
    if shift is None or attempt is None:
        raise ValueError("Standby promotion is missing shift or attempt context")

    remaining = standby_queue[1:]
    promoted_at = datetime.utcnow().isoformat()
    for attempt_id in await _attempt_ids_for_worker(db, cascade_id, worker_id):
        await update_outreach_attempt(
            db,
            attempt_id,
            outcome="promoted",
            status="responded",
            promoted_at=promoted_at,
            responded_at=promoted_at,
            conversation_summary=summary,
        )
    await mark_filled(
        db,
        shift_id=shift["id"],
        filled_by_worker_id=worker_id,
        fill_tier=_fill_tier_for_attempt(attempt["tier"]),
    )
    await update_cascade(
        db,
        cascade_id,
        status="completed",
        confirmed_worker_id=worker_id,
        standby_queue=remaining,
    )
    await _resequence_standby_positions(db, cascade_id, remaining)
    await _update_behavioral_scores(db, worker_id)
    return {"status": "confirmed", "worker_id": worker_id, "promoted": True}


async def _resequence_standby_positions(
    db: aiosqlite.Connection,
    cascade_id: int,
    standby_queue: list[int],
) -> None:
    for index, worker_id in enumerate(standby_queue, start=1):
        for attempt_id in await _attempt_ids_for_worker(db, cascade_id, worker_id):
            await update_outreach_attempt(db, attempt_id, standby_position=index)


async def _broadcast_batch_fully_resolved(
    db: aiosqlite.Connection,
    cascade_id: int,
) -> bool:
    cascade = await get_cascade(db, cascade_id)
    if not cascade or (cascade.get("outreach_mode") or "cascade") != "broadcast":
        return False
    if cascade.get("confirmed_worker_id"):
        return False

    async with db.execute(
        """SELECT worker_id, status, outcome
           FROM outreach_attempts
           WHERE cascade_id=?
           ORDER BY worker_id ASC, id DESC""",
        (cascade_id,),
    ) as cur:
        rows = await cur.fetchall()

    latest_by_worker: dict[int, dict] = {}
    for row in rows:
        worker_id = row["worker_id"]
        if worker_id not in latest_by_worker:
            latest_by_worker[worker_id] = dict(row)

    if not latest_by_worker:
        return False

    unresolved_statuses = {"pending", "sent", "delivered"}
    terminal_outcomes = {"declined", "no_response", "standby_expired"}
    positive_outcomes = {"confirmed", "standby", "promoted"}

    for attempt in latest_by_worker.values():
        if attempt.get("outcome") in positive_outcomes:
            return False
        if attempt.get("status") in unresolved_statuses and attempt.get("outcome") is None:
            return False
        if attempt.get("outcome") not in terminal_outcomes and attempt.get("outcome") is not None:
            return False

    return True


async def _mark_exhausted(
    db: aiosqlite.Connection,
    cascade_id: int,
    shift: dict,
    tier: int,
) -> dict:
    cascade = await get_cascade(db, cascade_id)
    restaurant = await get_restaurant(db, shift["restaurant_id"])
    if tier >= 2 and restaurant and restaurant.get("agency_supply_approved"):
        await update_cascade(db, cascade_id, current_tier=3)
        if cascade and cascade.get("manager_approved_tier3"):
            return await agency_router.route_to_agencies(db, cascade_id=cascade_id, shift_id=shift["id"])
        if restaurant.get("manager_phone"):
            notifications.notify_cascade_exhausted(
                manager_phone=restaurant["manager_phone"],
                role=shift["role"],
                date=shift["date"],
                start_time=shift["start_time"],
            )
            await audit_svc.append(
                db,
                AuditAction.manager_notified,
                entity_type="shift",
                entity_id=shift["id"],
                details={"filled": False, "manager_phone": restaurant["manager_phone"], "tier3_approval_requested": True},
            )
        return {"status": "awaiting_tier3_approval", "cascade_id": cascade_id}

    await update_cascade(db, cascade_id, status="exhausted")
    await audit_svc.append(
        db,
        AuditAction.cascade_exhausted,
        entity_type="cascade",
        entity_id=cascade_id,
        details={"shift_id": shift["id"], "final_tier": tier},
    )
    if restaurant and restaurant.get("manager_phone"):
        notifications.notify_cascade_exhausted(
            manager_phone=restaurant["manager_phone"],
            role=shift["role"],
            date=shift["date"],
            start_time=shift["start_time"],
        )
        await audit_svc.append(
            db,
            AuditAction.manager_notified,
            entity_type="shift",
            entity_id=shift["id"],
            details={"filled": False, "manager_phone": restaurant["manager_phone"]},
        )
    return {"status": "exhausted", "cascade_id": cascade_id}


async def _update_behavioral_scores(
    db: aiosqlite.Connection,
    worker_id: int,
) -> None:
    """Recalculate behavioral metrics from stored outreach history."""
    from app.db.queries import get_worker, get_worker_outreach_metrics, update_worker

    worker = await get_worker(db, worker_id)
    if worker is None:
        return

    metrics = await get_worker_outreach_metrics(db, worker_id)
    total_attempts = metrics["total_attempts"]
    total_responses = metrics["total_responses"]
    total_acceptances = metrics["total_acceptances"]
    total_filled = int(worker.get("total_shifts_filled") or 0)

    new_response_rate = round(total_responses / total_attempts, 4) if total_attempts else 0.0
    new_acceptance_rate = round(total_acceptances / total_responses, 4) if total_responses else 0.0
    new_show_up_rate = round(min(total_filled / total_acceptances, 1.0), 4) if total_acceptances else 0.0

    await update_worker(db, worker_id, {
        "response_rate": new_response_rate,
        "acceptance_rate": new_acceptance_rate,
        "show_up_rate": new_show_up_rate,
    })


async def record_response(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
    accepted: bool,
    summary: str = "",
) -> None:
    """Called when the Retell agent reports a worker's response."""
    if accepted:
        await claim_shift(db, cascade_id, worker_id, summary=summary)
        return
    await decline_shift(db, cascade_id, worker_id, summary=summary)
