"""
Caller lookup — resolve an inbound phone number to a known worker or manager.
Used by the Retell webhook when a call comes in to 1-800-BACKFILL.
"""
from typing import Optional
import aiosqlite

from app.db.queries import get_worker_by_phone, get_restaurant_by_name
from app.models.audit import AuditAction
from app.services import audit as audit_svc


async def lookup(
    db: aiosqlite.Connection, phone: str
) -> dict:
    """
    Returns a dict with:
        found: bool
        caller_type: 'worker' | 'manager' | 'unknown'
        record: the matched worker or restaurant dict (or None)
    """
    worker = await get_worker_by_phone(db, phone)
    if worker:
        await audit_svc.append(
            db,
            AuditAction.caller_lookup,
            entity_type="worker",
            entity_id=worker["id"],
            details={"phone": phone, "result": "worker_found"},
        )
        return {"found": True, "caller_type": "worker", "record": worker}

    # Check if the phone matches a restaurant manager
    async with db.execute(
        "SELECT * FROM restaurants WHERE manager_phone=?", (phone,)
    ) as cur:
        row = await cur.fetchone()
    if row:
        restaurant = dict(row)
        await audit_svc.append(
            db,
            AuditAction.caller_lookup,
            entity_type="restaurant",
            entity_id=restaurant["id"],
            details={"phone": phone, "result": "manager_found"},
        )
        return {"found": True, "caller_type": "manager", "record": restaurant}

    await audit_svc.append(
        db,
        AuditAction.caller_lookup,
        details={"phone": phone, "result": "unknown"},
    )
    return {"found": False, "caller_type": "unknown", "record": None}
