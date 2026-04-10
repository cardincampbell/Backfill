from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.finance import BillingLedgerEntry


class BillingEventType:
    FILL_CHARGED = "fill_charged"
    FILL_CAPPED = "fill_capped"
    FILL_VOIDED = "fill_voided"


@dataclass(frozen=True)
class BillingDecision:
    billing_event_type: str
    billing_cycle_start: datetime
    amount_cents: int
    cap_applied: bool
    fill_price_cents: int
    monthly_cap_cents: int
    billed_cents_before: int
    billed_cents_after: int


def _normalize_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    return value


def billing_cycle_start_for(*, occurred_at: datetime, timezone_name: str) -> datetime:
    local_zone = ZoneInfo(timezone_name)
    local_time = occurred_at.astimezone(local_zone)
    cycle_start_local = local_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return cycle_start_local.astimezone(ZoneInfo("UTC"))


async def billed_cents_for_location_cycle(
    session: AsyncSession,
    *,
    location_id: UUID,
    billing_cycle_start: datetime,
) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(BillingLedgerEntry.amount_cents), 0)).where(
            BillingLedgerEntry.location_id == location_id,
            BillingLedgerEntry.billing_cycle_start == billing_cycle_start,
        )
    )
    return int(total or 0)


async def billed_cents_for_campaign(session: AsyncSession, coverage_case_id: UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(BillingLedgerEntry.amount_cents), 0)).where(
            BillingLedgerEntry.coverage_case_id == coverage_case_id
        )
    )
    return int(total or 0)


async def evaluate_fill_charge(
    session: AsyncSession,
    *,
    location_id: UUID,
    occurred_at: datetime,
    timezone_name: str,
    fill_price_cents: int | None = None,
    monthly_cap_cents: int | None = None,
) -> BillingDecision:
    effective_fill_price = fill_price_cents if fill_price_cents is not None else settings.billing_fill_price_cents
    effective_monthly_cap = (
        monthly_cap_cents
        if monthly_cap_cents is not None
        else settings.billing_location_monthly_cap_cents
    )
    billing_cycle_start = billing_cycle_start_for(occurred_at=occurred_at, timezone_name=timezone_name)
    billed_before = await billed_cents_for_location_cycle(
        session,
        location_id=location_id,
        billing_cycle_start=billing_cycle_start,
    )
    remaining = max(0, effective_monthly_cap - billed_before)

    if remaining <= 0:
        amount_cents = 0
        billing_event_type = BillingEventType.FILL_CAPPED
    else:
        amount_cents = min(effective_fill_price, remaining)
        billing_event_type = BillingEventType.FILL_CHARGED if amount_cents > 0 else BillingEventType.FILL_CAPPED

    cap_applied = amount_cents < effective_fill_price
    return BillingDecision(
        billing_event_type=billing_event_type,
        billing_cycle_start=billing_cycle_start,
        amount_cents=amount_cents,
        cap_applied=cap_applied,
        fill_price_cents=effective_fill_price,
        monthly_cap_cents=effective_monthly_cap,
        billed_cents_before=billed_before,
        billed_cents_after=billed_before + amount_cents,
    )


async def append_entry(
    session: AsyncSession,
    *,
    business_id: UUID | None,
    location_id: UUID | None,
    coverage_case_id: UUID | None,
    shift_id: UUID | None,
    employee_id: UUID | None,
    billing_event_type: str,
    billing_cycle_start: datetime,
    amount_cents: int,
    cap_applied: bool,
    idempotency_key: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    error_message: str | None = None,
    occurred_at: datetime | None = None,
) -> BillingLedgerEntry:
    entry = BillingLedgerEntry(
        business_id=business_id,
        location_id=location_id,
        coverage_case_id=coverage_case_id,
        shift_id=shift_id,
        employee_id=employee_id,
        billing_event_type=billing_event_type,
        billing_cycle_start=billing_cycle_start,
        amount_cents=amount_cents,
        cap_applied=cap_applied,
        idempotency_key=idempotency_key,
        billing_metadata=dict(_normalize_value(metadata) or {}),
        error_message=error_message,
        occurred_at=occurred_at or billing_cycle_start,
    )
    session.add(entry)
    return entry


async def append_fill_entry(
    session: AsyncSession,
    *,
    business_id: UUID | None,
    location_id: UUID,
    coverage_case_id: UUID,
    shift_id: UUID | None,
    employee_id: UUID | None,
    occurred_at: datetime,
    timezone_name: str,
    fill_price_cents: int | None = None,
    monthly_cap_cents: int | None = None,
    idempotency_key: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> BillingLedgerEntry:
    decision = await evaluate_fill_charge(
        session,
        location_id=location_id,
        occurred_at=occurred_at,
        timezone_name=timezone_name,
        fill_price_cents=fill_price_cents,
        monthly_cap_cents=monthly_cap_cents,
    )
    effective_idempotency_key = idempotency_key or f"fill:{coverage_case_id}:{decision.billing_event_type}"
    return await append_entry(
        session,
        business_id=business_id,
        location_id=location_id,
        coverage_case_id=coverage_case_id,
        shift_id=shift_id,
        employee_id=employee_id,
        billing_event_type=decision.billing_event_type,
        billing_cycle_start=decision.billing_cycle_start,
        amount_cents=decision.amount_cents,
        cap_applied=decision.cap_applied,
        idempotency_key=effective_idempotency_key,
        metadata={
            "fill_price_cents": decision.fill_price_cents,
            "monthly_cap_cents": decision.monthly_cap_cents,
            "billed_cents_before": decision.billed_cents_before,
            "billed_cents_after": decision.billed_cents_after,
            **dict(_normalize_value(metadata) or {}),
        },
        occurred_at=occurred_at,
    )


async def append_void_entry(
    session: AsyncSession,
    *,
    business_id: UUID | None,
    location_id: UUID | None,
    coverage_case_id: UUID,
    shift_id: UUID | None,
    employee_id: UUID | None,
    billing_cycle_start: datetime,
    amount_cents: int | None = None,
    idempotency_key: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> BillingLedgerEntry:
    effective_amount = amount_cents
    if effective_amount is None:
        effective_amount = -(await billed_cents_for_campaign(session, coverage_case_id))
    if effective_amount > 0:
        effective_amount = -effective_amount
    effective_idempotency_key = idempotency_key or f"fill:void:{coverage_case_id}"
    return await append_entry(
        session,
        business_id=business_id,
        location_id=location_id,
        coverage_case_id=coverage_case_id,
        shift_id=shift_id,
        employee_id=employee_id,
        billing_event_type=BillingEventType.FILL_VOIDED,
        billing_cycle_start=billing_cycle_start,
        amount_cents=effective_amount,
        cap_applied=False,
        idempotency_key=effective_idempotency_key,
        metadata={
            "voided_amount_cents": abs(effective_amount),
            **dict(_normalize_value(metadata) or {}),
        },
        occurred_at=occurred_at,
    )
