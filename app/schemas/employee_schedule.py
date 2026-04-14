from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from app.schemas.common import BaseSchema


class EmployeeScheduleLinkRead(BaseSchema):
    schedule_url: str
    rotated_at: Optional[datetime]


class PublicEmployeeScheduleLocationRead(BaseSchema):
    location_id: UUID
    location_name: str
    location_timezone: str


class PublicEmployeeScheduleShiftRead(BaseSchema):
    shift_id: UUID
    location_id: UUID
    location_name: str
    role_id: UUID
    role_name: str
    starts_at: datetime
    ends_at: datetime
    timezone: str
    lifecycle_status: str
    staffing_status: str
    notes: Optional[str] = None


class PublicEmployeeScheduleRead(BaseSchema):
    business_id: UUID
    business_name: str
    employee_id: UUID
    employee_name: str
    timezone: str
    week_start_day: str
    week_start_date: date
    week_end_date: date
    selected_location_id: Optional[UUID] = None
    selected_location_name: Optional[str] = None
    available_locations: list[PublicEmployeeScheduleLocationRead]
    shifts: list[PublicEmployeeScheduleShiftRead]
