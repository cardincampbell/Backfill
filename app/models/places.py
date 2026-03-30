from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PlaceSuggestion(BaseModel):
    place_id: str
    provider: str
    label: str
    name: str
    resource_name: Optional[str] = None
    secondary_text: Optional[str] = None
    formatted_address: Optional[str] = None


class PlaceAutocompleteResponse(BaseModel):
    query: str
    provider: str
    suggestions: list[PlaceSuggestion]


class PlaceDetailsResponse(BaseModel):
    provider: str
    place: Optional[PlaceSuggestion] = None
