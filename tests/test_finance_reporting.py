from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.services import finance_reporting


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class FakeFinanceSession:
    def __init__(self):
        self.scalar_queue: list[object] = []
        self.execute_queue: list[list[tuple[object, object, object]]] = []

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return 0

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)


def test_micros_and_cents_helpers_round_consistently():
    assert finance_reporting.cents_to_micros(2000) == 20_000_000
    assert finance_reporting.micros_to_cents_rounded(4_100) == 0
    assert finance_reporting.micros_to_cents_rounded(15_000) == 2
    assert finance_reporting.micros_to_cents_rounded(-15_000) == -2


@pytest.mark.asyncio
async def test_campaign_cost_breakdown_groups_provider_and_product():
    session = FakeFinanceSession()
    coverage_case_id = uuid4()
    session.execute_queue = [[
        ("openai", "llm_generation", 4_100),
        ("retell", "voice_ai", 30_000),
    ]]

    rows = await finance_reporting.campaign_cost_breakdown(session, coverage_case_id)

    assert len(rows) == 2
    assert rows[0].provider == "openai"
    assert rows[0].product == "llm_generation"
    assert rows[0].total_cost_micros == 4_100
    assert rows[0].total_cost_cents_rounded == 0
    assert rows[1].provider == "retell"
    assert rows[1].product == "voice_ai"
    assert rows[1].total_cost_cents_rounded == 3


@pytest.mark.asyncio
async def test_campaign_economics_snapshot_combines_cost_and_billing_totals():
    session = FakeFinanceSession()
    coverage_case_id = uuid4()
    session.scalar_queue = [
        34_100,  # cost total micros
        2_000,   # billed cents
        2,       # cost entry count
        1,       # billing entry count
    ]

    snapshot = await finance_reporting.campaign_economics_snapshot(session, coverage_case_id)

    assert snapshot.coverage_case_id == coverage_case_id
    assert snapshot.total_cost_micros == 34_100
    assert snapshot.total_cost_cents_rounded == 3
    assert snapshot.total_billed_cents == 2_000
    assert snapshot.total_billed_micros == 20_000_000
    assert snapshot.gross_margin_micros == 19_965_900
    assert snapshot.gross_margin_cents_rounded == 1_997
    assert snapshot.cost_entry_count == 2
    assert snapshot.billed_entry_count == 1


@pytest.mark.asyncio
async def test_location_billing_cap_snapshot_uses_billing_decision():
    session = FakeFinanceSession()
    session.scalar_queue = [19_500]
    location_id = uuid4()
    occurred_at = datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc)

    snapshot = await finance_reporting.location_billing_cap_snapshot(
        session,
        location_id=location_id,
        occurred_at=occurred_at,
        timezone_name="America/Los_Angeles",
        fill_price_cents=2_000,
        monthly_cap_cents=20_000,
    )

    assert snapshot.location_id == location_id
    assert snapshot.billing_cycle_start == datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc)
    assert snapshot.billed_cents == 19_500
    assert snapshot.remaining_cents == 500
    assert snapshot.monthly_cap_cents == 20_000
    assert snapshot.fill_price_cents == 2_000
    assert snapshot.next_fill_charge_cents == 500
    assert snapshot.is_capped is False
