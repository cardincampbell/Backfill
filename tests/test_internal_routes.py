from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import get_db_session
from app.main import app


class DummyInternalSession:
    async def commit(self):
        return None

    async def rollback(self):
        return None


async def _override_db():
    yield DummyInternalSession()


def test_coverage_runtime_process_route_rejects_invalid_worker_key(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/internal/coverage/runtime/process",
            json={"limit": 5},
            headers={"X-Backfill-Worker-Key": "wrong_key"},
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "worker_auth_failed"}
    finally:
        app.dependency_overrides.clear()


def test_coverage_runtime_process_route_returns_service_batch_result(monkeypatch):
    captured: dict[str, int] = {}

    async def fake_process(_session, *, limit: int):
        captured["limit"] = limit
        return {
            "reconcile": {
                "claimed_count": 1,
                "filled_count": 0,
                "cancelled_count": 0,
                "exhausted_count": 0,
                "unchanged_count": 1,
                "failed_count": 0,
                "processed_case_ids": ["case_a"],
            },
            "offer_expiry": {
                "expired_count": 0,
                "exhausted_case_ids": [],
                "advanced_offer_ids": [],
            },
            "queued_cases": {
                "claimed_count": 1,
                "executed_count": 1,
                "exhausted_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "processed_case_ids": ["case_b"],
            },
            "delivery": {
                "claimed_count": 1,
                "sent_count": 1,
                "failed_count": 0,
                "processed_event_ids": ["evt_1"],
            },
            "processed_case_ids": ["case_a", "case_b"],
        }

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.coverage_runtime.process_coverage_runtime_batch", fake_process)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/internal/coverage/runtime/process",
            json={"limit": 7},
            headers={"X-Backfill-Worker-Key": "worker_test_key"},
        )
        assert response.status_code == 200
        assert captured["limit"] == 7
        assert response.json() == {
            "reconcile": {
                "claimed_count": 1,
                "filled_count": 0,
                "cancelled_count": 0,
                "exhausted_count": 0,
                "unchanged_count": 1,
                "failed_count": 0,
                "processed_case_ids": ["case_a"],
            },
            "offer_expiry": {
                "expired_count": 0,
                "exhausted_case_ids": [],
                "advanced_offer_ids": [],
            },
            "queued_cases": {
                "claimed_count": 1,
                "executed_count": 1,
                "exhausted_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "processed_case_ids": ["case_b"],
            },
            "delivery": {
                "claimed_count": 1,
                "sent_count": 1,
                "failed_count": 0,
                "processed_event_ids": ["evt_1"],
            },
            "processed_case_ids": ["case_a", "case_b"],
        }
    finally:
        app.dependency_overrides.clear()


def test_coverage_runtime_process_route_returns_503_when_worker_key_not_configured(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key=""),
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/internal/coverage/runtime/process",
                json={"limit": 3},
                headers={"X-Backfill-Worker-Key": "anything"},
            )
        assert response.status_code == 503
        assert response.json() == {"detail": "worker_api_key_not_configured"}
    finally:
        app.dependency_overrides.clear()
