from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.common import AuditActorType
from app.models.coverage import AuditLog
from app.models.events import PlatformEvent
from app.services import platform_events


class FakePlatformEventSession:
    def __init__(self):
        self.added: list[object] = []
        self.execute_values: list[object] = []

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "occurred_at") and getattr(obj, "occurred_at", None) is None:
            obj.occurred_at = datetime.now(timezone.utc)
        self.added.append(obj)

    async def execute(self, _stmt):
        values = list(self.execute_values)

        class _ScalarResult:
            def __init__(self, result_values):
                self._result_values = result_values

            def all(self):
                return list(self._result_values)

        class _ExecuteResult:
            def __init__(self, result_values):
                self._result_values = result_values

            def scalars(self):
                return _ScalarResult(self._result_values)

        return _ExecuteResult(values)


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

    platform_entries = [obj for obj in session.added if isinstance(obj, PlatformEvent)]
    assert len(platform_entries) == 1
    platform_entry = platform_entries[0]
    assert platform_entry.event_type == platform_events.PlatformEventType.COVERAGE_CAMPAIGN_CREATED
    assert platform_entry.compatibility_event_name == "coverage.case.created"
    assert platform_entry.entity_type == "coverage_case"
    assert platform_entry.entity_id == target_id
    assert platform_entry.payload == {"shift_id": "shift_123"}
    assert platform_entry.event_metadata["channel"] == "dashboard"
    assert platform_entry.event_metadata["session_id"] == str(channel_session_id)
    assert platform_entry.trace_id == platform_entry.event_metadata["trace_id"]
    assert platform_entry.occurred_at == entry.occurred_at

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

    platform_entries = [obj for obj in session.added if isinstance(obj, PlatformEvent)]
    assert len(platform_entries) == 1
    assert platform_entries[0].compatibility_event_name == platform_events.PlatformEventType.COVERAGE_PHASE_1_EXECUTED


def test_platform_event_type_includes_billing_events():
    assert platform_events.PlatformEventType.BILLING_FILL_CHARGED == "billing.fill.charged"
    assert platform_events.PlatformEventType.BILLING_FILL_CAPPED == "billing.fill.capped"
    assert platform_events.PlatformEventType.BILLING_FILL_VOIDED == "billing.fill.voided"


@pytest.mark.asyncio
async def test_list_platform_events_filters_by_scope():
    session = FakePlatformEventSession()
    business_id = uuid4()
    location_id = uuid4()
    first = PlatformEvent(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        schema_version=1,
        event_type=platform_events.PlatformEventType.BILLING_FILL_CHARGED,
        compatibility_event_name="billing.fill.charged",
        entity_type="coverage_case",
        entity_id=uuid4(),
        actor_type=AuditActorType.system,
        actor_user_id=None,
        actor_membership_id=None,
        trace_id="trace_1",
        payload={},
        event_metadata={},
        occurred_at=datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc),
    )
    second = PlatformEvent(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        schema_version=1,
        event_type=platform_events.PlatformEventType.BILLING_FILL_CAPPED,
        compatibility_event_name="billing.fill.capped",
        entity_type="coverage_case",
        entity_id=uuid4(),
        actor_type=AuditActorType.system,
        actor_user_id=None,
        actor_membership_id=None,
        trace_id="trace_2",
        payload={},
        event_metadata={},
        occurred_at=datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc),
    )
    session.execute_values = [first, second]

    result = await platform_events.list_events(
        session,
        business_id=business_id,
        location_id=location_id,
        event_type=platform_events.PlatformEventType.BILLING_FILL_CHARGED,
    )

    assert result == [first, second]
