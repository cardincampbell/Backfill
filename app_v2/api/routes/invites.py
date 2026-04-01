from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from uuid import UUID

from app_v2.api.deps import AuthDep, SessionDep
from app_v2.models.common import AuditActorType, InviteStatus, MembershipRole
from app_v2.models.identity import ManagerInvite
from app_v2.schemas.auth import OTPChallengeRequest
from app_v2.schemas.invites import (
    ManagerAccessEntry,
    ManagerAccessInviteCreate,
    ManagerAccessInviteResponse,
    ManagerAccessRevokeResponse,
    ManagerInviteChallengeRequest,
    ManagerInviteChallengeResponse,
    ManagerInvitePreviewResponse,
)
from app_v2.services import audit as audit_service
from app_v2.services import auth as auth_service, invites

router = APIRouter(tags=["v2-invites"])

ADMIN_ROLES = {MembershipRole.owner, MembershipRole.admin}


def _to_access_entry(entry: invites.ManagerAccessView) -> ManagerAccessEntry:
    return ManagerAccessEntry(
        id=entry.id,
        location_id=entry.location_id,
        entry_kind=entry.entry_kind,
        manager_name=entry.manager_name,
        manager_email=entry.manager_email,
        phone_e164=entry.phone_e164,
        role=entry.role,
        invite_status=entry.invite_status,
        accepted_at=entry.accepted_at,
        revoked_at=entry.revoked_at,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.get(
    "/businesses/{business_id}/locations/{location_id}/manager-access",
    response_model=list[ManagerAccessEntry],
)
async def list_location_manager_access(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=ADMIN_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        rows = await invites.list_location_manager_access(
            session,
            business_id=business_id,
            location_id=location_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [_to_access_entry(item) for item in rows]


@router.post(
    "/businesses/{business_id}/locations/{location_id}/manager-access",
    response_model=ManagerAccessInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_location_manager(
    business_id: UUID,
    location_id: UUID,
    payload: ManagerAccessInviteCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=ADMIN_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")

    actor_membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=location_id)
    inviter_name = auth_ctx.user.full_name or "A Backfill manager"
    try:
        invite, created, delivery_id = await invites.create_manager_invite(
            session,
            business_id=business_id,
            location_id=location_id,
            email=payload.email,
            manager_name=payload.manager_name,
            role=payload.role,
            invited_by_user_id=auth_ctx.user.id,
            inviter_name=inviter_name,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="manager_already_has_location_access",
        )

    await audit_service.append(
        session,
        event_name="manager_invite.created",
        target_type="manager_invite",
        target_id=invite.id,
        business_id=business_id,
        location_id=location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=actor_membership.id if actor_membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "recipient_email": invite.recipient_email,
            "role": invite.role.value,
            "created": created,
        },
    )
    await session.commit()
    return ManagerAccessInviteResponse(
        location_id=location_id,
        created=created,
        delivery_id=delivery_id,
        access=ManagerAccessEntry(
            id=invite.id,
            location_id=location_id,
            entry_kind="invite",
            manager_name=invites.invite_manager_name(invite),
            manager_email=invite.recipient_email,
            phone_e164=invite.recipient_phone_e164,
            role=invite.role.value,
            invite_status=invite.status.value,
            accepted_at=invite.accepted_at,
            revoked_at=None,
            created_at=invite.created_at,
            updated_at=invite.updated_at,
        ),
    )


@router.get("/manager-invites/{token}", response_model=ManagerInvitePreviewResponse)
async def get_manager_invite_preview(token: str, session: SessionDep):
    try:
        preview = await invites.get_invite_preview(session, raw_token=token)
        invites.assert_invite_is_usable(preview)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ManagerInvitePreviewResponse(
        invite_email=preview.invite.recipient_email,
        manager_name=preview.manager_name,
        business_id=preview.business.id,
        business_name=preview.business.brand_name or preview.business.legal_name,
        location_id=preview.location.id,
        location_name=preview.location.name,
        location_address=invites.location_address(preview.location),
        expires_at=preview.invite.expires_at,
        invite_status=preview.invite.status.value,
        invite_mode="existing_user" if preview.recipient_has_phone else "setup_new",
    )


@router.post(
    "/manager-invites/{token}/request-challenge",
    response_model=ManagerInviteChallengeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_manager_invite_challenge(
    token: str,
    payload: ManagerInviteChallengeRequest,
    session: SessionDep,
    request: Request,
):
    try:
        preview = await invites.get_invite_preview(session, raw_token=token)
        invites.assert_invite_is_usable(preview)
        challenge, user_exists = await auth_service.request_otp_challenge(
            session,
            OTPChallengeRequest(
                phone_e164=payload.phone_e164,
                purpose="invite_acceptance",
                locale=payload.locale,
                business_id=preview.business.id,
                location_id=preview.location.id,
                challenge_metadata={
                    **payload.challenge_metadata,
                    "invite_id": str(preview.invite.id),
                    "invite_email": preview.invite.recipient_email,
                    "manager_name": payload.manager_name or preview.manager_name,
                },
            ),
            ip_address=audit_service.request_client_ip(request),
            user_agent=audit_service.request_user_agent(request),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return ManagerInviteChallengeResponse(
        challenge=challenge,
        user_exists=user_exists,
        user_id=challenge.user_id,
        invite_mode="existing_user" if preview.recipient_has_phone else "setup_new",
    )


@router.delete(
    "/businesses/{business_id}/locations/{location_id}/manager-access/{membership_id}",
    response_model=ManagerAccessRevokeResponse,
)
async def revoke_location_manager_access(
    business_id: UUID,
    location_id: UUID,
    membership_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=ADMIN_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        membership = await invites.revoke_location_membership(
            session,
            business_id=business_id,
            location_id=location_id,
            membership_id=membership_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    actor_membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=location_id)
    await audit_service.append(
        session,
        event_name="membership.revoked",
        target_type="membership",
        target_id=membership.id,
        business_id=business_id,
        location_id=location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=actor_membership.id if actor_membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "role": membership.role.value,
            "status": membership.status.value,
            "revoked_user_id": str(membership.user_id),
        },
    )
    await session.commit()
    return ManagerAccessRevokeResponse(
        revoked=True,
        location_id=location_id,
        access_kind="membership",
        access_id=membership.id,
    )


@router.delete(
    "/businesses/{business_id}/locations/{location_id}/manager-invites/{invite_id}",
    response_model=ManagerAccessRevokeResponse,
)
async def revoke_manager_invite(
    business_id: UUID,
    location_id: UUID,
    invite_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=ADMIN_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    invite = await session.get(ManagerInvite, invite_id)
    if invite is None or invite.business_id != business_id or invite.location_id != location_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invite_not_found")
    invite.status = InviteStatus.revoked
    actor_membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=location_id)
    await audit_service.append(
        session,
        event_name="manager_invite.revoked",
        target_type="manager_invite",
        target_id=invite.id,
        business_id=business_id,
        location_id=location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=actor_membership.id if actor_membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={"recipient_email": invite.recipient_email},
    )
    await session.commit()
    return ManagerAccessRevokeResponse(
        revoked=True,
        location_id=location_id,
        access_kind="invite",
        access_id=invite.id,
    )
