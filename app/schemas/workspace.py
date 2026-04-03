from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.schemas.common import BaseSchema
from app.schemas.identity import MembershipRead, UserRead


class WorkspaceLocationRead(BaseSchema):
    membership_id: UUID
    membership_role: str
    membership_scope: str
    business_id: UUID
    business_name: str
    business_slug: str
    location_id: UUID
    location_name: str
    location_slug: str
    address_line_1: Optional[str]
    locality: Optional[str]
    region: Optional[str]
    postal_code: Optional[str]
    country_code: str
    timezone: str
    google_place_id: Optional[str]


class WorkspaceBusinessRead(BaseSchema):
    business_id: UUID
    business_name: str
    business_slug: str
    membership_role: str
    location_count: int
    locations: list[WorkspaceLocationRead]


class WorkspaceRead(BaseSchema):
    user: UserRead
    memberships: list[MembershipRead]
    onboarding_required: bool
    businesses: list[WorkspaceBusinessRead]
    locations: list[WorkspaceLocationRead]
