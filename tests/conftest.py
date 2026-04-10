import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.session import get_async_engine, get_async_sessionmaker
from app.main import app


@pytest.fixture(autouse=True)
def reset_rate_limits():
    import app.services.rate_limit as v2_rate_limit_mod

    v2_rate_limit_mod.reset_state_for_tests()
    yield
    v2_rate_limit_mod.reset_state_for_tests()


@pytest.fixture
def client():
    try:
        from fastapi.testclient import TestClient

        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def postgres_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if not settings.has_database_url:
        pytest.fail("DATABASE_URL is required for PostgreSQL row-lock integration tests")

    engine = get_async_engine()
    assert engine.dialect.name == "postgresql", (
        "PostgreSQL is required to validate FOR UPDATE row-lock behavior; "
        f"got {engine.dialect.name!r}"
    )
    return get_async_sessionmaker()
