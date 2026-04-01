from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app_v2.schemas.common import BaseSchema


class UserUpsert(BaseSchema):
    full_name: Optional[str] = None
    email: Optional[str] = None
    primary_phone_e164: Optional[str] = None
    is_phone_verified: bool = False
    profile_metadata: dict = Field(default_factory=dict)


class UserRead(BaseSchema):
    id: UUID
    full_name: Optional[str]
    email: Optional[str]
    primary_phone_e164: Optional[str]
    is_phone_verified: bool
    onboarding_completed_at: Optional[datetime]
    last_sign_in_at: Optional[datetime]
    profile_metadata: dict
    created_at: datetime
    updated_at: datetime


class MembershipCreate(BaseSchema):
    user_id: UUID
    role: str = "manager"
    location_id: Optional[UUID] = None
    status: str = "pending"
    invited_by_user_id: Optional[UUID] = None
    membership_metadata: dict = Field(default_factory=dict)


class MembershipRead(BaseSchema):
    id: UUID
    user_id: UUID
    business_id: UUID
    location_id: Optional[UUID]
    role: str
    status: str
    invited_by_user_id: Optional[UUID]
    accepted_at: Optional[datetime]
    revoked_at: Optional[datetime]
    membership_metadata: dict
    created_at: datetime
    updated_at: datetime
