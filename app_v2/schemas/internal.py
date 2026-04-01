from __future__ import annotations

from pydantic import Field

from app_v2.schemas.common import BaseSchema


class WorkerBatchRequest(BaseSchema):
    limit: int = 20


class OutboxProcessResponse(BaseSchema):
    claimed_count: int
    sent_count: int
    failed_count: int
    processed_event_ids: list[str] = Field(default_factory=list)


class OfferExpiryResponse(BaseSchema):
    expired_count: int
    exhausted_case_ids: list[str] = Field(default_factory=list)
    advanced_offer_ids: list[str] = Field(default_factory=list)
