from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.schemas.common import BaseSchema


class CampaignCostBreakdownRead(BaseSchema):
    provider: str
    product: str
    total_cost_micros: int
    total_cost_cents_rounded: int


class CampaignEconomicsRead(BaseSchema):
    coverage_case_id: UUID
    total_cost_micros: int
    total_cost_cents_rounded: int
    total_billed_cents: int
    total_billed_micros: int
    gross_margin_micros: int
    gross_margin_cents_rounded: int
    billed_entry_count: int
    cost_entry_count: int
    cost_breakdown: list[CampaignCostBreakdownRead]


class LocationBillingCapRead(BaseSchema):
    location_id: UUID
    billing_cycle_start: datetime
    billed_cents: int
    remaining_cents: int
    monthly_cap_cents: int
    fill_price_cents: int
    next_fill_charge_cents: int
    is_capped: bool


class CostLedgerEntryRead(BaseSchema):
    id: UUID
    business_id: UUID | None = None
    location_id: UUID | None = None
    coverage_case_id: UUID | None = None
    shift_id: UUID | None = None
    employee_id: UUID | None = None
    provider: str
    product: str
    reference_type: str
    reference_id: str | None = None
    idempotency_key: str | None = None
    quantity: Decimal
    unit_cost_micros: int
    total_cost_micros: int
    cost_metadata: dict[str, Any]
    error_message: str | None = None
    occurred_at: datetime


class BillingLedgerEntryRead(BaseSchema):
    id: UUID
    business_id: UUID | None = None
    location_id: UUID | None = None
    coverage_case_id: UUID | None = None
    shift_id: UUID | None = None
    employee_id: UUID | None = None
    billing_event_type: str
    billing_cycle_start: datetime
    amount_cents: int
    cap_applied: bool
    idempotency_key: str | None = None
    billing_metadata: dict[str, Any]
    error_message: str | None = None
    occurred_at: datetime
