"""
Backfill Native Lite adapter — the built-in system of record.

Used when:
  - The restaurant has no scheduling software
  - The scheduler is read-only (Homebase)

All writes go directly to the Backfill SQLite database.
This adapter is always available and is the default.
"""
from app.integrations.base import SchedulingAdapter
from app.db import queries


class NativeLiteAdapter(SchedulingAdapter):

    def __init__(self, db):
        self.db = db

    async def sync_roster(self, restaurant_id: int) -> list[dict]:
        return await queries.list_workers_for_restaurant(
            self.db, restaurant_id, active_consent_only=False
        )

    async def sync_schedule(self, restaurant_id: int, date_range: tuple) -> list[dict]:
        start, end = date_range
        async with self.db.execute(
            "SELECT * FROM shifts WHERE restaurant_id=? AND date BETWEEN ? AND ?",
            (restaurant_id, str(start), str(end)),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def on_vacancy(self, shift: dict) -> None:
        # Vacancy is already recorded in the DB by shift_manager — nothing extra needed
        pass

    async def push_fill(self, shift: dict, worker: dict) -> None:
        # Already updated in DB by shift_manager — nothing extra needed
        pass
