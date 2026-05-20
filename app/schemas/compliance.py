from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class ShiftComplianceOverrideCreate(BaseSchema):
    employee_id: UUID
    artifact_type: Literal["written_consent", "meal_waiver"] = "written_consent"
    rule_code: Optional[str] = None
    expires_at: Optional[datetime] = None
    note: Optional[str] = None
    artifact_payload: dict = Field(default_factory=dict)


class ShiftComplianceOverrideRead(BaseSchema):
    id: UUID
    business_id: UUID
    location_id: UUID
    shift_id: UUID
    employee_id: UUID
    assignment_id: Optional[UUID] = None
    labor_rule_profile_version_id: Optional[UUID] = None
    approved_by_user_id: Optional[UUID] = None
    rule_code: str
    artifact_type: str
    status: str
    engine_version: str
    profile_payload_hash: Optional[str] = None
    approved_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    note: Optional[str] = None
    reason_codes: list = Field(default_factory=list)
    artifact_payload: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ComplianceRuleSourceReferenceRead(BaseSchema):
    rule_code: str
    source_kind: str
    source_code: Optional[str] = None
    source_label: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    source_document_title: Optional[str] = None
    source_urls: list[str] = Field(default_factory=list)
    source_version: Optional[str] = None
    source_hash: Optional[str] = None
    version_id: Optional[UUID] = None
    payload_hash: Optional[str] = None
    effective_at: Optional[datetime] = None


class ShiftComplianceDecisionRead(BaseSchema):
    id: UUID
    occurred_at: datetime
    actor_type: str
    actor_user_id: Optional[UUID] = None
    actor_membership_id: Optional[UUID] = None
    trace_id: str
    shift_id: UUID
    employee_id: UUID
    assignment_id: Optional[UUID] = None
    coverage_case_id: Optional[UUID] = None
    decision_source: str
    decision_outcome: str
    engine_version: str
    profile_code: Optional[str] = None
    profile_version_id: Optional[UUID] = None
    profile_payload_hash: Optional[str] = None
    policy_version_id: Optional[UUID] = None
    policy_hash: Optional[str] = None
    policy_effective_at: Optional[datetime] = None
    policy_scope: Optional[str] = None
    blocking_rule_codes: list[str] = Field(default_factory=list)
    warning_rule_codes: list[str] = Field(default_factory=list)
    premium_rule_codes: list[str] = Field(default_factory=list)
    premium_total_cents: int = 0
    premium_components: list[dict] = Field(default_factory=list)
    unresolved_premium_rule_codes: list[str] = Field(default_factory=list)
    override_applied: bool = False
    override_artifact_id: Optional[UUID] = None
    rule_source_references: list[ComplianceRuleSourceReferenceRead] = Field(default_factory=list)
    evaluation: dict = Field(default_factory=dict)
