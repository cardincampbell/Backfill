from __future__ import annotations

import pytest

from app.services import communication_suppressions, retell_workflow


def test_email_unsubscribe_token_round_trips():
    token = communication_suppressions.build_email_unsubscribe_token(
        email="Taylor@example.com",
    )

    parsed = communication_suppressions.parse_email_unsubscribe_token(token)

    assert parsed == {
        "channel": "email",
        "destination": "taylor@example.com",
        "scope": "global",
    }


@pytest.mark.asyncio
async def test_handle_inbound_sms_command_processes_stop(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_suppress(session, *, channel, destination, scope="global", source, reason_code, metadata=None, occurred_at=None):
        captured["channel"] = channel
        captured["destination"] = destination
        captured["source"] = source
        captured["reason_code"] = reason_code
        return object(), True

    monkeypatch.setattr(communication_suppressions, "suppress_destination", fake_suppress)

    result = await communication_suppressions.handle_inbound_sms_command(
        object(),
        from_phone="+15555550100",
        body=" stop ",
        raw_payload={"Body": "STOP"},
    )

    assert result.handled is True
    assert result.action == "suppressed"
    assert captured == {
        "channel": "sms",
        "destination": "+15555550100",
        "source": "twilio_inbound",
        "reason_code": "user_unsubscribe",
    }


@pytest.mark.asyncio
async def test_handle_inbound_sms_command_processes_start(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_clear(session, *, channel, destination, scope="global", source, reason_code=None, metadata=None, occurred_at=None):
        captured["channel"] = channel
        captured["destination"] = destination
        captured["source"] = source
        captured["reason_code"] = reason_code or ""
        return object(), True

    monkeypatch.setattr(communication_suppressions, "clear_destination_suppression", fake_clear)

    result = await communication_suppressions.handle_inbound_sms_command(
        object(),
        from_phone="+15555550100",
        body="START",
        raw_payload={"Body": "START"},
    )

    assert result.handled is True
    assert result.action == "cleared"
    assert captured == {
        "channel": "sms",
        "destination": "+15555550100",
        "source": "twilio_inbound",
        "reason_code": "user_resubscribe",
    }


@pytest.mark.asyncio
async def test_retell_onboarding_link_skips_suppressed_destination(monkeypatch):
    async def fake_is_destination_suppressed(session, *, channel, destination, scope="global"):
        assert channel == "sms"
        assert destination == "+15555550100"
        return True

    def fake_send_sms(*, to: str, body: str, status_callback: str | None = None):
        raise AssertionError("send_sms should not be called when destination is suppressed")

    monkeypatch.setattr(
        retell_workflow.communication_suppressions,
        "is_destination_suppressed",
        fake_is_destination_suppressed,
    )
    monkeypatch.setattr(retell_workflow.messaging, "send_sms", fake_send_sms)

    result = await retell_workflow.send_onboarding_link(
        object(),
        "+15555550100",
        kind="invite",
    )

    assert result["status"] == "suppressed"
