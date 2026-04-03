from __future__ import annotations

from pydantic import Field

from app.schemas.common import BaseSchema


class WorkerBatchRequest(BaseSchema):
    limit: int = 20


class OutboxProcessResponse(BaseSchema):
    claimed_count: int
    sent_count: int
    failed_count: int
    processed_event_ids: list[str] = Field(default_factory=list)


class WebhookProcessResponse(BaseSchema):
    claimed_count: int
    sent_count: int
    failed_count: int
    cancelled_count: int
    processed_event_ids: list[str] = Field(default_factory=list)


class OfferExpiryResponse(BaseSchema):
    expired_count: int
    exhausted_case_ids: list[str] = Field(default_factory=list)
    advanced_offer_ids: list[str] = Field(default_factory=list)


class SchedulerSyncProcessResponse(BaseSchema):
    claimed_count: int
    completed_count: int
    failed_count: int
    retrying_count: int
    processed_job_ids: list[str] = Field(default_factory=list)
