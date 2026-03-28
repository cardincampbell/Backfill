"""
Shift lifecycle management.

Handles:
  - Marking a shift as vacant (worker calls out)
  - Marking a shift as filled
  - Triggering the cascade when a vacancy is created
"""
from __future__ import annotations

import aiosqlite
from typing import Optional

from app.db.queries import (
    get_shift,
    get_worker,
    update_shift_status,
    update_worker,
    insert_cascade,
    get_active_cascade_for_shift,
)
from app.models.audit import AuditAction
from app.services import audit as audit_svc
from app.services.outreach import hours_until_shift


async def create_vacancy(
    db: aiosqlite.Connection,
    shift_id: int,
    called_out_by_worker_id: Optional[int],
    actor: str = "system",
) -> dict:
    """
    Mark the shift as vacant, create a Cascade record, kick off fill engine.
    Returns the new cascade dict.
    """
    shift = await get_shift(db, shift_id)
    if shift is None:
        raise ValueError(f"Shift {shift_id} not found")

    existing = await get_active_cascade_for_shift(db, shift_id)
    if existing:
        return existing

    await update_shift_status(
        db,
        shift_id=shift_id,
        status="vacant",
        called_out_by=called_out_by_worker_id,
    )

    await audit_svc.append(
        db,
        AuditAction.vacancy_created,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={"called_out_by": called_out_by_worker_id},
    )

    outreach_mode = "broadcast" if hours_until_shift(shift) <= 4 else "cascade"
    cascade_id = await insert_cascade(db, shift_id, outreach_mode=outreach_mode)
    await audit_svc.append(
        db,
        AuditAction.cascade_started,
        actor="system",
        entity_type="cascade",
        entity_id=cascade_id,
        details={"shift_id": shift_id, "outreach_mode": outreach_mode},
    )

    return {
        "id": cascade_id,
        "shift_id": shift_id,
        "status": "active",
        "outreach_mode": outreach_mode,
        "current_tier": 1,
        "current_batch": 0,
        "current_position": 0,
        "confirmed_worker_id": None,
        "standby_queue": [],
    }


async def mark_filled(
    db: aiosqlite.Connection,
    shift_id: int,
    filled_by_worker_id: int,
    fill_tier: str,
    actor: str = "system",
) -> None:
    await update_shift_status(
        db,
        shift_id=shift_id,
        status="filled",
        filled_by=filled_by_worker_id,
        fill_tier=fill_tier,
    )

    # Increment total_shifts_filled and append the filled location to work history if new.
    await db.execute(
        "UPDATE workers SET total_shifts_filled = COALESCE(total_shifts_filled, 0) + 1 WHERE id=?",
        (filled_by_worker_id,),
    )
    await db.commit()

    shift = await get_shift(db, shift_id)
    location_id = shift["location_id"] if shift else None
    if location_id is not None:
        worker = await get_worker(db, filled_by_worker_id)
        if worker:
            worked = list(worker.get("locations_worked") or [])
            if location_id not in worked:
                worked.append(location_id)
                await update_worker(db, filled_by_worker_id, {"locations_worked": worked})

    await audit_svc.append(
        db,
        AuditAction.shift_filled,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={"filled_by": filled_by_worker_id, "fill_tier": fill_tier},
    )

    from app.services import sync_engine

    try:
        await sync_engine.enqueue_writeback(db, shift_id=shift_id)
    except Exception:
        # Scheduler write-back is best-effort; the local Backfill record remains
        # authoritative even if the external platform update fails.
        import logging

        logging.getLogger(__name__).warning(
            "Failed to enqueue writeback for shift %s — external platform will not be updated",
            shift_id,
            exc_info=True,
        )
