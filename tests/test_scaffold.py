from fastapi.testclient import TestClient

from app.db.base import Base
from app.main import app
from app.services.utils import role_code_from_name, slugify


def test_health_and_meta_routes():
    client = TestClient(app)

    health = client.get("/api/healthz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    meta = client.get("/api/meta")
    assert meta.status_code == 200
    assert meta.json()["database_backend"] == "postgresql"
    assert meta.json()["api_prefix"] == "/api"


def test_metadata_contains_core_tables():
    expected = {
        "businesses",
        "locations",
        "roles",
        "employees",
        "shifts",
        "shift_assignments",
        "coverage_cases",
        "coverage_offers",
        "coverage_contact_attempts",
        "users",
        "memberships",
        "sessions",
        "otp_challenges",
        "audit_logs",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))


def test_slug_helpers_are_postgres_rewrite_friendly():
    assert slugify("Whole Foods Market - Downtown LA") == "whole-foods-market-downtown-la"
    assert role_code_from_name("Front of House Lead") == "front_of_house_lead"
