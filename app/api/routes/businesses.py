from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import AuthDep, SessionDep
from app.models.common import AuditActorType, MembershipRole, MembershipStatus
from app.models.identity import Membership
from app.schemas.business import (
    BusinessCreate,
    BusinessIdentityDerivationRead,
    BusinessProfileUpdate,
    BusinessRoleDerivationRead,
    BusinessRead,
    LocationCreate,
    LocationDeleteResponse,
    LocationDeleteReadinessRead,
    LocationRead,
    LocationRoleAttach,
    LocationRoleCreateAndAssign,
    LocationRoleCreateAndAssignRead,
    LocationRoleReplace,
    LocationRoleRead,
    RoleCreate,
    RoleCreateResultRead,
    RoleRead,
)
from app.schemas.reliability_coaching import (
    ReliabilityCoachingCaseCloseWrite,
    ReliabilityCoachingCaseDetailRead,
    ReliabilityCoachingCaseRead,
    ReliabilityCoachingCaseSuppressWrite,
)
from app.schemas.settings import LocationSettingsRead, LocationSettingsUpdate
from app.schemas.settings import (
    BusinessShiftDefaultsRead,
    BusinessShiftDefaultsUpdate,
    LocationShiftDefaultsRead,
    LocationShiftDefaultsUpdate,
)
from app.services import audit as audit_service
from app.services import auth as auth_service, businesses, role_normalization, settings as settings_service
from app.services import reliability_coaching

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
        payload={"name": business.name, "display_name": business.display_name},
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


