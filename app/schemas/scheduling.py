from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class ShiftBreakWrite(BaseSchema):
    break_type: Literal["meal", "rest", "other"]
    is_paid: bool = False
    starts_at: datetime
    ends_at: datetime
    notes: Optional[str] = None
    break_metadata: dict = Field(default_factory=dict)


class ShiftBreakRead(BaseSchema):
    id: UUID
    sequence_no: int
    break_type: str
    is_paid: bool
    starts_at: datetime
    ends_at: datetime
    notes: Optional[str] = None
    break_metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ShiftSegmentWrite(BaseSchema):
    segment_type: Literal["work"] = "work"
    starts_at: datetime
    ends_at: datetime
    segment_metadata: dict = Field(default_factory=dict)
    breaks: list[ShiftBreakWrite] = Field(default_factory=list)


class ShiftSegmentRead(BaseSchema):
    id: UUID
    sequence_no: int
    segment_type: str
    starts_at: datetime
    ends_at: datetime
    segment_metadata: dict = Field(default_factory=dict)
    breaks: list[ShiftBreakRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ShiftCreate(BaseSchema):
    location_id: UUID
    role_id: UUID
    source_system: str = "backfill_native"
    source_shift_id: Optional[str] = None
    timezone: str
    starts_at: datetime
    ends_at: datetime
    seats_requested: int = 1
    requires_manager_approval: bool = False
    premium_cents: int = 0
    notes: Optional[str] = None
    shift_metadata: dict = Field(default_factory=dict)
    segments: list[ShiftSegmentWrite] = Field(default_factory=list)


class ShiftUpdate(BaseSchema):
    role_id: Optional[UUID] = None
    timezone: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    seats_requested: Optional[int] = None
    requires_manager_approval: Optional[bool] = None
    premium_cents: Optional[int] = None
    notes: Optional[str] = None
    shift_metadata: Optional[dict] = None
    segments: Optional[list[ShiftSegmentWrite]] = None


class ShiftRead(BaseSchema):
    id: UUID
    business_id: UUID
    location_id: UUID
    role_id: UUID
    source_system: str
    source_shift_id: Optional[str]
    timezone: str
    starts_at: datetime
    ends_at: datetime
    lifecycle_status: str
    staffing_status: str
    status: str
    seats_requested: int
    seats_filled: int
    requires_manager_approval: bool
    premium_cents: int
    notes: Optional[str]
    shift_metadata: dict
    segments: list[ShiftSegmentRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ShiftAssignmentWrite(BaseSchema):
    employee_id: Optional[UUID] = None
    source: Literal["scheduler_ui", "copilot"]
    note: Optional[str] = None
    expected_assignment_id: Optional[UUID] = None


class ShiftAssignmentRead(BaseSchema):
    assignment_id: UUID
    employee_id: Optional[UUID] = None
    employee_name: Optional[str] = None
    status: str
    assigned_via: str
    accepted_at: Optional[datetime] = None


class ShiftAssignmentMutationResponse(BaseSchema):
    shift_id: UUID
    lifecycle_status: str
    staffing_status: str
    status: str
    current_assignment: Optional[ShiftAssignmentRead] = None


class PublishedShiftAmendmentWrite(BaseSchema):
    action: Literal["cancel_shift", "unassign_shift", "reassign_shift"]
    reason_code: Literal["cancelled", "callout", "no_show", "reassignment", "amendment"]
    target_employee_id: Optional[UUID] = None
    source: Literal["scheduler_ui", "copilot", "retell_voice", "sms_automation"]
    note: Optional[str] = None


class PublishedShiftAmendmentRead(BaseSchema):
    shift_id: UUID
    action: Literal["cancel_shift", "unassign_shift", "reassign_shift"]
    reason_code: Literal["cancelled", "callout", "no_show", "reassignment", "amendment"]
    amended_from_published: bool
    schedule_break: bool
    lifecycle_status: str
    staffing_status: str
    status: str
    week_publish_state: Literal["amended"]
    current_assignment: Optional[ShiftAssignmentRead] = None


class ScheduleWeekPublishWrite(BaseSchema):
    source: Literal["scheduler_ui", "copilot", "coverage_automation"]
    notify_channels: list[Literal["sms", "email"]] = Field(default_factory=list)
    expected_shift_ids: Optional[list[UUID]] = None
    note: Optional[str] = None


class ScheduleWeekPublishComplianceSummaryRead(BaseSchema):
    selected_assignment_count: int = 0
    clear_assignment_count: int = 0
    warning_assignment_count: int = 0
    blocked_assignment_count: int = 0
    override_applied_count: int = 0
    override_eligible_warning_count: int = 0
    premium_total_cents: int = 0
    unresolved_premium_rule_count: int = 0
    unresolved_premium_rule_codes: list[str] = Field(default_factory=list)
    warning_rule_codes: list[str] = Field(default_factory=list)
    override_eligible_artifact_types: list[str] = Field(default_factory=list)
    warning_shift_ids: list[str] = Field(default_factory=list)
    blocked_shift_ids: list[str] = Field(default_factory=list)
    override_eligible_shift_ids: list[str] = Field(default_factory=list)


class ScheduleWeekPublishComplianceIssueRead(BaseSchema):
    rule_code: str
    status: str
    reason_codes: list[str] = Field(default_factory=list)
    premium_required: bool = False
    premium_type: Optional[str] = None
    premium_cents: int = 0
    unresolved_premium: bool = False
    would_block: bool = False
    artifact_type_allowed: Optional[str] = None
    override_applied: bool = False
    override_artifact_id: Optional[str] = None


class ScheduleWeekPublishComplianceReviewItemRead(BaseSchema):
    assignment_id: Optional[UUID] = None
    shift_id: UUID
    employee_id: UUID
    status: str
    blocking_rule_codes: list[str] = Field(default_factory=list)
    warning_rule_codes: list[str] = Field(default_factory=list)
    premium_total_cents: int = 0
    unresolved_premium_rule_codes: list[str] = Field(default_factory=list)
    override_applied: bool = False
    override_artifact_id: Optional[str] = None
    override_eligible_artifact_types: list[str] = Field(default_factory=list)
    policy_version_id: Optional[UUID] = None
    policy_hash: Optional[str] = None
    policy_effective_at: Optional[datetime] = None
    policy_scope: Optional[str] = None
    issues: list[ScheduleWeekPublishComplianceIssueRead] = Field(default_factory=list)


class ScheduleWeekPublishFuturePolicyReviewRead(BaseSchema):
    policy_version_id: Optional[UUID] = None
    policy_hash: Optional[str] = None
    policy_effective_at: datetime
    policy_scope: str
    summary: ScheduleWeekPublishComplianceSummaryRead = Field(
        default_factory=ScheduleWeekPublishComplianceSummaryRead
    )
    review_items: list[ScheduleWeekPublishComplianceReviewItemRead] = Field(
        default_factory=list
    )


class ScheduleWeekFuturePolicyReviewResponseRead(BaseSchema):
    week_start_date: date
    week_end_date: date
    summary: ScheduleWeekPublishComplianceSummaryRead = Field(
        default_factory=ScheduleWeekPublishComplianceSummaryRead
    )
    policy_reviews: list[ScheduleWeekPublishFuturePolicyReviewRead] = Field(
        default_factory=list
    )


class ScheduleWeekPublishRead(BaseSchema):
    business_id: UUID
    location_id: UUID
    week_start_date: date
    week_end_date: date
    publish_mode: Literal["draft_only_net_new"]
    published_shift_count: int
    already_scheduled_shift_count: int
    notification_enqueued_assignment_count: int
    notification_enqueued_employee_count: int
    published_shift_ids: list[UUID]
    already_scheduled_shift_ids: list[UUID]
    compliance_summary: ScheduleWeekPublishComplianceSummaryRead = Field(
        default_factory=ScheduleWeekPublishComplianceSummaryRead
    )
    compliance_review_items: list[ScheduleWeekPublishComplianceReviewItemRead] = Field(
        default_factory=list
    )


class ShiftDeleteResponse(BaseSchema):
    deleted: bool
    shift_id: UUID
