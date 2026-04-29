from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Business, Location
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.coverage import CoverageCase
from app.models.identity import Membership, Session, User
from app.models.finance import BillingLedgerEntry, CostLedgerEntry
from app.schemas.finance import (
    BusinessComplianceScheduledPolicyDriftRead,
    BusinessCompliancePolicySimulationRead,
    LocationComplianceScheduledPolicyDriftRead,
    LocationCompliancePayrollExportRead,
    LocationCompliancePolicySimulationRead,
    LocationComplianceTrendRead,
    LocationComplianceWeekRead,
    LocationComplianceWeekReplayRead,
)
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


def _make_business(*, business_id) -> Business:
    now = datetime.now(timezone.utc)
    return Business(
        id=business_id,
        name="Backfill Foods",
        display_name="Backfill Foods",
        slug="backfill-foods",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={},
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


def test_get_location_compliance_week_returns_snapshot(monkeypatch):
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

    async def fake_compliance_week_snapshot(_session, *, location, week_start_date):
        assert location.id == location_id
        assert week_start_date.isoformat() == "2026-04-06"
        return finance_reporting.LocationComplianceWeekSnapshot(
            location_id=location_id,
            week_start_date=week_start_date,
            week_end_date=week_start_date,
            shift_count=2,
            assigned_shift_count=2,
            employee_count=1,
            warning_assignment_count=1,
            blocked_assignment_count=0,
            unresolved_premium_assignment_count=1,
            premium_total_cents=1845,
            override_applied_count=1,
            warning_rule_codes=["meal_break_missing"],
            premium_rule_codes=["meal_break_premium"],
            unresolved_premium_rule_codes=["split_shift_premium"],
            artifact_type_counts=[
                finance_reporting.ComplianceArtifactTypeCountRow(
                    artifact_type="meal_waiver",
                    count=1,
                )
            ],
            shifts=[
                finance_reporting.ComplianceWeekShiftRow(
                    shift_id=uuid4(),
                    employee_id=uuid4(),
                    employee_name="Taylor Server",
                    role_id=uuid4(),
                    role_name="Server",
                    starts_at=datetime(2026, 4, 7, 16, 0, tzinfo=timezone.utc),
                    ends_at=datetime(2026, 4, 7, 23, 0, tzinfo=timezone.utc),
                    compliance_status="warning",
                    profile_code="ca_restaurant_v1",
                    blocking_rule_codes=[],
                    warning_rule_codes=["meal_break_missing"],
                    premium_rule_codes=["meal_break_premium"],
                    premium_total_cents=1845,
                    unresolved_premium_rule_codes=[],
                    override_applied=True,
                    override_artifact_id=uuid4(),
                )
            ],
            employees=[
                finance_reporting.ComplianceWeekEmployeeRow(
                    employee_id=uuid4(),
                    employee_name="Taylor Server",
                    assignment_count=2,
                    shift_ids=[uuid4()],
                    warning_rule_codes=["meal_break_missing"],
                    premium_rule_codes=["meal_break_premium"],
                    premium_total_cents=1845,
                    unresolved_premium_rule_codes=["split_shift_premium"],
                    override_applied_count=1,
                )
            ],
            override_artifacts=[
                finance_reporting.ComplianceOverrideArtifactSummaryRow(
                    artifact_id=uuid4(),
                    shift_id=uuid4(),
                    employee_id=uuid4(),
                    employee_name="Taylor Server",
                    rule_code="meal_break_missing",
                    artifact_type="meal_waiver",
                    approved_at=datetime(2026, 4, 7, 15, 0, tzinfo=timezone.utc),
                    expires_at=None,
                    note="Signed waiver on file",
                )
            ],
        )

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_week_snapshot",
        fake_compliance_week_snapshot,
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/finance/compliance-weeks/2026-04-06"
        )
        assert response.status_code == 200
        payload = LocationComplianceWeekRead.model_validate(response.json())
        assert payload.location_id == location_id
        assert payload.premium_total_cents == 1845
        assert payload.warning_rule_codes == ["meal_break_missing"]
        assert payload.artifact_type_counts[0].artifact_type == "meal_waiver"
        assert payload.artifact_type_counts[0].count == 1
        assert payload.shifts[0].employee_name == "Taylor Server"
        assert payload.employees[0].override_applied_count == 1
        assert payload.override_artifacts[0].artifact_type == "meal_waiver"
        assert payload.override_artifacts[0].note == "Signed waiver on file"
    finally:
        app.dependency_overrides.clear()


