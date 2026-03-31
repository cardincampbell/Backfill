from __future__ import annotations

from typing import Any

import httpx

from app.config import settings

_AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
_PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

_FALLBACK_SUGGESTIONS = [
    {"name": "Mission District", "formatted_address": "San Francisco, CA, USA"},
    {"name": "SoMa", "formatted_address": "San Francisco, CA, USA"},
    {"name": "Downtown", "formatted_address": "San Francisco, CA, USA"},
    {"name": "Financial District", "formatted_address": "San Francisco, CA, USA"},
    {"name": "Capitol Hill", "formatted_address": "Seattle, WA, USA"},
    {"name": "Ballard", "formatted_address": "Seattle, WA, USA"},
    {"name": "Downtown", "formatted_address": "Seattle, WA, USA"},
    {"name": "Downtown", "formatted_address": "Austin, TX, USA"},
    {"name": "South Congress", "formatted_address": "Austin, TX, USA"},
    {"name": "East Austin", "formatted_address": "Austin, TX, USA"},
    {"name": "The Domain", "formatted_address": "Austin, TX, USA"},
    {"name": "Downtown", "formatted_address": "Dallas, TX, USA"},
    {"name": "Deep Ellum", "formatted_address": "Dallas, TX, USA"},
    {"name": "Downtown", "formatted_address": "Houston, TX, USA"},
    {"name": "Montrose", "formatted_address": "Houston, TX, USA"},
    {"name": "The Heights", "formatted_address": "Houston, TX, USA"},
    {"name": "Downtown", "formatted_address": "Chicago, IL, USA"},
    {"name": "West Loop", "formatted_address": "Chicago, IL, USA"},
    {"name": "Wicker Park", "formatted_address": "Chicago, IL, USA"},
    {"name": "Lincoln Park", "formatted_address": "Chicago, IL, USA"},
    {"name": "Downtown", "formatted_address": "New York, NY, USA"},
    {"name": "Chelsea", "formatted_address": "New York, NY, USA"},
    {"name": "Tribeca", "formatted_address": "New York, NY, USA"},
    {"name": "Williamsburg", "formatted_address": "Brooklyn, NY, USA"},
    {"name": "Downtown", "formatted_address": "Los Angeles, CA, USA"},
    {"name": "Santa Monica", "formatted_address": "Los Angeles, CA, USA"},
    {"name": "Venice", "formatted_address": "Los Angeles, CA, USA"},
    {"name": "Beverly Hills", "formatted_address": "Los Angeles, CA, USA"},
    {"name": "Downtown", "formatted_address": "Miami, FL, USA"},
    {"name": "Brickell", "formatted_address": "Miami, FL, USA"},
    {"name": "Wynwood", "formatted_address": "Miami, FL, USA"},
    {"name": "South Beach", "formatted_address": "Miami Beach, FL, USA"},
    {"name": "Downtown", "formatted_address": "Nashville, TN, USA"},
    {"name": "12 South", "formatted_address": "Nashville, TN, USA"},
    {"name": "The Gulch", "formatted_address": "Nashville, TN, USA"},
]


def _infer_brand_name(name: str | None) -> str | None:
    text = (name or "").strip()
    if not text:
        return None
    for separator in (" — ", " – ", " - ", " | ", " · ", " @ "):
        if separator in text:
            head = text.split(separator, 1)[0].strip()
            if head:
                return head
    return text


def _address_component_text(
    components: list[dict[str, Any]],
    *wanted_types: str,
    short: bool = False,
) -> str | None:
    wanted = set(wanted_types)
    for component in components:
        component_types = set(component.get("types") or [])
        if not wanted.intersection(component_types):
            continue
        value = component.get("shortText" if short else "longText")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _location_label(
    *,
    neighborhood: str | None,
    sublocality: str | None,
    city: str | None,
    state_region: str | None,
) -> str | None:
    for candidate in (neighborhood, sublocality, city):
        if candidate:
            return candidate
    if state_region:
        return state_region
    return None


def _fallback_place_id(name: str, formatted_address: str) -> str:
    raw = f"{name}-{formatted_address}".lower()
    return "fallback:" + "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-")


def _manual_place_id(query: str) -> str:
    raw = query.strip().lower()
    return "manual:" + "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-")


