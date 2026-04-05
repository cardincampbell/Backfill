from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from uuid import UUID

from app.api.deps import AuthDep, OptionalAuthDep, SessionDep
from app.config import settings
from app.schemas.auth import (
    AuthMeResponse,
    OTPChallengeRequest,
    OTPChallengeRequestResponse,
    OTPChallengeVerifyRequest,
    OTPChallengeVerifyResponse,
    SessionRead,
    SessionRevokeResponse,
)
from app.services import audit as audit_service
from app.services import auth, rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        domain=settings.session_cookie_domain,
        path="/",
    )


def _set_trusted_device_cookie(response: Response, trusted_device_id: str) -> None:
    response.set_cookie(
        settings.trusted_device_cookie_name,
        trusted_device_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        domain=settings.session_cookie_domain,
        path="/",
    )


@router.post("/challenges/request", response_model=OTPChallengeRequestResponse, status_code=status.HTTP_201_CREATED)
async def request_challenge(
    payload: OTPChallengeRequest,
    session: SessionDep,
    request: Request,
    response: Response,
    auth_ctx: OptionalAuthDep,
):
    try:
        result = await auth.request_otp_challenge(
            session,
            payload,
            ip_address=audit_service.request_client_ip(request),
            user_agent=audit_service.request_user_agent(request),
            auth_ctx=auth_ctx,
            trusted_device_id=request.cookies.get(settings.trusted_device_cookie_name),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except rate_limit.RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=exc.detail,
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    if result.token:
        _set_session_cookie(response, result.token)
    if result.trusted_device_id:
        _set_trusted_device_cookie(response, result.trusted_device_id)

    return OTPChallengeRequestResponse(
        challenge=result.challenge,
        session=result.session,
        token=result.token,
        onboarding_required=result.onboarding_required,
        otp_required=result.otp_required,
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
            trusted_device_id=request.cookies.get(settings.trusted_device_cookie_name),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except rate_limit.RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=exc.detail,
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    if result.token:
        _set_session_cookie(response, result.token)
    if result.trusted_device_id:
        _set_trusted_device_cookie(response, result.trusted_device_id)

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


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(session: SessionDep, auth_ctx: AuthDep):
    return await auth.list_active_sessions_for_user(
        session,
        user_id=auth_ctx.user.id,
    )


@router.delete("/sessions/{session_id}", response_model=SessionRevokeResponse)
async def revoke_session(
    session_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    membership = None
    if auth_ctx.memberships:
        membership = auth.membership_for_scope(auth_ctx, auth_ctx.memberships[0].business_id)
    try:
        await auth.revoke_user_session(
            session,
            session_id=session_id,
            user_id=auth_ctx.user.id,
            actor_user_id=auth_ctx.user.id,
            actor_membership_id=membership.id if membership is not None else None,
            ip_address=audit_service.request_client_ip(request),
            user_agent=audit_service.request_user_agent(request),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SessionRevokeResponse(revoked=True)


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
        settings.session_cookie_name,
        path="/",
        domain=settings.session_cookie_domain,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
