from __future__ import annotations

from datetime import datetime
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
