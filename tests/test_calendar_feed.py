from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Location, Role
from app.models.common import (
    MembershipRole,
    MembershipStatus,
    SessionRiskLevel,
    ShiftLifecycleStatus,
    ShiftStaffingStatus,
)
from app.models.identity import Membership, Session, User
from app.models.scheduling import Shift
from app.services import calendar_feed as svc
from app.services.auth import AuthContext


# ---------------------------------------------------------------------------
# Fake infrastructure
# ---------------------------------------------------------------------------


class FakeResult:
    """Minimal stand-in for the SQLAlchemy ChunkedIteratorResult."""

    def __init__(self, items: list):
        self._items = items

    def scalar_one_or_none(self):
        return self._items[0] if len(self._items) == 1 else None

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list:
        return self._items


class FakeCalendarSession:
    def __init__(self):
        self.get_map: dict[tuple[type, object], object] = {}
        # execute_results is a FIFO queue — each call to execute() pops the front
        self.execute_results: list[FakeResult] = []
        self.flushed = 0
        self.commits = 0

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def execute(self, _query):
        if self.execute_results:
            return self.execute_results.pop(0)
        return FakeResult([])

    async def flush(self):
        self.flushed += 1

    async def commit(self):
        self.commits += 1


def _make_location(*, business_id, location_id=None, settings=None) -> Location:
    now = datetime.now(timezone.utc)
    return Location(
        id=location_id or uuid4(),
        business_id=business_id,
        name="Test Location",
        display_name="Test Location",
        slug="test-location",
        address_line_1="100 Main St",
        locality="San Francisco",
        region="CA",
        postal_code="94105",
        country_code="US",
        timezone="America/Los_Angeles",
        settings=settings or {},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_role(*, business_id, role_id=None, name="Server") -> Role:
    now = datetime.now(timezone.utc)
    return Role(
        id=role_id or uuid4(),
        business_id=business_id,
        code=name.lower().replace(" ", "_"),
        name=name,
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )


def _make_shift(
    *,
    business_id,
    location_id,
    role_id,
    shift_id=None,
    lifecycle_status=ShiftLifecycleStatus.scheduled,
    staffing_status=ShiftStaffingStatus.open,
    notes=None,
    seats=1,
) -> Shift:
    now = datetime.now(timezone.utc)
    return Shift(
        id=shift_id or uuid4(),
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        lifecycle_status=lifecycle_status,
        staffing_status=staffing_status,
        seats_requested=seats,
        seats_filled=0,
        requires_manager_approval=False,
        premium_cents=0,
        notes=notes,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )


def _make_auth_context(*, business_id, location_id=None) -> AuthContext:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name="Test Manager",
        email="manager@test.com",
        primary_phone_e164="+15555550100",
        is_phone_verified=True,
        onboarding_completed_at=now,
        profile_metadata={},
        created_at=now,
        updated_at=now,
    )
    session_obj = Session(
        id=uuid4(),
        user_id=user.id,
        token_hash="hashed",
        risk_level=SessionRiskLevel.low,
        elevated_actions=[],
        last_seen_at=now,
        expires_at=now + timedelta(hours=24),
        session_metadata={},
        created_at=now,
        updated_at=now,
    )
    membership = Membership(
        id=uuid4(),
        user_id=user.id,
        business_id=business_id,
        location_id=location_id,
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session_obj, memberships=[membership])


# ---------------------------------------------------------------------------
# Unit tests: publish status list
# ---------------------------------------------------------------------------


def test_draft_lifecycle_status_not_in_publishable_list():
    assert ShiftLifecycleStatus.draft not in svc._PUBLISHABLE_LIFECYCLE_STATUSES


def test_all_non_draft_lifecycle_statuses_are_publishable():
    for status in ShiftLifecycleStatus:
        if status != ShiftLifecycleStatus.draft:
            assert status in svc._PUBLISHABLE_LIFECYCLE_STATUSES, f"{status} should be publishable"


# ---------------------------------------------------------------------------
# Unit tests: get_or_create_feed_token
# ---------------------------------------------------------------------------


