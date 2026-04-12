from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import AuthDep, SessionDep
from app.config import settings
from app.models.common import MembershipRole
from app.schemas.weather import LocationWeatherForecastRead
from app.services import auth as auth_service
from app.services import weather as weather_service

router = APIRouter(
    prefix="/businesses/{business_id}/locations/{location_id}/weather",
    tags=["weather"],
)

READ_ROLES = {
    MembershipRole.owner,
    MembershipRole.admin,
    MembershipRole.manager,
    MembershipRole.viewer,
}


@router.get("/forecast", response_model=LocationWeatherForecastRead)
async def get_location_weather_forecast(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    response: Response,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    hours: int = Query(default=72, ge=1, le=settings.weather_forecast_max_hours),
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=READ_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_access_denied")

    try:
        forecast = await weather_service.get_location_forecast(
            session,
            business_id=business_id,
            location_id=location_id,
            starts_at=starts_at,
            ends_at=ends_at,
            hours=hours,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=300"
    return forecast