@router.get(
    "/{business_id}/reliability-coaching/cases",
    response_model=list[ReliabilityCoachingCaseRead],
)
async def list_reliability_coaching_cases(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    employee_id: UUID | None = None,
    limit: int = 50,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    coaching_cases = await reliability_coaching.list_business_coaching_cases(
        session,
        business_id=business_id,
        employee_id=employee_id,
        limit=limit,
    )
    return [reliability_coaching.coaching_case_read(coaching_case) for coaching_case in coaching_cases]


@router.get(
    "/{business_id}/reliability-coaching/cases/{coaching_case_id}",
    response_model=ReliabilityCoachingCaseDetailRead,
)
async def get_reliability_coaching_case(
    business_id: UUID,
    coaching_case_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    coaching_case = await reliability_coaching.get_business_coaching_case(
        session,
        business_id=business_id,
        coaching_case_id=coaching_case_id,
    )
    if coaching_case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="reliability_coaching_case_not_found")
    return reliability_coaching.coaching_case_detail_read(coaching_case)


@router.post(
    "/{business_id}/reliability-coaching/cases/{coaching_case_id}/suppress",
    response_model=ReliabilityCoachingCaseDetailRead,
)
async def suppress_reliability_coaching_case(
    business_id: UUID,
    coaching_case_id: UUID,
    payload: ReliabilityCoachingCaseSuppressWrite,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    try:
        coaching_case = await reliability_coaching.suppress_coaching_case(
            session,
            business_id=business_id,
            coaching_case_id=coaching_case_id,
            actor_user_id=auth_ctx.user.id,
            reason_code=payload.reason_code,
            note=payload.note,
            expires_at=payload.expires_at,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await audit_service.append(
        session,
        event_name="reliability_coaching.case.suppressed",
        target_type="reliability_coaching_case",
        target_id=coaching_case.id,
        business_id=business_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload=payload.model_dump(mode="json"),
    )
    await session.commit()
    return reliability_coaching.coaching_case_detail_read(coaching_case)


@router.post(
    "/{business_id}/reliability-coaching/cases/{coaching_case_id}/close",
    response_model=ReliabilityCoachingCaseDetailRead,
)
async def close_reliability_coaching_case(
    business_id: UUID,
    coaching_case_id: UUID,
    payload: ReliabilityCoachingCaseCloseWrite,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    try:
        coaching_case = await reliability_coaching.close_coaching_case(
            session,
            business_id=business_id,
            coaching_case_id=coaching_case_id,
            reason_code=payload.reason_code,
            note=payload.note,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await audit_service.append(
        session,
        event_name="reliability_coaching.case.closed",
        target_type="reliability_coaching_case",
        target_id=coaching_case.id,
        business_id=business_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload=payload.model_dump(mode="json"),
    )
    await session.commit()
    return reliability_coaching.coaching_case_detail_read(coaching_case)


@router.get(
    "/{business_id}/shift-defaults",
    response_model=BusinessShiftDefaultsRead,
)
async def get_business_shift_defaults(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        return await settings_service.get_business_shift_defaults(
            session,
            business_id=business_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/{business_id}/shift-defaults",
    response_model=BusinessShiftDefaultsRead,
)
async def update_business_shift_defaults(
    business_id: UUID,
    payload: BusinessShiftDefaultsUpdate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        defaults = await settings_service.update_business_shift_defaults(
            session,
            business_id=business_id,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    await audit_service.append(
        session,
        event_name="business.shift_defaults.updated",
        target_type="business",
        target_id=business_id,
        business_id=business_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload=payload.model_dump(),
    )
    await session.commit()
    return defaults


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
    except ValueError as exc:
        detail = str(exc)
        if detail == "location_already_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
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
        payload={"name": location.name, "display_name": location.display_name, "slug": location.slug},
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
                detail="This location has historical shifts and cannot be deleted from the account profile.",
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
        payload={"name": location.name, "display_name": location.display_name, "slug": location.slug},
    )
    await session.commit()
    return LocationDeleteResponse(deleted=True, location_id=location.id)


@router.get(
    "/{business_id}/locations/{location_id}/delete-readiness",
    response_model=LocationDeleteReadinessRead,
)
async def get_location_delete_readiness(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        return await businesses.get_location_delete_readiness(
            session,
            business_id=business_id,
            location_id=location_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


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


@router.get(
    "/{business_id}/locations/{location_id}/shift-defaults",
    response_model=LocationShiftDefaultsRead,
)
async def get_location_shift_defaults(
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
        return await settings_service.get_location_shift_defaults(
            session,
            business_id=business_id,
            location_id=location_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/{business_id}/locations/{location_id}/shift-defaults",
    response_model=LocationShiftDefaultsRead,
)
async def update_location_shift_defaults(
    business_id: UUID,
    location_id: UUID,
    payload: LocationShiftDefaultsUpdate,
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
        defaults = await settings_service.update_location_shift_defaults(
            session,
            business_id=business_id,
            location_id=location_id,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=location_id)
    await audit_service.append(
        session,
        event_name="location.shift_defaults.updated",
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
    return defaults


@router.get("/{business_id}/roles", response_model=list[RoleRead])
async def list_roles(business_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    return await businesses.list_roles(session, business_id)


@router.post("/{business_id}/roles", response_model=RoleCreateResultRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    business_id: UUID,
    payload: RoleCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
    response: Response,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        result = await businesses.create_role(session, business_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except role_normalization.RoleNameRejectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except ValueError as exc:
        detail = str(exc)
        if detail == "role_already_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
    if result.decision == "created_new":
        membership = auth_service.membership_for_scope(auth_ctx, business_id)
        await audit_service.append(
            session,
            event_name="role.created",
            target_type="role",
            target_id=result.role.id,
            business_id=business_id,
            actor_type=AuditActorType.user,
            actor_user_id=auth_ctx.user.id,
            actor_membership_id=membership.id if membership is not None else None,
            ip_address=audit_service.request_client_ip(request),
            user_agent=audit_service.request_user_agent(request),
            payload={"name": result.role.name, "code": result.role.code},
        )
    else:
        response.status_code = status.HTTP_200_OK
    await session.commit()
    return result


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
    "/{business_id}/identity/derive",
    response_model=BusinessIdentityDerivationRead,
)
async def derive_business_identity(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        business = await businesses.rerun_business_identity_derivation(session, business_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    derived_identity = business.settings.get("derived_identity", {})
    await audit_service.append(
        session,
        event_name="business.identity.derived",
        target_type="business",
        target_id=business.id,
        business_id=business.id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "display_name": business.display_name,
            "confidence": derived_identity.get("name_derivation_confidence"),
            "derivation_version": derived_identity.get("derivation_version"),
        },
    )
    await session.commit()
    return BusinessIdentityDerivationRead(
        business_id=business.id,
        display_name=business.display_name,
        settings=business.settings,
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


@router.get(
    "/{business_id}/locations/{location_id}/roles",
    response_model=list[LocationRoleRead],
)
async def list_location_roles(
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
        return await businesses.list_location_roles(session, business_id, location_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{business_id}/locations/{location_id}/roles",
    response_model=LocationRoleCreateAndAssignRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_and_assign_location_role(
    business_id: UUID,
    location_id: UUID,
    payload: LocationRoleCreateAndAssign,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        role, location_role = await businesses.create_and_assign_location_role(
            session,
            business_id,
            location_id,
            payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except role_normalization.RoleNameRejectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=location_id)
    await audit_service.append(
        session,
        event_name="location.role.created_and_attached",
        target_type="location_role",
        target_id=location_role.id,
        business_id=business_id,
        location_id=location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "role_id": str(role.id),
            "role_name": role.name,
            "location_role_id": str(location_role.id),
        },
    )
    await session.commit()
    return LocationRoleCreateAndAssignRead(role=role, location_role=location_role)


@router.put(
    "/{business_id}/locations/{location_id}/roles",
    response_model=list[LocationRoleRead],
)
async def replace_location_roles(
    business_id: UUID,
    location_id: UUID,
    payload: LocationRoleReplace,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        location_roles = await businesses.replace_location_roles(
            session,
            business_id,
            location_id,
            payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=location_id)
    await audit_service.append(
        session,
        event_name="location.roles.updated",
        target_type="location",
        target_id=location_id,
        business_id=business_id,
        location_id=location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "active_role_ids": [str(location_role.role_id) for location_role in location_roles],
            "active_role_count": len(location_roles),
        },
    )
    await session.commit()
    return location_roles
