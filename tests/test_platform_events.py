from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.common import AuditActorType
from app.models.coverage import AuditLog
from app.services import platform_events


class FakePlatformEventSession:
    def __init__(self):
        self.added: list[object] = []

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "occurred_at") and getattr(obj, "occurred_at", None) is None:
            obj.occurred_at = datetime.now(timezone.utc)
        self.added.append(obj)


@pytest.mark.asyncio
async def test_append_platform_event_preserves_compatibility_name_and_embeds_canonical_metadata(monkeypatch):
    session = FakePlatformEventSession()
    business_id = uuid4()
    location_id = uuid4()
    target_id = uuid4()
    membership_id = uuid4()
    user_id = uuid4()
    channel_session_id = uuid4()

    async def fake_enqueue(_session, _entry):
        return []

    monkeypatch.setattr("app.services.webhooks.enqueue_audit_event", fake_enqueue)

    entry = await platform_events.append(
        session,
        event_type=platform_events.PlatformEventType.COVERAGE_CAMPAIGN_CREATED,
        compatibility_event_name="coverage.case.created",
        target_type="coverage_case",
        target_id=target_id,
        business_id=business_id,
        location_id=location_id,
        actor_type=AuditActorType.user,
        actor_user_id=user_id,
        actor_membership_id=membership_id,
        payload={"shift_id": "shift_123"},
        metadata={"channel": "dashboard", "session_id": channel_session_id},
    )

    assert isinstance(entry, AuditLog)
    assert entry.event_name == "coverage.case.created"
    assert entry.payload["shift_id"] == "shift_123"

    envelope = entry.payload[platform_events.PLATFORM_EVENT_PAYLOAD_KEY]
    assert envelope["schema_version"] == platform_events.PLATFORM_EVENT_SCHEMA_VERSION
    assert envelope["event_type"] == platform_events.PlatformEventType.COVERAGE_CAMPAIGN_CREATED
    assert envelope["compatibility_event_name"] == "coverage.case.created"
    assert envelope["target_type"] == "coverage_case"
    assert envelope["target_id"] == str(target_id)
    assert envelope["metadata"]["channel"] == "dashboard"
    assert envelope["metadata"]["session_id"] == str(channel_session_id)
    assert envelope["metadata"]["trace_id"]


@pytest.mark.asyncio
async def test_append_platform_event_defaults_compatibility_name_to_event_type(monkeypatch):
    session = FakePlatformEventSession()

    async def fake_enqueue(_session, _entry):
        return []

    monkeypatch.setattr("app.services.webhooks.enqueue_audit_event", fake_enqueue)

    entry = await platform_events.append(
        session,
        event_type=platform_events.PlatformEventType.COVERAGE_PHASE_1_EXECUTED,
        target_type="coverage_case_run",
        payload={},
    )

    assert entry.event_name == platform_events.PlatformEventType.COVERAGE_PHASE_1_EXECUTED
    envelope = entry.payload[platform_events.PLATFORM_EVENT_PAYLOAD_KEY]
    assert envelope["compatibility_event_name"] == platform_events.PlatformEventType.COVERAGE_PHASE_1_EXECUTED
