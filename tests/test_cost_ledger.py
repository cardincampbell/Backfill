from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.finance import CostLedgerEntry
from app.services import cost_ledger


class FakeCostLedgerSession:
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


@pytest.fixture
def captured_platform_events(monkeypatch):
    captured: list[dict] = []

    async def fake_append(_session, **kwargs):
        captured.append(kwargs)
        return None

    monkeypatch.setattr(cost_ledger.platform_events, "append", fake_append)
    return captured


@pytest.mark.asyncio
async def test_append_entry_computes_total_cost_and_normalizes_metadata(captured_platform_events):
    session = FakeCostLedgerSession()
    business_id = uuid4()
    coverage_case_id = uuid4()
    occurred_at = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)

    entry = await cost_ledger.append_entry(
        session,
        provider=cost_ledger.CostProvider.RETELL,
        product=cost_ledger.CostProduct.VOICE_AI,
        reference_type="retell_call",
        reference_id=uuid4(),
        quantity=Decimal("2.5"),
        unit_cost_micros=1200,
        business_id=business_id,
        coverage_case_id=coverage_case_id,
        metadata={"trace_id": uuid4(), "minutes": Decimal("2.5")},
        occurred_at=occurred_at,
    )

    assert entry in session.added
    assert isinstance(entry, CostLedgerEntry)
    assert entry.business_id == business_id
    assert entry.coverage_case_id == coverage_case_id
    assert entry.provider == cost_ledger.CostProvider.RETELL
    assert entry.product == cost_ledger.CostProduct.VOICE_AI
    assert entry.quantity == Decimal("2.5")
    assert entry.unit_cost_micros == 1200
    assert entry.total_cost_micros == 3000
    assert isinstance(entry.cost_metadata["trace_id"], str)
    assert entry.cost_metadata["minutes"] == "2.5"
    assert entry.occurred_at == occurred_at
    assert len(captured_platform_events) == 1
    assert captured_platform_events[0]["event_type"] == cost_ledger.platform_events.PlatformEventType.FINANCE_COST_RECORDED
    assert captured_platform_events[0]["target_type"] == "coverage_case"
    assert captured_platform_events[0]["target_id"] == coverage_case_id


@pytest.mark.asyncio
async def test_append_llm_generation_cost_is_idempotent_shaped_and_optional(captured_platform_events):
    session = FakeCostLedgerSession()
    generation_id = uuid4()
    coverage_case_id = uuid4()

    entry = await cost_ledger.append_llm_generation_cost(
        session,
        generation_id=generation_id,
        provider=cost_ledger.CostProvider.OPENAI,
        purpose="intent_resolution",
        estimated_cost_micros=4100,
        coverage_case_id=coverage_case_id,
        model="gpt-test",
        prompt_version="v1",
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        metadata={"trace_id": "trace_123"},
    )

    assert entry is not None
    assert entry.reference_type == "llm_generation"
    assert entry.reference_id == str(generation_id)
    assert entry.idempotency_key == f"llm_generation:{generation_id}"
    assert entry.product == cost_ledger.CostProduct.LLM_GENERATION
    assert entry.total_cost_micros == 4100
    assert entry.cost_metadata["purpose"] == "intent_resolution"
    assert entry.cost_metadata["model"] == "gpt-test"
    assert entry.cost_metadata["total_tokens"] == 120
    assert entry.coverage_case_id == coverage_case_id
    assert len(captured_platform_events) == 1
    assert captured_platform_events[0]["payload"]["reference_type"] == "llm_generation"
    assert captured_platform_events[0]["payload"]["total_cost_micros"] == 4100

    none_entry = await cost_ledger.append_llm_generation_cost(
        session,
        generation_id=uuid4(),
        provider=cost_ledger.CostProvider.ANTHROPIC,
        purpose="general",
        estimated_cost_micros=None,
    )
    assert none_entry is None
    assert len(captured_platform_events) == 1


@pytest.mark.asyncio
async def test_total_cost_for_campaign_returns_integer_sum():
    session = FakeCostLedgerSession()
    session.scalar_value = 8300

    total = await cost_ledger.total_cost_for_campaign(session, uuid4())

    assert total == 8300
