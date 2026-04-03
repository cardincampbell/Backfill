from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema
from app.schemas.identity import MembershipRead, UserRead


class SessionCreateRequest(BaseSchema):
    user_id: UUID
    device_fingerprint: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    risk_level: str = "low"
    elevated_actions: list[str] = Field(default_factory=list)
    ttl_hours: int = 336
    session_metadata: dict = Field(default_factory=dict)


class SessionRead(BaseSchema):
    id: UUID
    user_id: UUID
    device_fingerprint: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    risk_level: str
    elevated_actions: list
    last_seen_at: Optional[datetime]
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    session_metadata: dict
    created_at: datetime
    updated_at: datetime


class SessionCreateResponse(BaseSchema):
    token: str
    session: SessionRead


class AuthMeResponse(BaseSchema):
    user: UserRead
    session: SessionRead
    memberships: list[MembershipRead]
    onboarding_required: bool


class OTPChallengeRequest(BaseSchema):
    phone_e164: str
    purpose: str = "sign_in"
    channel: str = "sms"
    locale: str = "en"
    business_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    challenge_metadata: dict = Field(default_factory=dict)


class OTPChallengeRead(BaseSchema):
    id: UUID
    user_id: Optional[UUID]
    phone_e164: str
    external_sid: Optional[str]
    channel: str
    purpose: str
    status: str
    attempt_count: int
    max_attempts: int
    requested_for_business_id: Optional[UUID]
    requested_for_location_id: Optional[UUID]
    expires_at: Optional[datetime]
    approved_at: Optional[datetime]
    challenge_metadata: dict
    created_at: datetime
    updated_at: datetime


class OTPChallengeRequestResponse(BaseSchema):
    challenge: OTPChallengeRead


class OTPChallengeVerifyRequest(BaseSchema):
    challenge_id: UUID
    phone_e164: str
    code: str
    device_fingerprint: Optional[str] = None
    risk_level: str = "low"
    session_metadata: dict = Field(default_factory=dict)


class OTPChallengeVerifyResponse(BaseSchema):
    challenge: OTPChallengeRead
    user: UserRead
    session: Optional[SessionRead] = None
    token: Optional[str] = None
    onboarding_required: bool
    step_up_granted: bool = False