def test_get_or_create_creates_token_when_none_exists():
    import asyncio
    business_id = uuid4()
    location = _make_location(business_id=business_id, settings={})
    fake_session = FakeCalendarSession()

    token, rotated_at, created = asyncio.get_event_loop().run_until_complete(
        svc.get_or_create_feed_token(fake_session, location)
    )

    assert isinstance(token, str) and len(token) > 20
    assert rotated_at is not None
    assert created is True
    assert fake_session.flushed == 1
    assert location.settings[svc.FEED_TOKEN_SETTINGS_KEY] == token


def test_get_or_create_returns_existing_token_without_flush():
    import asyncio
    existing_token = "existingtoken_abc123"
    now_str = datetime.now(timezone.utc).isoformat()
    business_id = uuid4()
    location = _make_location(
        business_id=business_id,
        settings={
            svc.FEED_TOKEN_SETTINGS_KEY: existing_token,
            svc.FEED_TOKEN_ROTATED_AT_KEY: now_str,
        },
    )
    fake_session = FakeCalendarSession()

    token, rotated_at, created = asyncio.get_event_loop().run_until_complete(
        svc.get_or_create_feed_token(fake_session, location)
    )

    assert token == existing_token
    assert created is False
    assert fake_session.flushed == 0


# ---------------------------------------------------------------------------
# Unit tests: rotate_feed_token
# ---------------------------------------------------------------------------


def test_rotate_generates_new_token():
    import asyncio
    old_token = "old_token_xyz"
    business_id = uuid4()
    location = _make_location(
        business_id=business_id,
        settings={svc.FEED_TOKEN_SETTINGS_KEY: old_token},
    )
    fake_session = FakeCalendarSession()

    new_token, rotated_at = asyncio.get_event_loop().run_until_complete(
        svc.rotate_feed_token(fake_session, location)
    )

    assert new_token != old_token
    assert isinstance(new_token, str) and len(new_token) > 20
    assert rotated_at is not None
    assert fake_session.flushed == 1
    assert location.settings[svc.FEED_TOKEN_SETTINGS_KEY] == new_token


# ---------------------------------------------------------------------------
# Unit tests: build_ics_text
# ---------------------------------------------------------------------------


def _base_location_and_role():
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    location = _make_location(business_id=business_id, location_id=location_id)
    role = _make_role(business_id=business_id, role_id=role_id)
    return business_id, location_id, role_id, location, role


def test_build_ics_text_stable_uid():
    business_id, location_id, role_id, location, role = _base_location_and_role()
    shift = _make_shift(business_id=business_id, location_id=location_id, role_id=role_id)

    ics = svc.build_ics_text(location, [shift], {role_id: role.name}, datetime.now(timezone.utc))

    assert f"UID:{shift.id}@backfill" in ics


def test_build_ics_text_cancelled_shift_has_cancelled_status():
    business_id, location_id, role_id, location, role = _base_location_and_role()
    shift = _make_shift(
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        lifecycle_status=ShiftLifecycleStatus.cancelled,
    )

    ics = svc.build_ics_text(location, [shift], {role_id: role.name}, datetime.now(timezone.utc))

    assert "STATUS:CANCELLED" in ics


def test_build_ics_text_scheduled_shift_has_confirmed_status():
    business_id, location_id, role_id, location, role = _base_location_and_role()
    shift = _make_shift(
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        lifecycle_status=ShiftLifecycleStatus.scheduled,
        staffing_status=ShiftStaffingStatus.covered,
    )

    ics = svc.build_ics_text(location, [shift], {role_id: role.name}, datetime.now(timezone.utc))

    assert "STATUS:CONFIRMED" in ics


def test_build_ics_text_in_progress_shift_has_confirmed_status():
    business_id, location_id, role_id, location, role = _base_location_and_role()
    shift = _make_shift(
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        lifecycle_status=ShiftLifecycleStatus.in_progress,
    )

    ics = svc.build_ics_text(location, [shift], {role_id: role.name}, datetime.now(timezone.utc))

    assert "STATUS:CONFIRMED" in ics