def test_replay_location_compliance_week_policy_returns_snapshot(monkeypatch):
    fake_session = FakeFinanceRouteSession()
    business_id = uuid4()
    location_id = uuid4()
    version_id = uuid4()
    fake_session.get_map[(Location, location_id)] = _make_location(
        business_id=business_id,
        location_id=location_id,
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_replay(_session, *, location, week_start_date, policy_version_id):
        assert location.id == location_id
        assert week_start_date.isoformat() == "2026-04-06"
        assert policy_version_id == version_id
        baseline = finance_reporting.LocationComplianceWeekSnapshot(
            location_id=location_id,
            week_start_date=week_start_date,
            week_end_date=week_start_date,
            shift_count=2,
            assigned_shift_count=2,
            employee_count=1,
            warning_assignment_count=1,
            blocked_assignment_count=0,
            unresolved_premium_assignment_count=0,
            premium_total_cents=1200,
            override_applied_count=0,
            warning_rule_codes=[],
            premium_rule_codes=[],
            unresolved_premium_rule_codes=[],
            artifact_type_counts=[],
            shifts=[],
            employees=[],
            override_artifacts=[],
        )
        replayed = finance_reporting.LocationComplianceWeekSnapshot(
            location_id=location_id,
            week_start_date=week_start_date,
            week_end_date=week_start_date,
            shift_count=2,
            assigned_shift_count=2,
            employee_count=1,
            warning_assignment_count=2,
            blocked_assignment_count=1,
            unresolved_premium_assignment_count=1,
            premium_total_cents=1800,
            override_applied_count=0,
            warning_rule_codes=[],
            premium_rule_codes=[],
            unresolved_premium_rule_codes=[],
            artifact_type_counts=[],
            shifts=[],
            employees=[],
            override_artifacts=[],
        )
        return finance_reporting.LocationComplianceWeekReplay(
            location_id=location_id,
            week_start_date=week_start_date,
            week_end_date=week_start_date,
            replay_policy_version_id=version_id,
            replay_policy_scope="location",
            replay_policy_hash="hash_replay_loc",
            replay_policy_effective_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
            baseline=baseline,
            replayed=replayed,
            delta=finance_reporting.ComplianceTrendDeltaSummary(
                warning_assignment_count_delta=1,
                blocked_assignment_count_delta=1,
                unresolved_premium_assignment_count_delta=1,
                override_applied_count_delta=0,
                premium_total_cents_delta=600,
            ),
        )

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_week_policy_replay",
        fake_replay,
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/finance/compliance-weeks/2026-04-06/replay-policy/{version_id}"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["replay_policy_version_id"] == str(version_id)
        assert payload["replay_policy_scope"] == "location"
        assert payload["delta"]["premium_total_cents_delta"] == 600
        assert payload["replayed"]["blocked_assignment_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_get_location_compliance_payroll_export_returns_snapshot(monkeypatch):
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

    async def fake_compliance_payroll_export(_session, *, location, week_start_date):
        assert location.id == location_id
        assert week_start_date.isoformat() == "2026-04-06"
        return finance_reporting.LocationCompliancePayrollExport(
            location_id=location_id,
            week_start_date=week_start_date,
            week_end_date=week_start_date,
            row_count=1,
            premium_payment_row_count=1,
            ready_adjustment_row_count=1,
            manual_review_row_count=1,
            missing_employee_identifier_row_count=0,
            artifact_record_row_count=0,
            total_premium_cents=1845,
            rows=[
                finance_reporting.CompliancePayrollAdjustmentRow(
                    shift_id=uuid4(),
                    employee_id=uuid4(),
                    employee_name="Taylor Server",
                    role_name="Server",
                    starts_at=datetime(2026, 4, 7, 16, 0, tzinfo=timezone.utc),
                    ends_at=datetime(2026, 4, 7, 23, 0, tzinfo=timezone.utc),
                    compliance_status="warning",
                    profile_code="ca_restaurant_v1",
                    premium_cents=1845,
                    premium_rule_codes=["meal_break_premium"],
                    unresolved_premium_rule_codes=["split_shift_premium"],
                    premium_payment_required=True,
                    manual_review_required=True,
                    override_applied=True,
                    override_artifact_id=uuid4(),
                    override_artifact_type="meal_waiver",
                    override_artifact_note="Signed waiver on file",
                    employee_identifier="EMP-42",
                    employee_identifier_type="employee_number",
                    earning_code="MEALPREM",
                    earning_label="Meal Break Premium",
                    source_rule_code="meal_break_premium",
                    source_reason_codes=["first_meal_break_missing"],
                )
            ],
        )

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_payroll_export",
        fake_compliance_payroll_export,
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/finance/compliance-weeks/2026-04-06/payroll-export"
        )
        assert response.status_code == 200
        payload = LocationCompliancePayrollExportRead.model_validate(response.json())
        assert payload.location_id == location_id
        assert payload.row_count == 1
        assert payload.total_premium_cents == 1845
        assert payload.rows[0].employee_name == "Taylor Server"
        assert payload.rows[0].premium_payment_required is True
        assert payload.rows[0].manual_review_required is True
        assert payload.rows[0].override_artifact_type == "meal_waiver"
    finally:
        app.dependency_overrides.clear()


def test_get_location_compliance_trend_returns_snapshot(monkeypatch):
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

    async def fake_compliance_trend(_session, *, location, end_week_start_date, week_count):
        assert location.id == location_id
        assert end_week_start_date.isoformat() == "2026-04-20"
        assert week_count == 3
        return finance_reporting.LocationComplianceTrendSnapshot(
            location_id=location_id,
            start_week_date=datetime(2026, 4, 6, 0, 0, tzinfo=timezone.utc).date(),
            end_week_date=end_week_start_date,
            week_count=3,
            total_shift_count=15,
            total_assigned_shift_count=12,
            total_warning_assignment_count=4,
            total_blocked_assignment_count=3,
            total_unresolved_premium_assignment_count=3,
            total_override_applied_count=4,
            total_premium_cents=6600,
            top_warning_rule_codes=[
                finance_reporting.ComplianceTrendRuleCountRow(
                    rule_code="meal_break_first_window",
                    count=2,
                )
            ],
            top_premium_rule_codes=[
                finance_reporting.ComplianceTrendRuleCountRow(
                    rule_code="meal_break_premium",
                    count=3,
                )
            ],
            top_unresolved_premium_rule_codes=[
                finance_reporting.ComplianceTrendRuleCountRow(
                    rule_code="split_shift_premium",
                    count=2,
                )
            ],
            weeks=[
                finance_reporting.ComplianceTrendWeekRow(
                    week_start_date=datetime(2026, 4, 6, 0, 0, tzinfo=timezone.utc).date(),
                    week_end_date=datetime(2026, 4, 12, 0, 0, tzinfo=timezone.utc).date(),
                    shift_count=4,
                    assigned_shift_count=3,
                    warning_assignment_count=1,
                    blocked_assignment_count=0,
                    unresolved_premium_assignment_count=1,
                    premium_total_cents=1000,
                    override_applied_count=1,
                ),
                finance_reporting.ComplianceTrendWeekRow(
                    week_start_date=datetime(2026, 4, 13, 0, 0, tzinfo=timezone.utc).date(),
                    week_end_date=datetime(2026, 4, 19, 0, 0, tzinfo=timezone.utc).date(),
                    shift_count=5,
                    assigned_shift_count=4,
                    warning_assignment_count=2,
                    blocked_assignment_count=1,
                    unresolved_premium_assignment_count=0,
                    premium_total_cents=2450,
                    override_applied_count=2,
                ),
            ],
        )

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_trend_snapshot",
        fake_compliance_trend,
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/finance/compliance-trends/2026-04-20",
            params={"week_count": 3},
        )
        assert response.status_code == 200
        payload = LocationComplianceTrendRead.model_validate(response.json())
        assert payload.location_id == location_id
        assert payload.week_count == 3
        assert payload.total_premium_cents == 6600
        assert payload.top_warning_rule_codes[0].rule_code == "meal_break_first_window"
        assert payload.top_premium_rule_codes[0].count == 3
        assert payload.weeks[1].premium_total_cents == 2450
    finally:
        app.dependency_overrides.clear()


