from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.api.deps import AuthDep, SessionDep
from app.config import settings
from app.db.session import get_async_sessionmaker
from app.domain.copilot import runtime as copilot_runtime
from app.models.common import MembershipRole
from app.schemas.copilot import (
    CopilotMessageCreate,
    CopilotSessionEventRead,
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


def _websocket_request_context(websocket: WebSocket) -> copilot_runtime.CopilotRequestContext:
    return copilot_runtime.CopilotRequestContext(
        ip_address=websocket.client.host if websocket.client else None,
        user_agent=websocket.headers.get("user-agent"),
    )


def _websocket_token(websocket: WebSocket) -> str | None:
    token = websocket.cookies.get(settings.session_cookie_name)
    authorization = websocket.headers.get("authorization")
    if token:
        return token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


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
    if payload.location_id is not None and not auth_service.has_location_access(
        auth_ctx,
        business_id,
        payload.location_id,
        allowed_roles=READ_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_access_denied")
    try:
        detail = await copilot_runtime.create_or_reuse_session(
            session,
            auth_ctx=auth_ctx,
            business_id=business_id,
            payload=payload,
            request_context=_request_context(request),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
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


@router.websocket("/sessions/{copilot_session_id}/live")
async def copilot_session_live(
    websocket: WebSocket,
    business_id: UUID,
    copilot_session_id: UUID,
):
    token = _websocket_token(websocket)
    if not token:
        await websocket.close(code=4401, reason="authentication_required")
        return

    sessionmaker = get_async_sessionmaker()
    async with sessionmaker() as auth_session:
        auth_ctx = await auth_service.resolve_auth_context(auth_session, token)
        if auth_ctx is None:
            await websocket.close(code=4401, reason="invalid_or_expired_session")
            return
        try:
            detail = await copilot_runtime.get_session_detail(
                auth_session,
                auth_ctx=auth_ctx,
                business_id=business_id,
                session_id=copilot_session_id,
            )
        except PermissionError as exc:
            detail_code = str(exc)
            close_code = 4403 if detail_code != "copilot_session_not_found" else 4404
            await websocket.close(code=close_code, reason=detail_code)
            return
        except LookupError as exc:
            await websocket.close(code=4404, reason=str(exc))
            return

    await websocket.accept()
    send_lock = asyncio.Lock()
    active_turn_task: asyncio.Task[None] | None = None
    active_trace_id: str | None = None

    async def send_event(event: CopilotSessionEventRead) -> None:
        async with send_lock:
            try:
                await websocket.send_json(event.model_dump(mode="json"))
            except (RuntimeError, WebSocketDisconnect):
                return

    async def send_session_error(code: str, message: str) -> None:
        await send_event(
            CopilotSessionEventRead(
                event_id=uuid4(),
                event_type="session.error",
                trace_id=active_trace_id or str(copilot_session_id),
                session_id=copilot_session_id,
                occurred_at=datetime.now(timezone.utc),
                payload={"code": code, "message": message},
            )
        )

    await send_event(
        CopilotSessionEventRead(
            event_id=uuid4(),
            event_type="session.ready",
            trace_id=str(copilot_session_id),
            session_id=copilot_session_id,
            occurred_at=datetime.now(timezone.utc),
            payload={"detail": detail.model_dump(mode="json")},
        )
    )

    async def run_turn(message_payload: CopilotMessageCreate, trace_id: str) -> None:
        nonlocal active_turn_task, active_trace_id
        async with sessionmaker() as turn_session:
            try:
                await copilot_runtime.create_turn(
                    turn_session,
                    auth_ctx=auth_ctx,
                    business_id=business_id,
                    session_id=copilot_session_id,
                    payload=message_payload,
                    request_context=_websocket_request_context(websocket),
                    live_event_publisher=send_event,
                    live_trace_id=trace_id,
                )
                await turn_session.commit()
            except asyncio.CancelledError:
                await turn_session.rollback()
                await send_event(
                    CopilotSessionEventRead(
                        event_id=uuid4(),
                        event_type="assistant.turn.failed",
                        trace_id=trace_id,
                        session_id=copilot_session_id,
                        occurred_at=datetime.now(timezone.utc),
                        payload={"error": {"code": "cancelled", "message": "Copilot request cancelled."}},
                    )
                )
                raise
            except PermissionError as exc:
                await turn_session.rollback()
                await send_event(
                    CopilotSessionEventRead(
                        event_id=uuid4(),
                        event_type="assistant.turn.failed",
                        trace_id=trace_id,
                        session_id=copilot_session_id,
                        occurred_at=datetime.now(timezone.utc),
                        payload={"error": {"code": str(exc), "message": str(exc)}},
                    )
                )
            except LookupError as exc:
                await turn_session.rollback()
                await send_event(
                    CopilotSessionEventRead(
                        event_id=uuid4(),
                        event_type="assistant.turn.failed",
                        trace_id=trace_id,
                        session_id=copilot_session_id,
                        occurred_at=datetime.now(timezone.utc),
                        payload={"error": {"code": str(exc), "message": str(exc)}},
                    )
                )
            except Exception:
                await turn_session.rollback()
                await send_event(
                    CopilotSessionEventRead(
                        event_id=uuid4(),
                        event_type="assistant.turn.failed",
                        trace_id=trace_id,
                        session_id=copilot_session_id,
                        occurred_at=datetime.now(timezone.utc),
                        payload={"error": {"code": "internal_error", "message": "Internal server error"}},
                    )
                )
            finally:
                active_turn_task = None
                active_trace_id = None

    try:
        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("type") if isinstance(payload, dict) else None
            if event_type == "user.message":
                if active_turn_task is not None and not active_turn_task.done():
                    await send_session_error("turn_in_progress", "Copilot is already working on a request.")
                    continue
                try:
                    message_payload = CopilotMessageCreate.model_validate(
                        {
                            "text": payload.get("text"),
                            "location_id": payload.get("location_id"),
                            "normalized_channel": payload.get("normalized_channel") or "dashboard",
                        }
                    )
                except ValidationError:
                    await send_session_error("invalid_message", "Copilot messages need text before they can be sent.")
                    continue
                active_trace_id = str(payload.get("trace_id") or uuid4())
                active_turn_task = asyncio.create_task(run_turn(message_payload, active_trace_id))
                continue

            if event_type == "assistant.cancel":
                if active_turn_task is None or active_turn_task.done():
                    await send_session_error("no_active_turn", "There is no Copilot turn to cancel.")
                    continue
                requested_trace_id = payload.get("trace_id")
                if requested_trace_id and active_trace_id and requested_trace_id != active_trace_id:
                    await send_session_error("trace_id_mismatch", "The requested Copilot turn is no longer active.")
                    continue
                active_turn_task.cancel()
                continue

            await send_session_error("unknown_event_type", "Unsupported Copilot socket message type.")
    except WebSocketDisconnect:
        if active_turn_task is not None and not active_turn_task.done():
            active_turn_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await active_turn_task


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