def test_build_ics_text_notes_in_description():
    business_id, location_id, role_id, location, role = _base_location_and_role()
    shift = _make_shift(
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        notes="Bring extra supplies",
    )

    ics = svc.build_ics_text(location, [shift], {role_id: role.name}, datetime.now(timezone.utc))

    assert "DESCRIPTION:Bring extra supplies" in ics


def test_build_ics_text_multi_seat_summary():
    business_id, location_id, role_id, location, role = _base_location_and_role()
    shift = _make_shift(
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        seats=3,
    )

    ics = svc.build_ics_text(location, [shift], {role_id: role.name}, datetime.now(timezone.utc))

    assert f"SUMMARY:{role.name} (3 seats)" in ics


def test_build_ics_text_empty_shifts_valid_calendar():
    business_id, location_id, _, location, _ = _base_location_and_role()
    ics = svc.build_ics_text(location, [], {}, datetime.now(timezone.utc))
    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.rstrip().endswith("END:VCALENDAR")


# ---------------------------------------------------------------------------
# Route tests: GET /api/ops/businesses/{bid}/locations/{lid}/calendar-feed
# ---------------------------------------------------------------------------


def test_get_calendar_feed_returns_403_without_location_access():
    business_id = uuid4()
    location_id = uuid4()
    fake_session = FakeCalendarSession()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=uuid4())  # different business

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/ops/businesses/{business_id}/locations/{location_id}/calendar-feed")
        assert response.status_code == 403
        assert response.json()["detail"] == "location_access_denied"
    finally:
        app.dependency_overrides.clear()


def test_get_calendar_feed_returns_404_for_unknown_location():
    business_id = uuid4()
    location_id = uuid4()
    fake_session = FakeCalendarSession()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/ops/businesses/{business_id}/locations/{location_id}/calendar-feed")
        assert response.status_code == 404
        assert response.json()["detail"] == "location_not_found"
    finally:
        app.dependency_overrides.clear()


def test_get_calendar_feed_creates_and_commits_token_on_first_call():
    business_id = uuid4()
    location_id = uuid4()
    location = _make_location(business_id=business_id, location_id=location_id, settings={})
    fake_session = FakeCalendarSession()
    fake_session.get_map[(Location, location_id)] = location

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/ops/businesses/{business_id}/locations/{location_id}/calendar-feed")
        assert response.status_code == 200
        payload = response.json()
        assert "feed_url" in payload
        assert ".ics" in payload["feed_url"]
        assert fake_session.commits == 1
    finally:
        app.dependency_overrides.clear()


def test_get_calendar_feed_does_not_commit_when_token_already_exists():
    business_id = uuid4()
    location_id = uuid4()
    existing_token = "alreadyexists_abc"
    location = _make_location(
        business_id=business_id,
        location_id=location_id,
        settings={
            svc.FEED_TOKEN_SETTINGS_KEY: existing_token,
            svc.FEED_TOKEN_ROTATED_AT_KEY: datetime.now(timezone.utc).isoformat(),
        },
    )
    fake_session = FakeCalendarSession()
    fake_session.get_map[(Location, location_id)] = location

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/ops/businesses/{business_id}/locations/{location_id}/calendar-feed")
        assert response.status_code == 200
        assert existing_token in response.json()["feed_url"]
        assert fake_session.commits == 0
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Route tests: POST /api/ops/.../calendar-feed/rotate
# ---------------------------------------------------------------------------


def test_rotate_calendar_feed_returns_new_url_and_commits():
    business_id = uuid4()
    location_id = uuid4()
    old_token = "old_token_abc123"
    location = _make_location(
        business_id=business_id,
        location_id=location_id,
        settings={svc.FEED_TOKEN_SETTINGS_KEY: old_token},
    )
    fake_session = FakeCalendarSession()
    fake_session.get_map[(Location, location_id)] = location

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/ops/businesses/{business_id}/locations/{location_id}/calendar-feed/rotate"
        )
        assert response.status_code == 200
        payload = response.json()
        assert "feed_url" in payload
        assert old_token not in payload["feed_url"]
        assert fake_session.commits == 1
    finally:
        app.dependency_overrides.clear()


