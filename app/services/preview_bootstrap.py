from __future__ import annotations

from datetime import date, timedelta

import aiosqlite

from app.db import queries
from app.services import backfill_shifts as backfill_shifts_svc


PREVIEW_TEAM: dict[str, list[str]] = {
    "Cashier": [
        "Beth Davies",
        "Bryan Wright",
        "Chris Nidoo",
        "Danielle Booker",
    ],
    "Floor Lead": [
        "Charlotte Dean",
        "Morgan Chen",
        "Priya Shah",
    ],
}


PREVIEW_SHIFT_BLUEPRINT: list[dict[str, object]] = [
    {"role": "Cashier", "day": 0, "start": "08:00:00", "end": "16:00:00", "worker_index": None},
    {"role": "Cashier", "day": 0, "start": "12:00:00", "end": "20:00:00", "worker_index": 1},
    {"role": "Cashier", "day": 1, "start": "08:00:00", "end": "16:00:00", "worker_index": 0},
    {"role": "Cashier", "day": 1, "start": "12:00:00", "end": "20:00:00", "worker_index": 2},
    {"role": "Cashier", "day": 2, "start": "08:00:00", "end": "16:00:00", "worker_index": 3},
    {"role": "Cashier", "day": 2, "start": "12:00:00", "end": "20:00:00", "worker_index": None},
    {"role": "Cashier", "day": 3, "start": "08:00:00", "end": "16:00:00", "worker_index": 0},
    {"role": "Cashier", "day": 3, "start": "12:00:00", "end": "20:00:00", "worker_index": 1},
    {"role": "Cashier", "day": 4, "start": "08:00:00", "end": "16:00:00", "worker_index": 2},
    {"role": "Cashier", "day": 4, "start": "12:00:00", "end": "20:00:00", "worker_index": 3},
    {"role": "Cashier", "day": 5, "start": "09:00:00", "end": "17:00:00", "worker_index": None},
    {"role": "Cashier", "day": 5, "start": "13:00:00", "end": "21:00:00", "worker_index": 1},
    {"role": "Cashier", "day": 6, "start": "09:00:00", "end": "17:00:00", "worker_index": 0},
    {"role": "Floor Lead", "day": 0, "start": "07:00:00", "end": "15:00:00", "worker_index": 0},
    {"role": "Floor Lead", "day": 1, "start": "09:00:00", "end": "17:00:00", "worker_index": 1},
    {"role": "Floor Lead", "day": 2, "start": "08:00:00", "end": "16:00:00", "worker_index": None},
    {"role": "Floor Lead", "day": 3, "start": "09:00:00", "end": "17:00:00", "worker_index": 2},
    {"role": "Floor Lead", "day": 4, "start": "08:00:00", "end": "16:00:00", "worker_index": 0},
    {"role": "Floor Lead", "day": 5, "start": "10:00:00", "end": "18:00:00", "worker_index": 1},
    {"role": "Floor Lead", "day": 6, "start": "10:00:00", "end": "18:00:00", "worker_index": None},
]


def _current_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def _preview_phone_number(location_id: int, worker_index: int) -> str:
    local_number = 2_000_000_000 + (location_id * 100) + worker_index
    return f"+1{local_number}"


async def bootstrap_preview_location(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    actor: str = "preview_bootstrap",
) -> dict:
    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError("Location not found")

    latest_schedule = await queries.get_latest_schedule_for_location(db, location_id)
    if latest_schedule is not None:
        existing_shifts = await queries.list_shifts(db, schedule_id=int(latest_schedule["id"]))
        if existing_shifts:
            existing_workers = await queries.list_workers(db, location_id=location_id)
            return {
                "location_id": location_id,
                "schedule_id": int(latest_schedule["id"]),
                "week_start_date": latest_schedule["week_start_date"],
                "worker_count": len(existing_workers),
                "shift_count": len(existing_shifts),
                "idempotent": True,
            }

    existing_workers = await queries.list_workers(db, location_id=location_id)
    role_workers: dict[str, list[int]] = {}
    next_worker_index = len(existing_workers)

    for role, names in PREVIEW_TEAM.items():
        role_workers[role] = []
        for priority, name in enumerate(names, start=1):
            existing = next(
                (
                    worker
                    for worker in existing_workers
                    if worker.get("name") == name and role in (worker.get("roles") or [])
                ),
                None,
            )
            if existing is not None:
                role_workers[role].append(int(existing["id"]))
                continue

            worker_id = await queries.insert_worker(
                db,
                {
                    "name": name,
                    "phone": _preview_phone_number(location_id, next_worker_index),
                    "roles": [role],
                    "location_id": location_id,
                    "priority_rank": priority,
                    "source": "preview_bootstrap",
                    "preferred_channel": "sms",
                    "sms_consent_status": "enrolled",
                    "voice_consent_status": "enrolled",
                    "employment_status": "active",
                },
            )
            role_workers[role].append(worker_id)
            next_worker_index += 1

    week_start = _current_monday()
    week_start_iso = week_start.isoformat()
    schedule = await queries.get_schedule_by_location_week(db, location_id, week_start_iso)
    if schedule is None:
        schedule_id = await queries.insert_schedule(
            db,
            {
                "location_id": location_id,
                "week_start_date": week_start_iso,
                "week_end_date": (week_start + timedelta(days=6)).isoformat(),
                "lifecycle_state": "draft",
                "created_by": actor,
            },
        )
        schedule = await queries.get_schedule(db, schedule_id)

    assert schedule is not None

    created_shift_count = 0
    for item in PREVIEW_SHIFT_BLUEPRINT:
        role = str(item["role"])
        worker_index = item.get("worker_index")
        worker_id = None
        if isinstance(worker_index, int):
            role_worker_ids = role_workers.get(role) or []
            if worker_index < len(role_worker_ids):
                worker_id = role_worker_ids[worker_index]

        await backfill_shifts_svc.create_schedule_shift(
            db,
            schedule_id=int(schedule["id"]),
            actor=actor,
            shift_payload={
                "role": role,
                "date": (week_start + timedelta(days=int(item["day"]))).isoformat(),
                "start_time": str(item["start"]),
                "end_time": str(item["end"]),
                "pay_rate": 22.0 if role == "Cashier" else 28.0,
                "worker_id": worker_id,
                "notes": "Preview shift",
                "shift_label": "Preview",
            },
        )
        created_shift_count += 1

    return {
        "location_id": location_id,
        "schedule_id": int(schedule["id"]),
        "week_start_date": week_start_iso,
        "worker_count": sum(len(names) for names in PREVIEW_TEAM.values()),
        "shift_count": created_shift_count,
        "idempotent": False,
    }
