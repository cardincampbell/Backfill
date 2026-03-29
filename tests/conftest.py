from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

from app.config import settings
from app.db.database import get_db
from main import app


@pytest.fixture(autouse=True)
def reset_rate_limits():
    import app.services.rate_limit as rate_limit_mod

    rate_limit_mod._WINDOWS.clear()
    yield
    rate_limit_mod._WINDOWS.clear()


@pytest.fixture(autouse=True)
def disable_ops_worker_by_default(monkeypatch):
    monkeypatch.setattr(settings, "backfill_ops_worker_enabled", False)
    yield


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
    original_internal_key = settings.backfill_internal_api_key
    original_ops_worker_enabled = settings.backfill_ops_worker_enabled
    settings.backfill_internal_api_key = "test-internal-key"
    settings.backfill_ops_worker_enabled = False
    try:
        from fastapi.testclient import TestClient

        with TestClient(app) as test_client:
            test_client.headers.update({"X-Backfill-Internal-Key": "test-internal-key"})
            yield test_client
    finally:
        settings.backfill_internal_api_key = original_internal_key
        settings.backfill_ops_worker_enabled = original_ops_worker_enabled
        app.dependency_overrides.clear()


@pytest.fixture
def public_client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    original_internal_key = settings.backfill_internal_api_key
    original_ops_worker_enabled = settings.backfill_ops_worker_enabled
    settings.backfill_internal_api_key = "test-internal-key"
    settings.backfill_ops_worker_enabled = False
    try:
        from fastapi.testclient import TestClient

        with TestClient(app) as test_client:
            yield test_client
    finally:
        settings.backfill_internal_api_key = original_internal_key
        settings.backfill_ops_worker_enabled = original_ops_worker_enabled
        app.dependency_overrides.clear()
