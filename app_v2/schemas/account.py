from __future__ import annotations

from app_v2.schemas.common import BaseSchema
from app_v2.schemas.identity import UserRead


class AccountProfileUpdate(BaseSchema):
    full_name: str
    email: str


class AccountProfileResponse(BaseSchema):
    user: UserRead
    onboarding_required: bool
