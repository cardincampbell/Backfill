from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PlaceSuggestion(BaseModel):
    place_id: str
    provider: str
    label: str
    name: str
    resource_name: Optional[str] = None
    secondary_text: Optional[str] = None
    formatted_address: Optional[str] = None
    brand_name: Optional[str] = None
    location_label: Optional[str] = None
    primary_type: Optional[str] = None
    primary_type_display_name: Optional[str] = None
    business_status: Optional[str] = None
    national_phone_number: Optional[str] = None
    international_phone_number: Optional[str] = None
    website_uri: Optional[str] = None
    google_maps_uri: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    utc_offset_minutes: Optional[int] = None
    rating: Optional[float] = None
    user_rating_count: Optional[int] = None
    city: Optional[str] = None
    state_region: Optional[str] = None
    postal_code: Optional[str] = None
    country_code: Optional[str] = None
    neighborhood: Optional[str] = None
    sublocality: Optional[str] = None
    types: list[str] = Field(default_factory=list)
    address_components: list[dict[str, Any]] = Field(default_factory=list)
    regular_opening_hours: dict[str, Any] = Field(default_factory=dict)
    plus_code: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlaceAutocompleteResponse(BaseModel):
    query: str
    provider: str
    suggestions: list[PlaceSuggestion]


class PlaceDetailsResponse(BaseModel):
    provider: str
    place: Optional[PlaceSuggestion] = None
