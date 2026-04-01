from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app_v2.api.deps import AuthDep, OptionalAuthDep, SessionDep
from app_v2.config import v2_settings
from app_v2.schemas.auth import (
    AuthMeResponse,
    OTPChallengeRequest,
    OTPChallengeRequestResponse,
    OTPChallengeVerifyRequest,
    OTPChallengeVerifyResponse,
    SessionCreateRequest,
    SessionCreateResponse,
)
from app_v2.services import audit as audit_service
from app_v2.services import auth

router = APIRouter(prefix="/auth", tags=["v2-auth"])


@router.post("/sessions", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreateRequest, session: SessionDep, response: Response):
    try:
        raw_token, record = await auth.create_session(session, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    response.set_cookie(
        v2_settings.session_cookie_name,
        raw_token,
        httponly=True,
        secure=v2_settings.session_cookie_secure,
        samesite="lax",
        max_age=payload.ttl_hours * 3600,
        domain=v2_settings.session_cookie_domain,
        path="/",
    )
    return SessionCreateResponse(token=raw_token, session=record)


@router.post("/challenges/request", response_model=OTPChallengeRequestResponse, status_code=status.HTTP_201_CREATED)
async def request_challenge(
    payload: OTPChallengeRequest,
    session: SessionDep,
    request: Request,
    auth_ctx: OptionalAuthDep,
):
    try:
        challenge, user_exists = await auth.request_otp_challenge(
            session,
            payload,
            ip_address=audit_service.request_client_ip(request),
            user_agent=audit_service.request_user_agent(request),
            auth_ctx=auth_ctx,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return OTPChallengeRequestResponse(
        challenge=challenge,
        user_exists=user_exists,
        user_id=challenge.user_id,
    )


@router.post("/challenges/verify", response_model=OTPChallengeVerifyResponse)
async def verify_challenge(
    payload: OTPChallengeVerifyRequest,
    session: SessionDep,
    request: Request,
    response: Response,
    auth_ctx: OptionalAuthDep,
):
    try:
        result = await auth.verify_otp_challenge(
            session,
            payload,
            ip_address=audit_service.request_client_ip(request),
            user_agent=audit_service.request_user_agent(request),
            auth_ctx=auth_ctx,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if result.token:
        response.set_cookie(
            v2_settings.session_cookie_name,
            result.token,
            httponly=True,
            secure=v2_settings.session_cookie_secure,
            samesite="lax",
            max_age=payload.ttl_hours * 3600,
            domain=v2_settings.session_cookie_domain,
            path="/",
        )

    return OTPChallengeVerifyResponse(
        challenge=result.challenge,
        user=result.user,
        session=result.session,
        token=result.token,
        onboarding_required=result.onboarding_required,
        step_up_granted=result.step_up_granted,
    )


@router.get("/me", response_model=AuthMeResponse)
async def me(auth_ctx: AuthDep):
    return AuthMeResponse(
        user=auth_ctx.user,
        session=auth_ctx.session,
        memberships=auth_ctx.memberships,
        onboarding_required=auth.onboarding_required_for_user(auth_ctx.user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(session: SessionDep, auth_ctx: AuthDep, request: Request, response: Response):
    membership = None
    if auth_ctx.memberships:
        membership = auth.membership_for_scope(auth_ctx, auth_ctx.memberships[0].business_id)
    await auth.revoke_session_by_id(
        session,
        auth_ctx.session.id,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
    )
    response.delete_cookie(
        v2_settings.session_cookie_name,
        path="/",
        domain=v2_settings.session_cookie_domain,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
