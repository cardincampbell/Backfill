from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.models.common import EmployeeStatus
from app.schemas.common import BaseSchema


class EmployeeCreate(BaseSchema):
    full_name: str
    preferred_name: Optional[str] = None
    phone_e164: Optional[str] = None
    email: Optional[str] = None
    external_ref: Optional[str] = None
    employee_number: Optional[str] = None
    employment_type: Optional[str] = None
    primary_location_id: Optional[UUID] = None
    hire_date: Optional[date] = None
    notes: Optional[str] = None
    employee_metadata: dict = Field(default_factory=dict)


class EmployeeNotificationPreferencesRead(BaseSchema):
    schedule_publish_email_enabled: bool = True
    schedule_publish_sms_enabled: bool = False
    email_opted_out_at: Optional[datetime] = None
    sms_opted_out_at: Optional[datetime] = None
    email_opt_out_reason: Optional[str] = None
    sms_opt_out_reason: Optional[str] = None


class EmployeeNotificationPreferencesUpdate(BaseSchema):
    schedule_publish_email_enabled: Optional[bool] = None
    schedule_publish_sms_enabled: Optional[bool] = None
    email_opted_out_at: Optional[datetime] = None
    sms_opted_out_at: Optional[datetime] = None
    email_opt_out_reason: Optional[str] = None
    sms_opt_out_reason: Optional[str] = None


class EmployeeRead(BaseSchema):
    id: UUID
    business_id: UUID
    primary_location_id: Optional[UUID]
    primary_location_name: Optional[str] = None
    primary_role_id: Optional[UUID] = None
    primary_role_name: Optional[str] = None
    external_ref: Optional[str]
    employee_number: Optional[str]
    full_name: str
    preferred_name: Optional[str]
    phone_e164: Optional[str]
    email: Optional[str]
    reliability_score: Optional[float] = 0.7
    status: str
    employment_type: Optional[str]
    hire_date: Optional[date]
    termination_date: Optional[date]
    notes: Optional[str]
    employee_metadata: dict
    notification_preferences: EmployeeNotificationPreferencesRead = Field(
        default_factory=EmployeeNotificationPreferencesRead
    )
    role_ids: list[UUID] = Field(default_factory=list)
    role_names: list[str] = Field(default_factory=list)
    location_ids: list[UUID] = Field(default_factory=list)
    location_names: list[str] = Field(default_factory=list)
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


class EmployeeImportErrorRead(BaseSchema):
    row_number: Optional[int] = None
    message: str


class EmployeeBulkImportRead(BaseSchema):
    created_count: int
    skipped_count: int
    employees: list[EmployeeRead] = Field(default_factory=list)
    errors: list[EmployeeImportErrorRead] = Field(default_factory=list)
    default_location_id: Optional[UUID] = None
    default_location_name: Optional[str] = None


class EmployeeRoleCreate(BaseSchema):
    role_id: UUID
    proficiency_level: int = 1
    is_primary: bool = False
    role_metadata: dict = Field(default_factory=dict)


class EmployeeRoleRead(BaseSchema):
    id: UUID
    employee_id: UUID
    role_id: UUID
    role_code: Optional[str] = None
    role_name: Optional[str] = None
    proficiency_level: int
    is_primary: bool
    acquired_at: Optional[datetime]
    role_metadata: dict
    created_at: datetime
    updated_at: datetime


class EmployeeLocationCreate(BaseSchema):
    location_id: UUID
    is_primary: bool = False
    access_level: str = "approved"
    location_source: Optional[str] = None
    can_cover_last_minute: bool = True
    can_blast: bool = True
    travel_radius_miles: Optional[int] = None
    location_metadata: dict = Field(default_factory=dict)


class EmployeeLocationRead(BaseSchema):
    id: UUID
    employee_id: UUID
    location_id: UUID
    location_name: Optional[str] = None
    location_slug: Optional[str] = None
    is_primary: bool
    access_level: str
    location_source: Optional[str]
    can_cover_last_minute: bool
    can_blast: bool
    travel_radius_miles: Optional[int]
    location_metadata: dict
    created_at: datetime
    updated_at: datetime


class EmployeeRoleUpsert(BaseSchema):
    role_id: UUID
    proficiency_level: Optional[int] = None
    is_primary: bool = False
    role_metadata: Optional[dict] = None


class EmployeeLocationUpsert(BaseSchema):
    location_id: UUID
    is_primary: bool = False
    access_level: Optional[str] = None
    location_source: Optional[str] = None
    can_cover_last_minute: Optional[bool] = None
    can_blast: Optional[bool] = None
    travel_radius_miles: Optional[int] = None
    location_metadata: Optional[dict] = None


class EmployeeUpdate(BaseSchema):
    full_name: Optional[str] = None
    preferred_name: Optional[str] = None
    phone_e164: Optional[str] = None
    email: Optional[str] = None
    external_ref: Optional[str] = None
    employee_number: Optional[str] = None
    employment_type: Optional[str] = None
    status: Optional[EmployeeStatus] = None
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None
    notes: Optional[str] = None
    employee_metadata: Optional[dict] = None
    notification_preferences: Optional[EmployeeNotificationPreferencesUpdate] = None
    roles: Optional[list[EmployeeRoleUpsert]] = None
    locations: Optional[list[EmployeeLocationUpsert]] = None


class EmployeeProfileRead(EmployeeRead):
    roles: list[EmployeeRoleRead] = Field(default_factory=list)
    locations: list[EmployeeLocationRead] = Field(default_factory=list)


class EmployeeDeleteReadinessRead(BaseSchema):
    business_id: UUID
    employee_id: UUID
    can_delete: bool
    reason: Optional[str] = None


class EmployeeDeleteResponse(BaseSchema):
    deleted: bool
    employee_id: UUID


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


class EmployeeAvailabilityRuleReplace(BaseSchema):
    rules: list[EmployeeAvailabilityRuleCreate] = Field(default_factory=list)


class SelfEmployeeAvailabilityRead(BaseSchema):
    employee_id: UUID
    employee_name: str
    timezone: str
    rules: list[EmployeeAvailabilityRuleRead] = Field(default_factory=list)
