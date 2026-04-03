from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app_v2.api.deps import AuthDep, SessionDep
from app_v2.models.common import AuditActorType, MembershipRole
from app_v2.schemas.identity import MembershipCreate, MembershipRead, UserRead
from app_v2.services import audit as audit_service
from app_v2.services import auth as auth_service, identity

router = APIRouter(tags=["v2-identity"])
ADMIN_ROLES = {MembershipRole.owner, MembershipRole.admin}


@router.get("/users", response_model=list[UserRead])
async def list_users(session: SessionDep, auth_ctx: AuthDep):
    return [auth_ctx.user]

@router.get("/users/{user_id}", response_model=UserRead)
async def get_user(user_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    if auth_ctx.user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user_access_denied")
    user = await identity.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    return user


@router.get("/businesses/{business_id}/memberships", response_model=list[MembershipRead])
async def list_memberships(business_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    return await identity.list_memberships_for_business(session, business_id)


@router.post("/businesses/{business_id}/memberships", response_model=MembershipRead, status_code=status.HTTP_201_CREATED)
async def create_membership(
    business_id: UUID,
    payload: MembershipCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        membership = await identity.create_membership(session, business_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    actor_membership = auth_service.membership_for_scope(auth_ctx, business_id)
    await audit_service.append(
        session,
        event_name="membership.granted",
        target_type="membership",
        target_id=membership.id,
        business_id=business_id,
        location_id=membership.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=actor_membership.id if actor_membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={"role": membership.role, "status": membership.status},
    )
    await session.commit()
    return membership
