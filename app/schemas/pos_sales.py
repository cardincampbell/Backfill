from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import BaseSchema


class PosSalesFactPayload(BaseSchema):
    business_id: UUID
    location_id: UUID
    provider: str
    provider_account_id: str | None = None
    provider_location_id: str
    observed_at: datetime
    bucket_start: datetime
    bucket_end: datetime
    gross_sales_cents: int = 0
    net_sales_cents: int = 0
    order_count: int = Field(default=0, ge=0)
    guest_count: int | None = Field(default=None, ge=0)
    refund_count: int | None = Field(default=None, ge=0)
    source_payload: dict = Field(default_factory=dict)
    dedupe_key: str | None = None

    @model_validator(mode="after")
    def validate_bucket_window(self):
        if self.bucket_end <= self.bucket_start:
            raise ValueError("pos_sales_bucket_invalid")
        return self