def test_rotate_calendar_feed_returns_403_without_access():
    business_id = uuid4()
    location_id = uuid4()
    fake_session = FakeCalendarSession()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=uuid4())

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/ops/businesses/{business_id}/locations/{location_id}/calendar-feed/rotate"
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Route tests: GET /api/calendar-feeds/{token}.ics  (anonymous)
# ---------------------------------------------------------------------------


def test_ics_endpoint_returns_404_for_unknown_token():
    fake_session = FakeCalendarSession()
    fake_session.execute_results = [FakeResult([])]

    async def override_db():
        yield fake_session

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    try:
        response = client.get("/api/calendar-feeds/badtoken.ics")
        assert response.status_code == 404
        assert response.json()["detail"] == "feed_not_found"
    finally:
        app.dependency_overrides.clear()


def test_ics_endpoint_returns_text_calendar_for_valid_token():
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    feed_token = "valid_feed_token_abc"

    location = _make_location(
        business_id=business_id,
        location_id=location_id,
        settings={svc.FEED_TOKEN_SETTINGS_KEY: feed_token},
    )
    shift = _make_shift(
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        lifecycle_status=ShiftLifecycleStatus.scheduled,
        staffing_status=ShiftStaffingStatus.covered,
    )
    role = _make_role(business_id=business_id, role_id=role_id)

    fake_session = FakeCalendarSession()
    fake_session.execute_results = [
        FakeResult([location]),   # get_location_by_feed_token
        FakeResult([shift]),      # shifts query
        FakeResult([role]),       # roles query
    ]

    async def override_db():
        yield fake_session

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    try:
        response = client.get(f"/api/calendar-feeds/{feed_token}.ics")
        assert response.status_code == 200
        assert "text/calendar" in response.headers["content-type"]
        body = response.text
        assert "BEGIN:VCALENDAR" in body
        assert f"UID:{shift.id}@backfill" in body
        assert "STATUS:CONFIRMED" in body
        # subscription feed — no Content-Disposition attachment header
        assert "content-disposition" not in response.headers
    finally:
        app.dependency_overrides.clear()


def test_ics_endpoint_excludes_draft_shifts():
    """build_location_ics filters drafts via lifecycle_status.in_(_PUBLISHABLE_LIFECYCLE_STATUSES).

    The fake session returns empty shifts (simulating the DB filtering out drafts).
    """
    business_id = uuid4()
    location_id = uuid4()
    feed_token = "draft_exclusion_token"

    location = _make_location(
        business_id=business_id,
        location_id=location_id,
        settings={svc.FEED_TOKEN_SETTINGS_KEY: feed_token},
    )

    fake_session = FakeCalendarSession()
    fake_session.execute_results = [
        FakeResult([location]),
        FakeResult([]),   # no publishable shifts
    ]

    async def override_db():
        yield fake_session

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    try:
        response = client.get(f"/api/calendar-feeds/{feed_token}.ics")
        assert response.status_code == 200
        body = response.text
        assert "BEGIN:VCALENDAR" in body
        assert "BEGIN:VEVENT" not in body
    finally:
        app.dependency_overrides.clear()


def test_ics_endpoint_renders_cancelled_shift_with_cancelled_status():
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    feed_token = "cancelled_event_token"

    location = _make_location(
        business_id=business_id,
        location_id=location_id,
        settings={svc.FEED_TOKEN_SETTINGS_KEY: feed_token},
    )
    cancelled_shift = _make_shift(
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        lifecycle_status=ShiftLifecycleStatus.cancelled,
    )
    role = _make_role(business_id=business_id, role_id=role_id)

    fake_session = FakeCalendarSession()
    fake_session.execute_results = [
        FakeResult([location]),
        FakeResult([cancelled_shift]),
        FakeResult([role]),
    ]

    async def override_db():
        yield fake_session

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    try:
        response = client.get(f"/api/calendar-feeds/{feed_token}.ics")
        assert response.status_code == 200
        body = response.text
        assert "STATUS:CANCELLED" in body
        assert f"UID:{cancelled_shift.id}@backfill" in body
    finally:
        app.dependency_overrides.clear()
