from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import LlmGeneration
from app.models.events import PlatformEvent
from app.models.finance import BillingLedgerEntry, CostLedgerEntry

_TRACE_SCAN_MULTIPLIER = 20
_TRACE_SCAN_MIN = 200
_TRACE_SCAN_MAX = 1000


@dataclass(frozen=True)
class TraceReport:
    trace_id: str
    platform_events: list[PlatformEvent]
    llm_generations: list[LlmGeneration]
    cost_entries: list[CostLedgerEntry]
    billing_entries: list[BillingLedgerEntry]
    total_cost_micros: int
    total_billed_cents: int


def _trace_scan_limit(limit: int) -> int:
    normalized_limit = max(1, limit)
    return min(max(normalized_limit * _TRACE_SCAN_MULTIPLIER, _TRACE_SCAN_MIN), _TRACE_SCAN_MAX)


def _metadata_trace_id(metadata: Mapping[str, Any] | None) -> str | None:
    if not isinstance(metadata, Mapping):
        return None
    raw_value = metadata.get("trace_id")
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    return value or None


async def _recent_platform_events(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    trace_id: str,
    limit: int,
) -> list[PlatformEvent]:
    stmt = (
        select(PlatformEvent)
        .where(
            PlatformEvent.business_id == business_id,
            PlatformEvent.trace_id == trace_id,
        )
        .order_by(PlatformEvent.occurred_at.desc(), PlatformEvent.created_at.desc())
        .limit(max(1, limit))
    )
    if location_id is not None:
        stmt = stmt.where(PlatformEvent.location_id == location_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _recent_llm_generations(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    trace_id: str,
    limit: int,
) -> list[LlmGeneration]:
    stmt = (
        select(LlmGeneration)
        .where(
            LlmGeneration.business_id == business_id,
            LlmGeneration.trace_id == trace_id,
        )
        .order_by(LlmGeneration.started_at.desc(), LlmGeneration.created_at.desc())
        .limit(max(1, limit))
    )
    if location_id is not None:
        stmt = stmt.where(LlmGeneration.location_id == location_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _recent_cost_entries(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    trace_id: str,
    limit: int,
) -> list[CostLedgerEntry]:
    stmt = (
        select(CostLedgerEntry)
        .where(CostLedgerEntry.business_id == business_id)
        .order_by(CostLedgerEntry.occurred_at.desc(), CostLedgerEntry.created_at.desc())
        .limit(_trace_scan_limit(limit))
    )
    if location_id is not None:
        stmt = stmt.where(CostLedgerEntry.location_id == location_id)
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    return [
        row
        for row in rows
        if _metadata_trace_id(row.cost_metadata) == trace_id
    ][: max(1, limit)]


async def _recent_billing_entries(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    trace_id: str,
    limit: int,
) -> list[BillingLedgerEntry]:
    stmt = (
        select(BillingLedgerEntry)
        .where(BillingLedgerEntry.business_id == business_id)
        .order_by(BillingLedgerEntry.occurred_at.desc(), BillingLedgerEntry.created_at.desc())
        .limit(_trace_scan_limit(limit))
    )
    if location_id is not None:
        stmt = stmt.where(BillingLedgerEntry.location_id == location_id)
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    return [
        row
        for row in rows
        if _metadata_trace_id(row.billing_metadata) == trace_id
    ][: max(1, limit)]


async def trace_report(
    session: AsyncSession,
    *,
    business_id: UUID,
    trace_id: str,
    location_id: UUID | None = None,
    limit: int = 50,
) -> TraceReport:
    normalized_trace_id = trace_id.strip()
    platform_event_rows = await _recent_platform_events(
        session,
        business_id=business_id,
        location_id=location_id,
        trace_id=normalized_trace_id,
        limit=limit,
    )
    llm_generation_rows = await _recent_llm_generations(
        session,
        business_id=business_id,
        location_id=location_id,
        trace_id=normalized_trace_id,
        limit=limit,
    )
    cost_entry_rows = await _recent_cost_entries(
        session,
        business_id=business_id,
        location_id=location_id,
        trace_id=normalized_trace_id,
        limit=limit,
    )
    billing_entry_rows = await _recent_billing_entries(
        session,
        business_id=business_id,
        location_id=location_id,
        trace_id=normalized_trace_id,
        limit=limit,
    )

    return TraceReport(
        trace_id=normalized_trace_id,
        platform_events=platform_event_rows,
        llm_generations=llm_generation_rows,
        cost_entries=cost_entry_rows,
        billing_entries=billing_entry_rows,
        total_cost_micros=sum(int(item.total_cost_micros or 0) for item in cost_entry_rows),
        total_billed_cents=sum(int(item.amount_cents or 0) for item in billing_entry_rows),
    )
