from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response

from app.api.deps import SessionDep
from app.schemas.employee_schedule import PublicEmployeeScheduleRead
from app.services import employee_schedule_links as employee_schedule_link_service

router = APIRouter(prefix="/employee-schedules", tags=["employee-schedules"])


@router.get("/{token}", response_model=PublicEmployeeScheduleRead)
async def get_employee_schedule(
    token: str,
    session: SessionDep,
    response: Response,
    week_start: date | None = None,
    location_id: UUID | None = None,
):
    try:
        schedule_read, touched = await employee_schedule_link_service.get_employee_schedule_read(
            session,
            raw_token=token,
            week_start=week_start,
            location_id=location_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if schedule_read is None:
        raise HTTPException(status_code=404, detail="schedule_link_not_found")
    if touched:
        await session.commit()
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return schedule_read
