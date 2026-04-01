from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.models.places import PlaceAutocompleteResponse, PlaceDetailsResponse
from app.services import places as places_service

places_router = APIRouter(prefix="/places", tags=["v2-places"])
legacy_places_router = APIRouter(prefix="/api/places", tags=["legacy-places"])


def _google_places_error_detail(exc: httpx.HTTPStatusError, operation: str) -> str:
    default = (
        f"{operation} failed. Verify GOOGLE_PLACES_API_KEY, billing, "
        "Places API (New) access, and key restrictions."
    )
    try:
        payload = exc.response.json()
    except Exception:
        payload = None

    error = payload.get("error") if isinstance(payload, dict) else None
    status = error.get("status") if isinstance(error, dict) else None
    message = error.get("message") if isinstance(error, dict) else None

    if status or message:
        parts = [f"{operation} failed"]
        if status:
            parts.append(str(status))
        if message:
            parts.append(str(message))
        parts.append(
            "Check GOOGLE_PLACES_API_KEY, billing, Places API (New), and key restrictions."
        )
        return ". ".join(parts)

    return default


async def _autocomplete_impl(
    *,
    q: str,
    session_token: Optional[str],
    latitude: Optional[float],
    longitude: Optional[float],
    radius_meters: Optional[float],
) -> dict[str, object]:
    try:
        payload = await places_service.autocomplete_places(
            q,
            session_token=session_token,
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=_google_places_error_detail(exc, "Places autocomplete"),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Places autocomplete unavailable") from exc
    return {
        "query": q.strip(),
        "provider": payload["provider"],
        "suggestions": payload["suggestions"],
    }


async def _details_impl(
    *,
    place_id: str,
    session_token: Optional[str],
) -> dict[str, object]:
    try:
        place = await places_service.get_place_details(place_id, session_token=session_token)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=_google_places_error_detail(exc, "Place lookup"),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Place lookup unavailable") from exc
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return {
        "provider": place["provider"],
        "place": place,
    }


@places_router.get("/autocomplete", response_model=PlaceAutocompleteResponse)
@legacy_places_router.get("/autocomplete", response_model=PlaceAutocompleteResponse)
async def get_places_autocomplete(
    q: str = Query(..., min_length=2, max_length=120),
    session_token: Optional[str] = Query(default=None, max_length=256),
    latitude: Optional[float] = Query(default=None, ge=-90, le=90),
    longitude: Optional[float] = Query(default=None, ge=-180, le=180),
    radius_meters: Optional[float] = Query(default=None, gt=0, le=50000),
):
    return await _autocomplete_impl(
        q=q,
        session_token=session_token,
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
    )


@places_router.get("/details", response_model=PlaceDetailsResponse)
@legacy_places_router.get("/details", response_model=PlaceDetailsResponse)
async def get_place_details(
    place_id: str = Query(..., min_length=2, max_length=256),
    session_token: Optional[str] = Query(default=None, max_length=256),
):
    return await _details_impl(place_id=place_id, session_token=session_token)