def test_get_location_scheduled_policy_drift_returns_snapshot(monkeypatch):
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

    async def fake_scheduled_policy_drift(_session, *, location, start_week_date, week_count):
        assert location.id == location_id
        assert start_week_date.isoformat() == "2026-05-04"
        assert week_count == 4
        return finance_reporting.LocationComplianceScheduledPolicyDrift(
            location_id=location_id,
            start_week_date=start_week_date,
            end_week_date=date(2026, 5, 25),
            week_count=4,
            activating_policy_versions=[
                finance_reporting.CompliancePolicyActivationRow(
                    policy_version_id=uuid4(),
                    policy_scope="location",
                    policy_hash="future_loc_hash",
                    effective_at=datetime(2026, 5, 6, 15, 0, tzinfo=timezone.utc),
                    location_id=location_id,
                    location_name="Santa Monica",
                )
            ],
            frozen_current=finance_reporting.LocationComplianceTrendSnapshot(
                location_id=location_id,
                start_week_date=start_week_date,
                end_week_date=date(2026, 5, 25),
                week_count=4,
                total_shift_count=20,
                total_assigned_shift_count=18,
                total_warning_assignment_count=3,
                total_blocked_assignment_count=1,
                total_unresolved_premium_assignment_count=1,
                total_override_applied_count=1,
                total_premium_cents=1800,
                top_warning_rule_codes=[],
                top_premium_rule_codes=[],
                top_unresolved_premium_rule_codes=[],
                weeks=[],
            ),
            scheduled=finance_reporting.LocationComplianceTrendSnapshot(
                location_id=location_id,
                start_week_date=start_week_date,
                end_week_date=date(2026, 5, 25),
                week_count=4,
                total_shift_count=20,
                total_assigned_shift_count=18,
                total_warning_assignment_count=5,
                total_blocked_assignment_count=3,
                total_unresolved_premium_assignment_count=2,
                total_override_applied_count=2,
                total_premium_cents=2600,
                top_warning_rule_codes=[],
                top_premium_rule_codes=[],
                top_unresolved_premium_rule_codes=[],
                weeks=[],
            ),
            delta=finance_reporting.ComplianceTrendDeltaSummary(
                warning_assignment_count_delta=2,
                blocked_assignment_count_delta=2,
                unresolved_premium_assignment_count_delta=1,
                override_applied_count_delta=1,
                premium_total_cents_delta=800,
            ),
            week_deltas=[
                finance_reporting.ComplianceTrendDeltaRow(
                    week_start_date=start_week_date,
                    week_end_date=date(2026, 5, 10),
                    warning_assignment_count_delta=1,
                    blocked_assignment_count_delta=1,
                    unresolved_premium_assignment_count_delta=0,
                    override_applied_count_delta=0,
                    premium_total_cents_delta=300,
                )
            ],
        )

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_scheduled_policy_drift",
        fake_scheduled_policy_drift,
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/finance/scheduled-policy-drift/2026-05-04",
            params={"week_count": 4},
        )
        assert response.status_code == 200
        payload = LocationComplianceScheduledPolicyDriftRead.model_validate(response.json())
        assert payload.location_id == location_id
        assert payload.week_count == 4
        assert payload.delta.premium_total_cents_delta == 800
        assert payload.activating_policy_versions[0].policy_hash == "future_loc_hash"
    finally:
        app.dependency_overrides.clear()


