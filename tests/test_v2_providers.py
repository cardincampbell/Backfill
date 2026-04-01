from __future__ import annotations

from fastapi.testclient import TestClient

from app_v2.api.deps import get_db_session
from app_v2.main import app


class DummySession:
    async def commit(self):
        return None


async def _override_db():
    yield DummySession()


def test_twilio_status_callback_route_accepts_valid_signature(monkeypatch):
    captured: dict = {}

    async def fake_apply(session, **kwargs):
        captured.update(kwargs)
        return {"matched": True}

    monkeypatch.setattr("app_v2.api.routes.providers._validate_signature", lambda request, params: True)
    monkeypatch.setattr("app_v2.api.routes.providers.delivery.apply_twilio_status_callback", fake_apply)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v2/providers/twilio/sms/status",
            data={
                "MessageSid": "SM123",
                "MessageStatus": "delivered",
            },
        )
        assert response.status_code == 204
        assert captured["message_sid"] == "SM123"
        assert captured["message_status"] == "delivered"
    finally:
        app.dependency_overrides.clear()


def test_twilio_inbound_route_returns_twiml(monkeypatch):
    monkeypatch.setattr("app_v2.api.routes.providers._validate_signature", lambda request, params: True)

    async def fake_handle(session, **kwargs):
        return "You're confirmed for the shift."

    monkeypatch.setattr("app_v2.api.routes.providers.delivery.handle_twilio_inbound_reply", fake_handle)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v2/providers/twilio/sms/inbound",
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
