from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import retell


@pytest.mark.asyncio
async def test_create_phone_call_stringifies_dynamic_variables(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeCallClient:
        def create_phone_call(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(call_id="call_123")

    fake_settings = SimpleNamespace(
        retell_api_key="retell_test",
        retell_from_number="+15555550111",
        retell_agent_id="agent_default",
        retell_agent_id_inbound="",
        retell_agent_id_outbound="agent_outbound",
        retell_chat_agent_id="chat_default",
        retell_chat_agent_id_inbound="",
        retell_chat_agent_id_outbound="chat_outbound",
    )

    monkeypatch.setattr(retell, "settings", fake_settings)
    monkeypatch.setattr(retell, "get_client", lambda: SimpleNamespace(call=_FakeCallClient()))

    call_id = await retell.create_phone_call(
        to_number="+15555550100",
        metadata={"offer_id": "offer_123"},
        dynamic_variables={
            "employee_first_name": "Taylor",
            "premium_cents": 500,
            "shift_context": '{"shift_id":"abc"}',
            "none_value": None,
        },
        agent_kind="outbound",
    )

    assert call_id == "call_123"
    assert captured["from_number"] == "+15555550111"
    assert captured["to_number"] == "+15555550100"
    assert captured["override_agent_id"] == "agent_outbound"
    assert captured["retell_llm_dynamic_variables"] == {
        "employee_first_name": "Taylor",
        "premium_cents": "500",
        "shift_context": '{"shift_id":"abc"}',
        "none_value": "",
    }


def test_create_sms_chat_stringifies_dynamic_variables(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"chat_id": "chat_123"}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse()

    fake_settings = SimpleNamespace(
        retell_api_key="retell_test",
        retell_from_number="+15555550111",
        retell_agent_id="agent_default",
        retell_agent_id_inbound="",
        retell_agent_id_outbound="agent_outbound",
        retell_chat_agent_id="chat_default",
        retell_chat_agent_id_inbound="",
        retell_chat_agent_id_outbound="chat_outbound",
    )

    monkeypatch.setattr(retell, "settings", fake_settings)
    monkeypatch.setattr(retell.httpx, "post", fake_post)

    chat_id = retell.create_sms_chat(
        to_number="+15555550100",
        body="Need you to cover a shift.",
        metadata={"offer_id": "offer_123"},
        dynamic_variables={"premium_cents": 500, "reply_deadline": None},
        agent_kind="outbound",
    )

    assert chat_id == "chat_123"
    assert captured["json"]["override_agent_id"] == "chat_outbound"
    assert captured["json"]["retell_llm_dynamic_variables"] == {
        "initial_message": "Need you to cover a shift.",
        "premium_cents": "500",
        "reply_deadline": "",
    }
