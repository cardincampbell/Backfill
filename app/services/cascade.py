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
from datetime import datetime
from typing import Optional
import aiosqlite

from app.db.queries import (
    get_shift,
    get_cascade,
    update_cascade,
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
    position = cascade["current_position"]

    if tier == 1:
        workers = await _eligible_tier1_workers(db, shift, exclude_worker_id=shift.get("called_out_by"))
        if position >= len(workers):
            await update_cascade(db, cascade_id, current_tier=2, current_position=0)
            await audit_svc.append(
                db,
                AuditAction.tier_escalated,
                entity_type="cascade",
                entity_id=cascade_id,
                details={"shift_id": shift["id"], "from_tier": 1, "to_tier": 2},
            )
            return await advance(db, cascade_id)

        worker = workers[position]
        result = await _send_initial_outreach(db, cascade_id, worker, tier, shift)
        await update_cascade(db, cascade_id, current_position=position + 1)
        return {
            "status": "outreach_sent",
            "attempt_ids": result["attempt_ids"],
            "worker_id": worker["id"],
            "channels": result["channels"],
        }

    if tier == 2:
        workers = await _eligible_tier2_workers(db, shift, exclude_worker_id=shift.get("called_out_by"))
        if position >= len(workers):
            return await _mark_exhausted(db, cascade_id, shift, tier)

        worker = workers[position]
        result = await _send_initial_outreach(db, cascade_id, worker, tier, shift)
        await update_cascade(db, cascade_id, current_position=position + 1)
        return {
            "status": "outreach_sent",
            "attempt_ids": result["attempt_ids"],
            "worker_id": worker["id"],
            "channels": result["channels"],
        }

    if tier == 3:
        cascade = await get_cascade(db, cascade_id)
        requests = await list_agency_requests(db, cascade_id=cascade_id)
        if requests:
            return {"status": "agency_routed", "cascade_id": cascade_id, "requests": requests}
        if cascade and cascade.get("manager_approved_tier3"):
            return await agency_router.route_to_agencies(db, cascade_id=cascade_id, shift_id=shift["id"])
        return {"status": "awaiting_tier3_approval", "cascade_id": cascade_id}

    return await _mark_exhausted(db, cascade_id, shift, tier)


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
    from app.db.queries import update_outreach_outcome, update_cascade
    from app.services.shift_manager import mark_filled

    cascade = await get_cascade(db, cascade_id)
    shift_id = cascade["shift_id"]
    outcome = "accepted" if accepted else "declined"

    attempt_tier = cascade["current_tier"]
    # Find the most recent attempt for this worker in this cascade
    async with db.execute(
        """SELECT id, tier FROM outreach_attempts
           WHERE cascade_id=? AND worker_id=? ORDER BY id DESC LIMIT 1""",
        (cascade_id, worker_id),
    ) as cur:
        row = await cur.fetchone()

    if row:
        attempt_tier = row[1]
        await update_outreach_outcome(
            db,
            attempt_id=row[0],
            outcome=outcome,
            conversation_summary=summary,
        )

    await audit_svc.append(
        db,
        AuditAction.outreach_response,
        entity_type="cascade",
        entity_id=cascade_id,
        details={"worker_id": worker_id, "outcome": outcome, "shift_id": shift_id},
    )

    if accepted:
        fill_tier = "tier2_alumni" if attempt_tier == 2 else "tier1_internal"
        await mark_filled(
            db,
            shift_id=shift_id,
            filled_by_worker_id=worker_id,
            fill_tier=fill_tier,
        )
        await _update_behavioral_scores(db, worker_id)
        await update_cascade(db, cascade_id, status="completed")
    else:
        await _update_behavioral_scores(db, worker_id)
        await advance(db, cascade_id)
