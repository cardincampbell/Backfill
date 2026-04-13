from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_context
from app.main import app
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.identity import Membership, Session, User
from app.services.auth import AuthContext
from app.services.realtime_events import RealtimeEventBroker, RealtimePlatformEvent


def _make_auth_context(
    *,
    business_id,
    role=MembershipRole.manager,
    location_id=None,
) -> AuthContext:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name="Jordan Lead",
        email="jordan@example.com",
        primary_phone_e164="+15555550131",
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
        expires_at=now,
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


@pytest.mark.asyncio
async def test_realtime_broker_filters_by_business_and_location():
    broker = RealtimeEventBroker()
    matching = RealtimePlatformEvent(
        platform_event_id=str(uuid4()),
        business_id="business-1",
        location_id="location-1",
        event_type="schedule.shift.assigned",
        entity_type="shift",
        entity_id=str(uuid4()),
        trace_id="trace-1",
        occurred_at="2026-04-13T16:00:00Z",
    )
    other_location = RealtimePlatformEvent(
        platform_event_id=str(uuid4()),
        business_id="business-1",
        location_id="location-2",
        event_type="schedule.shift.assigned",
        entity_type="shift",
        entity_id=str(uuid4()),
        trace_id="trace-2",
        occurred_at="2026-04-13T16:01:00Z",
    )
    other_business = RealtimePlatformEvent(
        platform_event_id=str(uuid4()),
        business_id="business-2",
        location_id="location-1",
        event_type="schedule.shift.assigned",
        entity_type="shift",
        entity_id=str(uuid4()),
        trace_id="trace-3",
        occurred_at="2026-04-13T16:02:00Z",
    )

    async with broker.subscribe(business_id="business-1", location_id="location-1") as queue:
        await broker.publish_local(other_location)
        await broker.publish_local(other_business)
        await broker.publish_local(matching)
        received = await asyncio.wait_for(queue.get(), timeout=1)

    assert received == matching


def test_realtime_events_route_streams_platform_event(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    streamed_event = RealtimePlatformEvent(
        platform_event_id=str(uuid4()),
        business_id=str(business_id),
        location_id=str(location_id),
        event_type="schedule.week.published",
        entity_type="location",
        entity_id=str(location_id),
        trace_id="trace_123",
        occurred_at="2026-04-13T16:00:00Z",
    )

    class FakeBroker:
        async def ensure_started(self):
            return None

        @asynccontextmanager
        async def subscribe(self, *, business_id: str, location_id: str | None = None):
            assert business_id == str(business_id_uuid)
            assert location_id == str(location_uuid)
            queue: asyncio.Queue[RealtimePlatformEvent] = asyncio.Queue()
            queue.put_nowait(streamed_event)
            yield queue

    business_id_uuid = business_id
    location_uuid = location_id

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    monkeypatch.setattr("app.api.routes.realtime.get_realtime_event_broker", lambda: FakeBroker())
    disconnect_states = iter([False, True])

    async def fake_is_disconnected(_self):
        return next(disconnect_states, True)

    monkeypatch.setattr("starlette.requests.Request.is_disconnected", fake_is_disconnected)
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        with client.stream(
            "GET",
            f"/api/businesses/{business_id}/realtime/events?location_id={location_id}",
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            lines: list[str] = []
            for line in response.iter_lines():
                if line:
                    lines.append(line)
                if line.startswith("data:"):
                    break

        payload_line = next(line for line in lines if line.startswith("data:"))
        payload = json.loads(payload_line.removeprefix("data:"))
        assert payload["event_type"] == "schedule.week.published"
        assert payload["location_id"] == str(location_id)
    finally:
        app.dependency_overrides.clear()


def test_realtime_events_route_requires_target_location_access():
    business_id = uuid4()
    allowed_location_id = uuid4()
    blocked_location_id = uuid4()

    async def override_auth():
        return _make_auth_context(
            business_id=business_id,
            location_id=allowed_location_id,
        )

    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/realtime/events?location_id={blocked_location_id}"
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "location_access_denied"
    finally:
        app.dependency_overrides.clear()
