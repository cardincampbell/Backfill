from datetime import datetime, timedelta

import pytest
import httpx

from app.config import settings
from app.db import queries
from app.models.audit import AuditAction
from app.services import retell
from app.services import retell_reconcile


class _FakeResponse:
    call_id = "CA123"


class _FakeCallClient:
    def __init__(self):
        self.kwargs = None
        self.retrieve_id = None
        self.list_kwargs = None

    def create_phone_call(self, **kwargs):
        self.kwargs = kwargs
        return _FakeResponse()

    def retrieve(self, call_id):
        self.retrieve_id = call_id
        return {"call_id": call_id, "call_status": "ended"}

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return [{"call_id": "call_1"}, {"call_id": "call_2"}]


class _FakeRetellClient:
    def __init__(self):
        self.call = _FakeCallClient()


@pytest.mark.asyncio
async def test_create_phone_call_uses_outbound_agent_override(monkeypatch):
    fake_client = _FakeRetellClient()

    monkeypatch.setattr(settings, "retell_agent_id", "generic-agent")
    monkeypatch.setattr(settings, "retell_agent_id_outbound", "outbound-agent")
    monkeypatch.setattr(settings, "retell_agent_id_inbound", "inbound-agent")
    monkeypatch.setattr(settings, "retell_from_number", "+13105550100")
    monkeypatch.setattr(retell, "_client", fake_client)

    call_id = await retell.create_phone_call(
        to_number="+13105550101",
        metadata={"cascade_id": 1},
    )

    assert call_id == "CA123"
    assert fake_client.call.kwargs["override_agent_id"] == "outbound-agent"


@pytest.mark.asyncio
async def test_create_phone_call_uses_inbound_agent_when_requested(monkeypatch):
    fake_client = _FakeRetellClient()

    monkeypatch.setattr(settings, "retell_agent_id", "generic-agent")
    monkeypatch.setattr(settings, "retell_agent_id_outbound", "outbound-agent")
    monkeypatch.setattr(settings, "retell_agent_id_inbound", "inbound-agent")
    monkeypatch.setattr(settings, "retell_from_number", "+13105550100")
    monkeypatch.setattr(retell, "_client", fake_client)

    call_id = await retell.create_phone_call(
        to_number="+13105550101",
        metadata={"cascade_id": 1},
        agent_kind="inbound",
    )

    assert call_id == "CA123"
    assert fake_client.call.kwargs["override_agent_id"] == "inbound-agent"


@pytest.mark.asyncio
async def test_get_call_and_list_calls_use_retell_client(monkeypatch):
    fake_client = _FakeRetellClient()
    monkeypatch.setattr(retell, "_client", fake_client)

    call = await retell.get_call("call_123")
    calls = await retell.list_calls(limit=25)

    assert call["call_id"] == "call_123"
    assert fake_client.call.retrieve_id == "call_123"
    assert calls == [{"call_id": "call_1"}, {"call_id": "call_2"}]
    assert fake_client.call.list_kwargs == {"limit": 25, "sort_order": "descending"}


def test_create_sms_chat_uses_outbound_chat_agent(monkeypatch):
    captured = {}

    def _fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout

        class _Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"chat_id": "chat_123"}

        return _Response()

    monkeypatch.setattr(settings, "retell_api_key", "retell-secret")
    monkeypatch.setattr(settings, "retell_from_number", "+13105550100")
    monkeypatch.setattr(settings, "retell_chat_agent_id", "chat-generic")
    monkeypatch.setattr(settings, "retell_chat_agent_id_outbound", "chat-outbound")
    monkeypatch.setattr(retell.httpx, "post", _fake_post)

    chat_id = retell.create_sms_chat(
        to_number="+13105550101",
        body="hello",
        metadata={"cascade_id": 1},
        dynamic_variables={"signup_url": "https://usebackfill.com/signup/test"},
    )

    assert chat_id == "chat_123"
    assert captured["url"] == "https://api.retellai.com/create-sms-chat"
    assert captured["json"]["override_agent_id"] == "chat-outbound"
    assert captured["json"]["metadata"]["cascade_id"] == 1
    assert captured["json"]["retell_llm_dynamic_variables"]["initial_message"] == "hello"
    assert captured["json"]["retell_llm_dynamic_variables"]["signup_url"] == "https://usebackfill.com/signup/test"


