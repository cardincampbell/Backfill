import pytest
import httpx

from app.config import settings
from app.services import retell


class _FakeResponse:
    call_id = "CA123"


class _FakeCallClient:
    def __init__(self):
        self.kwargs = None

    def create_phone_call(self, **kwargs):
        self.kwargs = kwargs
        return _FakeResponse()


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
    )

    assert chat_id == "chat_123"
    assert captured["url"] == "https://api.retellai.com/create-outbound-sms"
    assert captured["json"]["override_agent_id"] == "chat-outbound"
    assert captured["json"]["metadata"]["system_message"] == "hello"
    assert captured["json"]["metadata"]["cascade_id"] == 1
