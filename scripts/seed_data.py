"""
Seed restaurants, workers, and shifts for local development and demo.

Demo scenario:
  Maria calls out of her line cook shift at Taco Spot →
  Backfill texts James (priority 1) → James accepts → manager notified.

Usage:
    .venv/bin/python scripts/seed_data.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiosqlite
from app.db.database import DB_PATH, init_db
from app.db.queries import (
    insert_restaurant,
    insert_worker,
    insert_shift,
)


async def main():
    await init_db()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # ── Restaurant ──────────────────────────────────────────────────────
        restaurant_id = await insert_restaurant(db, {
            "name": "Taco Spot Downtown",
            "address": "123 Main St, Los Angeles, CA 90012",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "manager_email": "mike@tacospot.com",
            "scheduling_platform": "backfill_native",
            "onboarding_info": "Park in the rear lot. Report to the kitchen manager on arrival. Dress code: black non-slip shoes.",
            "agency_supply_approved": False,
            "preferred_agency_partners": [],
        })
        print(f"✓ Restaurant created: id={restaurant_id}")

        # ── Workers ─────────────────────────────────────────────────────────
        # Maria — caller-outer (priority 3, so she's not first in cascade)
        maria_id = await insert_worker(db, {
            "name": "Maria Gonzalez",
            "phone": "+13105550101",
            "email": "maria@example.com",
            "worker_type": "internal",
            "preferred_channel": "sms",
            "roles": ["line_cook"],
            "priority_rank": 3,
            "restaurant_id": restaurant_id,
            "source": "csv_import",
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
            "consent_text_version": "v1.0",
            "consent_channel": "csv_import",
        })
        print(f"✓ Worker created: Maria id={maria_id}")

        # James — first in cascade (priority 1)
        james_id = await insert_worker(db, {
            "name": "James Park",
            "phone": "+13105550102",
            "email": "james@example.com",
            "worker_type": "internal",
            "preferred_channel": "sms",
            "roles": ["line_cook", "prep_cook"],
            "priority_rank": 1,
            "restaurant_id": restaurant_id,
            "source": "csv_import",
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
            "consent_text_version": "v1.0",
            "consent_channel": "csv_import",
        })
        print(f"✓ Worker created: James id={james_id}")

        # Sofia — backup (priority 2)
        sofia_id = await insert_worker(db, {
            "name": "Sofia Reyes",
            "phone": "+13105550103",
            "worker_type": "internal",
            "preferred_channel": "both",
            "roles": ["line_cook", "server"],
            "priority_rank": 2,
            "restaurant_id": restaurant_id,
            "source": "csv_import",
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
            "consent_text_version": "v1.0",
            "consent_channel": "csv_import",
        })
        print(f"✓ Worker created: Sofia id={sofia_id}")

        # ── Shift ────────────────────────────────────────────────────────────
        shift_id = await insert_shift(db, {
            "restaurant_id": restaurant_id,
            "role": "line_cook",
            "date": "2026-03-25",
            "start_time": "06:00",
            "end_time": "14:00",
            "pay_rate": 22.00,
            "requirements": ["food_handler_card"],
            "status": "scheduled",
            "source_platform": "backfill_native",
        })
        print(f"✓ Shift created: id={shift_id}")

        print()
        print("Seed complete. Demo scenario:")
        print(f"  POST /api/shifts/backfill  {{shift_id: {shift_id}, worker_id: {maria_id}}}")
        print(f"  → Maria (id={maria_id}) calls out")
        print(f"  → Cascade reaches out to James (id={james_id}) first")
        print(f"  → If James declines, Sofia (id={sofia_id}) is next")


if __name__ == "__main__":
    asyncio.run(main())
