from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AuthDep, SessionDep
from app.models.common import AuditActorType, MembershipRole, MembershipStatus
from app.models.identity import Membership
from app.schemas.business import (
    BusinessCreate,
    BusinessProfileUpdate,
    BusinessRoleDerivationRead,
    BusinessRead,
    LocationCreate,
    LocationDeleteResponse,
    LocationRead,
    LocationRoleAttach,
    LocationRoleRead,
    RoleCreate,
    RoleRead,
)
from app.schemas.settings import LocationSettingsRead, LocationSettingsUpdate
from app.services import audit as audit_service
from app.services import auth as auth_service, businesses, settings as settings_service

router = APIRouter(prefix="/businesses", tags=["businesses"])

MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}
ADMIN_ROLES = {MembershipRole.owner, MembershipRole.admin}


@router.get("", response_model=list[BusinessRead])
async def list_businesses(session: SessionDep, auth_ctx: AuthDep):
    business_ids = list({membership.business_id for membership in auth_ctx.memberships})
    return await businesses.list_businesses(session, business_ids=business_ids)


@router.post("", response_model=BusinessRead, status_code=status.HTTP_201_CREATED)
async def create_business(payload: BusinessCreate, session: SessionDep, auth_ctx: AuthDep):
    business = await businesses.create_business(session, payload)
    owner_membership = Membership(
        user_id=auth_ctx.user.id,
        business_id=business.id,
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        accepted_at=datetime.now(timezone.utc),
        membership_metadata={"source": "business_create"},
    )
    session.add(owner_membership)
    await session.flush()
    await audit_service.append(
        session,
        event_name="business.created",
        target_type="business",
        target_id=business.id,
        business_id=business.id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=owner_membership.id,
        payload={"brand_name": business.brand_name, "legal_name": business.legal_name},
    )
    await audit_service.append(
        session,
        event_name="membership.granted",
        target_type="membership",
        target_id=owner_membership.id,
        business_id=business.id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=owner_membership.id,
        payload={"role": owner_membership.role.value, "status": owner_membership.status.value},
    )
    await session.commit()
    return business


@router.get("/{business_id}", response_model=BusinessRead)
async def get_business(business_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    business = await businesses.get_business(session, business_id)
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="business_not_found")
    return business


@router.patch("/{business_id}", response_model=BusinessRead)
async def update_business(
    business_id: UUID,
    payload: BusinessProfileUpdate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    business = await businesses.get_business(session, business_id)
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="business_not_found")
    try:
        changes = await businesses.update_business_profile(session, business, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    if changes:
        await audit_service.append(
            session,
            event_name="business.profile.updated",
            target_type="business",
            target_id=business.id,
            business_id=business.id,
            actor_type=AuditActorType.user,
            actor_user_id=auth_ctx.user.id,
            actor_membership_id=membership.id if membership is not None else None,
            ip_address=audit_service.request_client_ip(request),
            user_agent=audit_service.request_user_agent(request),
            payload=changes,
        )
        await session.commit()
        await session.refresh(business)
    return business


@router.get("/{business_id}/locations", response_model=list[LocationRead])
async def list_locations(business_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    return await businesses.list_locations(session, business_id)


@router.get("/{business_id}/locations/{location_id}", response_model=LocationRead)
async def get_location(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=MANAGER_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_access_denied")
    location = await businesses.get_location(session, business_id, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="location_not_found")
    return location


@router.post("/{business_id}/locations", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
async def create_location(
    business_id: UUID,
    payload: LocationCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        location = await businesses.create_location(session, business_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    await audit_service.append(
        session,
        event_name="location.created",
        target_type="location",
        target_id=location.id,
        business_id=business_id,
        location_id=location.id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={"name": location.name, "slug": location.slug},
    )
    await session.commit()
    return location


@router.delete(
    "/{business_id}/locations/{location_id}",
    response_model=LocationDeleteResponse,
)
async def delete_location(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        location = await businesses.delete_location(session, business_id, location_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        detail = str(exc)
        if detail == "location_has_operational_data":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This location already has operational data and cannot be deleted from the account profile.",
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=location_id)
    await audit_service.append(
        session,
        event_name="location.deleted",
        target_type="location",
        target_id=location.id,
        business_id=business_id,
        location_id=location.id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={"name": location.name, "slug": location.slug},
    )
    await session.commit()
    return LocationDeleteResponse(deleted=True, location_id=location.id)


@router.get(
    "/{business_id}/locations/{location_id}/settings",
    response_model=LocationSettingsRead,
)
async def get_location_settings(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=MANAGER_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_access_denied")
    try:
        return await settings_service.get_location_settings(
            session,
            business_id=business_id,
            location_id=location_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/{business_id}/locations/{location_id}/settings",
    response_model=LocationSettingsRead,
)
async def update_location_settings(
    business_id: UUID,
    location_id: UUID,
    payload: LocationSettingsUpdate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=MANAGER_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_access_denied")
    try:
        settings_state = await settings_service.update_location_settings(
            session,
            business_id=business_id,
            location_id=location_id,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=location_id)
    await audit_service.append(
        session,
        event_name="location.settings.updated",
        target_type="location",
        target_id=location_id,
        business_id=business_id,
        location_id=location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload=payload.model_dump(exclude_unset=True),
    )
    await session.commit()
    return settings_state


@router.get("/{business_id}/roles", response_model=list[RoleRead])
async def list_roles(business_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    return await businesses.list_roles(session, business_id)


@router.post("/{business_id}/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    business_id: UUID,
    payload: RoleCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        role = await businesses.create_role(session, business_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    await audit_service.append(
        session,
        event_name="role.created",
        target_type="role",
        target_id=role.id,
        business_id=business_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={"name": role.name, "code": role.code},
    )
    await session.commit()
    return role


@router.post(
    "/{business_id}/roles/derive",
    response_model=BusinessRoleDerivationRead,
)
async def derive_roles_for_business(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        business, roles = await businesses.rerun_role_derivation(session, business_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    derived_classification = business.settings.get("derived_classification", {})
    await audit_service.append(
        session,
        event_name="business.roles.derived",
        target_type="business",
        target_id=business.id,
        business_id=business.id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "vertical": business.vertical,
            "role_count": len(roles),
            "derivation_version": derived_classification.get("derivation_version"),
        },
    )
    await session.commit()
    return BusinessRoleDerivationRead(
        business_id=business.id,
        vertical=business.vertical,
        settings=business.settings,
        roles=roles,
    )


@router.post(
    "/{business_id}/locations/{location_id}/roles/{role_id}",
    response_model=LocationRoleRead,
    status_code=status.HTTP_201_CREATED,
)
async def attach_role_to_location(
    business_id: UUID,
    location_id: UUID,
    role_id: UUID,
    payload: LocationRoleAttach,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        location_role = await businesses.attach_role_to_location(session, business_id, location_id, role_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return location_role
