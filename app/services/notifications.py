"""
Manager notification service.
"""
from typing import Optional

import aiosqlite

from app.services.messaging import send_sms


def notify_shift_filled(
    manager_phone: str,
    worker_name: str,
    role: str,
    date: str,
    start_time: str,
    fill_tier: str,
) -> Optional[str]:
    """Send an SMS to the manager confirming coverage. Returns Twilio SID."""
    tier_label = {
        "tier1_internal": "one of your staff members",
        "tier2_alumni": "a trusted prior worker",
        "tier3_agency": "a partner agency worker",
    }.get(fill_tier, "a worker")

    body = (
        f"✅ Backfill: Your {role} shift on {date} at {start_time} "
        f"has been covered by {worker_name} ({tier_label}). "
        f"Reply STATUS to check coverage anytime."
    )
    return send_sms(manager_phone, body)


def notify_cascade_exhausted(
    manager_phone: str,
    role: str,
    date: str,
    start_time: str,
) -> Optional[str]:
    """Notify manager that no internal coverage was found."""
    body = (
        f"⚠️ Backfill: We couldn't find internal coverage for your "
        f"{role} shift on {date} at {start_time}. "
        f"Reply AGENCY to approve routing to a partner staffing agency, "
        f"or call 1-800-BACKFILL to handle manually."
    )
    return send_sms(manager_phone, body)


async def fire_manager_notification(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
    filled: bool,
) -> None:
    """Shared helper: notify manager of fill or exhaustion. Used by retell_hooks and twilio_hooks."""
    from app.db.queries import get_cascade, get_shift, get_worker, get_restaurant
    from app.models.audit import AuditAction
    from app.services import audit as audit_svc

    cascade = await get_cascade(db, cascade_id)
    if not cascade:
        return
    shift = await get_shift(db, cascade["shift_id"])
    if not shift:
        return
    restaurant = await get_restaurant(db, shift["restaurant_id"])
    if not restaurant or not restaurant.get("manager_phone"):
        return

    if filled:
        worker = await get_worker(db, worker_id)
        notify_shift_filled(
            manager_phone=restaurant["manager_phone"],
            worker_name=worker["name"] if worker else "a worker",
            role=shift["role"],
            date=shift["date"],
            start_time=shift["start_time"],
            fill_tier=shift.get("fill_tier") or "tier1_internal",
        )
    else:
        notify_cascade_exhausted(
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
        details={"filled": filled, "manager_phone": restaurant["manager_phone"]},
    )
