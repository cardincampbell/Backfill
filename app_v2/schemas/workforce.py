from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional
from uuid import UUID

from pydantic import Field

from app_v2.schemas.common import BaseSchema


class EmployeeCreate(BaseSchema):
    full_name: str
    preferred_name: Optional[str] = None
    phone_e164: Optional[str] = None
    email: Optional[str] = None
    external_ref: Optional[str] = None
    employee_number: Optional[str] = None
    employment_type: Optional[str] = None
    home_location_id: Optional[UUID] = None
    hire_date: Optional[date] = None
    notes: Optional[str] = None
    employee_metadata: dict = Field(default_factory=dict)


class EmployeeRead(BaseSchema):
    id: UUID
    business_id: UUID
    home_location_id: Optional[UUID]
    external_ref: Optional[str]
    employee_number: Optional[str]
    full_name: str
    preferred_name: Optional[str]
    phone_e164: Optional[str]
    email: Optional[str]
    status: str
    employment_type: Optional[str]
    hire_date: Optional[date]
    termination_date: Optional[date]
    notes: Optional[str]
    employee_metadata: dict
    created_at: datetime
    updated_at: datetime


class EmployeeEnrollAtLocationCreate(BaseSchema):
    location_id: UUID
    role_ids: list[UUID]
    full_name: str
    preferred_name: Optional[str] = None
    phone_e164: Optional[str] = None
    email: Optional[str] = None
    external_ref: Optional[str] = None
    employee_number: Optional[str] = None
    employment_type: Optional[str] = None
    hire_date: Optional[date] = None
    notes: Optional[str] = None
    employee_metadata: dict = Field(default_factory=dict)


class EmployeeEnrollmentRead(BaseSchema):
    employee: EmployeeRead
    roles: list["EmployeeRoleRead"]


class EmployeeRoleCreate(BaseSchema):
    role_id: UUID
    proficiency_level: int = 1
    is_primary: bool = False
    role_metadata: dict = Field(default_factory=dict)


class EmployeeRoleRead(BaseSchema):
    id: UUID
    employee_id: UUID
    role_id: UUID
    proficiency_level: int
    is_primary: bool
    acquired_at: Optional[datetime]
    role_metadata: dict
    created_at: datetime
    updated_at: datetime


class EmployeeLocationClearanceCreate(BaseSchema):
    location_id: UUID
    access_level: str = "approved"
    clearance_source: Optional[str] = None
    can_cover_last_minute: bool = True
    can_blast: bool = True
    travel_radius_miles: Optional[int] = None
    clearance_metadata: dict = Field(default_factory=dict)


class EmployeeLocationClearanceRead(BaseSchema):
    id: UUID
    employee_id: UUID
    location_id: UUID
    access_level: str
    clearance_source: Optional[str]
    can_cover_last_minute: bool
    can_blast: bool
    travel_radius_miles: Optional[int]
    clearance_metadata: dict
    created_at: datetime
    updated_at: datetime


class EmployeeAvailabilityRuleCreate(BaseSchema):
    day_of_week: int
    start_local_time: time
    end_local_time: time
    timezone: str
    availability_type: str = "available"
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    priority: int = 0
    availability_metadata: dict = Field(default_factory=dict)


class EmployeeAvailabilityRuleRead(BaseSchema):
    id: UUID
    employee_id: UUID
    day_of_week: int
    start_local_time: time
    end_local_time: time
    timezone: str
    availability_type: str
    valid_from: Optional[date]
    valid_until: Optional[date]
    priority: int
    availability_metadata: dict
    created_at: datetime
    updated_at: datetime
