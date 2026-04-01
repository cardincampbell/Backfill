from __future__ import annotations

from collections import defaultdict
from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app_v2.api.deps import AuthDep, SessionDep
from app_v2.models.common import MembershipRole
from app_v2.schemas.workspace import WorkspaceBusinessRead, WorkspaceLocationRead, WorkspaceRead
from app_v2.services import auth as auth_service
from app_v2.services import workspace as workspace_service
from app_v2.services import workspace_board as workspace_board_service
from app_v2.schemas.workspace_board import WorkspaceLocationBoardRead

router = APIRouter(prefix="/workspace", tags=["v2-workspace"])
READ_ROLES = {
    MembershipRole.owner,
    MembershipRole.admin,
    MembershipRole.manager,
    MembershipRole.viewer,
}


@router.get("", response_model=WorkspaceRead)
async def get_workspace(session: SessionDep, auth_ctx: AuthDep):
    workspace_locations = await workspace_service.list_workspace_locations(session, auth_ctx)
    location_rows = [
        WorkspaceLocationRead(
            membership_id=item.membership.id,
            membership_role=item.membership.role,
            membership_scope=item.membership_scope,
            business_id=item.business.id,
            business_name=item.business.brand_name or item.business.legal_name,
            business_slug=item.business.slug,
            location_id=item.location.id,
            location_name=item.location.name,
            location_slug=item.location.slug,
            address_line_1=item.location.address_line_1,
            locality=item.location.locality,
            region=item.location.region,
            postal_code=item.location.postal_code,
            country_code=item.location.country_code,
            timezone=item.location.timezone,
            google_place_id=item.location.google_place_id,
        )
        for item in workspace_locations
    ]

    business_groups: dict[str, list[WorkspaceLocationRead]] = defaultdict(list)
    for row in location_rows:
        business_groups[str(row.business_id)].append(row)

    businesses = [
        WorkspaceBusinessRead(
            business_id=rows[0].business_id,
            business_name=rows[0].business_name,
            business_slug=rows[0].business_slug,
            membership_role=max(rows, key=lambda row: {"viewer": 1, "manager": 2, "admin": 3, "owner": 4}.get(row.membership_role, 0)).membership_role,
            location_count=len(rows),
            locations=rows,
        )
        for rows in business_groups.values()
    ]
    businesses.sort(key=lambda item: item.business_name.lower())

    return WorkspaceRead(
        user=auth_ctx.user,
        memberships=auth_ctx.memberships,
        onboarding_required=auth_service.onboarding_required_for_user(auth_ctx.user),
        businesses=businesses,
        locations=location_rows,
    )


@router.get(
    "/businesses/{business_id}/locations/{location_id}/board",
    response_model=WorkspaceLocationBoardRead,
)
async def get_location_board(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    week_start: date | None = None,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=READ_ROLES,
    ):
        raise HTTPException(status_code=403, detail="location_access_denied")
    try:
        return await workspace_board_service.get_location_board(
            session,
            business_id=business_id,
            location_id=location_id,
            week_start=week_start,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