def test_simulate_location_compliance_policy_returns_snapshot(monkeypatch):
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

    async def fake_policy_simulation(
        _session,
        *,
        location,
        end_week_start_date,
        week_count,
        proposed_location_compliance_settings,
    ):
        assert location.id == location_id
        assert end_week_start_date.isoformat() == "2026-04-20"
        assert week_count == 4
        assert proposed_location_compliance_settings == {
            "minimum_rest_hours": 12.0,
            "block_unresolved_premiums": True,
        }
        baseline = finance_reporting.LocationComplianceTrendSnapshot(
            location_id=location_id,
            start_week_date=datetime(2026, 3, 30, 0, 0, tzinfo=timezone.utc).date(),
            end_week_date=end_week_start_date,
            week_count=4,
            total_shift_count=20,
            total_assigned_shift_count=16,
            total_warning_assignment_count=4,
            total_blocked_assignment_count=1,
            total_unresolved_premium_assignment_count=1,
            total_override_applied_count=2,
            total_premium_cents=2800,
            top_warning_rule_codes=[],
            top_premium_rule_codes=[],
            top_unresolved_premium_rule_codes=[],
            weeks=[],
        )
        simulated = finance_reporting.LocationComplianceTrendSnapshot(
            location_id=location_id,
            start_week_date=datetime(2026, 3, 30, 0, 0, tzinfo=timezone.utc).date(),
            end_week_date=end_week_start_date,
            week_count=4,
            total_shift_count=20,
            total_assigned_shift_count=16,
            total_warning_assignment_count=6,
            total_blocked_assignment_count=3,
            total_unresolved_premium_assignment_count=2,
            total_override_applied_count=1,
            total_premium_cents=4600,
            top_warning_rule_codes=[],
            top_premium_rule_codes=[],
            top_unresolved_premium_rule_codes=[],
            weeks=[],
        )
        return finance_reporting.LocationCompliancePolicySimulation(
            location_id=location_id,
            end_week_start_date=end_week_start_date,
            week_count=4,
            baseline_location_compliance_policy_hash="preview_hash_1234567890",
            baseline_location_compliance_settings={
                "minimum_rest_hours": 10.0,
                "block_unresolved_premiums": False,
            },
            proposed_location_compliance_settings={
                "minimum_rest_hours": 12.0,
                "block_unresolved_premiums": True,
            },
            baseline=baseline,
            simulated=simulated,
            delta=finance_reporting.ComplianceTrendDeltaSummary(
                warning_assignment_count_delta=2,
                blocked_assignment_count_delta=2,
                unresolved_premium_assignment_count_delta=1,
                override_applied_count_delta=-1,
                premium_total_cents_delta=1800,
            ),
            week_deltas=[
                finance_reporting.ComplianceTrendDeltaRow(
                    week_start_date=datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc).date(),
                    week_end_date=datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc).date(),
                    warning_assignment_count_delta=1,
                    blocked_assignment_count_delta=1,
                    unresolved_premium_assignment_count_delta=1,
                    override_applied_count_delta=0,
                    premium_total_cents_delta=700,
                )
            ],
        )

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_policy_simulation",
        fake_policy_simulation,
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/locations/{location_id}/finance/compliance-trends/2026-04-20/simulate-policy",
            json={
                "week_count": 4,
                "compliance": {
                    "minimum_rest_hours": 12,
                    "block_unresolved_premiums": True,
                },
            },
        )
        assert response.status_code == 200
        payload = LocationCompliancePolicySimulationRead.model_validate(response.json())
        assert payload.location_id == location_id
        assert payload.week_count == 4
        assert payload.baseline_location_compliance_policy_hash == "preview_hash_1234567890"
        assert payload.baseline_location_compliance_settings.minimum_rest_hours == 10
        assert payload.proposed_location_compliance_settings.minimum_rest_hours == 12
        assert payload.proposed_location_compliance_settings.block_unresolved_premiums is True
        assert payload.delta.blocked_assignment_count_delta == 2
        assert payload.delta.premium_total_cents_delta == 1800
        assert payload.week_deltas[0].premium_total_cents_delta == 700
    finally:
        app.dependency_overrides.clear()


