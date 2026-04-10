from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.finance import BillingLedgerEntry
from app.services import billing_ledger


class FakeBillingSession:
    def __init__(self):
        self.added: list[object] = []
        self.scalar_value = None

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        self.added.append(obj)

    async def scalar(self, _query):
        return self.scalar_value


class FakeSettings:
    billing_fill_price_cents = 2000
    billing_location_monthly_cap_cents = 20000


@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    monkeypatch.setattr(billing_ledger, "settings", FakeSettings())


@pytest.fixture
def captured_platform_events(monkeypatch):
    captured: list[dict] = []

    async def fake_append(_session, **kwargs):
        captured.append(kwargs)
        return None

    monkeypatch.setattr(billing_ledger.platform_events, "append", fake_append)
    return captured


def test_billing_cycle_start_uses_location_timezone_boundary():
    occurred_at = datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc)

    cycle_start = billing_ledger.billing_cycle_start_for(
        occurred_at=occurred_at,
        timezone_name="America/Los_Angeles",
    )

    assert cycle_start == datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_evaluate_fill_charge_charges_full_price_below_cap():
    session = FakeBillingSession()
    session.scalar_value = 18000

    decision = await billing_ledger.evaluate_fill_charge(
        session,
        location_id=uuid4(),
        occurred_at=datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc),
        timezone_name="America/Los_Angeles",
    )

    assert decision.billing_event_type == billing_ledger.BillingEventType.FILL_CHARGED
    assert decision.amount_cents == 2000
    assert decision.cap_applied is False
    assert decision.billed_cents_before == 18000
    assert decision.billed_cents_after == 20000


@pytest.mark.asyncio
async def test_evaluate_fill_charge_partially_charges_when_cap_boundary_is_crossed():
    session = FakeBillingSession()
    session.scalar_value = 19500

    decision = await billing_ledger.evaluate_fill_charge(
        session,
        location_id=uuid4(),
        occurred_at=datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc),
        timezone_name="America/Los_Angeles",
    )

    assert decision.billing_event_type == billing_ledger.BillingEventType.FILL_CHARGED
    assert decision.amount_cents == 500
    assert decision.cap_applied is True
    assert decision.billed_cents_after == 20000


@pytest.mark.asyncio
async def test_evaluate_fill_charge_caps_when_cycle_is_already_exhausted():
    session = FakeBillingSession()
    session.scalar_value = 20000

    decision = await billing_ledger.evaluate_fill_charge(
        session,
        location_id=uuid4(),
        occurred_at=datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc),
        timezone_name="America/Los_Angeles",
    )

    assert decision.billing_event_type == billing_ledger.BillingEventType.FILL_CAPPED
    assert decision.amount_cents == 0
    assert decision.cap_applied is True


@pytest.mark.asyncio
async def test_append_fill_entry_records_evaluated_metadata_and_idempotency(captured_platform_events):
    session = FakeBillingSession()
    session.scalar_value = 18000
    business_id = uuid4()
    location_id = uuid4()
    coverage_case_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()
    occurred_at = datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc)

    entry = await billing_ledger.append_fill_entry(
        session,
        business_id=business_id,
        location_id=location_id,
        coverage_case_id=coverage_case_id,
        shift_id=shift_id,
        employee_id=employee_id,
        occurred_at=occurred_at,
        timezone_name="America/Los_Angeles",
        metadata={"trace_id": "trace_123"},
    )

    assert entry in session.added
    assert isinstance(entry, BillingLedgerEntry)
    assert entry.business_id == business_id
    assert entry.location_id == location_id
    assert entry.coverage_case_id == coverage_case_id
    assert entry.shift_id == shift_id
    assert entry.employee_id == employee_id
    assert entry.billing_event_type == billing_ledger.BillingEventType.FILL_CHARGED
    assert entry.amount_cents == 2000
    assert entry.cap_applied is False
    assert entry.idempotency_key == f"fill:{coverage_case_id}:{billing_ledger.BillingEventType.FILL_CHARGED}"
    assert entry.billing_metadata["trace_id"] == "trace_123"
    assert entry.billing_metadata["billed_cents_after"] == 20000
    assert entry.occurred_at == occurred_at
    assert len(captured_platform_events) == 1
    assert captured_platform_events[0]["event_type"] == billing_ledger.platform_events.PlatformEventType.BILLING_FILL_CHARGED
    assert captured_platform_events[0]["target_type"] == "coverage_case"
    assert captured_platform_events[0]["target_id"] == coverage_case_id


@pytest.mark.asyncio
async def test_append_void_entry_defaults_to_negative_campaign_total(captured_platform_events):
    session = FakeBillingSession()
    session.scalar_value = 2000
    business_id = uuid4()
    location_id = uuid4()
    coverage_case_id = uuid4()
    cycle_start = datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc)
    occurred_at = datetime(2026, 4, 12, 18, 30, tzinfo=timezone.utc)

    entry = await billing_ledger.append_void_entry(
        session,
        business_id=business_id,
        location_id=location_id,
        coverage_case_id=coverage_case_id,
        shift_id=None,
        employee_id=None,
        billing_cycle_start=cycle_start,
        occurred_at=occurred_at,
        metadata={"reason": "shift_cancelled"},
    )

    assert isinstance(entry, BillingLedgerEntry)
    assert entry.billing_event_type == billing_ledger.BillingEventType.FILL_VOIDED
    assert entry.amount_cents == -2000
    assert entry.cap_applied is False
    assert entry.idempotency_key == f"fill:void:{coverage_case_id}"
    assert entry.billing_metadata["voided_amount_cents"] == 2000
    assert entry.billing_metadata["reason"] == "shift_cancelled"
    assert entry.occurred_at == occurred_at
    assert len(captured_platform_events) == 1
    assert captured_platform_events[0]["event_type"] == billing_ledger.platform_events.PlatformEventType.BILLING_FILL_VOIDED
    assert captured_platform_events[0]["payload"]["amount_cents"] == -2000
