from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.integrations import ProviderCallbackLog
from app.services import provider_callbacks


class DummyCallbackSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.get_map: dict[tuple[type, object], object] = {}
        self.execute_queue: list[list[object]] = []

    async def scalar(self, _query):
        return None

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def execute(self, _query):
        class _ExecuteResult:
            def __init__(self, values):
                self._values = values

            def scalar_one_or_none(self):
                if not self._values:
                    return None
                return self._values[0]

        if self.execute_queue:
            return _ExecuteResult(self.execute_queue.pop(0))
        raise AssertionError("execute should be stubbed in this test")

    def add(self, obj):
        self.get_map[(type(obj), obj.id)] = obj

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _callback_entry(**overrides) -> ProviderCallbackLog:
    entry = ProviderCallbackLog(
        id=overrides.pop("id", uuid4()),
        provider=overrides.pop("provider", "twilio"),
        route_key=overrides.pop("route_key", "twilio_sms_status"),
        event_type=overrides.pop("event_type", "delivered"),
        provider_event_id=overrides.pop("provider_event_id", "evt_123"),
        dedupe_key=overrides.pop("dedupe_key", "twilio:evt_123"),
        status=overrides.pop("status", "received"),
        headers=overrides.pop("headers", {}),
        payload=overrides.pop("payload", {}),
        result_payload=overrides.pop("result_payload", {}),
        error_message=overrides.pop("error_message", None),
        received_at=overrides.pop("received_at", datetime.now(timezone.utc)),
        processed_at=overrides.pop("processed_at", None),
    )
    for key, value in overrides.items():
        setattr(entry, key, value)
    return entry


def test_dedupe_key_prefers_provider_event_id() -> None:
    key = provider_callbacks.dedupe_key_for_callback(
        provider="twilio",
        provider_event_id="SM123",
        payload={"MessageSid": "SM999"},
        event_type="delivered",
    )

    assert key == "twilio:SM123"


def test_dedupe_key_falls_back_to_stable_payload_hash() -> None:
    left = provider_callbacks.dedupe_key_for_callback(
        provider="retell",
        provider_event_id=None,
        payload={"event": "call_started", "call": {"id": "call_123", "status": "started"}},
        event_type="call_started",
    )
    right = provider_callbacks.dedupe_key_for_callback(
        provider="retell",
        provider_event_id=None,
        payload={"call": {"status": "started", "id": "call_123"}, "event": "call_started"},
        event_type="call_started",
    )

    assert left == right
    assert left.startswith("retell:")


def test_dedupe_key_separates_retell_lifecycle_events_for_same_call() -> None:
    started = provider_callbacks.dedupe_key_for_callback(
        provider="retell",
        provider_event_id="call_123",
        payload={"event": "call_started"},
        event_type="call_started",
    )
    ended = provider_callbacks.dedupe_key_for_callback(
        provider="retell",
        provider_event_id="call_123",
        payload={"event": "call_ended"},
        event_type="call_ended",
    )

    assert started == "retell:call_started:call_123"
    assert ended == "retell:call_ended:call_123"
    assert started != ended


