from pathlib import Path

import aiosqlite
import pytest


@pytest.mark.asyncio
async def test_init_db_migrates_legacy_restaurant_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy_backfill.db"

    import app.db.database as db_mod
    from app.db import queries

    monkeypatch.setattr(db_mod, "DB_PATH", Path(db_path))

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE restaurants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                manager_phone TEXT,
                preferred_agency_partners TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                roles TEXT NOT NULL DEFAULT '[]',
                certifications TEXT NOT NULL DEFAULT '[]',
                restaurant_id INTEGER,
                restaurant_assignments TEXT NOT NULL DEFAULT '[]',
                restaurants_worked TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER,
                role TEXT NOT NULL,
                date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                pay_rate REAL NOT NULL,
                requirements TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'scheduled',
                source_platform TEXT NOT NULL DEFAULT 'backfill_native'
            )
            """
        )
        await db.execute(
            """
            INSERT INTO restaurants (id, name, manager_phone)
            VALUES (1, 'Legacy Ops', '+15550000001')
            """
        )
        await db.execute(
            """
            INSERT INTO workers (
                id, name, phone, restaurant_id, restaurant_assignments, restaurants_worked
            ) VALUES (
                1, 'Legacy Worker', '+15550000002', 1, '[{"restaurant_id": 1}]', '[1]'
            )
            """
        )
        await db.execute(
            """
            INSERT INTO shifts (
                id, restaurant_id, role, date, start_time, end_time, pay_rate
            ) VALUES (
                1, 1, 'picker', '2026-03-26', '09:00:00', '17:00:00', 20
            )
            """
        )
        await db.commit()

    await db_mod.init_db()

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT name, type FROM sqlite_master WHERE name IN ('locations', 'restaurants') ORDER BY name") as cur:
            objects = {(row["name"], row["type"]) for row in await cur.fetchall()}
        assert ("locations", "table") in objects
        assert ("restaurants", "view") not in objects

        async with db.execute("PRAGMA table_info(workers)") as cur:
            worker_columns = {row["name"] for row in await cur.fetchall()}
        assert "location_id" in worker_columns
        assert "location_assignments" in worker_columns
        assert "locations_worked" in worker_columns
        assert "restaurant_id" not in worker_columns

        async with db.execute("PRAGMA table_info(shifts)") as cur:
            shift_columns = {row["name"] for row in await cur.fetchall()}
        assert "location_id" in shift_columns
        assert "restaurant_id" not in shift_columns

        location = await queries.get_location(db, 1)
        worker = await queries.get_worker(db, 1)
        shift = await queries.get_shift(db, 1)

    assert location is not None
    assert location["name"] == "Legacy Ops"

    assert worker is not None
    assert worker["location_id"] == 1
    assert worker["location_assignments"] == [{"location_id": 1}]
    assert worker["locations_worked"] == [1]

    assert shift is not None
    assert shift["location_id"] == 1
