from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from app.schemas.common import BaseSchema
from app.schemas.events import PlatformEventRead
from app.schemas.finance import BillingLedgerEntryRead, CostLedgerEntryRead
from app.schemas.llm import LlmGenerationSummaryRead


class ProjectionStatusRead(BaseSchema):
    projection_name: str
    schema_version: int
    last_source_created_at: Optional[datetime]
    last_source_event_id: Optional[UUID]
    cursor_status: str
    last_run_started_at: Optional[datetime]
    last_run_completed_at: Optional[datetime]
    last_error: Optional[str]
    cursor_metadata: dict


class ProviderCallbackLogRead(BaseSchema):
    id: UUID
    provider: str
    route_key: str
    event_type: str | None = None
    provider_event_id: str | None = None
    dedupe_key: str
    status: str
    headers: dict
    payload: dict
    result_payload: dict
    error_message: str | None = None
    received_at: datetime
    processed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BusinessTraceRead(BaseSchema):
    trace_id: str
    platform_event_count: int
    llm_generation_count: int
    cost_entry_count: int
    billing_entry_count: int
    total_cost_micros: int
    total_billed_cents: int
    platform_events: list[PlatformEventRead]
    llm_generations: list[LlmGenerationSummaryRead]
    cost_entries: list[CostLedgerEntryRead]
    billing_entries: list[BillingLedgerEntryRead]


class CalendarFeedRead(BaseSchema):
    feed_url: str
    rotated_at: Optional[datetime]
