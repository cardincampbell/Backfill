import pytest

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
