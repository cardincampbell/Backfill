from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app_v2.schemas.common import BaseSchema


SchedulerProviderLiteral = Literal["backfill_native", "7shifts", "deputy", "wheniwork", "homebase"]


class SchedulerConnectionUpsert(BaseSchema):
    provider: SchedulerProviderLiteral
    provider_location_ref: Optional[str] = None
    install_url: Optional[str] = None
    credentials: dict = Field(default_factory=dict)
    webhook_secret: Optional[str] = None
    writeback_enabled: bool = False
    connection_metadata: dict = Field(default_factory=dict)


class SchedulerConnectionRead(BaseSchema):
    id: UUID
    business_id: UUID
    location_id: UUID
    provider: str
    provider_location_ref: Optional[str]
    install_url: Optional[str]
    status: str
    writeback_enabled: bool
    has_credentials: bool
    secret_hint: Optional[str]
    connection_metadata: dict
    last_roster_sync_at: Optional[datetime]
    last_roster_sync_status: Optional[str]
    last_schedule_sync_at: Optional[datetime]
    last_schedule_sync_status: Optional[str]
    last_event_sync_at: Optional[datetime]
    last_rolling_sync_at: Optional[datetime]
    last_daily_sync_at: Optional[datetime]
    last_writeback_at: Optional[datetime]
    last_sync_error: Optional[str]
    webhook_path: Optional[str] = None


class SchedulerSyncJobRead(BaseSchema):
    id: UUID
    connection_id: Optional[UUID]
    provider: str
    job_type: str
    scope: Optional[str]
    scope_ref: Optional[str]
    status: str
    attempt_count: int
    max_attempts: int
    next_run_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    last_error: Optional[str]


class SchedulerSyncTriggerResult(BaseSchema):
    connection: SchedulerConnectionRead
    roster_job_id: Optional[UUID] = None
    schedule_job_id: Optional[UUID] = None


class RetellConversationRead(BaseSchema):
    id: UUID
    business_id: Optional[UUID]
    location_id: Optional[UUID]
    coverage_case_id: Optional[UUID]
    coverage_offer_id: Optional[UUID]
    shift_id: Optional[UUID]
    employee_id: Optional[UUID]
    external_id: str
    conversation_type: str
    event_type: Optional[str]
    direction: Optional[str]
    status: Optional[str]
    phone_from: Optional[str]
    phone_to: Optional[str]
    conversation_summary: Optional[str]
    transcript_text: Optional[str]
    metadata_json: dict
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
