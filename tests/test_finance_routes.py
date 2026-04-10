from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Location
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.coverage import CoverageCase
from app.models.identity import Membership, Session, User
from app.models.finance import BillingLedgerEntry, CostLedgerEntry
from app.services import finance_reporting
from app.services.auth import AuthContext


class FakeFinanceRouteSession:
    def __init__(self):
        self.get_map: dict[tuple[type, object], object] = {}

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))


def _make_auth_context(*, business_id, location_id=None, role=MembershipRole.manager) -> AuthContext:
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


def _make_location(*, business_id, location_id, timezone_name="America/Los_Angeles") -> Location:
    now = datetime.now(timezone.utc)
    return Location(
        id=location_id,
        business_id=business_id,
        name="Santa Monica",
        display_name="Santa Monica",
        slug="santa-monica",
        address_line_1="123 Ocean Ave",
        locality="Santa Monica",
        region="CA",
        postal_code="90401",
        country_code="US",
        timezone=timezone_name,
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_coverage_case(*, coverage_case_id, location_id) -> CoverageCase:
    now = datetime.now(timezone.utc)
    return CoverageCase(
        id=coverage_case_id,
        shift_id=uuid4(),
        location_id=location_id,
        role_id=uuid4(),
        status="running",
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        created_at=now,
        updated_at=now,
    )


def test_get_location_billing_cap_returns_snapshot(monkeypatch):
    fake_session = FakeFinanceRouteSession()
    business_id = uuid4()
    location_id = uuid4()
    fake_session.get_map[(Location, location_id)] = _make_location(
        business_id=business_id,
        location_id=location_id,
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_cap_snapshot(_session, **kwargs):
        assert kwargs["location_id"] == location_id
        return finance_reporting.LocationBillingCapSnapshot(
            location_id=location_id,
            billing_cycle_start=datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc),
            billed_cents=18000,
            remaining_cents=2000,
            monthly_cap_cents=20000,
            fill_price_cents=2000,
            next_fill_charge_cents=2000,
            is_capped=False,
        )

    monkeypatch.setattr(finance_reporting, "location_billing_cap_snapshot", fake_cap_snapshot)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/businesses/{business_id}/locations/{location_id}/finance/billing-cap")
        assert response.status_code == 200
        assert response.json() == {
            "location_id": str(location_id),
            "billing_cycle_start": "2026-04-01T07:00:00Z",
            "billed_cents": 18000,
            "remaining_cents": 2000,
            "monthly_cap_cents": 20000,
            "fill_price_cents": 2000,
            "next_fill_charge_cents": 2000,
            "is_capped": False,
        }
    finally:
        app.dependency_overrides.clear()


def test_get_campaign_economics_returns_snapshot_and_breakdown(monkeypatch):
    fake_session = FakeFinanceRouteSession()
    business_id = uuid4()
    location_id = uuid4()
    coverage_case_id = uuid4()
    fake_session.get_map[(Location, location_id)] = _make_location(
        business_id=business_id,
        location_id=location_id,
    )
    fake_session.get_map[(CoverageCase, coverage_case_id)] = _make_coverage_case(
        coverage_case_id=coverage_case_id,
        location_id=location_id,
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_campaign_snapshot(_session, case_id):
        assert case_id == coverage_case_id
        return finance_reporting.CampaignEconomicsSnapshot(
            coverage_case_id=coverage_case_id,
            total_cost_micros=34100,
            total_cost_cents_rounded=3,
            total_billed_cents=2000,
            total_billed_micros=20_000_000,
            gross_margin_micros=19_965_900,
            gross_margin_cents_rounded=1997,
            billed_entry_count=1,
            cost_entry_count=2,
        )

    async def fake_breakdown(_session, case_id):
        assert case_id == coverage_case_id
        return [
            finance_reporting.CampaignCostBreakdownRow(
                provider="openai",
                product="llm_generation",
                total_cost_micros=4100,
                total_cost_cents_rounded=0,
            ),
            finance_reporting.CampaignCostBreakdownRow(
                provider="retell",
                product="voice_ai",
                total_cost_micros=30000,
                total_cost_cents_rounded=3,
            ),
        ]

    monkeypatch.setattr(finance_reporting, "campaign_economics_snapshot", fake_campaign_snapshot)
    monkeypatch.setattr(finance_reporting, "campaign_cost_breakdown", fake_breakdown)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/finance/coverage-cases/{coverage_case_id}/economics"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["coverage_case_id"] == str(coverage_case_id)
        assert payload["total_cost_micros"] == 34100
        assert payload["total_billed_cents"] == 2000
        assert payload["gross_margin_cents_rounded"] == 1997
        assert payload["cost_breakdown"][0]["provider"] == "openai"
        assert payload["cost_breakdown"][1]["product"] == "voice_ai"
    finally:
        app.dependency_overrides.clear()


def test_get_campaign_economics_enforces_location_access():
    fake_session = FakeFinanceRouteSession()
    business_id = uuid4()
    location_id = uuid4()
    coverage_case_id = uuid4()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, role=MembershipRole.viewer)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/finance/coverage-cases/{coverage_case_id}/economics"
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "location_access_denied"
    finally:
        app.dependency_overrides.clear()


def test_list_campaign_cost_entries_returns_entries(monkeypatch):
    fake_session = FakeFinanceRouteSession()
    business_id = uuid4()
    location_id = uuid4()
    coverage_case_id = uuid4()
    fake_session.get_map[(Location, location_id)] = _make_location(
        business_id=business_id,
        location_id=location_id,
    )
    fake_session.get_map[(CoverageCase, coverage_case_id)] = _make_coverage_case(
        coverage_case_id=coverage_case_id,
        location_id=location_id,
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_list_cost_entries(_session, *, coverage_case_id: object, limit: int):
        assert coverage_case_id == fake_case_id
        assert limit == 25
        return [
            CostLedgerEntry(
                id=uuid4(),
                business_id=business_id,
                location_id=location_id,
                coverage_case_id=fake_case_id,
                provider="retell",
                product="voice_ai",
                reference_type="call",
                reference_id="call_123",
                idempotency_key="retell:call_123",
                quantity=Decimal("1.500000"),
                unit_cost_micros=20_000,
                total_cost_micros=30_000,
                cost_metadata={"minutes": "1.5"},
                occurred_at=datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc),
                created_at=datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc),
            )
        ]

    fake_case_id = coverage_case_id
    monkeypatch.setattr(finance_reporting, "list_cost_entries", fake_list_cost_entries)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/finance/coverage-cases/{coverage_case_id}/cost-entries?limit=25"
        )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["provider"] == "retell"
        assert payload[0]["product"] == "voice_ai"
        assert float(payload[0]["quantity"]) == 1.5
        assert payload[0]["total_cost_micros"] == 30_000
        assert payload[0]["cost_metadata"]["minutes"] == "1.5"
    finally:
        app.dependency_overrides.clear()


