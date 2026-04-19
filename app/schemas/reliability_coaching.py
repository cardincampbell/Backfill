from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class ReliabilityCoachingCaseRead(BaseSchema):
    id: UUID
    business_id: UUID
    employee_id: UUID
    case_status: str
    delivery_status: str
    coaching_style: str
    trigger_metric: str
    trigger_threshold: int
    trigger_window_days: int
    trigger_count: int
    opened_at: datetime
    last_triggered_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    escalated_at: Optional[datetime] = None
    suppressed_at: Optional[datetime] = None
    suppression_reason_code: Optional[str] = None
    suppression_note: Optional[str] = None
    suppression_expires_at: Optional[datetime] = None
    case_metadata: dict = Field(default_factory=dict)


class ReliabilityCoachingAttemptRead(BaseSchema):
    id: UUID
    coaching_case_id: UUID
    outbox_event_id: Optional[UUID] = None
    channel: str
    status: str
    attempt_no: int
    provider: Optional[str] = None
    provider_conversation_id: Optional[str] = None
    queued_at: datetime
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    next_eligible_at: Optional[datetime] = None
    prompt_payload: dict = Field(default_factory=dict)
    attempt_metadata: dict = Field(default_factory=dict)


class ReliabilityCoachingOutcomeRead(BaseSchema):
    id: UUID
    coaching_case_id: UUID
    attempt_id: UUID
    outcome_code: str
    barrier_code: Optional[str] = None
    availability_update_requested: bool
    manager_followup_requested: bool
    coaching_acknowledged: bool
    opt_out: bool
    recorded_at: datetime
    outcome_payload: dict = Field(default_factory=dict)


class ReliabilityCoachingCaseDetailRead(ReliabilityCoachingCaseRead):
    attempts: list[ReliabilityCoachingAttemptRead] = Field(default_factory=list)
    outcomes: list[ReliabilityCoachingOutcomeRead] = Field(default_factory=list)


class ReliabilityCoachingCaseSuppressWrite(BaseSchema):
    reason_code: str
    note: Optional[str] = None
    expires_at: Optional[datetime] = None


class ReliabilityCoachingCaseCloseWrite(BaseSchema):
    reason_code: str
    note: Optional[str] = None
