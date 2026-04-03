from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main as main_module
from app.api.routes import places as places_routes


def test_places_routes_support_v2_path(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            run_migrations_on_startup=False,
            backfill_allowed_origins=[],
            environment="test",
            api_prefix="/api",
            expose_internal_errors=True,
        ),
    )

    async def fake_autocomplete_places(
        query: str,
        *,
        session_token: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_meters: float | None = None,
    ) -> dict[str, object]:
        assert query == "starbucks"
        assert session_token == "sess_123"
        assert latitude is None
        assert longitude is None
        assert radius_meters is None
        return {
            "provider": "google",
            "suggestions": [
                {
                    "place_id": "abc123",
                    "provider": "google",
                    "label": "Starbucks · San Francisco, CA, USA",
                    "name": "Starbucks",
                    "formatted_address": "San Francisco, CA, USA",
                    "secondary_text": "San Francisco, CA, USA",
                    "types": [],
                    "address_components": [],
                    "regular_opening_hours": {},
                    "plus_code": {},
                    "metadata": {},
                }
            ],
        }

    monkeypatch.setattr(places_routes.places_service, "autocomplete_places", fake_autocomplete_places)

    app = main_module.create_app()
    client = TestClient(app)

    response = client.get("/api/places/autocomplete?q=starbucks&session_token=sess_123")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "google"
    assert payload["suggestions"][0]["place_id"] == "abc123"
