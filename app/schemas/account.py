from __future__ import annotations

from typing import Literal

from app.schemas.common import BaseSchema
from app.schemas.identity import UserRead


class AccountProfileUpdate(BaseSchema):
    full_name: str
    email: str
    appearance_preference: Literal["light", "dark", "system"] | None = None


class AccountProfileResponse(BaseSchema):
    user: UserRead
    onboarding_required: bool
