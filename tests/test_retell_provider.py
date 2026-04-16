from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_db_session
from app.main import app
from app.services import provider_callbacks


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

    async def fake_process(session, entry):
        assert entry.status == "received"
        return type(
            "CallbackResult",
            (),
            {
                "response_kind": "json",
                "response_payload": {"status": "accepted", "offer_id": "offer_123"},
                "response_text": None,
            },
        )()

    async def fake_record(*args, **kwargs):
        return CallbackEntry(), True

    monkeypatch.setattr("app.api.routes.retell_provider._validate_signature", lambda raw_body, signature: True)
    monkeypatch.setattr("app.api.routes.retell_provider.provider_callbacks.record_raw_callback", fake_record)
    monkeypatch.setattr("app.api.routes.retell_provider.provider_callbacks.process_callback_entry_synchronously", fake_process)

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
        assert response.json() == {"status": "accepted", "offer_id": "offer_123"}
    finally:
        app.dependency_overrides.clear()


def test_retell_public_webhook_alias_returns_dispatch_result(monkeypatch):
    class CallbackEntry:
        id = "cb_retell_alias"
        status = "received"
        result_payload = {}

    async def fake_process(session, entry):
        assert entry.status == "received"
        return type(
            "CallbackResult",
            (),
            {
                "response_kind": "json",
                "response_payload": {"status": "vacancy_created", "shift_id": "shift_123"},
                "response_text": None,
            },
        )()

    async def fake_record(*args, **kwargs):
        return CallbackEntry(), True

    monkeypatch.setattr("app.api.routes.retell_provider._validate_signature", lambda raw_body, signature: True)
    monkeypatch.setattr("app.api.routes.retell_provider.provider_callbacks.record_raw_callback", fake_record)
    monkeypatch.setattr("app.api.routes.retell_provider.provider_callbacks.process_callback_entry_synchronously", fake_process)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/webhooks/retell",
            headers={"X-Retell-Signature": "sig_valid"},
            json={
                "event": "function_call",
                "name": "create_vacancy",
                "args": {"shift_id": "shift_123", "employee_id": "emp_123"},
            },
        )
        assert response.status_code == 200
        assert response.json() == {"status": "vacancy_created", "shift_id": "shift_123"}
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


def test_retell_inbound_webhook_returns_personalized_call_context(monkeypatch):
    async def fake_build_inbound(_session, body):
        assert body["event"] == "call_inbound"
        return {
            "call_inbound": {
                "override_agent_id": "agent_inbound_123",
                "metadata": {"employee_id": "emp_123", "shift_id": "shift_123"},
                "dynamic_variables": {"caller_first_name": "Taylor", "employee_found": "true"},
                "agent_override": {
                    "retell_llm": {
                        "begin_message": "Hi Taylor, this is Backfill's AI assistant. Are you calling about your upcoming shift?"
                    }
                },
            }
        }

    monkeypatch.setattr("app.api.routes.retell_provider._validate_signature", lambda raw_body, signature: True)
    monkeypatch.setattr(
        "app.api.routes.retell_provider.provider_callbacks.retell_workflow.build_inbound_webhook_response",
        fake_build_inbound,
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/webhooks/retell",
            headers={"X-Retell-Signature": "sig_valid"},
            json={
                "event": "call_inbound",
                "call_inbound": {"from_number": "+15555550100"},
            },
        )
        assert response.status_code == 200
        assert response.json()["call_inbound"]["override_agent_id"] == "agent_inbound_123"
        assert response.json()["call_inbound"]["metadata"]["employee_id"] == "emp_123"
    finally:
        app.dependency_overrides.clear()


def test_retell_function_call_route_returns_conflict_when_duplicate_is_processing(monkeypatch):
    class CallbackEntry:
        id = "cb_retell_3"
        status = "processing"
        result_payload = {}

    async def fake_record(*args, **kwargs):
        return CallbackEntry(), False

    async def fake_process(session, entry):
        raise provider_callbacks.CallbackProcessingError(
            "callback_processing_in_progress",
            status_code=409,
            detail="callback_processing_in_progress",
        )

    monkeypatch.setattr("app.api.routes.retell_provider._validate_signature", lambda raw_body, signature: True)
    monkeypatch.setattr("app.api.routes.retell_provider.provider_callbacks.record_raw_callback", fake_record)
    monkeypatch.setattr("app.api.routes.retell_provider.provider_callbacks.process_callback_entry_synchronously", fake_process)

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
        assert response.status_code == 409
        assert response.json() == {"detail": "callback_processing_in_progress"}
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
