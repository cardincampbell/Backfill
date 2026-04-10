from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_db_session
from app.main import app


class DummySession:
    async def commit(self):
        return None

    async def rollback(self):
        return None


async def _override_db():
    yield DummySession()


def test_twilio_status_callback_route_accepts_valid_signature(monkeypatch):
    captured: dict = {}

    class CallbackEntry:
        status = "received"
        result_payload = {}

    async def fake_apply(session, **kwargs):
        captured.update(kwargs)
        return {"matched": True}

    async def fake_record(*args, **kwargs):
        captured["callback_recorded"] = kwargs["provider_event_id"]
        return CallbackEntry(), True

    async def fake_mark_processed(*args, **kwargs):
        captured["callback_processed"] = kwargs["result_payload"]
        return None

    monkeypatch.setattr("app.api.routes.providers._validate_signature", lambda request, params: True)
    monkeypatch.setattr("app.api.routes.providers.delivery.apply_twilio_status_callback", fake_apply)
    monkeypatch.setattr("app.api.routes.providers.provider_callbacks.record_raw_callback", fake_record)
    monkeypatch.setattr("app.api.routes.providers.provider_callbacks.mark_processed", fake_mark_processed)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/providers/twilio/sms/status",
            data={
                "MessageSid": "SM123",
                "MessageStatus": "delivered",
            },
        )
        assert response.status_code == 204
        assert captured["message_sid"] == "SM123"
        assert captured["message_status"] == "delivered"
        assert captured["callback_recorded"] == "SM123"
        assert captured["callback_processed"] == {"matched": True}
    finally:
        app.dependency_overrides.clear()


def test_twilio_inbound_route_returns_twiml(monkeypatch):
    monkeypatch.setattr("app.api.routes.providers._validate_signature", lambda request, params: True)

    class CallbackEntry:
        status = "received"
        result_payload = {}

    async def fake_handle(session, **kwargs):
        return "You're confirmed for the shift."

    async def fake_record(*args, **kwargs):
        return CallbackEntry(), True

    async def fake_mark_processed(*args, **kwargs):
        return None

    monkeypatch.setattr("app.api.routes.providers.delivery.handle_twilio_inbound_reply", fake_handle)
    monkeypatch.setattr("app.api.routes.providers.provider_callbacks.record_raw_callback", fake_record)
    monkeypatch.setattr("app.api.routes.providers.provider_callbacks.mark_processed", fake_mark_processed)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/providers/twilio/sms/inbound",
            data={
                "From": "+15555550100",
                "Body": "YES",
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/xml")
        assert "You&apos;re confirmed" not in response.text
        assert "You're confirmed for the shift." in response.text
    finally:
        app.dependency_overrides.clear()