def test_create_sms_chat_falls_back_to_number_level_agent_binding(monkeypatch):
    captured = {}

    def _fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout

        class _Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"chat_id": "chat_456"}

        return _Response()

    monkeypatch.setattr(settings, "retell_api_key", "retell-secret")
    monkeypatch.setattr(settings, "retell_from_number", "+13105550100")
    monkeypatch.setattr(settings, "retell_chat_agent_id", "")
    monkeypatch.setattr(settings, "retell_chat_agent_id_outbound", "")
    monkeypatch.setattr(retell.httpx, "post", _fake_post)

    chat_id = retell.create_sms_chat(
        to_number="+13105550101",
        body="hello fallback",
        metadata={"source": "onboarding"},
        dynamic_variables={"business_name": "Whole Foods"},
    )

    assert chat_id == "chat_456"
    assert captured["url"] == "https://api.retellai.com/create-sms-chat"
    assert "override_agent_id" not in captured["json"]
    assert captured["json"]["metadata"]["source"] == "onboarding"
    assert captured["json"]["retell_llm_dynamic_variables"]["initial_message"] == "hello fallback"
    assert captured["json"]["retell_llm_dynamic_variables"]["business_name"] == "Whole Foods"


@pytest.mark.asyncio
async def test_get_chat_and_list_chats_use_httpx(monkeypatch):
    captured = []

    def _fake_get(url, headers, timeout, params=None):
        captured.append((url, headers, timeout, params))

        class _Response:
            def raise_for_status(self):
                return None

            def json(self):
                if url.endswith("/list-chat"):
                    return [{"chat_id": "chat_1"}]
                return {"chat_id": "chat_123", "chat_status": "ended"}

        return _Response()

    monkeypatch.setattr(settings, "retell_api_key", "retell-secret")
    monkeypatch.setattr(retell.httpx, "get", _fake_get)

    chat = await retell.get_chat("chat_123")
    chats = await retell.list_chats(limit=10)

    assert chat["chat_id"] == "chat_123"
    assert chats == [{"chat_id": "chat_1"}]
    assert captured[0][0].endswith("/get-chat/chat_123")
    assert captured[1][0].endswith("/list-chat")
    assert captured[1][3] == {"limit": 10, "sort_order": "descending"}


@pytest.mark.asyncio
async def test_sync_recent_activity_targets_missing_urgent_call_by_id(db, monkeypatch):
    start = datetime.utcnow() + timedelta(hours=1)
    outreach_at = datetime.utcnow() - timedelta(minutes=settings.retell_reconcile_drift_grace_minutes + 1)
    location_id = await queries.insert_location(
        db,
        {
            "name": "Urgent Warehouse",
            "vertical": "warehouse",
            "scheduling_platform": "backfill_native",
        },
    )
    shift_id = await queries.insert_shift(
        db,
        {
            "location_id": location_id,
            "role": "picker",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": "17:00:00",
            "pay_rate": 20.0,
            "requirements": [],
            "status": "vacant",
            "source_platform": "backfill_native",
        },
    )
    await queries.insert_audit(
        db,
        {
            "timestamp": outreach_at.isoformat(),
            "actor": "system",
            "action": AuditAction.outreach_sent.value,
            "entity_type": "outreach_attempt",
            "entity_id": 1,
            "details": {
            "shift_id": shift_id,
            "channel": "voice",
            "call_id": "call_urgent_1",
        },
        },
    )

    async def _fake_get_call(call_id):
        return {
            "call_id": call_id,
            "call_status": "ended",
            "start_timestamp": datetime.utcnow().timestamp(),
            "metadata": {"shift_id": shift_id, "location_id": location_id},
            "transcript": "Worker confirmed by phone.",
            "call_analysis": {"call_summary": "Worker confirmed."},
        }

    monkeypatch.setattr(retell, "get_call", _fake_get_call)
    async def _fake_list_calls(limit=50):
        return []

    async def _fake_list_chats(limit=50):
        return []

    monkeypatch.setattr(retell, "list_calls", _fake_list_calls)
    monkeypatch.setattr(retell, "list_chats", _fake_list_chats)

    result = await retell_reconcile.sync_recent_activity(db, lookback_minutes=20, limit=10)

    assert result["urgent_shift_count"] == 1
    assert result["targeted_calls_synced"] == 1
    conversation = await queries.get_retell_conversation_by_external_id(db, "call_urgent_1")
    assert conversation is not None
    assert conversation["shift_id"] == shift_id
    assert conversation["conversation_summary"] == "Worker confirmed."


