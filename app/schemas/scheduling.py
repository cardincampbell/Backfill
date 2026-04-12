from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


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


class ShiftDeleteResponse(BaseSchema):
    deleted: bool
    shift_id: UUID
