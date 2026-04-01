from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from app_v2.api.deps import AuthDep, SessionDep
from app_v2.schemas.onboarding import (
    OnboardingProfileResponse,
    OnboardingProfileUpdate,
    OwnerWorkspaceBootstrapRequest,
    OwnerWorkspaceBootstrapResponse,
)
from app_v2.services import audit as audit_service
from app_v2.services import auth as auth_service
from app_v2.services import onboarding

router = APIRouter(prefix="/onboarding", tags=["v2-onboarding"])


@router.post("/profile", response_model=OnboardingProfileResponse)
async def complete_profile(
    payload: OnboardingProfileUpdate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    membership = auth_ctx.memberships[0] if auth_ctx.memberships else None
    try:
        user = await onboarding.complete_profile(
            session,
            auth_ctx.user,
            payload,
            business_id=membership.business_id if membership is not None else None,
            location_id=membership.location_id if membership is not None else None,
            actor_membership_id=membership.id if membership is not None else None,
            ip_address=audit_service.request_client_ip(request),
            user_agent=audit_service.request_user_agent(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return OnboardingProfileResponse(
        user=user,
        memberships=auth_ctx.memberships,
        onboarding_required=auth_service.onboarding_required_for_user(user),
    )


@router.post("/bootstrap-owner", response_model=OwnerWorkspaceBootstrapResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_owner_workspace(
    payload: OwnerWorkspaceBootstrapRequest,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    try:
        user, business, location, owner_membership = await onboarding.bootstrap_owner_workspace(
            session,
            auth_ctx,
            payload,
            ip_address=audit_service.request_client_ip(request),
            user_agent=audit_service.request_user_agent(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return OwnerWorkspaceBootstrapResponse(
        user=user,
        business=business,
        location=location,
        owner_membership=owner_membership,
        onboarding_required=auth_service.onboarding_required_for_user(user),
        created_at=datetime.now(timezone.utc),
    )