@pytest.mark.asyncio
async def test_sync_recent_activity_uses_watermark_overlap(db, monkeypatch):
    now = datetime.utcnow()
    await queries.set_app_state(
        db,
        retell_reconcile.STATE_KEY_LAST_RECONCILE_AT,
        (now - timedelta(minutes=2)).isoformat(),
    )

    async def _fake_list_calls(limit=50):
        return [
            {
                "call_id": "call_old",
                "call_status": "ended",
                "started_at": (now - timedelta(minutes=60)).isoformat(),
            },
            {
                "call_id": "call_recent",
                "call_status": "ended",
                "started_at": (now - timedelta(minutes=1)).isoformat(),
            },
        ]

    async def _fake_list_chats(limit=50):
        return []

    monkeypatch.setattr(retell, "list_calls", _fake_list_calls)
    monkeypatch.setattr(retell, "list_chats", _fake_list_chats)

    result = await retell_reconcile.sync_recent_activity(db, lookback_minutes=20, limit=10)

    assert result["calls_synced"] == 1
    assert await queries.get_retell_conversation_by_external_id(db, "call_old") is None
    assert await queries.get_retell_conversation_by_external_id(db, "call_recent") is not None


@pytest.mark.asyncio
async def test_sync_recent_activity_enters_repair_mode_after_webhook_failure(db, monkeypatch):
    start = datetime.utcnow() + timedelta(hours=8)
    outreach_at = datetime.utcnow() - timedelta(minutes=settings.retell_reconcile_drift_grace_minutes + 1)
    location_id = await queries.insert_location(
        db,
        {
            "name": "Non Urgent Retail",
            "vertical": "retail",
            "scheduling_platform": "backfill_native",
        },
    )
    shift_id = await queries.insert_shift(
        db,
        {
            "location_id": location_id,
            "role": "cashier",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 18.0,
            "requirements": [],
            "status": "vacant",
            "source_platform": "backfill_native",
        },
    )
    await queries.insert_audit(
        db,
        {
            "timestamp": outreach_at.isoformat(),
            "actor": "system",
            "action": AuditAction.outreach_sent.value,
            "entity_type": "outreach_attempt",
            "entity_id": 1,
            "details": {
            "shift_id": shift_id,
            "channel": "voice",
            "call_id": "call_repair_1",
        },
        },
    )
    await retell_reconcile.mark_webhook_failure(
        db,
        event="call_analyzed",
        error="webhook timeout",
    )

    async def _fake_get_call(call_id):
        return {
            "call_id": call_id,
            "call_status": "ended",
            "started_at": datetime.utcnow().isoformat(),
            "metadata": {"shift_id": shift_id, "location_id": location_id},
            "transcript": "Worker declined.",
            "call_analysis": {"call_summary": "Worker declined."},
        }

    async def _fake_list_calls(limit=50):
        return []

    async def _fake_list_chats(limit=50):
        return []

    monkeypatch.setattr(retell, "get_call", _fake_get_call)
    monkeypatch.setattr(retell, "list_calls", _fake_list_calls)
    monkeypatch.setattr(retell, "list_chats", _fake_list_chats)

    result = await retell_reconcile.sync_recent_activity(db, lookback_minutes=20, limit=10)

    assert result["webhook_repair_mode"] is True
    assert result["recent_webhook_failure"] is True
    assert result["repair_mode_calls_synced"] == 1
    conversation = await queries.get_retell_conversation_by_external_id(db, "call_repair_1")
    assert conversation is not None


@pytest.mark.asyncio
async def test_sync_call_by_id_creates_signup_session_for_inbound_business_call(db, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.onboarding.send_sms",
        lambda to, body, **kwargs: sent.append((to, body, kwargs)) or "SM902",
    )

    async def _fake_get_call(call_id):
        return {
            "call_id": call_id,
            "direction": "inbound",
            "call_status": "ended",
            "from_number": "+13105550888",
            "to_number": "+14244992663",
            "transcript": "User: For business. User: We need help covering shifts when someone calls out.",
            "call_analysis": {
                "call_summary": "The caller contacted Backfill to discuss using the service for last-minute shift gaps.",
                "custom_analysis_data": {},
            },
        }

    monkeypatch.setattr(retell, "get_call", _fake_get_call)

    result = await retell_reconcile.sync_call_by_id(db, "call_reconcile_business_1")

    assert result["status"] == "ok"
    session = await queries.get_onboarding_session_by_source_external_id(db, "call_reconcile_business_1")
    assert session is not None
    assert session["contact_phone"] == "+13105550888"
    assert sent
