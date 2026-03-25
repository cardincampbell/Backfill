"""
Seed agency partner directory for Phase 3 testing.

Usage:
    .venv/bin/python scripts/seed_agencies.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiosqlite
from app.db.database import DB_PATH, init_db
from app.db.queries import insert_agency_partner


async def main():
    await init_db()

    async with aiosqlite.connect(DB_PATH) as db:

        a1 = await insert_agency_partner(db, {
            "name": "LA Restaurant Staffing Co.",
            "coverage_areas": ["LA - Downtown", "LA - Westside", "LA - Valley"],
            "roles_supported": ["line_cook", "prep_cook", "dishwasher", "server", "busser"],
            "certifications_supported": ["food_handler_card", "servsafe"],
            "contact_channel": "email",
            "contact_info": "dispatch@larstaffing.example.com",
            "avg_response_time_minutes": 45,
            "acceptance_rate": 0.82,
            "fill_rate": 0.75,
            "billing_model": "referral_fee",
            "sla_tier": "standard",
            "active": True,
        })
        print(f"✓ Agency created: LA Restaurant Staffing Co. id={a1}")

        a2 = await insert_agency_partner(db, {
            "name": "QuickFill Pro",
            "coverage_areas": ["LA - Downtown", "LA - Hollywood"],
            "roles_supported": ["line_cook", "server", "bartender", "host"],
            "certifications_supported": ["food_handler_card", "servsafe", "tips"],
            "contact_channel": "sms",
            "contact_info": "+13235550200",
            "avg_response_time_minutes": 20,
            "acceptance_rate": 0.91,
            "fill_rate": 0.88,
            "billing_model": "both",
            "sla_tier": "priority",
            "active": True,
        })
        print(f"✓ Agency created: QuickFill Pro id={a2}")

        print("\nAgency seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
