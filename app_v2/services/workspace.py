from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_v2.models.business import Business, Location
from app_v2.models.common import MembershipRole, MembershipStatus
from app_v2.models.identity import Membership
from app_v2.services import auth as auth_service


ROLE_ORDER = {
    MembershipRole.owner: 4,
    MembershipRole.admin: 3,
    MembershipRole.manager: 2,
    MembershipRole.viewer: 1,
}


@dataclass
class WorkspaceLocation:
    membership: Membership
    business: Business
    location: Location
    membership_scope: str


def _better_membership(candidate: Membership, current: Membership | None) -> bool:
    if current is None:
        return True
    if ROLE_ORDER.get(candidate.role, 0) != ROLE_ORDER.get(current.role, 0):
        return ROLE_ORDER.get(candidate.role, 0) > ROLE_ORDER.get(current.role, 0)
    if candidate.location_id is None and current.location_id is not None:
        return True
    if candidate.location_id is not None and current.location_id is None:
        return False
    return candidate.created_at > current.created_at


async def list_workspace_locations(
    session: AsyncSession,
    auth_ctx: auth_service.AuthContext,
) -> list[WorkspaceLocation]:
    memberships = [
        membership
        for membership in auth_ctx.memberships
        if membership.status == MembershipStatus.active and membership.revoked_at is None
    ]
    business_ids = sorted({membership.business_id for membership in memberships})
    if not business_ids:
        return []

    business_rows = await session.execute(select(Business).where(Business.id.in_(business_ids)))
    businesses = {business.id: business for business in business_rows.scalars().all()}

    location_rows = await session.execute(
        select(Location)
        .where(Location.business_id.in_(business_ids), Location.is_active.is_(True))
        .order_by(Location.created_at.desc())
    )
    locations = list(location_rows.scalars().all())

    by_location: dict[UUID, WorkspaceLocation] = {}
    for location in locations:
        business = businesses.get(location.business_id)
        if business is None:
            continue
        for membership in memberships:
            if membership.business_id != location.business_id:
                continue
            if membership.location_id is not None and membership.location_id != location.id:
                continue
            current = by_location.get(location.id)
            if _better_membership(membership, current.membership if current is not None else None):
                by_location[location.id] = WorkspaceLocation(
                    membership=membership,
                    business=business,
                    location=location,
                    membership_scope="business" if membership.location_id is None else "location",
                )

    return sorted(
        by_location.values(),
        key=lambda item: (
            item.business.brand_name or item.business.legal_name,
            item.location.name,
        ),
    )
