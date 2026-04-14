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
        id = "cb_123"
        status = "received"
        result_payload = {}

    async def fake_record(*args, **kwargs):
        captured["callback_recorded"] = kwargs["provider_event_id"]
        return CallbackEntry(), True

    monkeypatch.setattr("app.api.routes.providers._validate_signature", lambda request, params: True)
    monkeypatch.setattr("app.api.routes.providers.provider_callbacks.record_raw_callback", fake_record)

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
        assert captured["callback_recorded"] == "SM123"
    finally:
        app.dependency_overrides.clear()


def test_twilio_inbound_route_returns_twiml(monkeypatch):
    monkeypatch.setattr("app.api.routes.providers._validate_signature", lambda request, params: True)

    class CallbackEntry:
        id = "cb_456"
        status = "received"
        result_payload = {}

    async def fake_record(*args, **kwargs):
        return CallbackEntry(), True

    class CallbackResult:
        response_kind = "twiml"
        response_text = "Backfill SMS alerts are off for this number. Reply START to opt back in."

    monkeypatch.setattr("app.api.routes.providers.provider_callbacks.record_raw_callback", fake_record)
    async def fake_process(session, entry):
        return CallbackResult()
    monkeypatch.setattr(
        "app.api.routes.providers.provider_callbacks.process_callback_entry_synchronously",
        fake_process,
    )

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
        assert "Reply START to opt back in." in response.text
    finally:
        app.dependency_overrides.clear()


def test_email_unsubscribe_route_renders_success_page(monkeypatch):
    class Suppression:
        id = "supp_123"

    async def fake_suppress(session, *, token, metadata=None, source="email_unsubscribe_link", reason_code="user_unsubscribe"):
        assert token == "signed-token"
        return Suppression(), True

    monkeypatch.setattr(
        "app.api.routes.communications.communication_suppressions.suppress_email_from_token",
        fake_suppress,
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.get("/api/communications/unsubscribe", params={"token": "signed-token"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "has been unsubscribed" in response.text
    finally:
        app.dependency_overrides.clear()


def test_email_unsubscribe_route_returns_bad_request_for_invalid_token(monkeypatch):
    async def fake_suppress(session, *, token, metadata=None, source="email_unsubscribe_link", reason_code="user_unsubscribe"):
        raise ValueError("invalid_unsubscribe_token")

    monkeypatch.setattr(
        "app.api.routes.communications.communication_suppressions.suppress_email_from_token",
        fake_suppress,
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.get("/api/communications/unsubscribe", params={"token": "bad-token"})
        assert response.status_code == 400
        assert response.json()["detail"] == "invalid_unsubscribe_token"
    finally:
        app.dependency_overrides.clear()
