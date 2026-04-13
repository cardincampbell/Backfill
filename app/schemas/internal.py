from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class ProjectionStatus(BaseSchema):
    projection_name: str
    schema_version: int
    last_source_created_at: Optional[datetime]
    last_source_event_id: Optional[UUID]
    cursor_status: str
    last_run_started_at: Optional[datetime]
    last_run_completed_at: Optional[datetime]
    last_error: Optional[str]
    cursor_metadata: dict


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


class FeedProjectionProcessResponse(BaseSchema):
    projection_name: str
    status: str
    claimed: bool
    cursor_status: str
    processed_count: int
    processed_source_event_ids: list[str] = Field(default_factory=list)
    latest_source_event_id: str | None = None
    latest_source_created_at: datetime | None = None


class FeedProjectionRebuildResponse(BaseSchema):
    projection_name: str
    status: str
    claimed: bool
    cursor_status: str
    deleted_count: int
    processed_count: int
    processed_source_event_ids: list[str] = Field(default_factory=list)
    latest_source_event_id: str | None = None
    latest_source_created_at: datetime | None = None
