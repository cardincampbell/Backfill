from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.api.deps import SessionDep
from app.services import calendar_feed as calendar_feed_service

router = APIRouter(prefix="/calendar-feeds", tags=["calendar-feeds"])


@router.get("/{feed_token}.ics", response_class=PlainTextResponse)
async def get_calendar_feed_ics(
    feed_token: str,
    session: SessionDep,
) -> PlainTextResponse:
    """Anonymous ICS endpoint. No auth required — the feed token acts as a bearer."""
    location = await calendar_feed_service.get_location_by_feed_token(session, feed_token)
    if location is None:
        raise HTTPException(status_code=404, detail="feed_not_found")
    ics_text = await calendar_feed_service.build_location_ics(session, location)
    return PlainTextResponse(
        content=ics_text,
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )
