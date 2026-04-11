from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import AuthDep, SessionDep
from app.models.common import MembershipRole
from app.schemas.events import PlatformEventRead
from app.services import auth as auth_service
from app.services import feed_projections

router = APIRouter(prefix="/businesses/{business_id}/events", tags=["events"])
MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}


@router.get("", response_model=list[PlatformEventRead])
async def list_platform_events(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    location_id: UUID | None = None,
    entity_type: str | None = None,
    event_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=250),
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=403, detail="business_access_denied")
    return await feed_projections.list_feed_events(
        session,
        business_id=business_id,
        location_id=location_id,
        entity_type=entity_type,
        event_type=event_type,
        limit=limit,
    )
