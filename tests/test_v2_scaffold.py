from fastapi.testclient import TestClient

from app_v2.db.base import Base
from app_v2.main import app
from app_v2.services.utils import role_code_from_name, slugify


def test_v2_health_and_meta_routes():
    client = TestClient(app)

    health = client.get("/api/v2/healthz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": "v2"}

    meta = client.get("/api/v2/meta")
    assert meta.status_code == 200
    assert meta.json()["database_backend"] == "postgresql"
    assert meta.json()["api_prefix"] == "/api/v2"


def test_v2_metadata_contains_core_tables():
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
