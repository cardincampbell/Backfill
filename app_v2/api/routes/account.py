from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app_v2.api.deps import AuthDep, SessionDep
from app_v2.schemas.account import AccountProfileResponse, AccountProfileUpdate
from app_v2.services import account as account_service
from app_v2.services import audit as audit_service
from app_v2.services import auth as auth_service

router = APIRouter(prefix="/account", tags=["v2-account"])


@router.patch("/profile", response_model=AccountProfileResponse)
async def update_profile(
    payload: AccountProfileUpdate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    membership = auth_ctx.memberships[0] if auth_ctx.memberships else None
    try:
        user = await account_service.update_profile(
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

    return AccountProfileResponse(
        user=user,
        onboarding_required=auth_service.onboarding_required_for_user(user),
    )
