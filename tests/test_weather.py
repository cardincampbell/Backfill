from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Location
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.identity import Membership, Session, User
from app.services.auth import AuthContext
from app.services import weather as weather_service


class FakeWeatherSession:
    pass


def _make_auth_context(*, business_id, location_id, role=MembershipRole.manager) -> AuthContext:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name="Pat Lead",
        email="pat@example.com",
        primary_phone_e164="+15555550199",
        is_phone_verified=True,
        onboarding_completed_at=now,
        profile_metadata={},
        created_at=now,
        updated_at=now,
    )
    session = Session(
        id=uuid4(),
        user_id=user.id,
        token_hash="hashed",
        risk_level=SessionRiskLevel.low,
        elevated_actions=[],
        last_seen_at=now,
        expires_at=now + timedelta(hours=12),
        session_metadata={},
        created_at=now,
        updated_at=now,
    )
    membership = Membership(
        id=uuid4(),
        user_id=user.id,
        business_id=business_id,
        location_id=location_id,
        role=role,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeAsyncClient:
    last_request: dict | None = None

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        FakeAsyncClient.last_request = {"url": url, "params": dict(params or {})}
        return FakeResponse(
            {
                "timezone": "America/Los_Angeles",
                "hourly": {
                    "time": [
                        "2026-04-14T09:00",
                        "2026-04-14T10:00",
                        "2026-04-14T11:00",
                    ],
                    "temperature_2m": [62.0, 59.0, 57.0],
                    "precipitation_probability": [10, 65, 90],
                    "precipitation": [0.0, 0.08, 0.34],
                    "wind_speed_10m": [8.0, 18.0, 34.0],
                    "weather_code": [1, 61, 95],
                },
            }
        )


def test_get_location_forecast_normalizes_open_meteo(monkeypatch):
    session = FakeWeatherSession()
    business_id = uuid4()
    location_id = uuid4()
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        country_code="US",
        timezone="America/Los_Angeles",
        latitude=Decimal("34.050000"),
        longitude=Decimal("-118.250000"),
        settings={},
        google_place_metadata={},
        is_active=True,
    )

    async def fake_get_location(_session, _business_id, _location_id):
        assert _business_id == business_id
        assert _location_id == location_id
        return location

    monkeypatch.setattr(weather_service.businesses, "get_location", fake_get_location)
    monkeypatch.setattr(weather_service.httpx, "AsyncClient", FakeAsyncClient)

    forecast = asyncio.run(
        weather_service.get_location_forecast(
            session,
            business_id=business_id,
            location_id=location_id,
            starts_at=datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 14, 19, 0, tzinfo=timezone.utc),
        )
    )

    assert forecast.provider == "open_meteo"
    assert forecast.summary.worst_severity_flag == "high"
    assert forecast.summary.precipitation_hour_count == 2
    assert forecast.summary.peak_wind_speed_mph == 34.0
    assert [point.weather_label for point in forecast.points] == [
        "Mainly clear",
        "Light rain",
        "Thunderstorm",
    ]
    assert [point.severity_flag for point in forecast.points] == [
        "none",
        "monitor",
        "high",
    ]
    assert FakeAsyncClient.last_request is not None
    assert FakeAsyncClient.last_request["params"]["timezone"] == "America/Los_Angeles"


def test_get_location_forecast_requires_coordinates(monkeypatch):
    session = FakeWeatherSession()
    business_id = uuid4()
    location_id = uuid4()
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        country_code="US",
        timezone="America/Los_Angeles",
        latitude=None,
        longitude=None,
        settings={},
        google_place_metadata={},
        is_active=True,
    )

    async def fake_get_location(_session, _business_id, _location_id):
        return location

    monkeypatch.setattr(weather_service.businesses, "get_location", fake_get_location)

    try:
        asyncio.run(
            weather_service.get_location_forecast(
                session,
                business_id=business_id,
                location_id=location_id,
            )
        )
    except ValueError as exc:
        assert str(exc) == "location_coordinates_required"
    else:
        raise AssertionError("Expected location_coordinates_required")


def test_weather_route_returns_forecast(monkeypatch):
    fake_session = FakeWeatherSession()
    business_id = uuid4()
    location_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id, location_id=location_id)
    now = datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc)

    async def override_db():
        yield fake_session

    async def override_auth():
        return auth_ctx

    async def fake_get_location_forecast(_session, **kwargs):
        assert kwargs["business_id"] == business_id
        assert kwargs["location_id"] == location_id
        return weather_service.LocationWeatherForecastRead(
            business_id=business_id,
            location_id=location_id,
            provider="open_meteo",
            timezone="America/Los_Angeles",
            latitude=34.05,
            longitude=-118.25,
            fetched_at=now,
            range_start=now,
            range_end=now + timedelta(hours=3),
            summary=weather_service.LocationWeatherForecastSummaryRead(
                worst_severity_flag="monitor",
                monitor_hour_count=2,
                high_hour_count=0,
                precipitation_hour_count=1,
                peak_precipitation_inches=0.08,
                peak_wind_speed_mph=18.0,
            ),
            points=[
                weather_service.LocationWeatherForecastPointRead(
                    forecast_at=now,
                    temperature_f=62.0,
                    precipitation_probability=10,
                    precipitation_inches=0.0,
                    wind_speed_mph=8.0,
                    weather_code=1,
                    weather_label="Mainly clear",
                    severity_flag="none",
                )
            ],
        )

    monkeypatch.setattr(
        "app.api.routes.weather.weather_service.get_location_forecast",
        fake_get_location_forecast,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/businesses/{business_id}/locations/{location_id}/weather/forecast?hours=24")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, max-age=300, stale-while-revalidate=300"
        payload = response.json()
        assert payload["provider"] == "open_meteo"
        assert payload["summary"]["worst_severity_flag"] == "monitor"
    finally:
        app.dependency_overrides.clear()


def test_weather_route_requires_location_access():
    fake_session = FakeWeatherSession()
    business_id = uuid4()
    location_id = uuid4()
    auth_ctx = _make_auth_context(business_id=uuid4(), location_id=uuid4())

    async def override_db():
        yield fake_session

    async def override_auth():
        return auth_ctx

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/businesses/{business_id}/locations/{location_id}/weather/forecast")
        assert response.status_code == 403
        assert response.json()["detail"] == "location_access_denied"
    finally:
        app.dependency_overrides.clear()