def test_simulate_business_compliance_policy_returns_snapshot(monkeypatch):
    fake_session = FakeFinanceRouteSession()
    business_id = uuid4()
    fake_session.get_map[(Business, business_id)] = _make_business(
        business_id=business_id,
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    async def fake_business_policy_simulation(
        _session,
        *,
        business,
        end_week_start_date,
        week_count,
        proposed_business_compliance_settings,
    ):
        assert business.id == business_id
        assert end_week_start_date.isoformat() == "2026-04-20"
        assert week_count == 4
        assert proposed_business_compliance_settings == {
            "minimum_rest_hours": 12.0,
            "block_unresolved_premiums": True,
        }
        baseline = finance_reporting.BusinessComplianceTrendSnapshot(
            business_id=business_id,
            end_week_start_date=end_week_start_date,
            week_count=4,
            location_count=2,
            total_shift_count=40,
            total_assigned_shift_count=36,
            total_warning_assignment_count=6,
            total_blocked_assignment_count=2,
            total_unresolved_premium_assignment_count=1,
            total_override_applied_count=3,
            total_premium_cents=4200,
            top_warning_rule_codes=[],
            top_premium_rule_codes=[],
            top_unresolved_premium_rule_codes=[],
            weeks=[],
            locations=[
                finance_reporting.BusinessComplianceLocationTrendRow(
                    location_id=uuid4(),
                    location_name="Downtown",
                    total_shift_count=20,
                    total_assigned_shift_count=18,
                    total_warning_assignment_count=3,
                    total_blocked_assignment_count=1,
                    total_unresolved_premium_assignment_count=1,
                    total_override_applied_count=2,
                    total_premium_cents=2400,
                )
            ],
        )
        simulated = finance_reporting.BusinessComplianceTrendSnapshot(
            business_id=business_id,
            end_week_start_date=end_week_start_date,
            week_count=4,
            location_count=2,
            total_shift_count=40,
            total_assigned_shift_count=36,
            total_warning_assignment_count=8,
            total_blocked_assignment_count=5,
            total_unresolved_premium_assignment_count=2,
            total_override_applied_count=2,
            total_premium_cents=6100,
            top_warning_rule_codes=[],
            top_premium_rule_codes=[],
            top_unresolved_premium_rule_codes=[],
            weeks=[],
            locations=[
                finance_reporting.BusinessComplianceLocationTrendRow(
                    location_id=baseline.locations[0].location_id,
                    location_name="Downtown",
                    total_shift_count=20,
                    total_assigned_shift_count=18,
                    total_warning_assignment_count=5,
                    total_blocked_assignment_count=4,
                    total_unresolved_premium_assignment_count=1,
                    total_override_applied_count=1,
                    total_premium_cents=4300,
                )
            ],
        )
        return finance_reporting.BusinessCompliancePolicySimulation(
            business_id=business_id,
            end_week_start_date=end_week_start_date,
            week_count=4,
            location_count=2,
            baseline_business_compliance_policy_hash="business_preview_hash_1234567890",
            baseline_business_compliance_settings={
                "minimum_rest_hours": 10.0,
                "block_unresolved_premiums": False,
            },
            proposed_business_compliance_settings={
                "minimum_rest_hours": 12.0,
                "block_unresolved_premiums": True,
            },
            baseline=baseline,
            simulated=simulated,
            delta=finance_reporting.ComplianceTrendDeltaSummary(
                warning_assignment_count_delta=2,
                blocked_assignment_count_delta=3,
                unresolved_premium_assignment_count_delta=1,
                override_applied_count_delta=-1,
                premium_total_cents_delta=1900,
            ),
            week_deltas=[],
            location_deltas=[
                finance_reporting.BusinessComplianceLocationDeltaRow(
                    location_id=baseline.locations[0].location_id,
                    location_name="Downtown",
                    warning_assignment_count_delta=2,
                    blocked_assignment_count_delta=3,
                    unresolved_premium_assignment_count_delta=0,
                    override_applied_count_delta=-1,
                    premium_total_cents_delta=1900,
                )
            ],
        )

    monkeypatch.setattr(
        finance_reporting,
        "business_compliance_policy_simulation",
        fake_business_policy_simulation,
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/finance/compliance-trends/2026-04-20/simulate-policy",
            json={
                "week_count": 4,
                "compliance": {
                    "minimum_rest_hours": 12,
                    "block_unresolved_premiums": True,
                },
            },
        )
        assert response.status_code == 200
        payload = BusinessCompliancePolicySimulationRead.model_validate(response.json())
        assert payload.business_id == business_id
        assert payload.location_count == 2
        assert payload.baseline_business_compliance_policy_hash == "business_preview_hash_1234567890"
        assert payload.proposed_business_compliance_settings.minimum_rest_hours == 12
        assert payload.delta.blocked_assignment_count_delta == 3
        assert payload.location_deltas[0].location_name == "Downtown"
        assert payload.location_deltas[0].premium_total_cents_delta == 1900
    finally:
        app.dependency_overrides.clear()


def test_get_business_scheduled_policy_drift_returns_snapshot(monkeypatch):
    fake_session = FakeFinanceRouteSession()
    business_id = uuid4()
    fake_session.get_map[(Business, business_id)] = _make_business(
        business_id=business_id,
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    async def fake_scheduled_policy_drift(_session, *, business, start_week_date, week_count):
        assert business.id == business_id
        assert start_week_date.isoformat() == "2026-05-04"
        assert week_count == 4
        return finance_reporting.BusinessComplianceScheduledPolicyDrift(
            business_id=business_id,
            start_week_date=start_week_date,
            end_week_date=date(2026, 5, 25),
            week_count=4,
            location_count=2,
            activating_policy_versions=[
                finance_reporting.CompliancePolicyActivationRow(
                    policy_version_id=uuid4(),
                    policy_scope="business",
                    policy_hash="future_business_hash",
                    effective_at=datetime(2026, 5, 5, 15, 0, tzinfo=timezone.utc),
                )
            ],
            frozen_current=finance_reporting.BusinessComplianceTrendSnapshot(
                business_id=business_id,
                end_week_start_date=date(2026, 5, 25),
                week_count=4,
                location_count=2,
                total_shift_count=40,
                total_assigned_shift_count=36,
                total_warning_assignment_count=5,
                total_blocked_assignment_count=2,
                total_unresolved_premium_assignment_count=1,
                total_override_applied_count=2,
                total_premium_cents=3000,
                top_warning_rule_codes=[],
                top_premium_rule_codes=[],
                top_unresolved_premium_rule_codes=[],
                weeks=[],
                locations=[],
            ),
            scheduled=finance_reporting.BusinessComplianceTrendSnapshot(
                business_id=business_id,
                end_week_start_date=date(2026, 5, 25),
                week_count=4,
                location_count=2,
                total_shift_count=40,
                total_assigned_shift_count=36,
                total_warning_assignment_count=7,
                total_blocked_assignment_count=4,
                total_unresolved_premium_assignment_count=2,
                total_override_applied_count=3,
                total_premium_cents=4700,
                top_warning_rule_codes=[],
                top_premium_rule_codes=[],
                top_unresolved_premium_rule_codes=[],
                weeks=[],
                locations=[],
            ),
            delta=finance_reporting.ComplianceTrendDeltaSummary(
                warning_assignment_count_delta=2,
                blocked_assignment_count_delta=2,
                unresolved_premium_assignment_count_delta=1,
                override_applied_count_delta=1,
                premium_total_cents_delta=1700,
            ),
            week_deltas=[
                finance_reporting.ComplianceTrendDeltaRow(
                    week_start_date=start_week_date,
                    week_end_date=date(2026, 5, 10),
                    warning_assignment_count_delta=1,
                    blocked_assignment_count_delta=1,
                    unresolved_premium_assignment_count_delta=1,
                    override_applied_count_delta=0,
                    premium_total_cents_delta=600,
                )
            ],
            location_deltas=[
                finance_reporting.BusinessComplianceLocationDeltaRow(
                    location_id=uuid4(),
                    location_name="Downtown",
                    warning_assignment_count_delta=2,
                    blocked_assignment_count_delta=2,
                    unresolved_premium_assignment_count_delta=1,
                    override_applied_count_delta=1,
                    premium_total_cents_delta=1700,
                )
            ],
        )

    monkeypatch.setattr(
        finance_reporting,
        "business_compliance_scheduled_policy_drift",
        fake_scheduled_policy_drift,
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/finance/scheduled-policy-drift/2026-05-04",
            params={"week_count": 4},
        )
        assert response.status_code == 200
        payload = BusinessComplianceScheduledPolicyDriftRead.model_validate(response.json())
        assert payload.business_id == business_id
        assert payload.location_count == 2
        assert payload.delta.blocked_assignment_count_delta == 2
        assert payload.activating_policy_versions[0].policy_hash == "future_business_hash"
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
