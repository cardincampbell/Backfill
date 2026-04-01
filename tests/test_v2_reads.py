from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app_v2.api.deps import get_auth_context
from app_v2.db.session import get_db_session
from app_v2.main import app
from app_v2.models.common import AuditActorType
from app_v2.models.coverage import AuditLog
from app_v2.services.auth import AuthContext
from tests.test_v2_auth import DummySession, _make_auth_context


async def _override_db():
    yield DummySession()


def test_v2_audit_logs_route_returns_scoped_events(monkeypatch):
    auth_ctx: AuthContext = _make_auth_context(with_membership=True)
    business_id = auth_ctx.memberships[0].business_id
    audit_entry = AuditLog(
        id=uuid4(),
        business_id=business_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        event_name="coverage.phase_1.executed",
        target_type="coverage_case_run",
        payload={"candidate_count": 3},
        occurred_at=datetime.now(timezone.utc),
    )

    async def override_auth():
        return auth_ctx

    async def fake_list_logs(_session, *, business_id, location_id=None, limit=50):
        assert business_id == auth_ctx.memberships[0].business_id
        assert location_id is None
        assert limit == 25
        return [audit_entry]

    monkeypatch.setattr("app_v2.api.routes.audit.audit_service.list_logs", fake_list_logs)

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.get(f"/api/v2/businesses/{business_id}/audit-logs?limit=25")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["event_name"] == "coverage.phase_1.executed"
    finally:
        app.dependency_overrides.clear()


def test_v2_shift_list_forwards_location_and_window_filters(monkeypatch):
    auth_ctx: AuthContext = _make_auth_context(with_membership=True)
    business_id = auth_ctx.memberships[0].business_id
    captured = {}

    async def override_auth():
        return auth_ctx

    async def fake_list_shifts(_session, business_id, *, location_id=None, starts_at=None, ends_at=None):
        captured["business_id"] = business_id
        captured["location_id"] = location_id
        captured["starts_at"] = starts_at
        captured["ends_at"] = ends_at
        return []

    monkeypatch.setattr("app_v2.api.routes.scheduling.scheduling.list_shifts", fake_list_shifts)

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/v2/businesses/{business_id}/shifts",
            params={
                "location_id": str(uuid4()),
                "starts_at": "2026-04-01T07:00:00Z",
                "ends_at": "2026-04-07T07:00:00Z",
            },
        )
        assert response.status_code == 200
        assert captured["business_id"] == business_id
        assert captured["location_id"] is not None
        assert captured["starts_at"] is not None
        assert captured["ends_at"] is not None
    finally:
        app.dependency_overrides.clear()
