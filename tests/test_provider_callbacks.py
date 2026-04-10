from __future__ import annotations

from app.services import provider_callbacks


def test_dedupe_key_prefers_provider_event_id() -> None:
    key = provider_callbacks.dedupe_key_for_callback(
        provider="twilio",
        provider_event_id="SM123",
        payload={"MessageSid": "SM999"},
    )

    assert key == "twilio:SM123"


def test_dedupe_key_falls_back_to_stable_payload_hash() -> None:
    left = provider_callbacks.dedupe_key_for_callback(
        provider="retell",
        provider_event_id=None,
        payload={"event": "call_started", "call": {"id": "call_123", "status": "started"}},
    )
    right = provider_callbacks.dedupe_key_for_callback(
        provider="retell",
        provider_event_id=None,
        payload={"call": {"status": "started", "id": "call_123"}, "event": "call_started"},
    )

    assert left == right
    assert left.startswith("retell:")
