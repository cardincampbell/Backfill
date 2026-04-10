from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import BillingLedgerEntry, CostLedgerEntry
from app.services import billing_ledger, cost_ledger

MICROS_PER_CENT = 10_000


@dataclass(frozen=True)
class CampaignCostBreakdownRow:
    provider: str
    product: str
    total_cost_micros: int
    total_cost_cents_rounded: int


@dataclass(frozen=True)
class CampaignEconomicsSnapshot:
    coverage_case_id: UUID
    total_cost_micros: int
    total_cost_cents_rounded: int
    total_billed_cents: int
    total_billed_micros: int
    gross_margin_micros: int
    gross_margin_cents_rounded: int
    billed_entry_count: int
    cost_entry_count: int


@dataclass(frozen=True)
class LocationBillingCapSnapshot:
    location_id: UUID
    billing_cycle_start: Any
    billed_cents: int
    remaining_cents: int
    monthly_cap_cents: int
    fill_price_cents: int
    next_fill_charge_cents: int
    is_capped: bool


def micros_to_cents_rounded(micros: int) -> int:
    return int(
        (Decimal(micros) / Decimal(MICROS_PER_CENT)).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def cents_to_micros(cents: int) -> int:
    return int(cents * MICROS_PER_CENT)


async def total_billed_for_campaign(session: AsyncSession, coverage_case_id: UUID) -> int:
    return await billing_ledger.billed_cents_for_campaign(session, coverage_case_id)


async def _count_cost_entries(session: AsyncSession, coverage_case_id: UUID) -> int:
    total = await session.scalar(
        select(func.count()).select_from(CostLedgerEntry).where(
            CostLedgerEntry.coverage_case_id == coverage_case_id
        )
    )
    return int(total or 0)


async def _count_billing_entries(session: AsyncSession, coverage_case_id: UUID) -> int:
    total = await session.scalar(
        select(func.count()).select_from(BillingLedgerEntry).where(
            BillingLedgerEntry.coverage_case_id == coverage_case_id
        )
    )
    return int(total or 0)


async def campaign_cost_breakdown(
    session: AsyncSession,
    coverage_case_id: UUID,
) -> list[CampaignCostBreakdownRow]:
    result = await session.execute(
        select(
            CostLedgerEntry.provider,
            CostLedgerEntry.product,
            func.coalesce(func.sum(CostLedgerEntry.total_cost_micros), 0),
        )
        .where(CostLedgerEntry.coverage_case_id == coverage_case_id)
        .group_by(CostLedgerEntry.provider, CostLedgerEntry.product)
        .order_by(CostLedgerEntry.provider.asc(), CostLedgerEntry.product.asc())
    )
    rows = result.all()
    breakdown: list[CampaignCostBreakdownRow] = []
    for provider, product, total_cost_micros in rows:
        normalized_total = int(total_cost_micros or 0)
        breakdown.append(
            CampaignCostBreakdownRow(
                provider=provider,
                product=product,
                total_cost_micros=normalized_total,
                total_cost_cents_rounded=micros_to_cents_rounded(normalized_total),
            )
        )
    return breakdown


async def campaign_economics_snapshot(
    session: AsyncSession,
    coverage_case_id: UUID,
) -> CampaignEconomicsSnapshot:
    total_cost_micros = await cost_ledger.total_cost_for_campaign(session, coverage_case_id)
    total_billed_cents = await total_billed_for_campaign(session, coverage_case_id)
    total_billed_micros = cents_to_micros(total_billed_cents)
    gross_margin_micros = total_billed_micros - total_cost_micros
    cost_entry_count = await _count_cost_entries(session, coverage_case_id)
    billed_entry_count = await _count_billing_entries(session, coverage_case_id)
    return CampaignEconomicsSnapshot(
        coverage_case_id=coverage_case_id,
        total_cost_micros=total_cost_micros,
        total_cost_cents_rounded=micros_to_cents_rounded(total_cost_micros),
        total_billed_cents=total_billed_cents,
        total_billed_micros=total_billed_micros,
        gross_margin_micros=gross_margin_micros,
        gross_margin_cents_rounded=micros_to_cents_rounded(gross_margin_micros),
        billed_entry_count=billed_entry_count,
        cost_entry_count=cost_entry_count,
    )


async def location_billing_cap_snapshot(
    session: AsyncSession,
    *,
    location_id: UUID,
    occurred_at,
    timezone_name: str,
    fill_price_cents: int | None = None,
    monthly_cap_cents: int | None = None,
) -> LocationBillingCapSnapshot:
    decision = await billing_ledger.evaluate_fill_charge(
        session,
        location_id=location_id,
        occurred_at=occurred_at,
        timezone_name=timezone_name,
        fill_price_cents=fill_price_cents,
        monthly_cap_cents=monthly_cap_cents,
    )
    remaining_cents = max(0, decision.monthly_cap_cents - decision.billed_cents_before)
    return LocationBillingCapSnapshot(
        location_id=location_id,
        billing_cycle_start=decision.billing_cycle_start,
        billed_cents=decision.billed_cents_before,
        remaining_cents=remaining_cents,
        monthly_cap_cents=decision.monthly_cap_cents,
        fill_price_cents=decision.fill_price_cents,
        next_fill_charge_cents=decision.amount_cents,
        is_capped=decision.amount_cents == 0,
    )


async def list_cost_entries(
    session: AsyncSession,
    *,
    coverage_case_id: UUID,
    limit: int = 50,
) -> list[CostLedgerEntry]:
    result = await session.execute(
        select(CostLedgerEntry)
        .where(CostLedgerEntry.coverage_case_id == coverage_case_id)
        .order_by(CostLedgerEntry.occurred_at.desc(), CostLedgerEntry.created_at.desc())
        .limit(max(1, min(limit, 250)))
    )
    return list(result.scalars().all())


async def list_billing_entries(
    session: AsyncSession,
    *,
    coverage_case_id: UUID,
    limit: int = 50,
) -> list[BillingLedgerEntry]:
    result = await session.execute(
        select(BillingLedgerEntry)
        .where(BillingLedgerEntry.coverage_case_id == coverage_case_id)
        .order_by(BillingLedgerEntry.occurred_at.desc(), BillingLedgerEntry.created_at.desc())
        .limit(max(1, min(limit, 250)))
    )
    return list(result.scalars().all())
