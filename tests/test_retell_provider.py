from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_db_session
from app.main import app


class DummyRetellSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


async def _override_db():
    yield DummyRetellSession()


def test_retell_function_call_route_returns_dispatch_result(monkeypatch):
    class CallbackEntry:
        id = "cb_retell_1"
        status = "received"
        result_payload = {}

    async def fake_record(*args, **kwargs):
        return CallbackEntry(), True

    monkeypatch.setattr("app.api.routes.retell_provider._validate_signature", lambda raw_body, signature: True)
    monkeypatch.setattr("app.api.routes.retell_provider.provider_callbacks.record_raw_callback", fake_record)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/providers/retell/webhook",
            headers={"X-Retell-Signature": "sig_valid"},
            json={
                "event": "function_call",
                "name": "claim_shift",
                "args": {"offer_id": "offer_123"},
            },
        )
        assert response.status_code == 200
        assert response.json() == {
            "status": "received",
            "event": "function_call",
            "callback_log_id": "cb_retell_1",
        }
    finally:
        app.dependency_overrides.clear()


def test_retell_lifecycle_route_persists_conversation(monkeypatch):
    class CallbackEntry:
        id = "cb_retell_2"
        status = "received"
        result_payload = {}

    async def fake_record(*args, **kwargs):
        return CallbackEntry(), True

    monkeypatch.setattr("app.api.routes.retell_provider._validate_signature", lambda raw_body, signature: True)
    monkeypatch.setattr("app.api.routes.retell_provider.provider_callbacks.record_raw_callback", fake_record)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/providers/retell/webhook",
            headers={"X-Retell-Signature": "sig_valid"},
            json={
                "event": "call_started",
                "call": {"call_id": "call_123"},
            },
        )
        assert response.status_code == 200
        assert response.json() == {
            "status": "received",
            "event": "call_started",
            "callback_log_id": "cb_retell_2",
        }
    finally:
        app.dependency_overrides.clear()


def test_retell_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr("app.api.routes.retell_provider._validate_signature", lambda raw_body, signature: False)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/providers/retell/webhook",
            json={"event": "call_started", "call": {"call_id": "call_123"}},
        )
        assert response.status_code == 403
        assert response.json() == {"detail": "invalid_webhook_signature"}
    finally:
        app.dependency_overrides.clear()
