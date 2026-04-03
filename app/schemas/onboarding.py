from __future__ import annotations

from datetime import datetime

from app.schemas.business import BusinessCreate, BusinessRead, LocationCreate, LocationRead
from app.schemas.common import BaseSchema
from app.schemas.identity import MembershipRead, UserRead


class OnboardingProfileUpdate(BaseSchema):
    full_name: str
    email: str


class OnboardingProfileResponse(BaseSchema):
    user: UserRead
    memberships: list[MembershipRead]
    onboarding_required: bool


class OwnerWorkspaceBootstrapRequest(BaseSchema):
    profile: OnboardingProfileUpdate
    business: BusinessCreate
    location: LocationCreate


class OwnerWorkspaceBootstrapResponse(BaseSchema):
    user: UserRead
    business: BusinessRead
    location: LocationRead
    owner_membership: MembershipRead
    onboarding_required: bool
    created_at: datetime
