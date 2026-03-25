from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

from app.db.database import get_db
from main import app


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_backfill.db"

    import app.db.database as db_mod

    monkeypatch.setattr(db_mod, "DB_PATH", Path(db_path))
    await db_mod.init_db()

    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        from fastapi.testclient import TestClient

        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
