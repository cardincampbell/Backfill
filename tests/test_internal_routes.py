from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_db_session
from app.main import app
from app.models.integrations import ProviderCallbackLog


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


def test_list_provider_callback_logs_requires_valid_worker_key(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.get(
            "/api/internal/providers/callbacks",
            headers={"X-Backfill-Worker-Key": "wrong_key"},
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "worker_auth_failed"}
    finally:
        app.dependency_overrides.clear()


def test_list_provider_callback_logs_returns_filtered_rows(monkeypatch):
    now = datetime(2026, 4, 10, 20, 0, tzinfo=timezone.utc)
    row = ProviderCallbackLog(
        id=uuid4(),
        provider="retell",
        route_key="retell_webhook",
        event_type="function_call",
        provider_event_id="evt_123",
        dedupe_key="retell:evt_123",
        status="processed",
        headers={"x-retell-signature": "sig"},
        payload={"event": "function_call"},
        result_payload={"status": "ok"},
        error_message=None,
        received_at=now,
        processed_at=now,
        created_at=now,
        updated_at=now,
    )

    async def fake_list(_session, **kwargs):
        assert kwargs["provider"] == "retell"
        assert kwargs["route_key"] == "retell_webhook"
        assert kwargs["status"] == "processed"
        assert kwargs["event_type"] == "function_call"
        assert kwargs["provider_event_id"] == "evt_123"
        assert kwargs["dedupe_key"] == "retell:evt_123"
        assert kwargs["limit"] == 25
        return [row]

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.provider_callbacks.list_callback_logs", fake_list)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.get(
            "/api/internal/providers/callbacks"
            "?provider=retell&route_key=retell_webhook&status=processed"
            "&event_type=function_call&provider_event_id=evt_123&dedupe_key=retell:evt_123&limit=25",
            headers={"X-Backfill-Worker-Key": "worker_test_key"},
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(row.id),
                "provider": "retell",
                "route_key": "retell_webhook",
                "event_type": "function_call",
                "provider_event_id": "evt_123",
                "dedupe_key": "retell:evt_123",
                "status": "processed",
                "headers": {"x-retell-signature": "sig"},
                "payload": {"event": "function_call"},
                "result_payload": {"status": "ok"},
                "error_message": None,
                "received_at": "2026-04-10T20:00:00Z",
                "processed_at": "2026-04-10T20:00:00Z",
                "created_at": "2026-04-10T20:00:00Z",
                "updated_at": "2026-04-10T20:00:00Z",
            }
        ]
    finally:
        app.dependency_overrides.clear()


def test_get_provider_callback_log_returns_row(monkeypatch):
    now = datetime(2026, 4, 10, 20, 5, tzinfo=timezone.utc)
    callback_log_id = uuid4()
    row = ProviderCallbackLog(
        id=callback_log_id,
        provider="twilio",
        route_key="twilio_sms_status",
        event_type="delivered",
        provider_event_id="SM123",
        dedupe_key="twilio:SM123",
        status="processed",
        headers={},
        payload={"MessageSid": "SM123"},
        result_payload={"status": "delivered"},
        error_message=None,
        received_at=now,
        processed_at=now,
        created_at=now,
        updated_at=now,
    )

    async def fake_get(_session, **kwargs):
        assert kwargs["callback_log_id"] == callback_log_id
        return row

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.provider_callbacks.get_callback_log", fake_get)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/internal/providers/callbacks/{callback_log_id}",
            headers={"X-Backfill-Worker-Key": "worker_test_key"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(callback_log_id)
        assert payload["provider"] == "twilio"
        assert payload["route_key"] == "twilio_sms_status"
        assert payload["result_payload"]["status"] == "delivered"
    finally:
        app.dependency_overrides.clear()
