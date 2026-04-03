import pytest
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
