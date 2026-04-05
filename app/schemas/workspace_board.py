from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from app.schemas.common import BaseSchema


class WorkspaceBoardRoleRead(BaseSchema):
    role_id: UUID
    role_code: str
    role_name: str
    min_headcount: Optional[int] = None
    max_headcount: Optional[int] = None


class WorkspaceBoardWorkerRead(BaseSchema):
    employee_id: UUID
    full_name: str
    preferred_name: Optional[str] = None
    phone_e164: Optional[str] = None
    email: Optional[str] = None
    home_location_id: Optional[UUID] = None
    reliability_score: float
    avg_response_time_seconds: Optional[int] = None
    role_ids: list[UUID]
    role_names: list[str]
    can_cover_here: bool
    can_blast_here: bool


class WorkspaceBoardShiftAssignmentRead(BaseSchema):
    assignment_id: UUID
    employee_id: Optional[UUID] = None
    employee_name: Optional[str] = None
    status: str
    assigned_via: str
    accepted_at: Optional[datetime] = None


class WorkspaceBoardShiftRead(BaseSchema):
    shift_id: UUID
    role_id: UUID
    role_code: str
    role_name: str
    starts_at: datetime
    ends_at: datetime
    status: str
    seats_requested: int
    seats_filled: int
    requires_manager_approval: bool
    premium_cents: int
    notes: Optional[str] = None
    current_assignment: Optional[WorkspaceBoardShiftAssignmentRead] = None
    coverage_case_id: Optional[UUID] = None
    coverage_case_status: Optional[str] = None
    pending_offer_count: int = 0
    delivered_offer_count: int = 0
    standby_depth: int = 0
    manager_action_required: bool = False


class WorkspaceBoardActionSummaryRead(BaseSchema):
    total: int
    approval_required: int
    active_coverage: int
    open_shifts: int


class WorkspaceLocationBoardRead(BaseSchema):
    business_id: UUID
    business_name: str
    business_slug: str
    location_id: UUID
    location_name: str
    location_slug: str
    address_line_1: Optional[str] = None
    locality: Optional[str] = None
    region: Optional[str] = None
    postal_code: Optional[str] = None
    country_code: str
    timezone: str
    week_start_date: date
    week_end_date: date
    location_role_setup_required: bool = False
    roles: list[WorkspaceBoardRoleRead]
    available_roles: list[WorkspaceBoardRoleRead] = []
    workers: list[WorkspaceBoardWorkerRead]
    shifts: list[WorkspaceBoardShiftRead]
    action_summary: WorkspaceBoardActionSummaryRead
