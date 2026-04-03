import pytest
from app_v2.main import app


@pytest.fixture(autouse=True)
def reset_rate_limits():
    import app_v2.services.rate_limit as v2_rate_limit_mod

    v2_rate_limit_mod._WINDOWS.clear()
    yield
    v2_rate_limit_mod._WINDOWS.clear()


@pytest.fixture
def client():
    try:
        from fastapi.testclient import TestClient

        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
