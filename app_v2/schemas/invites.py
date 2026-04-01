from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app_v2.schemas.auth import OTPChallengeRequestResponse
from app_v2.schemas.common import BaseSchema


class ManagerAccessInviteCreate(BaseSchema):
    email: str
    manager_name: Optional[str] = None
    role: str = "manager"


class ManagerAccessEntry(BaseSchema):
    id: UUID
    location_id: UUID
    entry_kind: Literal["membership", "invite"]
    manager_name: Optional[str] = None
    manager_email: Optional[str] = None
    phone_e164: Optional[str] = None
    role: str
    invite_status: str
    invite_channel: str = "email"
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ManagerAccessInviteResponse(BaseSchema):
    location_id: UUID
    created: bool
    delivery_id: Optional[str] = None
    access: ManagerAccessEntry


class ManagerAccessRevokeResponse(BaseSchema):
    revoked: bool
    location_id: UUID
    access_kind: Literal["membership", "invite"]
    access_id: UUID


class ManagerInvitePreviewResponse(BaseSchema):
    invite_email: str
    manager_name: Optional[str] = None
    business_id: UUID
    business_name: str
    location_id: UUID
    location_name: str
    location_address: Optional[str] = None
    expires_at: Optional[datetime] = None
    invite_status: str
    invite_mode: Literal["setup_new", "existing_user"]


class ManagerInviteChallengeRequest(BaseSchema):
    phone_e164: str
    manager_name: Optional[str] = None
    locale: str = "en"
    challenge_metadata: dict = Field(default_factory=dict)


class ManagerInviteChallengeResponse(OTPChallengeRequestResponse):
    invite_mode: Literal["setup_new", "existing_user"]