@pytest.mark.asyncio
async def test_process_callback_entry_returns_duplicate_result_for_processed_inbound() -> None:
    session = DummyCallbackSession()
    entry = _callback_entry(
        route_key="twilio_sms_inbound",
        event_type="sms_inbound",
        status="processed",
        result_payload={"reply_message": "Already handled."},
    )

    result = await provider_callbacks.process_callback_entry(session, entry)

    assert result.duplicate is True
    assert result.response_kind == "twiml"
    assert result.response_text == "Already handled."
    assert session.commits == 0
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_process_callback_entry_reprocesses_failed_twilio_status(monkeypatch) -> None:
    session = DummyCallbackSession()
    entry = _callback_entry(
        status="failed",
        payload={
            "MessageSid": "SM123",
            "MessageStatus": "delivered",
        },
        error_message="transient_error",
    )
    session.get_map[(ProviderCallbackLog, entry.id)] = entry

    async def fake_apply(*args, **kwargs):
        assert kwargs["message_sid"] == "SM123"
        assert kwargs["message_status"] == "delivered"
        return {"matched": True, "status": "delivered"}

    monkeypatch.setattr(provider_callbacks.delivery, "apply_twilio_status_callback", fake_apply)

    result = await provider_callbacks.process_callback_entry(session, entry)

    assert result.response_kind == "empty"
    assert entry.status == "processed"
    assert entry.error_message is None
    assert entry.result_payload == {"matched": True, "status": "delivered"}
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_process_callback_entry_marks_failed_and_raises_typed_error(monkeypatch) -> None:
    session = DummyCallbackSession()
    entry = _callback_entry(
        provider="retell",
        route_key="retell_webhook",
        event_type="function_call",
        provider_event_id="call_123",
        dedupe_key="retell:call_123",
        payload={
            "event": "function_call",
            "name": "claim_shift",
            "args": {"offer_id": "offer_123"},
        },
    )
    session.get_map[(ProviderCallbackLog, entry.id)] = entry

    async def fake_dispatch(_session, name, args):
        assert name == "claim_shift"
        assert args["offer_id"] == "offer_123"
        raise LookupError("offer_not_found")

    monkeypatch.setattr(provider_callbacks.retell_workflow, "dispatch_function_call", fake_dispatch)

    with pytest.raises(provider_callbacks.CallbackProcessingError) as exc_info:
        await provider_callbacks.process_callback_entry(session, entry)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "offer_not_found"
    assert entry.status == "dead_lettered"
    assert entry.error_message == "offer_not_found"
    assert session.rollbacks == 1
    assert session.commits == 1


@pytest.mark.asyncio
async def test_process_retell_function_call_enriches_args_from_payload_context(monkeypatch) -> None:
    session = DummyCallbackSession()
    employee_id = uuid4()
    shift_id = uuid4()
    entry = _callback_entry(
        provider="retell",
        route_key="retell_webhook",
        event_type="function_call",
        provider_event_id="call_123",
        dedupe_key="retell:call_123",
        payload={
            "event": "function_call",
            "name": "create_vacancy",
            "args": {},
            "from_number": "+15555550100",
            "metadata": {
                "employee_id": str(employee_id),
                "shift_id": str(shift_id),
            },
        },
    )
    session.get_map[(ProviderCallbackLog, entry.id)] = entry

    async def fake_dispatch(_session, name, args):
        assert name == "create_vacancy"
        assert args["phone"] == "+15555550100"
        assert args["employee_id"] == str(employee_id)
        assert args["shift_id"] == str(shift_id)
        return {"status": "vacancy_created", "shift_id": args["shift_id"]}

    monkeypatch.setattr(provider_callbacks.retell_workflow, "dispatch_function_call", fake_dispatch)

    result = await provider_callbacks.process_callback_entry(session, entry)

    assert result.response_payload == {"status": "vacancy_created", "shift_id": str(shift_id)}
    assert entry.status == "processed"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_process_callback_batch_counts_processed_and_failed(monkeypatch) -> None:
    session = DummyCallbackSession()
    first = _callback_entry()
    second = _callback_entry(id=uuid4(), provider_event_id="evt_456", dedupe_key="twilio:evt_456")

    async def fake_claim(_session, *, limit, now, business_resolver=None):
        assert limit == 10
        assert now.tzinfo is not None
        assert business_resolver is not None
        return [first, second]

    async def fake_process(_session, entry):
        if entry.id == second.id:
            raise provider_callbacks.CallbackProcessingError("boom")
        return provider_callbacks.CallbackProcessingResult(
            callback_log_id=entry.id,
            response_kind="empty",
            response_payload={"matched": True},
        )

    monkeypatch.setattr(provider_callbacks.worker_runtime, "claim_provider_callback_logs", fake_claim)
    monkeypatch.setattr(provider_callbacks, "process_callback_entry", fake_process)

    result = await provider_callbacks.process_callback_batch(session, limit=10)

    assert result == {
        "claimed_count": 2,
        "processed_count": 1,
        "failed_count": 1,
        "dead_lettered_count": 0,
        "processed_callback_ids": [str(first.id), str(second.id)],
    }


