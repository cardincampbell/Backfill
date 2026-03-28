from app.config import settings
from app.services import messaging


def test_send_sms_routes_through_retell_when_enabled(monkeypatch):
    calls = []

    def _fake_sms_chat(*, to_number, body, metadata=None, dynamic_variables=None):
        calls.append((to_number, body, metadata, dynamic_variables))
        return "chat_123"

    monkeypatch.setattr(settings, "retell_sms_enabled", True)
    monkeypatch.setattr("app.services.retell.create_sms_chat", _fake_sms_chat)

    message_id = messaging.send_sms(
        "+13105550101",
        "Shift available",
        metadata={"cascade_id": 7},
        dynamic_variables={"role": "line_cook"},
    )

    assert message_id == "chat_123"
    assert calls == [("+13105550101", "Shift available", {"cascade_id": 7}, {"role": "line_cook"})]