def _build_fallback_suggestion(item: dict[str, str]) -> dict[str, str]:
    name = item["name"]
    formatted_address = item["formatted_address"]
    city = formatted_address.split(",")[0].strip() if "," in formatted_address else None
    return {
        "place_id": _fallback_place_id(name, formatted_address),
        "provider": "fallback",
        "label": f"{name} · {formatted_address}",
        "name": name,
        "brand_name": _infer_brand_name(name),
        "location_label": city,
        "formatted_address": formatted_address,
        "secondary_text": formatted_address,
        "resource_name": None,
        "city": city,
        "metadata": {"formatted_address": formatted_address},
    }


def _build_manual_suggestion(query: str) -> dict[str, str | None]:
    normalized = query.strip()
    return {
        "place_id": _manual_place_id(normalized),
        "provider": "fallback",
        "label": normalized,
        "name": normalized,
        "brand_name": _infer_brand_name(normalized),
        "location_label": None,
        "formatted_address": None,
        "secondary_text": "Use typed location",
        "resource_name": None,
        "metadata": {"typed_query": normalized},
    }


def _fallback_autocomplete(query: str) -> dict[str, Any]:
    normalized = query.strip().lower()
    if len(normalized) < 2:
        return {"provider": "fallback", "suggestions": []}
    suggestions = [_build_manual_suggestion(query)]
    for item in _FALLBACK_SUGGESTIONS:
        haystack = f"{item['name']} {item['formatted_address']}".lower()
        if normalized in haystack:
            suggestion = _build_fallback_suggestion(item)
            if suggestion["label"].lower() != query.strip().lower():
                suggestions.append(suggestion)
        if len(suggestions) >= 8:
            break
    return {"provider": "fallback", "suggestions": suggestions}


def _fallback_details(place_id: str) -> dict[str, Any] | None:
    if place_id.startswith("manual:"):
        raw = place_id[len("manual:"):].replace("-", " ").strip()
        name = " ".join(part.capitalize() for part in raw.split()) or "Custom location"
        return {
            "place_id": place_id,
            "provider": "fallback",
            "label": name,
            "name": name,
            "brand_name": _infer_brand_name(name),
            "location_label": None,
            "formatted_address": None,
            "secondary_text": "Use typed location",
            "resource_name": None,
            "metadata": {"typed_query": name},
        }
    for item in _FALLBACK_SUGGESTIONS:
        suggestion = _build_fallback_suggestion(item)
        if suggestion["place_id"] == place_id:
            return suggestion
    return None


def _google_headers(field_mask: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": field_mask,
    }


def _parse_autocomplete_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for entry in payload.get("suggestions") or []:
        prediction = entry.get("placePrediction") or {}
        place_id = prediction.get("placeId")
        if not place_id:
            continue
        text = ((prediction.get("text") or {}).get("text") or "").strip()
        structured = prediction.get("structuredFormat") or {}
        main_text = ((structured.get("mainText") or {}).get("text") or "").strip()
        secondary_text = ((structured.get("secondaryText") or {}).get("text") or "").strip()
        name = main_text or text or place_id
        label = text or " · ".join(part for part in (main_text, secondary_text) if part)
        brand_name = _infer_brand_name(name)
        suggestions.append(
            {
                "place_id": place_id,
                "provider": "google",
                "label": label or name,
                "name": name,
                "brand_name": brand_name,
                "location_label": secondary_text or None,
                "secondary_text": secondary_text or None,
                "formatted_address": secondary_text or None,
                "resource_name": prediction.get("place"),
                "metadata": {"autocomplete_prediction": prediction},
            }
        )
    return suggestions


