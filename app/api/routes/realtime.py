from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from app.api.deps import AuthDep
from app.models.common import MembershipRole
from app.services import auth as auth_service
from app.services.realtime_events import get_realtime_event_broker

router = APIRouter(prefix="/businesses/{business_id}/realtime", tags=["realtime"])

READ_ROLES = {
    MembershipRole.owner,
    MembershipRole.admin,
    MembershipRole.manager,
    MembershipRole.viewer,
}


def _sse_frame(*, event: str | None = None, data: dict | None = None) -> str:
    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")
    if data is not None:
        payload = json.dumps(data, separators=(",", ":"))
        for chunk in payload.splitlines() or [""]:
            lines.append(f"data: {chunk}")
    return "\n".join(lines) + "\n\n"


@router.get("/events")
async def stream_realtime_events(
    business_id: UUID,
    request: Request,
    auth_ctx: AuthDep,
    location_id: UUID | None = None,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=READ_ROLES):
        raise HTTPException(status_code=403, detail="business_access_denied")
    if location_id is not None and not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=READ_ROLES,
    ):
        raise HTTPException(status_code=403, detail="location_access_denied")

    broker = get_realtime_event_broker()
    await broker.ensure_started()

    async def event_stream():
        yield "retry: 3000\n\n"
        async with broker.subscribe(
            business_id=str(business_id),
            location_id=str(location_id) if location_id is not None else None,
        ) as queue:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield _sse_frame(event="platform_event", data=event.model_dump())

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
