from __future__ import annotations

from datetime import datetime
from enum import Enum
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


class ReplayMode(str, Enum):
    dry_run = "dry_run"
    reprocess_if_preconditions_match = "reprocess_if_preconditions_match"
    force_requeue = "force_requeue"


class CallbackReplayRequest(BaseSchema):
    mode: ReplayMode = ReplayMode.dry_run


class CallbackReplayResponse(BaseSchema):
    callback_log_id: UUID
    mode: ReplayMode
    action: str
    allowed: bool
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider: str | None = None
    route_key: str | None = None
    status_before: str | None = None
    status_after: str | None = None
    error_message: str | None = None
    response_kind: str | None = None
    response_payload: dict = Field(default_factory=dict)


class OutboxReplayRequest(BaseSchema):
    mode: ReplayMode = ReplayMode.dry_run


class OutboxReplayResponse(BaseSchema):
    outbox_event_id: UUID
    mode: ReplayMode
    action: str
    allowed: bool
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    topic: str | None = None
    status_before: str | None = None
    status_after: str | None = None
    offer_id: UUID | None = None
    coverage_case_id: UUID | None = None
    processed: bool = False
    sent: bool = False
    failed: bool = False
    error_message: str | None = None
    result_payload: dict = Field(default_factory=dict)


class OutboxProcessResponse(BaseSchema):
    claimed_count: int
    sent_count: int
    failed_count: int
    processed_event_ids: list[str] = Field(default_factory=list)


class InvariantIssue(BaseSchema):
    code: str
    severity: str
    aggregate_type: str
    aggregate_id: str
    message: str
    metadata: dict = Field(default_factory=dict)


class InvariantScanResponse(BaseSchema):
    checked_at: datetime
    issue_count: int
    counts_by_code: dict[str, int] = Field(default_factory=dict)
    counts_by_severity: dict[str, int] = Field(default_factory=dict)
    issues: list[InvariantIssue] = Field(default_factory=list)


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