def test_list_campaign_billing_entries_returns_entries(monkeypatch):
    fake_session = FakeFinanceRouteSession()
    business_id = uuid4()
    location_id = uuid4()
    coverage_case_id = uuid4()
    fake_session.get_map[(Location, location_id)] = _make_location(
        business_id=business_id,
        location_id=location_id,
    )
    fake_session.get_map[(CoverageCase, coverage_case_id)] = _make_coverage_case(
        coverage_case_id=coverage_case_id,
        location_id=location_id,
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_list_billing_entries(_session, *, coverage_case_id: object, limit: int):
        assert coverage_case_id == fake_case_id
        assert limit == 10
        return [
            BillingLedgerEntry(
                id=uuid4(),
                business_id=business_id,
                location_id=location_id,
                coverage_case_id=fake_case_id,
                billing_event_type="fill_charged",
                billing_cycle_start=datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc),
                amount_cents=2_000,
                cap_applied=False,
                idempotency_key="fill:123",
                billing_metadata={"billed_cents_after": 2_000},
                occurred_at=datetime(2026, 4, 10, 18, 45, tzinfo=timezone.utc),
                created_at=datetime(2026, 4, 10, 18, 45, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 10, 18, 45, tzinfo=timezone.utc),
            )
        ]

    fake_case_id = coverage_case_id
    monkeypatch.setattr(finance_reporting, "list_billing_entries", fake_list_billing_entries)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/finance/coverage-cases/{coverage_case_id}/billing-entries?limit=10"
        )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["billing_event_type"] == "fill_charged"
        assert payload[0]["amount_cents"] == 2_000
        assert payload[0]["billing_metadata"]["billed_cents_after"] == 2_000
    finally:
        app.dependency_overrides.clear()
