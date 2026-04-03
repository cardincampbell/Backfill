from __future__ import annotations

from fastapi.testclient import TestClient

from app_v2.api.deps import get_db_session
from app_v2.main import app


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


def test_v2_retell_function_call_route_returns_dispatch_result(monkeypatch):
    async def fake_dispatch(session, name, args):
        assert name == "claim_shift"
        assert args["offer_id"] == "offer_123"
        return {"status": "accepted", "offer_id": "offer_123"}

    monkeypatch.setattr("app_v2.api.routes.retell_provider.retell_workflow.dispatch_function_call", fake_dispatch)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v2/providers/retell/webhook",
            json={
                "event": "function_call",
                "name": "claim_shift",
                "args": {"offer_id": "offer_123"},
            },
        )
        assert response.status_code == 200
        assert response.json() == {"status": "accepted", "offer_id": "offer_123"}
    finally:
        app.dependency_overrides.clear()


def test_v2_retell_lifecycle_route_persists_conversation(monkeypatch):
    class Conversation:
        id = "conv_123"

    async def fake_persist(session, body):
        assert body["event"] == "call_started"
        return Conversation()

    monkeypatch.setattr("app_v2.api.routes.retell_provider.retell_workflow.persist_payload", fake_persist)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v2/providers/retell/webhook",
            json={
                "event": "call_started",
                "call": {"call_id": "call_123"},
            },
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "conversation_id": "conv_123"}
    finally:
        app.dependency_overrides.clear()
