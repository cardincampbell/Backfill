from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class BusinessCreate(BaseSchema):
    legal_name: str
    brand_name: Optional[str] = None
    slug: Optional[str] = None
    vertical: Optional[str] = None
    primary_phone_e164: Optional[str] = None
    primary_email: Optional[str] = None
    timezone: str = "America/Los_Angeles"
    settings: dict = Field(default_factory=dict)
    place_metadata: dict = Field(default_factory=dict)


class BusinessProfileUpdate(BaseSchema):
    brand_name: str
    vertical: Optional[str] = None
    primary_email: Optional[str] = None
    timezone: str
    company_address: Optional[str] = None


class BusinessRead(BaseSchema):
    id: UUID
    legal_name: str
    brand_name: Optional[str]
    slug: str
    vertical: Optional[str]
    primary_phone_e164: Optional[str]
    primary_email: Optional[str]
    timezone: str
    status: str
    settings: dict
    place_metadata: dict
    created_at: datetime
    updated_at: datetime


class LocationCreate(BaseSchema):
    name: str
    slug: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    locality: Optional[str] = None
    region: Optional[str] = None
    postal_code: Optional[str] = None
    country_code: str = "US"
    timezone: str = "America/Los_Angeles"
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    google_place_id: Optional[str] = None
    google_place_metadata: dict = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)


class LocationRead(BaseSchema):
    id: UUID
    business_id: UUID
    name: str
    slug: str
    address_line_1: Optional[str]
    address_line_2: Optional[str]
    locality: Optional[str]
    region: Optional[str]
    postal_code: Optional[str]
    country_code: str
    timezone: str
    latitude: Optional[Decimal]
    longitude: Optional[Decimal]
    google_place_id: Optional[str]
    google_place_metadata: dict
    is_active: bool
    settings: dict
    created_at: datetime
    updated_at: datetime


class LocationDeleteResponse(BaseSchema):
    deleted: bool
    location_id: UUID


class RoleCreate(BaseSchema):
    code: Optional[str] = None
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    min_notice_minutes: int = 0
    default_shift_length_minutes: Optional[int] = None
    coverage_priority: int = 100
    metadata_json: dict = Field(default_factory=dict)


class RoleRead(BaseSchema):
    id: UUID
    business_id: UUID
    code: str
    name: str
    category: Optional[str]
    description: Optional[str]
    min_notice_minutes: int
    default_shift_length_minutes: Optional[int]
    coverage_priority: int
    metadata_json: dict
    created_at: datetime
    updated_at: datetime


class BusinessRoleDerivationRead(BaseSchema):
    business_id: UUID
    vertical: Optional[str]
    settings: dict
    roles: list[RoleRead]


class LocationRoleAttach(BaseSchema):
    min_headcount: Optional[int] = None
    max_headcount: Optional[int] = None
    premium_rules: dict = Field(default_factory=dict)
    coverage_settings: dict = Field(default_factory=dict)


class LocationRoleRead(BaseSchema):
    id: UUID
    location_id: UUID
    role_id: UUID
    is_active: bool
    min_headcount: Optional[int]
    max_headcount: Optional[int]
    premium_rules: dict
    coverage_settings: dict
    created_at: datetime
    updated_at: datetime
