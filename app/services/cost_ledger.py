from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import CostLedgerEntry


class CostProvider:
    RETELL = "retell"
    TWILIO = "twilio"
    TWILIO_VERIFY = "twilio_verify"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class CostProduct:
    SMS = "sms"
    VOICE = "voice"
    VOICE_AI = "voice_ai"
    LLM_GENERATION = "llm_generation"


def _normalize_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    return value


def _decimal_quantity(quantity: int | float | Decimal) -> Decimal:
    if isinstance(quantity, Decimal):
        return quantity
    return Decimal(str(quantity))


def _total_cost_micros(quantity: Decimal, unit_cost_micros: int) -> int:
    return int((quantity * Decimal(unit_cost_micros)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


async def append_entry(
    session: AsyncSession,
    *,
    provider: str,
    product: str,
    reference_type: str,
    quantity: int | float | Decimal,
    unit_cost_micros: int,
    total_cost_micros: int | None = None,
    business_id: UUID | None = None,
    location_id: UUID | None = None,
    coverage_case_id: UUID | None = None,
    shift_id: UUID | None = None,
    employee_id: UUID | None = None,
    reference_id: UUID | str | None = None,
    idempotency_key: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    error_message: str | None = None,
    occurred_at: datetime | None = None,
) -> CostLedgerEntry:
    normalized_quantity = _decimal_quantity(quantity)
    computed_total = total_cost_micros
    if computed_total is None:
        computed_total = _total_cost_micros(normalized_quantity, unit_cost_micros)
    entry = CostLedgerEntry(
        business_id=business_id,
        location_id=location_id,
        coverage_case_id=coverage_case_id,
        shift_id=shift_id,
        employee_id=employee_id,
        provider=provider,
        product=product,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id is not None else None,
        idempotency_key=idempotency_key,
        quantity=normalized_quantity,
        unit_cost_micros=unit_cost_micros,
        total_cost_micros=computed_total,
        cost_metadata=dict(_normalize_value(metadata) or {}),
        error_message=error_message,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    session.add(entry)
    return entry


async def append_llm_generation_cost(
    session: AsyncSession,
    *,
    generation_id: UUID,
    provider: str,
    purpose: str,
    estimated_cost_micros: int | None,
    business_id: UUID | None = None,
    location_id: UUID | None = None,
    coverage_case_id: UUID | None = None,
    shift_id: UUID | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    metadata: Mapping[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> CostLedgerEntry | None:
    if estimated_cost_micros is None:
        return None

    return await append_entry(
        session,
        provider=provider,
        product=CostProduct.LLM_GENERATION,
        reference_type="llm_generation",
        reference_id=generation_id,
        idempotency_key=f"llm_generation:{generation_id}",
        quantity=1,
        unit_cost_micros=estimated_cost_micros,
        total_cost_micros=estimated_cost_micros,
        business_id=business_id,
        location_id=location_id,
        coverage_case_id=coverage_case_id,
        shift_id=shift_id,
        metadata={
            "purpose": purpose,
            "model": model,
            "prompt_version": prompt_version,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            **dict(_normalize_value(metadata) or {}),
        },
        occurred_at=occurred_at,
    )


async def total_cost_for_campaign(session: AsyncSession, coverage_case_id: UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(CostLedgerEntry.total_cost_micros), 0)).where(
            CostLedgerEntry.coverage_case_id == coverage_case_id
        )
    )
    return int(total or 0)
