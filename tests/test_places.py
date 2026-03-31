from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.services import places as places_svc


class _FakeResponse:
    def __init__(self, url: str, payload: dict, status_code: int = 200):
        self._url = url
        self._payload = payload
        self.status_code = status_code
        self.text = "ok"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", self._url)
            response = httpx.Response(self.status_code, request=request, json=self._payload)
            raise httpx.HTTPStatusError("http error", request=request, response=response)


class _FakeAsyncClient:
    def __init__(self, responses, calls):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        self._calls.append((url, headers or {}, json or {}))
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_autocomplete_places_uses_text_search_for_address_queries(monkeypatch):
    monkeypatch.setattr(settings, "google_places_api_key", "test-google-key")
    monkeypatch.setattr(settings, "backfill_google_places_enabled", True)

    calls = []
    responses = [
        _FakeResponse(
            "https://places.googleapis.com/v1/places:autocomplete",
            {"suggestions": []},
        ),
        _FakeResponse(
            "https://places.googleapis.com/v1/places:searchText",
            {
                "places": [
                    {
                        "id": "addr-123",
                        "name": "places/addr-123",
                        "displayName": {"text": "225 Lincoln Blvd"},
                        "formattedAddress": "225 Lincoln Blvd, Venice, CA 90291, USA",
                        "location": {"latitude": 33.99, "longitude": -118.47},
                        "primaryType": "street_address",
                        "primaryTypeDisplayName": {"text": "Street Address"},
                        "addressComponents": [
                            {"longText": "Venice", "shortText": "Venice", "types": ["neighborhood"]},
                            {"longText": "Los Angeles", "shortText": "Los Angeles", "types": ["locality"]},
                            {"longText": "CA", "shortText": "CA", "types": ["administrative_area_level_1"]},
                        ],
                    }
                ]
            },
        ),
        _FakeResponse(
            "https://places.googleapis.com/v1/places:searchText",
            {
                "places": [
                    {
                        "id": "place-123",
                        "name": "places/place-123",
                        "displayName": {"text": "Whole Foods Market"},
                        "formattedAddress": "225 Lincoln Blvd, Venice, CA 90291, USA",
                        "location": {"latitude": 33.9902, "longitude": -118.4701},
                        "primaryType": "grocery_store",
                        "primaryTypeDisplayName": {"text": "Grocery Store"},
                        "addressComponents": [
                            {"longText": "Venice", "shortText": "Venice", "types": ["neighborhood"]},
                            {"longText": "Los Angeles", "shortText": "Los Angeles", "types": ["locality"]},
                            {"longText": "CA", "shortText": "CA", "types": ["administrative_area_level_1"]},
                        ],
                    }
                ]
            },
        ),
    ]
    monkeypatch.setattr(
        places_svc.httpx,
        "AsyncClient",
        lambda timeout=6.0: _FakeAsyncClient(responses, calls),
    )

    payload = await places_svc.autocomplete_places(
        "225 Lincoln Blvd",
        latitude=33.99,
        longitude=-118.47,
        radius_meters=50000,
    )

    assert payload["provider"] == "google"
    assert payload["suggestions"][0]["name"] == "Whole Foods Market"
    assert calls[0][0].endswith("places:autocomplete")
    assert calls[1][0].endswith("places:searchText")
    assert calls[1][2]["rankPreference"] == "DISTANCE"
    assert calls[1][2]["locationBias"]["circle"]["radius"] == 50000
    assert calls[2][2]["textQuery"] == "businesses near 225 Lincoln Blvd"
    assert calls[2][2]["locationBias"]["circle"]["radius"] == 1500.0


@pytest.mark.asyncio
async def test_autocomplete_places_prioritizes_local_text_search_results(monkeypatch):
    monkeypatch.setattr(settings, "google_places_api_key", "test-google-key")
    monkeypatch.setattr(settings, "backfill_google_places_enabled", True)

    calls = []
    responses = [
        _FakeResponse(
            "https://places.googleapis.com/v1/places:autocomplete",
            {
                "suggestions": [
                    {
                        "placePrediction": {
                            "place": "places/remote-1",
                            "placeId": "remote-1",
                            "text": {"text": "Whole Foods Market · Portland, OR, USA"},
                            "structuredFormat": {
                                "mainText": {"text": "Whole Foods Market"},
                                "secondaryText": {"text": "Portland, OR, USA"},
                            },
                        }
                    }
                ]
            },
        ),
        _FakeResponse(
            "https://places.googleapis.com/v1/places:searchText",
            {
                "places": [
                    {
                        "id": "local-1",
                        "name": "places/local-1",
                        "displayName": {"text": "Whole Foods Market"},
                        "formattedAddress": "777 The Alameda, San Jose, CA 95126, USA",
                        "location": {"latitude": 37.33, "longitude": -121.91},
                        "primaryType": "grocery_store",
                        "primaryTypeDisplayName": {"text": "Grocery Store"},
                        "addressComponents": [
                            {"longText": "San Jose", "shortText": "San Jose", "types": ["locality"]},
                            {"longText": "CA", "shortText": "CA", "types": ["administrative_area_level_1"]},
                        ],
                    }
                ]
            },
        ),
    ]
    monkeypatch.setattr(
        places_svc.httpx,
        "AsyncClient",
        lambda timeout=6.0: _FakeAsyncClient(responses, calls),
    )

    payload = await places_svc.autocomplete_places(
        "whole foods",
        latitude=37.33,
        longitude=-121.91,
        radius_meters=50000,
    )

    assert payload["provider"] == "google"
    assert [item["place_id"] for item in payload["suggestions"]] == ["local-1"]
    assert calls[1][2]["textQuery"] == "whole foods"