@pytest.mark.asyncio
async def test_process_callback_entry_synchronously_claims_and_processes_received_entry(monkeypatch) -> None:
    session = DummyCallbackSession()
    entry = _callback_entry(
        status="received",
        payload={"MessageSid": "SM123", "MessageStatus": "delivered"},
    )
    session.get_map[(ProviderCallbackLog, entry.id)] = entry
    session.execute_queue = [[entry]]

    async def fake_process(_session, claimed_entry):
        assert claimed_entry.status == "processing"
        claimed_entry.status = "processed"
        claimed_entry.result_payload = {"matched": True}
        return provider_callbacks.CallbackProcessingResult(
            callback_log_id=claimed_entry.id,
            response_kind="empty",
            response_payload={"matched": True},
        )

    monkeypatch.setattr(provider_callbacks, "process_callback_entry", fake_process)

    result = await provider_callbacks.process_callback_entry_synchronously(session, entry)

    assert result.response_payload == {"matched": True}
    assert session.commits == 1


@pytest.mark.asyncio
async def test_process_callback_entry_synchronously_returns_processed_duplicate_result() -> None:
    session = DummyCallbackSession()
    entry = _callback_entry(
        status="processed",
        route_key="twilio_sms_inbound",
        result_payload={"reply_message": "Already handled."},
    )
    session.execute_queue = [[entry]]

    result = await provider_callbacks.process_callback_entry_synchronously(session, entry)

    assert result.duplicate is True
    assert result.response_text == "Already handled."
    assert session.commits == 1


@pytest.mark.asyncio
async def test_process_callback_entry_marks_non_retryable_error_as_dead_letter(monkeypatch) -> None:
    session = DummyCallbackSession()
    entry = _callback_entry(
        provider="retell",
        route_key="retell_webhook",
        event_type="function_call",
        provider_event_id="call_123",
        dedupe_key="retell:call_123",
        payload={
            "event": "function_call",
            "name": "claim_shift",
            "args": {"offer_id": "offer_123"},
        },
    )
    session.get_map[(ProviderCallbackLog, entry.id)] = entry

    async def fake_dispatch(_session, _name, _args):
        raise LookupError("offer_not_found")

    monkeypatch.setattr(provider_callbacks.retell_workflow, "dispatch_function_call", fake_dispatch)

    with pytest.raises(provider_callbacks.CallbackProcessingError):
        await provider_callbacks.process_callback_entry(session, entry)

    assert entry.status == "dead_lettered"
    assert entry.result_payload["failure_count"] == 1
    assert entry.result_payload["terminal_state"] == "dead_lettered"
    assert entry.result_payload["terminal_status_code"] == 404


@pytest.mark.asyncio
async def test_process_callback_entry_dead_letters_after_retry_budget(monkeypatch) -> None:
    session = DummyCallbackSession()
    entry = _callback_entry(
        status="failed",
        result_payload={"failure_count": 2},
        payload={
            "MessageSid": "SM123",
            "MessageStatus": "delivered",
        },
    )
    session.get_map[(ProviderCallbackLog, entry.id)] = entry

    async def fake_apply(*args, **kwargs):
        raise RuntimeError("provider_unavailable")

    monkeypatch.setattr(provider_callbacks.delivery, "apply_twilio_status_callback", fake_apply)

    with pytest.raises(RuntimeError):
        await provider_callbacks.process_callback_entry(session, entry)

    assert entry.status == "dead_lettered"
    assert entry.result_payload["failure_count"] == 3
    assert entry.result_payload["terminal_state"] == "dead_lettered"


@pytest.mark.asyncio
async def test_process_callback_entry_synchronously_returns_dead_letter_error() -> None:
    session = DummyCallbackSession()
    entry = _callback_entry(
        status="dead_lettered",
        error_message="offer_not_found",
        result_payload={
            "terminal_status_code": 404,
            "terminal_detail": "offer_not_found",
        },
    )
    session.execute_queue = [[entry]]

    with pytest.raises(provider_callbacks.CallbackProcessingError) as exc_info:
        await provider_callbacks.process_callback_entry_synchronously(session, entry)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "offer_not_found"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_process_callback_entry_synchronously_rejects_duplicate_while_processing() -> None:
    session = DummyCallbackSession()
    entry = _callback_entry(status="processing")
    session.execute_queue = [[entry]]

    with pytest.raises(provider_callbacks.CallbackProcessingError) as exc_info:
        await provider_callbacks.process_callback_entry_synchronously(session, entry)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "callback_processing_in_progress"
    assert session.commits == 1
