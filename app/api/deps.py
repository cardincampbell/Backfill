from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db_session
from app.services import auth as auth_service

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_auth_context(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    session_cookie: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
):
    token = session_cookie
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication_required")

    auth = await auth_service.resolve_auth_context(session, token)
    if auth is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_or_expired_session")
    return auth


AuthDep = Annotated[auth_service.AuthContext, Depends(get_auth_context)]


async def get_optional_auth_context(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    session_cookie: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
):
    token = session_cookie
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    return await auth_service.resolve_auth_context(session, token)


OptionalAuthDep = Annotated[Optional[auth_service.AuthContext], Depends(get_optional_auth_context)]