def _build_google_place_response(payload: dict[str, Any]) -> dict[str, Any]:
    display_name = ((payload.get("displayName") or {}).get("text") or "").strip()
    formatted_address = (payload.get("formattedAddress") or "").strip()
    location = payload.get("location") or {}
    address_components = payload.get("addressComponents") or []
    brand_name = _infer_brand_name(display_name or payload.get("id"))
    neighborhood = _address_component_text(address_components, "neighborhood")
    sublocality = _address_component_text(
        address_components,
        "sublocality",
        "sublocality_level_1",
        "sublocality_level_2",
    )
    city = _address_component_text(
        address_components,
        "locality",
        "postal_town",
        "administrative_area_level_3",
    )
    state_region = _address_component_text(
        address_components,
        "administrative_area_level_1",
        short=True,
    )
    postal_code = _address_component_text(address_components, "postal_code")
    country_code = _address_component_text(address_components, "country", short=True)
    location_label = _location_label(
        neighborhood=neighborhood,
        sublocality=sublocality,
        city=city,
        state_region=state_region,
    )
    primary_type_display = (
        ((payload.get("primaryTypeDisplayName") or {}).get("text") or "").strip() or None
    )
    return {
        "place_id": payload.get("id") or "",
        "provider": "google",
        "label": " · ".join(part for part in (display_name, formatted_address) if part)
        or display_name
        or payload.get("id")
        or "",
        "name": display_name or payload.get("id") or "",
        "resource_name": payload.get("name"),
        "secondary_text": formatted_address or None,
        "formatted_address": formatted_address or None,
        "brand_name": brand_name,
        "location_label": location_label,
        "primary_type": payload.get("primaryType"),
        "primary_type_display_name": primary_type_display,
        "business_status": payload.get("businessStatus"),
        "national_phone_number": payload.get("nationalPhoneNumber"),
        "international_phone_number": payload.get("internationalPhoneNumber"),
        "website_uri": payload.get("websiteUri"),
        "google_maps_uri": payload.get("googleMapsUri"),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "utc_offset_minutes": payload.get("utcOffsetMinutes"),
        "rating": payload.get("rating"),
        "user_rating_count": payload.get("userRatingCount"),
        "city": city,
        "state_region": state_region,
        "postal_code": postal_code,
        "country_code": country_code,
        "neighborhood": neighborhood,
        "sublocality": sublocality,
        "types": payload.get("types") or [],
        "address_components": address_components,
        "regular_opening_hours": payload.get("regularOpeningHours") or {},
        "plus_code": payload.get("plusCode") or {},
        "metadata": payload,
    }


async def autocomplete_places(
    query: str,
    *,
    session_token: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_meters: float | None = None,
) -> dict[str, Any]:
    normalized = query.strip()
    if len(normalized) < 2:
        return {"provider": "fallback", "suggestions": []}

    if not settings.backfill_google_places_enabled or not settings.google_places_api_key:
        return _fallback_autocomplete(normalized)

    body: dict[str, Any] = {
        "input": normalized,
        "languageCode": "en",
        "regionCode": settings.google_places_region_code,
    }
    if latitude is not None and longitude is not None:
        body["locationBias"] = {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": radius_meters or 50000.0,
            }
        }
    if session_token:
        body["sessionToken"] = session_token
    if settings.google_places_country_codes:
        body["includedRegionCodes"] = settings.google_places_country_codes

    async with httpx.AsyncClient(timeout=6.0) as client:
        response = await client.post(
            _AUTOCOMPLETE_URL,
            headers=_google_headers(
                "suggestions.placePrediction.place,"
                "suggestions.placePrediction.placeId,"
                "suggestions.placePrediction.text,"
                "suggestions.placePrediction.structuredFormat"
            ),
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    return {"provider": "google", "suggestions": _parse_autocomplete_response(payload)}


async def get_place_details(place_id: str, *, session_token: str | None = None) -> dict[str, Any] | None:
    normalized = place_id.strip()
    if not normalized:
        return None

    if not settings.backfill_google_places_enabled or not settings.google_places_api_key:
        return _fallback_details(normalized)

    params: dict[str, str] = {}
    if session_token:
        params["sessionToken"] = session_token

    async with httpx.AsyncClient(timeout=6.0) as client:
        response = await client.get(
            _PLACE_DETAILS_URL.format(place_id=normalized),
            headers=_google_headers(
                "id,"
                "name,"
                "displayName,"
                "formattedAddress,"
                "location,"
                "googleMapsUri,"
                "websiteUri,"
                "nationalPhoneNumber,"
                "internationalPhoneNumber,"
                "regularOpeningHours,"
                "utcOffsetMinutes,"
                "businessStatus,"
                "types,"
                "primaryType,"
                "primaryTypeDisplayName,"
                "addressComponents,"
                "rating,"
                "userRatingCount,"
                "plusCode"
            ),
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
    return _build_google_place_response(payload)
