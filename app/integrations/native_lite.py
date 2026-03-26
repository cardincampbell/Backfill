"""
Backfill Native Lite adapter — the built-in system of record.

Used when:
  - The location has no scheduling software
  - The scheduler is read-only (Homebase)

All writes go directly to the Backfill SQLite database.
This adapter is always available and is the default.
"""
from __future__ import annotations

from app.integrations.base import SchedulingAdapter
from app.db import queries


class NativeLiteAdapter(SchedulingAdapter):

    def __init__(self, db):
        self.db = db

    async def sync_roster(self, location_id: int) -> list[dict]:
        return await queries.list_workers_for_location(
            self.db, location_id, active_consent_only=False
        )

    async def sync_schedule(self, location_id: int, date_range: tuple) -> list[dict]:
        start, end = date_range
        shifts = await queries.list_shifts(self.db, location_id=location_id)
        return [
            shift
            for shift in shifts
            if str(start) <= str(shift.get("date") or "") <= str(end)
        ]

    async def on_vacancy(self, shift: dict) -> None:
        # Vacancy is already recorded in the DB by shift_manager — nothing extra needed
        pass

    async def push_fill(self, shift: dict, worker: dict) -> None:
        # Already updated in DB by shift_manager — nothing extra needed
        pass
