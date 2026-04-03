from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class CoverageCaseCreate(BaseSchema):
    shift_id: UUID
    phase_target: str = "phase_1"
    reason_code: Optional[str] = None
    priority: int = 100
    requires_manager_approval: bool = False
    triggered_by: Optional[str] = None
    case_metadata: dict = Field(default_factory=dict)


class CoverageCaseRead(BaseSchema):
    id: UUID
    shift_id: UUID
    location_id: UUID
    role_id: UUID
    status: str
    phase_target: str
    reason_code: Optional[str]
    priority: int
    requires_manager_approval: bool
    triggered_by: Optional[str]
    opened_at: Optional[datetime]
    closed_at: Optional[datetime]
    case_metadata: dict
    created_at: datetime
    updated_at: datetime


class CoverageCaseRunRead(BaseSchema):
    id: UUID
    coverage_case_id: UUID
    phase_no: int
    strategy: str
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    candidate_count: int
    run_metadata: dict
    created_at: datetime
    updated_at: datetime


class CoverageExecutionPlan(BaseSchema):
    phase: str
    operating_mode: str
    strategy: str
    time_to_shift_minutes: int
    dispatch_limit: int
    offer_ttl_minutes: int
    premium_cents: int = 0
    phase_2_eligible: bool = False
    phase_2_reason: Optional[str] = None


class CoverageExecutionDecision(BaseSchema):
    coverage_case_id: UUID
    shift_id: UUID
    recommended_phase: Optional[str] = None
    recommendation_reason: str
    phase_1_candidate_count: int = 0
    phase_2_candidate_count: int = 0
    phase_1_plan: CoverageExecutionPlan
    phase_2_plan: CoverageExecutionPlan


class CoverageCandidatePreview(BaseSchema):
    employee_id: UUID
    employee_name: str
    phone_e164: Optional[str] = None
    home_location_id: Optional[UUID] = None
    rank: int
    score: float
    source: str = "phase_1"
    qualification_status: str = "qualified"
    exclusion_reasons: list[str] = Field(default_factory=list)
    scoring_factors: dict = Field(default_factory=dict)
    availability_snapshot: dict = Field(default_factory=dict)


class Phase1CoveragePreview(BaseSchema):
    shift_id: UUID
    location_id: UUID
    role_id: UUID
    candidate_count: int
    plan: CoverageExecutionPlan
    candidates: list[CoverageCandidatePreview]


class Phase2CoveragePreview(BaseSchema):
    shift_id: UUID
    location_id: UUID
    role_id: UUID
    candidate_count: int
    plan: CoverageExecutionPlan
    candidates: list[CoverageCandidatePreview]


class CoverageOfferRead(BaseSchema):
    id: UUID
    coverage_case_id: UUID
    coverage_case_run_id: Optional[UUID]
    coverage_candidate_id: Optional[UUID]
    employee_id: UUID
    channel: str
    status: str
    delivery_provider: Optional[str]
    provider_message_id: Optional[str]
    idempotency_key: str
    sent_at: Optional[datetime]
    expires_at: Optional[datetime]
    accepted_at: Optional[datetime]
    declined_at: Optional[datetime]
    offer_metadata: dict
    created_at: datetime
    updated_at: datetime


class CoverageOfferResponseCreate(BaseSchema):
    response: str
    response_channel: str = "web"
    response_code: Optional[str] = None
    response_text: Optional[str] = None
    response_payload: dict = Field(default_factory=dict)


class CoverageOfferResponseRead(BaseSchema):
    id: UUID
    coverage_offer_id: UUID
    response_channel: str
    response_code: Optional[str]
    response_text: Optional[str]
    response_payload: dict
    responded_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class CoverageOfferActionResult(BaseSchema):
    offer: CoverageOfferRead
    response: CoverageOfferResponseRead
    coverage_case: CoverageCaseRead
    shift_id: UUID
    assignment_id: Optional[UUID] = None
    assignment_status: Optional[str] = None


class CoverageExecutionDispatchRequest(BaseSchema):
    phase_override: Optional[str] = None
    channel: str = "sms"
    dispatch_limit: Optional[int] = None
    offer_ttl_minutes: Optional[int] = None
    run_metadata: dict = Field(default_factory=dict)


class CoverageExecutionDispatchResult(BaseSchema):
    decision: CoverageExecutionDecision
    phase_executed: Optional[str] = None
    coverage_case: CoverageCaseRead
    run: Optional[CoverageCaseRunRead] = None
    plan: Optional[CoverageExecutionPlan] = None
    candidate_count: int = 0
    offers: list[CoverageOfferRead] = Field(default_factory=list)


class Phase1ExecutionRequest(BaseSchema):
    dispatch_limit: int = 1
    channel: str = "sms"
    offer_ttl_minutes: int = 15
    run_metadata: dict = Field(default_factory=dict)


class Phase1ExecutionResult(BaseSchema):
    coverage_case: CoverageCaseRead
    run: CoverageCaseRunRead
    plan: CoverageExecutionPlan
    candidate_count: int
    candidates: list[CoverageCandidatePreview]
    offers: list[CoverageOfferRead]


class Phase2ExecutionRequest(BaseSchema):
    dispatch_limit: int = 5
    channel: str = "sms"
    offer_ttl_minutes: int = 15
    run_metadata: dict = Field(default_factory=dict)


class Phase2ExecutionResult(BaseSchema):
    coverage_case: CoverageCaseRead
    run: CoverageCaseRunRead
    plan: CoverageExecutionPlan
    candidate_count: int
    candidates: list[CoverageCandidatePreview]
    offers: list[CoverageOfferRead]
