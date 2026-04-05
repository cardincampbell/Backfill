from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AuthDep, SessionDep
from app.models.common import AuditActorType, MembershipRole
from app.schemas.scheduling import ShiftCreate, ShiftDeleteResponse, ShiftRead, ShiftUpdate
from app.services import audit as audit_service
from app.services import auth as auth_service, scheduling

router = APIRouter(prefix="/businesses/{business_id}/shifts", tags=["scheduling"])
MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}


@router.get("", response_model=list[ShiftRead])
async def list_shifts(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    location_id: UUID | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    return await scheduling.list_shifts(
        session,
        business_id,
        location_id=location_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )


@router.post("", response_model=ShiftRead, status_code=status.HTTP_201_CREATED)
async def create_shift(
    business_id: UUID,
    payload: ShiftCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        shift = await scheduling.create_shift(session, business_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=shift.location_id)
    await audit_service.append(
        session,
        event_name="shift.created",
        target_type="shift",
        target_id=shift.id,
        business_id=business_id,
        location_id=shift.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "role_id": str(shift.role_id),
            "starts_at": shift.starts_at.isoformat(),
            "ends_at": shift.ends_at.isoformat(),
        },
    )
    await session.commit()
    return shift


@router.patch("/{shift_id}", response_model=ShiftRead)
async def update_shift(
    business_id: UUID,
    shift_id: UUID,
    payload: ShiftUpdate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        shift = await scheduling.update_shift(session, business_id, shift_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=shift.location_id)
    await audit_service.append(
        session,
        event_name="shift.updated",
        target_type="shift",
        target_id=shift.id,
        business_id=business_id,
        location_id=shift.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload=payload.model_dump(exclude_none=True, mode="json"),
    )
    await session.commit()
    return shift


@router.delete("/{shift_id}", response_model=ShiftDeleteResponse)
async def delete_shift(
    business_id: UUID,
    shift_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        shift = await scheduling.delete_shift(session, business_id, shift_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=shift.location_id)
    await audit_service.append(
        session,
        event_name="shift.deleted",
        target_type="shift",
        target_id=shift.id,
        business_id=business_id,
        location_id=shift.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={"role_id": str(shift.role_id)},
    )
    await session.commit()
    return ShiftDeleteResponse(deleted=True, shift_id=shift.id)
