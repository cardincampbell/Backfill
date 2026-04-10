from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AuthDep, SessionDep
from app.domain.copilot import runtime as copilot_runtime
from app.models.common import MembershipRole
from app.schemas.copilot import (
    CopilotMessageCreate,
    CopilotSessionCreate,
    CopilotSessionDetailRead,
    CopilotToolRead,
    CopilotTurnRead,
)
from app.services import audit as audit_service
from app.services import auth as auth_service

router = APIRouter(prefix="/businesses/{business_id}/copilot", tags=["copilot"])
READ_ROLES = {
    MembershipRole.owner,
    MembershipRole.admin,
    MembershipRole.manager,
    MembershipRole.viewer,
}


def _request_context(request: Request) -> copilot_runtime.CopilotRequestContext:
    return copilot_runtime.CopilotRequestContext(
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
    )


@router.get("/tools", response_model=list[CopilotToolRead])
async def list_tools(
    business_id: UUID,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=READ_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    return await copilot_runtime.list_copilot_tools()


@router.post("/sessions", response_model=CopilotSessionDetailRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    business_id: UUID,
    payload: CopilotSessionCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=READ_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        detail = await copilot_runtime.create_or_reuse_session(
            session,
            auth_ctx=auth_ctx,
            business_id=business_id,
            payload=payload,
            request_context=_request_context(request),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return detail


@router.get("/sessions/{copilot_session_id}", response_model=CopilotSessionDetailRead)
async def get_session(
    business_id: UUID,
    copilot_session_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    try:
        return await copilot_runtime.get_session_detail(
            session,
            auth_ctx=auth_ctx,
            business_id=business_id,
            session_id=copilot_session_id,
        )
    except PermissionError as exc:
        detail = str(exc)
        status_code = status.HTTP_403_FORBIDDEN if detail != "copilot_session_not_found" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/sessions/{copilot_session_id}/messages", response_model=CopilotTurnRead)
async def create_message(
    business_id: UUID,
    copilot_session_id: UUID,
    payload: CopilotMessageCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    try:
        turn = await copilot_runtime.create_turn(
            session,
            auth_ctx=auth_ctx,
            business_id=business_id,
            session_id=copilot_session_id,
            payload=payload,
            request_context=_request_context(request),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return turn
