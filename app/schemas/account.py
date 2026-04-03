from __future__ import annotations

from app.schemas.common import BaseSchema
from app.schemas.identity import UserRead


class AccountProfileUpdate(BaseSchema):
    full_name: str
    email: str


class AccountProfileResponse(BaseSchema):
    user: UserRead
    onboarding_required: bool
