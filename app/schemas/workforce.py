from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.models.common import EmployeeStatus
from app.schemas.common import BaseSchema

WeekdayName = Literal[
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
]


class EmployeeWorkPermitRuleProfile(BaseSchema):
    template_code: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    source_url: Optional[str] = None
    allowed_weekdays: list[WeekdayName] = Field(default_factory=list)
    daily_max_minutes: Optional[int] = Field(default=None, ge=0)
    daily_max_minutes_in_session: Optional[int] = Field(default=None, ge=0)
    daily_max_minutes_summer_break: Optional[int] = Field(default=None, ge=0)
    daily_max_minutes_school_day: Optional[int] = Field(default=None, ge=0)
    daily_max_minutes_non_school_day: Optional[int] = Field(default=None, ge=0)
    daily_max_minutes_preceding_non_school_day: Optional[int] = Field(default=None, ge=0)
    weekly_max_minutes: Optional[int] = Field(default=None, ge=0)
    weekly_max_minutes_in_session: Optional[int] = Field(default=None, ge=0)
    weekly_max_minutes_summer_break: Optional[int] = Field(default=None, ge=0)
    weekly_max_minutes_school_week: Optional[int] = Field(default=None, ge=0)
    weekly_max_minutes_non_school_week: Optional[int] = Field(default=None, ge=0)
    earliest_start_local_time: Optional[time] = None
    earliest_start_local_time_school_day: Optional[time] = None
    earliest_start_local_time_non_school_day: Optional[time] = None
    latest_end_local_time: Optional[time] = None
    latest_end_local_time_in_session: Optional[time] = None
    latest_end_local_time_summer_break: Optional[time] = None
    latest_end_local_time_school_day: Optional[time] = None
    latest_end_local_time_non_school_day: Optional[time] = None
    latest_end_local_time_preceding_non_school_day: Optional[time] = None


class EmployeeWorkPermitCreate(BaseSchema):
    permit_number: str
    issuing_authority: Optional[str] = None
    issued_on: Optional[date] = None
    effective_start_date: Optional[date] = None
    effective_end_date: Optional[date] = None
    max_daily_minutes: Optional[int] = Field(default=None, ge=0)
    max_weekly_minutes: Optional[int] = Field(default=None, ge=0)
    earliest_start_local_time: Optional[time] = None
    latest_end_local_time: Optional[time] = None
    rule_profile: Optional[EmployeeWorkPermitRuleProfile] = None
    permit_metadata: dict = Field(default_factory=dict)


class EmployeeWorkPermitRead(BaseSchema):
    id: UUID
    employee_id: UUID
    permit_number: str
    issuing_authority: Optional[str] = None
    issued_on: Optional[date] = None
    effective_start_date: Optional[date] = None
    effective_end_date: Optional[date] = None
    max_daily_minutes: Optional[int] = None
    max_weekly_minutes: Optional[int] = None
    earliest_start_local_time: Optional[time] = None
    latest_end_local_time: Optional[time] = None
    rule_profile: Optional[EmployeeWorkPermitRuleProfile] = None
    permit_metadata: dict
    created_at: datetime
    updated_at: datetime


class EmployeeWorkPermitTemplateRead(BaseSchema):
    code: str
    label: str
    description: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    source_url: Optional[str] = None
    source_document_title: Optional[str] = None
    source_version: Optional[str] = None
    source_hash: Optional[str] = None
    effective_start_date: Optional[date] = None
    effective_end_date: Optional[date] = None
    payload_hash: Optional[str] = None
    rule_families: list[str] = Field(default_factory=list)
    rule_profile: EmployeeWorkPermitRuleProfile


class EmployeeCreate(BaseSchema):
    full_name: str
    preferred_name: Optional[str] = None
    phone_e164: Optional[str] = None
    email: Optional[str] = None
    external_ref: Optional[str] = None
    employee_number: Optional[str] = None
    employment_type: Optional[str] = None
    base_hourly_rate_cents: Optional[int] = Field(default=None, ge=0)
    date_of_birth: Optional[date] = None
    minor_school_status: Optional[str] = None
    work_permit_number: Optional[str] = None
    work_permit_effective_start_on: Optional[date] = None
    work_permit_expires_on: Optional[date] = None
    work_permit_max_daily_minutes: Optional[int] = Field(default=None, ge=0)
    work_permit_max_weekly_minutes: Optional[int] = Field(default=None, ge=0)
    work_permit_earliest_start_local_time: Optional[time] = None
    work_permit_latest_end_local_time: Optional[time] = None
    work_permits: list[EmployeeWorkPermitCreate] = Field(default_factory=list)
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
    base_hourly_rate_cents: Optional[int] = None
    date_of_birth: Optional[date] = None
    minor_school_status: Optional[str] = None
    work_permit_number: Optional[str] = None
    work_permit_effective_start_on: Optional[date] = None
    work_permit_expires_on: Optional[date] = None
    work_permit_max_daily_minutes: Optional[int] = None
    work_permit_max_weekly_minutes: Optional[int] = None
    work_permit_earliest_start_local_time: Optional[time] = None
    work_permit_latest_end_local_time: Optional[time] = None
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
    base_hourly_rate_cents: Optional[int] = Field(default=None, ge=0)
    date_of_birth: Optional[date] = None
    minor_school_status: Optional[str] = None
    work_permit_number: Optional[str] = None
    work_permit_effective_start_on: Optional[date] = None
    work_permit_expires_on: Optional[date] = None
    work_permit_max_daily_minutes: Optional[int] = Field(default=None, ge=0)
    work_permit_max_weekly_minutes: Optional[int] = Field(default=None, ge=0)
    work_permit_earliest_start_local_time: Optional[time] = None
    work_permit_latest_end_local_time: Optional[time] = None
    work_permits: list[EmployeeWorkPermitCreate] = Field(default_factory=list)
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
    base_hourly_rate_cents: Optional[int] = Field(default=None, ge=0)
    date_of_birth: Optional[date] = None
    minor_school_status: Optional[str] = None
    work_permit_number: Optional[str] = None
    work_permit_effective_start_on: Optional[date] = None
    work_permit_expires_on: Optional[date] = None
    work_permit_max_daily_minutes: Optional[int] = Field(default=None, ge=0)
    work_permit_max_weekly_minutes: Optional[int] = Field(default=None, ge=0)
    work_permit_earliest_start_local_time: Optional[time] = None
    work_permit_latest_end_local_time: Optional[time] = None
    work_permits: Optional[list[EmployeeWorkPermitCreate]] = None
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
    work_permits: list[EmployeeWorkPermitRead] = Field(default_factory=list)


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
