from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.business import Business, Location, Role
from app.models.compliance import ComplianceOverrideArtifact
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee
from app.models.finance import BillingLedgerEntry, CostLedgerEntry
from app.services import finance_reporting
from app.services import settings as settings_service


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)

    def scalars(self):
        return self


class FakeFinanceSession:
    def __init__(self):
        self.get_map: dict[tuple[type, object], object] = {}
        self.scalar_queue: list[object] = []
        self.execute_queue: list[list[object]] = []

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return 0

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)


def test_micros_and_cents_helpers_round_consistently():
    assert finance_reporting.cents_to_micros(2000) == 20_000_000
    assert finance_reporting.micros_to_cents_rounded(4_100) == 0
    assert finance_reporting.micros_to_cents_rounded(15_000) == 2
    assert finance_reporting.micros_to_cents_rounded(-15_000) == -2


@pytest.mark.asyncio
async def test_campaign_cost_breakdown_groups_provider_and_product():
    session = FakeFinanceSession()
    coverage_case_id = uuid4()
    session.execute_queue = [[
        ("openai", "llm_generation", 4_100),
        ("retell", "voice_ai", 30_000),
    ]]

    rows = await finance_reporting.campaign_cost_breakdown(session, coverage_case_id)

    assert len(rows) == 2
    assert rows[0].provider == "openai"
    assert rows[0].product == "llm_generation"
    assert rows[0].total_cost_micros == 4_100
    assert rows[0].total_cost_cents_rounded == 0
    assert rows[1].provider == "retell"
    assert rows[1].product == "voice_ai"
    assert rows[1].total_cost_cents_rounded == 3


@pytest.mark.asyncio
async def test_campaign_economics_snapshot_combines_cost_and_billing_totals():
    session = FakeFinanceSession()
    coverage_case_id = uuid4()
    session.scalar_queue = [
        34_100,  # cost total micros
        2_000,   # billed cents
        2,       # cost entry count
        1,       # billing entry count
    ]

    snapshot = await finance_reporting.campaign_economics_snapshot(session, coverage_case_id)

    assert snapshot.coverage_case_id == coverage_case_id
    assert snapshot.total_cost_micros == 34_100
    assert snapshot.total_cost_cents_rounded == 3
    assert snapshot.total_billed_cents == 2_000
    assert snapshot.total_billed_micros == 20_000_000
    assert snapshot.gross_margin_micros == 19_965_900
    assert snapshot.gross_margin_cents_rounded == 1_997
    assert snapshot.cost_entry_count == 2
    assert snapshot.billed_entry_count == 1


@pytest.mark.asyncio
async def test_location_billing_cap_snapshot_uses_billing_decision():
    session = FakeFinanceSession()
    session.scalar_queue = [19_500]
    location_id = uuid4()
    occurred_at = datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc)

    snapshot = await finance_reporting.location_billing_cap_snapshot(
        session,
        location_id=location_id,
        occurred_at=occurred_at,
        timezone_name="America/Los_Angeles",
        fill_price_cents=2_000,
        monthly_cap_cents=20_000,
    )

    assert snapshot.location_id == location_id
    assert snapshot.billing_cycle_start == datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc)
    assert snapshot.billed_cents == 19_500
    assert snapshot.remaining_cents == 500
    assert snapshot.monthly_cap_cents == 20_000
    assert snapshot.fill_price_cents == 2_000
    assert snapshot.next_fill_charge_cents == 500
    assert snapshot.is_capped is False


@pytest.mark.asyncio
async def test_list_cost_entries_returns_newest_first():
    session = FakeFinanceSession()
    coverage_case_id = uuid4()
    newer_entry = CostLedgerEntry(
        id=uuid4(),
        coverage_case_id=coverage_case_id,
        provider="retell",
        product="voice_ai",
        reference_type="call",
        quantity=Decimal("1.000000"),
        unit_cost_micros=30_000,
        total_cost_micros=30_000,
        cost_metadata={},
        occurred_at=datetime(2026, 4, 10, 18, 5, tzinfo=timezone.utc),
        created_at=datetime(2026, 4, 10, 18, 5, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 10, 18, 5, tzinfo=timezone.utc),
    )
    older_entry = CostLedgerEntry(
        id=uuid4(),
        coverage_case_id=coverage_case_id,
        provider="openai",
        product="llm_generation",
        reference_type="llm_generation",
        quantity=Decimal("1.000000"),
        unit_cost_micros=4_100,
        total_cost_micros=4_100,
        cost_metadata={},
        occurred_at=datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc),
    )
    session.execute_queue = [[newer_entry, older_entry]]

    rows = await finance_reporting.list_cost_entries(session, coverage_case_id=coverage_case_id)

    assert rows == [newer_entry, older_entry]


@pytest.mark.asyncio
async def test_list_billing_entries_returns_newest_first():
    session = FakeFinanceSession()
    coverage_case_id = uuid4()
    newer_entry = BillingLedgerEntry(
        id=uuid4(),
        coverage_case_id=coverage_case_id,
        billing_event_type="fill_voided",
        billing_cycle_start=datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc),
        amount_cents=-2_000,
        cap_applied=False,
        billing_metadata={},
        occurred_at=datetime(2026, 4, 10, 19, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 4, 10, 19, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 10, 19, 0, tzinfo=timezone.utc),
    )
    older_entry = BillingLedgerEntry(
        id=uuid4(),
        coverage_case_id=coverage_case_id,
        billing_event_type="fill_charged",
        billing_cycle_start=datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc),
        amount_cents=2_000,
        cap_applied=False,
        billing_metadata={},
        occurred_at=datetime(2026, 4, 10, 18, 45, tzinfo=timezone.utc),
        created_at=datetime(2026, 4, 10, 18, 45, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 10, 18, 45, tzinfo=timezone.utc),
    )
    session.execute_queue = [[newer_entry, older_entry]]

    rows = await finance_reporting.list_billing_entries(session, coverage_case_id=coverage_case_id)

    assert rows == [newer_entry, older_entry]


@pytest.mark.asyncio
async def test_location_compliance_week_snapshot_aggregates_assignment_premiums_and_artifacts():
    session = FakeFinanceSession()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    shift_id = uuid4()
    artifact_id = uuid4()
    now = datetime(2026, 4, 8, 17, 0, tzinfo=timezone.utc)

    location = Location(
        id=location_id,
        business_id=uuid4(),
        name="Hollywood",
        display_name="Hollywood",
        slug="hollywood",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    role = Role(
        id=role_id,
        business_id=location.business_id,
        code="server",
        name="Server",
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=location.business_id,
        full_name="Taylor Server",
        status="active",
        created_at=now,
        updated_at=now,
    )
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift_id,
        employee_id=employee_id,
        status="accepted",
        assigned_via="manual",
        sequence_no=1,
        assignment_metadata={
            "employee_name": employee.full_name,
            "compliance_evaluation": {
                "status": "warning",
                "profile_code": "ca_restaurant_v1",
                "blocking_rule_codes": [],
                "warning_rule_codes": ["meal_break_missing"],
                "premium_rule_codes": ["meal_break_premium"],
                "premium_total_cents": 1845,
                "unresolved_premium_rule_codes": [],
                "override_applied": True,
                "override_artifact_id": str(artifact_id),
            },
        },
        created_at=now,
        updated_at=now,
    )
    assignment.employee = employee
    shift = Shift(
        id=shift_id,
        business_id=location.business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now,
        premium_cents=0,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.role = role
    shift.assignments = [assignment]
    artifact = ComplianceOverrideArtifact(
        id=artifact_id,
        business_id=location.business_id,
        location_id=location_id,
        shift_id=shift_id,
        employee_id=employee_id,
        rule_code="meal_break_missing",
        artifact_type="meal_waiver",
        status="approved",
        engine_version="compliance_v1",
        approved_at=now,
        reason_codes=[],
        artifact_payload={},
        created_at=now,
        updated_at=now,
    )
    artifact.employee = employee
    session.execute_queue = [[shift], [artifact]]

    snapshot = await finance_reporting.location_compliance_week_snapshot(
        session,
        location=location,
        week_start_date=now.date(),
    )

    assert snapshot.location_id == location_id
    assert snapshot.shift_count == 1
    assert snapshot.assigned_shift_count == 1
    assert snapshot.employee_count == 1
    assert snapshot.warning_assignment_count == 1
    assert snapshot.blocked_assignment_count == 0
    assert snapshot.unresolved_premium_assignment_count == 0
    assert snapshot.premium_total_cents == 1845
    assert snapshot.override_applied_count == 1
    assert snapshot.warning_rule_codes == ["meal_break_missing"]
    assert snapshot.premium_rule_codes == ["meal_break_premium"]
    assert snapshot.artifact_type_counts[0].artifact_type == "meal_waiver"
    assert snapshot.artifact_type_counts[0].count == 1
    assert snapshot.shifts[0].employee_name == "Taylor Server"
    assert snapshot.shifts[0].override_artifact_id == artifact_id
    assert snapshot.employees[0].premium_total_cents == 1845
    assert snapshot.override_artifacts[0].artifact_id == artifact_id
    assert snapshot.override_artifacts[0].employee_name == "Taylor Server"


@pytest.mark.asyncio
async def test_location_compliance_week_snapshot_falls_back_to_live_resolution_for_older_assignments(monkeypatch):
    session = FakeFinanceSession()
    location_id = uuid4()
    employee_id = uuid4()
    shift_id = uuid4()
    now = datetime(2026, 4, 8, 17, 0, tzinfo=timezone.utc)

    location = Location(
        id=location_id,
        business_id=uuid4(),
        name="Hollywood",
        display_name="Hollywood",
        slug="hollywood",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=location.business_id,
        full_name="Jordan Draft",
        status="active",
        created_at=now,
        updated_at=now,
    )
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift_id,
        employee_id=employee_id,
        status="accepted",
        assigned_via="manual",
        sequence_no=1,
        assignment_metadata={"employee_name": employee.full_name},
        created_at=now,
        updated_at=now,
    )
    assignment.employee = employee
    shift = Shift(
        id=shift_id,
        business_id=location.business_id,
        location_id=location_id,
        role_id=uuid4(),
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now,
        premium_cents=0,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.assignments = [assignment]
    session.execute_queue = [[shift]]

    from app.services import scheduling as scheduling_service

    async def fake_resolve_assignment_compliance(*_args, **_kwargs):
        return {}, {"status": "warning"}, object()

    def fake_compliance_metadata_for_assignment(_evaluation, *, override_artifact):
        assert override_artifact is not None
        return {
            "status": "warning",
            "blocking_rule_codes": [],
            "warning_rule_codes": ["rest_window"],
            "premium_rule_codes": [],
            "premium_total_cents": 0,
            "unresolved_premium_rule_codes": ["split_shift_premium"],
            "override_applied": False,
            "override_artifact_id": None,
            "profile_code": "ca_restaurant_v1",
        }

    monkeypatch.setattr(scheduling_service, "_resolve_assignment_compliance", fake_resolve_assignment_compliance)
    monkeypatch.setattr(
        scheduling_service,
        "_compliance_metadata_for_assignment",
        fake_compliance_metadata_for_assignment,
    )

    snapshot = await finance_reporting.location_compliance_week_snapshot(
        session,
        location=location,
        week_start_date=now.date(),
    )

    assert snapshot.warning_assignment_count == 1
    assert snapshot.unresolved_premium_assignment_count == 1
    assert snapshot.warning_rule_codes == ["rest_window"]
    assert snapshot.unresolved_premium_rule_codes == ["split_shift_premium"]


@pytest.mark.asyncio
async def test_location_compliance_payroll_export_builds_payroll_rows_from_week_snapshot(monkeypatch):
    location_id = uuid4()
    employee_id = uuid4()
    shift_id = uuid4()
    artifact_id = uuid4()
    week_start_date = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc).date()

    fake_snapshot = finance_reporting.LocationComplianceWeekSnapshot(
        location_id=location_id,
        week_start_date=week_start_date,
        week_end_date=week_start_date,
        shift_count=2,
        assigned_shift_count=2,
        employee_count=1,
        warning_assignment_count=1,
        blocked_assignment_count=0,
        unresolved_premium_assignment_count=1,
        premium_total_cents=2250,
        override_applied_count=1,
        warning_rule_codes=["meal_break_first_window"],
        premium_rule_codes=["meal_break_first_window"],
        unresolved_premium_rule_codes=["split_shift_premium"],
        artifact_type_counts=[],
        shifts=[
            finance_reporting.ComplianceWeekShiftRow(
                shift_id=shift_id,
                employee_id=employee_id,
                employee_name="Taylor Server",
                role_id=uuid4(),
                role_name="Server",
                starts_at=datetime(2026, 4, 7, 16, 0, tzinfo=timezone.utc),
                ends_at=datetime(2026, 4, 7, 23, 0, tzinfo=timezone.utc),
                compliance_status="warning",
                profile_code="ca_restaurant_v1",
                blocking_rule_codes=[],
                warning_rule_codes=["meal_break_first_window"],
                premium_rule_codes=["meal_break_first_window"],
                premium_total_cents=2250,
                unresolved_premium_rule_codes=["split_shift_premium"],
                override_applied=True,
                override_artifact_id=artifact_id,
                premium_components=[
                    {
                        "rule_code": "meal_break_first_window",
                        "premium_type": "fixed_cents",
                        "premium_cents": 2250,
                        "reason_codes": ["first_meal_break_missing"],
                    }
                ],
            ),
            finance_reporting.ComplianceWeekShiftRow(
                shift_id=uuid4(),
                employee_id=employee_id,
                employee_name="Taylor Server",
                role_id=uuid4(),
                role_name="Server",
                starts_at=datetime(2026, 4, 8, 16, 0, tzinfo=timezone.utc),
                ends_at=datetime(2026, 4, 8, 23, 0, tzinfo=timezone.utc),
                compliance_status="clear",
                profile_code="ca_restaurant_v1",
                blocking_rule_codes=[],
                warning_rule_codes=[],
                premium_rule_codes=[],
                premium_total_cents=0,
                unresolved_premium_rule_codes=[],
                override_applied=False,
                override_artifact_id=None,
            ),
        ],
        employees=[],
        override_artifacts=[
            finance_reporting.ComplianceOverrideArtifactSummaryRow(
                artifact_id=artifact_id,
                shift_id=shift_id,
                employee_id=employee_id,
                employee_name="Taylor Server",
                rule_code="meal_break_first_window",
                artifact_type="meal_waiver",
                approved_at=datetime(2026, 4, 7, 15, 0, tzinfo=timezone.utc),
                expires_at=None,
                note="Signed waiver on file",
            )
        ],
    )

    async def fake_location_compliance_week_snapshot(_session, *, location, week_start_date: date):
        assert location.id == location_id
        assert week_start_date == week_start_date_value
        return fake_snapshot

    week_start_date_value = week_start_date

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_week_snapshot",
        fake_location_compliance_week_snapshot,
    )

    class FakeLocation:
        id = location_id
        business_id = uuid4()

    session = FakeFinanceSession()
    session.get_map[(Business, FakeLocation.business_id)] = Business(
        id=FakeLocation.business_id,
        name="Backfill Foods",
        display_name="Backfill Foods",
        slug="backfill-foods",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={},
        created_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
    )
    session.get_map[(Employee, employee_id)] = Employee(
        id=employee_id,
        business_id=FakeLocation.business_id,
        employee_number="EMP-42",
        external_ref="toast-42",
        full_name="Taylor Server",
        status="active",
        created_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
    )
    export = await finance_reporting.location_compliance_payroll_export(
        session,
        location=FakeLocation(),
        week_start_date=week_start_date,
    )

    assert export.location_id == location_id
    assert export.provider_profile == "generic_csv_v1"
    assert export.row_count == 2
    assert export.premium_payment_row_count == 1
    assert export.manual_review_row_count == 1
    assert export.ready_adjustment_row_count == 1
    assert export.missing_employee_identifier_row_count == 0
    assert export.artifact_record_row_count == 0
    assert export.total_premium_cents == 2250
    assert export.rows[0].employee_name == "Taylor Server"
    assert export.rows[0].employee_number == "EMP-42"
    assert export.rows[0].external_ref == "toast-42"
    assert export.rows[0].employee_identifier == "EMP-42"
    assert export.rows[0].employee_identifier_type == "employee_number"
    assert export.rows[0].earning_code == "MEALPREM"
    assert export.rows[0].premium_payment_required is True
    assert export.rows[0].manual_review_required is False
    assert export.rows[0].override_artifact_type == "meal_waiver"
    assert export.rows[0].override_artifact_note == "Signed waiver on file"
    assert export.rows[0].rule_source_references[0]["rule_code"] == "meal_break_first_window"
    assert export.rows[0].rule_source_references[0]["source_kind"] == "labor_rule_profile"
    assert export.rows[1].payroll_row_kind == "manual_review"
    assert export.rows[1].unresolved_premium_rule_codes == ["split_shift_premium"]


@pytest.mark.asyncio
async def test_location_compliance_payroll_export_enforces_gusto_employee_number_requirement(monkeypatch):
    location_id = uuid4()
    employee_id = uuid4()
    shift_id = uuid4()
    week_start_date = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc).date()
    business_id = uuid4()

    fake_snapshot = finance_reporting.LocationComplianceWeekSnapshot(
        location_id=location_id,
        week_start_date=week_start_date,
        week_end_date=week_start_date,
        shift_count=1,
        assigned_shift_count=1,
        employee_count=1,
        warning_assignment_count=1,
        blocked_assignment_count=0,
        unresolved_premium_assignment_count=0,
        premium_total_cents=2250,
        override_applied_count=0,
        warning_rule_codes=["meal_break_first_window"],
        premium_rule_codes=["meal_break_first_window"],
        unresolved_premium_rule_codes=[],
        artifact_type_counts=[],
        shifts=[
            finance_reporting.ComplianceWeekShiftRow(
                shift_id=shift_id,
                employee_id=employee_id,
                employee_name="Taylor Server",
                role_id=uuid4(),
                role_name="Server",
                starts_at=datetime(2026, 4, 7, 16, 0, tzinfo=timezone.utc),
                ends_at=datetime(2026, 4, 7, 23, 0, tzinfo=timezone.utc),
                compliance_status="warning",
                profile_code="ca_restaurant_v1",
                blocking_rule_codes=[],
                warning_rule_codes=["meal_break_first_window"],
                premium_rule_codes=["meal_break_first_window"],
                premium_total_cents=2250,
                unresolved_premium_rule_codes=[],
                override_applied=False,
                override_artifact_id=None,
                premium_components=[
                    {
                        "rule_code": "meal_break_first_window",
                        "premium_type": "fixed_cents",
                        "premium_cents": 2250,
                        "reason_codes": ["first_meal_break_missing"],
                    }
                ],
            ),
        ],
        employees=[],
        override_artifacts=[],
    )

    async def fake_location_compliance_week_snapshot(_session, *, location, week_start_date: date):
        assert location.id == location_id
        assert week_start_date == expected_week_start_date
        return fake_snapshot

    expected_week_start_date = week_start_date

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_week_snapshot",
        fake_location_compliance_week_snapshot,
    )

    class FakeLocation:
        pass

    FakeLocation.id = location_id
    FakeLocation.business_id = business_id

    session = FakeFinanceSession()
    session.get_map[(Business, business_id)] = Business(
        id=business_id,
        name="Backfill Foods",
        display_name="Backfill Foods",
        slug="backfill-foods",
        timezone="America/Los_Angeles",
        status="active",
        settings={
            "compliance_payroll_export": {
                "provider_profile": "gusto_csv_v1",
                "employee_identifier_priority": ["external_ref", "employee_number"],
                "allow_internal_employee_id_fallback": True,
            }
        },
        place_metadata={},
        created_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
    )
    session.get_map[(Employee, employee_id)] = Employee(
        id=employee_id,
        business_id=business_id,
        employee_number=None,
        external_ref="toast-42",
        full_name="Taylor Server",
        status="active",
        created_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
    )

    export = await finance_reporting.location_compliance_payroll_export(
        session,
        location=FakeLocation(),
        week_start_date=week_start_date,
    )

    assert export.provider_profile == "gusto_csv_v1"
    assert export.premium_payment_row_count == 0
    assert export.ready_adjustment_row_count == 0
    assert export.manual_review_row_count == 1
    assert export.missing_employee_identifier_row_count == 1
    assert export.rows[0].payroll_row_kind == "manual_review"
    assert export.rows[0].source_reason_codes == [
        "first_meal_break_missing",
        "missing_employee_number",
    ]


@pytest.mark.asyncio
async def test_location_compliance_payroll_export_allows_quickbooks_external_reference(monkeypatch):
    location_id = uuid4()
    employee_id = uuid4()
    shift_id = uuid4()
    week_start_date = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc).date()
    business_id = uuid4()

    fake_snapshot = finance_reporting.LocationComplianceWeekSnapshot(
        location_id=location_id,
        week_start_date=week_start_date,
        week_end_date=week_start_date,
        shift_count=1,
        assigned_shift_count=1,
        employee_count=1,
        warning_assignment_count=1,
        blocked_assignment_count=0,
        unresolved_premium_assignment_count=0,
        premium_total_cents=2250,
        override_applied_count=0,
        warning_rule_codes=["meal_break_first_window"],
        premium_rule_codes=["meal_break_first_window"],
        unresolved_premium_rule_codes=[],
        artifact_type_counts=[],
        shifts=[
            finance_reporting.ComplianceWeekShiftRow(
                shift_id=shift_id,
                employee_id=employee_id,
                employee_name="Taylor Server",
                role_id=uuid4(),
                role_name="Server",
                starts_at=datetime(2026, 4, 7, 16, 0, tzinfo=timezone.utc),
                ends_at=datetime(2026, 4, 7, 23, 0, tzinfo=timezone.utc),
                compliance_status="warning",
                profile_code="ca_restaurant_v1",
                blocking_rule_codes=[],
                warning_rule_codes=["meal_break_first_window"],
                premium_rule_codes=["meal_break_first_window"],
                premium_total_cents=2250,
                unresolved_premium_rule_codes=[],
                override_applied=False,
                override_artifact_id=None,
                premium_components=[
                    {
                        "rule_code": "meal_break_first_window",
                        "premium_type": "fixed_cents",
                        "premium_cents": 2250,
                        "reason_codes": ["first_meal_break_missing"],
                    }
                ],
            ),
        ],
        employees=[],
        override_artifacts=[],
    )

    async def fake_location_compliance_week_snapshot(_session, *, location, week_start_date: date):
        assert location.id == location_id
        assert week_start_date == expected_week_start_date
        return fake_snapshot

    expected_week_start_date = week_start_date

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_week_snapshot",
        fake_location_compliance_week_snapshot,
    )

    class FakeLocation:
        pass

    FakeLocation.id = location_id
    FakeLocation.business_id = business_id

    session = FakeFinanceSession()
    session.get_map[(Business, business_id)] = Business(
        id=business_id,
        name="Backfill Foods",
        display_name="Backfill Foods",
        slug="backfill-foods",
        timezone="America/Los_Angeles",
        status="active",
        settings={
            "compliance_payroll_export": {
                "provider_profile": "quickbooks_csv_v1",
                "employee_identifier_priority": ["employee_number", "external_ref"],
                "allow_internal_employee_id_fallback": False,
            }
        },
        place_metadata={},
        created_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
    )
    session.get_map[(Employee, employee_id)] = Employee(
        id=employee_id,
        business_id=business_id,
        employee_number=None,
        external_ref="toast-42",
        full_name="Taylor Server",
        status="active",
        created_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
    )

    export = await finance_reporting.location_compliance_payroll_export(
        session,
        location=FakeLocation(),
        week_start_date=week_start_date,
    )

    assert export.provider_profile == "quickbooks_csv_v1"
    assert export.premium_payment_row_count == 1
    assert export.ready_adjustment_row_count == 1
    assert export.manual_review_row_count == 0
    assert export.missing_employee_identifier_row_count == 0
    assert export.rows[0].payroll_row_kind == "premium_payment"
    assert export.rows[0].employee_number is None
    assert export.rows[0].external_ref == "toast-42"
    assert export.rows[0].rule_source_references[0]["rule_code"] == "meal_break_first_window"


@pytest.mark.asyncio
async def test_business_compliance_policy_simulation_aggregates_location_impacts(monkeypatch):
    session = FakeFinanceSession()
    business_id = uuid4()
    now = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
    business = Business(
        id=business_id,
        name="Backfill Foods",
        display_name="Backfill Foods",
        slug="backfill-foods",
        timezone="America/Los_Angeles",
        status="active",
        settings={"compliance": {"minimum_rest_hours": 10}},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )
    location_a = Location(
        id=uuid4(),
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    location_b = Location(
        id=uuid4(),
        business_id=business_id,
        name="Midtown",
        display_name="Midtown",
        slug="midtown",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    session.execute_queue = [
        [location_a, location_b],
        [location_a, location_b],
    ]
    baseline_rows = {
        (location_a.id, date(2026, 4, 13)): {"shift_count": 3, "blocked": 0, "premium": 100, "warning": 1},
        (location_a.id, date(2026, 4, 20)): {"shift_count": 4, "blocked": 1, "premium": 200, "warning": 1},
        (location_b.id, date(2026, 4, 13)): {"shift_count": 2, "blocked": 0, "premium": 50, "warning": 0},
        (location_b.id, date(2026, 4, 20)): {"shift_count": 3, "blocked": 0, "premium": 75, "warning": 1},
    }
    simulated_rows = {
        (location_a.id, date(2026, 4, 13)): {"shift_count": 3, "blocked": 1, "premium": 350, "warning": 2},
        (location_a.id, date(2026, 4, 20)): {"shift_count": 4, "blocked": 2, "premium": 500, "warning": 2},
        (location_b.id, date(2026, 4, 13)): {"shift_count": 2, "blocked": 0, "premium": 50, "warning": 0},
        (location_b.id, date(2026, 4, 20)): {"shift_count": 3, "blocked": 0, "premium": 75, "warning": 1},
    }

    async def fake_location_week_snapshot(
        _session,
        *,
        location,
        week_start_date,
        business_settings_override=None,
        force_recompute=False,
        **_kwargs,
    ):
        rows = simulated_rows if business_settings_override else baseline_rows
        source = rows[(location.id, week_start_date)]
        return finance_reporting.LocationComplianceWeekSnapshot(
            location_id=location.id,
            week_start_date=week_start_date,
            week_end_date=week_start_date + finance_reporting.timedelta(days=6),
            shift_count=source["shift_count"],
            assigned_shift_count=source["shift_count"],
            employee_count=1,
            warning_assignment_count=source["warning"],
            blocked_assignment_count=source["blocked"],
            unresolved_premium_assignment_count=0,
            premium_total_cents=source["premium"],
            override_applied_count=0,
            warning_rule_codes=["meal_break_missing"] if source["warning"] else [],
            premium_rule_codes=["meal_break_premium"] if source["premium"] else [],
            unresolved_premium_rule_codes=[],
            artifact_type_counts=[],
            shifts=[],
            employees=[],
            override_artifacts=[],
        )

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_week_snapshot",
        fake_location_week_snapshot,
    )

    simulation = await finance_reporting.business_compliance_policy_simulation(
        session,
        business=business,
        end_week_start_date=date(2026, 4, 20),
        week_count=2,
        proposed_business_compliance_settings={
            "minimum_rest_hours": 12,
            "require_structured_break_plans": True,
        },
    )

    assert simulation.business_id == business_id
    assert simulation.location_count == 2
    assert simulation.baseline_business_compliance_policy_hash == finance_reporting.settings_service.compliance_policy_hash(
        {"minimum_rest_hours": 10}
    )
    assert simulation.baseline.total_premium_cents == 425
    assert simulation.simulated.total_premium_cents == 975
    assert simulation.delta.blocked_assignment_count_delta == 2
    assert simulation.delta.premium_total_cents_delta == 550
    assert simulation.location_deltas[0].location_name == "Downtown"
    assert simulation.location_deltas[0].blocked_assignment_count_delta == 2
    assert simulation.location_deltas[0].premium_total_cents_delta == 550


@pytest.mark.asyncio
async def test_location_compliance_trend_snapshot_aggregates_recent_weeks(monkeypatch):
    location_id = uuid4()
    end_week_start_date = date(2026, 4, 20)
    week_snapshots = {
        date(2026, 4, 6): finance_reporting.LocationComplianceWeekSnapshot(
            location_id=location_id,
            week_start_date=date(2026, 4, 6),
            week_end_date=date(2026, 4, 12),
            shift_count=4,
            assigned_shift_count=3,
            employee_count=2,
            warning_assignment_count=1,
            blocked_assignment_count=0,
            unresolved_premium_assignment_count=1,
            premium_total_cents=1000,
            override_applied_count=1,
            warning_rule_codes=["meal_break_first_window"],
            premium_rule_codes=["meal_break_premium"],
            unresolved_premium_rule_codes=["split_shift_premium"],
            artifact_type_counts=[],
            shifts=[],
            employees=[],
            override_artifacts=[],
        ),
        date(2026, 4, 13): finance_reporting.LocationComplianceWeekSnapshot(
            location_id=location_id,
            week_start_date=date(2026, 4, 13),
            week_end_date=date(2026, 4, 19),
            shift_count=5,
            assigned_shift_count=4,
            employee_count=3,
            warning_assignment_count=2,
            blocked_assignment_count=1,
            unresolved_premium_assignment_count=0,
            premium_total_cents=2450,
            override_applied_count=2,
            warning_rule_codes=["meal_break_first_window", "rest_break_missing"],
            premium_rule_codes=["meal_break_premium"],
            unresolved_premium_rule_codes=[],
            artifact_type_counts=[],
            shifts=[],
            employees=[],
            override_artifacts=[],
        ),
        date(2026, 4, 20): finance_reporting.LocationComplianceWeekSnapshot(
            location_id=location_id,
            week_start_date=date(2026, 4, 20),
            week_end_date=date(2026, 4, 26),
            shift_count=6,
            assigned_shift_count=5,
            employee_count=3,
            warning_assignment_count=1,
            blocked_assignment_count=2,
            unresolved_premium_assignment_count=2,
            premium_total_cents=3150,
            override_applied_count=1,
            warning_rule_codes=["rest_break_missing"],
            premium_rule_codes=["meal_break_premium", "split_shift_premium"],
            unresolved_premium_rule_codes=["split_shift_premium"],
            artifact_type_counts=[],
            shifts=[],
            employees=[],
            override_artifacts=[],
        ),
    }

    async def fake_location_compliance_week_snapshot(_session, *, location, week_start_date: date):
        assert location.id == location_id
        return week_snapshots[week_start_date]

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_week_snapshot",
        fake_location_compliance_week_snapshot,
    )

    class FakeLocation:
        id = location_id

    trend = await finance_reporting.location_compliance_trend_snapshot(
        FakeFinanceSession(),
        location=FakeLocation(),
        end_week_start_date=end_week_start_date,
        week_count=3,
    )

    assert trend.location_id == location_id
    assert trend.start_week_date == date(2026, 4, 6)
    assert trend.end_week_date == end_week_start_date
    assert trend.week_count == 3
    assert trend.total_shift_count == 15
    assert trend.total_assigned_shift_count == 12
    assert trend.total_warning_assignment_count == 4
    assert trend.total_blocked_assignment_count == 3
    assert trend.total_unresolved_premium_assignment_count == 3
    assert trend.total_override_applied_count == 4
    assert trend.total_premium_cents == 6600
    assert [row.week_start_date for row in trend.weeks] == [
        date(2026, 4, 6),
        date(2026, 4, 13),
        date(2026, 4, 20),
    ]
    assert trend.top_warning_rule_codes[0].rule_code == "meal_break_first_window"
    assert trend.top_warning_rule_codes[0].count == 2
    assert trend.top_premium_rule_codes[0].rule_code == "meal_break_premium"
    assert trend.top_premium_rule_codes[0].count == 3
    assert trend.top_unresolved_premium_rule_codes[0].rule_code == "split_shift_premium"
    assert trend.top_unresolved_premium_rule_codes[0].count == 2


@pytest.mark.asyncio
async def test_location_compliance_policy_simulation_returns_baseline_simulated_and_deltas(monkeypatch):
    location_id = uuid4()
    end_week_start_date = date(2026, 4, 20)
    baseline = finance_reporting.LocationComplianceTrendSnapshot(
        location_id=location_id,
        start_week_date=date(2026, 4, 13),
        end_week_date=end_week_start_date,
        week_count=2,
        total_shift_count=10,
        total_assigned_shift_count=8,
        total_warning_assignment_count=3,
        total_blocked_assignment_count=1,
        total_unresolved_premium_assignment_count=1,
        total_override_applied_count=2,
        total_premium_cents=2800,
        top_warning_rule_codes=[],
        top_premium_rule_codes=[],
        top_unresolved_premium_rule_codes=[],
        weeks=[
            finance_reporting.ComplianceTrendWeekRow(
                week_start_date=date(2026, 4, 13),
                week_end_date=date(2026, 4, 19),
                shift_count=5,
                assigned_shift_count=4,
                warning_assignment_count=1,
                blocked_assignment_count=0,
                unresolved_premium_assignment_count=0,
                premium_total_cents=1200,
                override_applied_count=1,
            ),
            finance_reporting.ComplianceTrendWeekRow(
                week_start_date=date(2026, 4, 20),
                week_end_date=date(2026, 4, 26),
                shift_count=5,
                assigned_shift_count=4,
                warning_assignment_count=2,
                blocked_assignment_count=1,
                unresolved_premium_assignment_count=1,
                premium_total_cents=1600,
                override_applied_count=1,
            ),
        ],
    )
    simulated = finance_reporting.LocationComplianceTrendSnapshot(
        location_id=location_id,
        start_week_date=date(2026, 4, 13),
        end_week_date=end_week_start_date,
        week_count=2,
        total_shift_count=10,
        total_assigned_shift_count=8,
        total_warning_assignment_count=5,
        total_blocked_assignment_count=3,
        total_unresolved_premium_assignment_count=2,
        total_override_applied_count=1,
        total_premium_cents=4600,
        top_warning_rule_codes=[],
        top_premium_rule_codes=[],
        top_unresolved_premium_rule_codes=[],
        weeks=[
            finance_reporting.ComplianceTrendWeekRow(
                week_start_date=date(2026, 4, 13),
                week_end_date=date(2026, 4, 19),
                shift_count=5,
                assigned_shift_count=4,
                warning_assignment_count=2,
                blocked_assignment_count=1,
                unresolved_premium_assignment_count=1,
                premium_total_cents=1900,
                override_applied_count=1,
            ),
            finance_reporting.ComplianceTrendWeekRow(
                week_start_date=date(2026, 4, 20),
                week_end_date=date(2026, 4, 26),
                shift_count=5,
                assigned_shift_count=4,
                warning_assignment_count=3,
                blocked_assignment_count=2,
                unresolved_premium_assignment_count=1,
                premium_total_cents=2700,
                override_applied_count=0,
            ),
        ],
    )
    observed_location_overrides: list[dict[str, object] | None] = []

    async def fake_location_compliance_trend_snapshot(
        _session,
        *,
        location,
        end_week_start_date: date,
        week_count: int,
        location_settings_override=None,
        force_recompute=False,
        **_kwargs,
    ):
        assert location.id == location_id
        assert end_week_start_date == date(2026, 4, 20)
        assert week_count == 2
        observed_location_overrides.append(
            dict(location_settings_override) if location_settings_override is not None else None
        )
        if force_recompute:
            return simulated
        return baseline

    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_trend_snapshot",
        fake_location_compliance_trend_snapshot,
    )

    class FakeLocation:
        id = location_id
        settings = {
            "compliance": {
                "minimum_rest_hours": 10,
                "block_unresolved_premiums": True,
            }
        }

    result = await finance_reporting.location_compliance_policy_simulation(
        FakeFinanceSession(),
        location=FakeLocation(),
        end_week_start_date=end_week_start_date,
        week_count=2,
        proposed_location_compliance_settings={
            "minimum_rest_hours": 12,
            "block_unresolved_premiums": True,
        },
    )

    assert observed_location_overrides == [
        None,
        {"minimum_rest_hours": 12, "block_unresolved_premiums": True},
    ]
    assert result.location_id == location_id
    assert result.baseline_location_compliance_settings["minimum_rest_hours"] == 10
    assert result.baseline_location_compliance_settings["block_unresolved_premiums"] is True
    assert isinstance(result.baseline_location_compliance_policy_hash, str)
    assert result.baseline_location_compliance_policy_hash
    assert result.delta.warning_assignment_count_delta == 2
    assert result.delta.blocked_assignment_count_delta == 2
    assert result.delta.unresolved_premium_assignment_count_delta == 1
    assert result.delta.override_applied_count_delta == -1
    assert result.delta.premium_total_cents_delta == 1800
    assert result.week_deltas[0].premium_total_cents_delta == 700
    assert result.week_deltas[1].blocked_assignment_count_delta == 1


@pytest.mark.asyncio
async def test_location_compliance_week_policy_replay_uses_selected_policy_version(monkeypatch):
    session = FakeFinanceSession()
    business_id = uuid4()
    location_id = uuid4()
    version_id = uuid4()
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    version = finance_reporting.CompliancePolicyVersion(
        id=version_id,
        business_id=business_id,
        location_id=location_id,
        policy_scope="location",
        policy_hash="hash_replay_loc",
        settings_payload={
            "minimum_rest_hours": 12,
            "written_consent_allowed": None,
            "first_meal_waiver_allowed": None,
            "second_meal_waiver_allowed": None,
            "require_structured_break_plans": True,
            "block_unresolved_premiums": False,
            "max_daily_minutes": None,
            "max_weekly_minutes": None,
        },
        effective_at=now,
        superseded_at=None,
        created_at=now,
        updated_at=now,
    )
    session.get_map[(finance_reporting.CompliancePolicyVersion, version_id)] = version

    async def fake_week_snapshot(
        _session,
        *,
        location,
        week_start_date,
        location_settings_override=None,
        force_recompute=False,
        **_kwargs,
    ):
        if force_recompute:
            assert isinstance(location_settings_override, dict)
            assert location_settings_override["compliance_policy_version_id"] == str(version_id)
            return finance_reporting.LocationComplianceWeekSnapshot(
                location_id=location.id,
                week_start_date=week_start_date,
                week_end_date=week_start_date,
                shift_count=3,
                assigned_shift_count=3,
                employee_count=2,
                warning_assignment_count=2,
                blocked_assignment_count=1,
                unresolved_premium_assignment_count=1,
                premium_total_cents=1700,
                override_applied_count=0,
                warning_rule_codes=[],
                premium_rule_codes=[],
                unresolved_premium_rule_codes=[],
                artifact_type_counts=[],
                shifts=[],
                employees=[],
                override_artifacts=[],
            )
        return finance_reporting.LocationComplianceWeekSnapshot(
            location_id=location.id,
            week_start_date=week_start_date,
            week_end_date=week_start_date,
            shift_count=3,
            assigned_shift_count=3,
            employee_count=2,
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

    monkeypatch.setattr(finance_reporting, "location_compliance_week_snapshot", fake_week_snapshot)

    replay = await finance_reporting.location_compliance_week_policy_replay(
        session,
        location=location,
        week_start_date=date(2026, 4, 20),
        policy_version_id=version_id,
    )

    assert replay.location_id == location_id
    assert replay.replay_policy_version_id == version_id
    assert replay.replay_policy_scope == "location"
    assert replay.replay_policy_hash == "hash_replay_loc"
    assert replay.delta.blocked_assignment_count_delta == 1
    assert replay.delta.warning_assignment_count_delta == 1
    assert replay.delta.premium_total_cents_delta == 500


@pytest.mark.asyncio
async def test_location_compliance_scheduled_policy_drift_compares_frozen_and_scheduled_trends(monkeypatch):
    session = FakeFinanceSession()
    business_id = uuid4()
    location_id = uuid4()
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    business = Business(
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
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    location.business = business
    start_week_date = date(2026, 5, 4)
    trend_calls: list[dict[str, object]] = []

    async def fake_effective_business_settings_payload(_session, *, business, as_of):
        assert business.id == business_id
        assert as_of.tzinfo is not None
        return {
            "compliance": {"minimum_rest_hours": 10},
            "compliance_policy_hash": "business_hash_frozen",
        }

    async def fake_effective_location_settings_payload(_session, *, business, location, as_of):
        assert business.id == business_id
        assert location.id == location_id
        assert as_of.tzinfo is not None
        return {
            "compliance": {"minimum_rest_hours": 10, "require_structured_break_plans": False},
            "compliance_policy_hash": "location_hash_frozen",
            "compliance_policy_scope": "location",
        }

    async def fake_location_compliance_trend_snapshot(
        _session,
        *,
        location,
        end_week_start_date,
        week_count,
        business_settings_override=None,
        location_settings_override=None,
        force_recompute=False,
    ):
        trend_calls.append(
            {
                "location_id": location.id,
                "end_week_start_date": end_week_start_date,
                "week_count": week_count,
                "force_recompute": force_recompute,
                "business_settings_override": business_settings_override,
                "location_settings_override": location_settings_override,
            }
        )
        if force_recompute:
            return finance_reporting.LocationComplianceTrendSnapshot(
                location_id=location.id,
                start_week_date=start_week_date,
                end_week_date=end_week_start_date,
                week_count=week_count,
                total_shift_count=14,
                total_assigned_shift_count=12,
                total_warning_assignment_count=3,
                total_blocked_assignment_count=1,
                total_unresolved_premium_assignment_count=1,
                total_override_applied_count=1,
                total_premium_cents=1500,
                top_warning_rule_codes=[],
                top_premium_rule_codes=[],
                top_unresolved_premium_rule_codes=[],
                weeks=[
                    finance_reporting.ComplianceTrendWeekRow(
                        week_start_date=start_week_date,
                        week_end_date=start_week_date + timedelta(days=6),
                        shift_count=7,
                        assigned_shift_count=6,
                        warning_assignment_count=1,
                        blocked_assignment_count=0,
                        unresolved_premium_assignment_count=0,
                        premium_total_cents=500,
                        override_applied_count=1,
                    ),
                    finance_reporting.ComplianceTrendWeekRow(
                        week_start_date=start_week_date + timedelta(days=7),
                        week_end_date=start_week_date + timedelta(days=13),
                        shift_count=7,
                        assigned_shift_count=6,
                        warning_assignment_count=2,
                        blocked_assignment_count=1,
                        unresolved_premium_assignment_count=1,
                        premium_total_cents=1000,
                        override_applied_count=0,
                    ),
                ],
            )
        return finance_reporting.LocationComplianceTrendSnapshot(
            location_id=location.id,
            start_week_date=start_week_date,
            end_week_date=end_week_start_date,
            week_count=week_count,
            total_shift_count=14,
            total_assigned_shift_count=12,
            total_warning_assignment_count=6,
            total_blocked_assignment_count=3,
            total_unresolved_premium_assignment_count=2,
            total_override_applied_count=2,
            total_premium_cents=2400,
            top_warning_rule_codes=[],
            top_premium_rule_codes=[],
            top_unresolved_premium_rule_codes=[],
            weeks=[
                finance_reporting.ComplianceTrendWeekRow(
                    week_start_date=start_week_date,
                    week_end_date=start_week_date + timedelta(days=6),
                    shift_count=7,
                    assigned_shift_count=6,
                    warning_assignment_count=2,
                    blocked_assignment_count=1,
                    unresolved_premium_assignment_count=0,
                    premium_total_cents=900,
                    override_applied_count=1,
                ),
                finance_reporting.ComplianceTrendWeekRow(
                    week_start_date=start_week_date + timedelta(days=7),
                    week_end_date=start_week_date + timedelta(days=13),
                    shift_count=7,
                    assigned_shift_count=6,
                    warning_assignment_count=4,
                    blocked_assignment_count=2,
                    unresolved_premium_assignment_count=2,
                    premium_total_cents=1500,
                    override_applied_count=1,
                ),
            ],
        )

    async def fake_scheduled_policy_versions_for_window(
        _session,
        *,
        business_id,
        window_end_at,
        reference_time,
        location_id=None,
    ):
        assert business_id == location.business_id
        assert location_id == location.id
        assert reference_time.tzinfo is not None
        assert window_end_at > reference_time
        return [
            finance_reporting.CompliancePolicyActivationRow(
                policy_version_id=uuid4(),
                policy_scope="business",
                policy_hash="business_future_hash",
                effective_at=datetime(2026, 5, 6, 15, 0, tzinfo=timezone.utc),
            )
        ]

    monkeypatch.setattr(
        settings_service,
        "effective_business_settings_payload",
        fake_effective_business_settings_payload,
    )
    monkeypatch.setattr(
        settings_service,
        "effective_location_settings_payload",
        fake_effective_location_settings_payload,
    )
    monkeypatch.setattr(
        finance_reporting,
        "location_compliance_trend_snapshot",
        fake_location_compliance_trend_snapshot,
    )
    monkeypatch.setattr(
        finance_reporting,
        "_scheduled_policy_versions_for_window",
        fake_scheduled_policy_versions_for_window,
    )

    result = await finance_reporting.location_compliance_scheduled_policy_drift(
        session,
        location=location,
        start_week_date=start_week_date,
        week_count=2,
    )

    assert result.location_id == location_id
    assert result.week_count == 2
    assert result.delta.warning_assignment_count_delta == 3
    assert result.delta.blocked_assignment_count_delta == 2
    assert result.delta.unresolved_premium_assignment_count_delta == 1
    assert result.delta.override_applied_count_delta == 1
    assert result.delta.premium_total_cents_delta == 900
    assert result.week_deltas[0].blocked_assignment_count_delta == 1
    assert result.week_deltas[0].premium_total_cents_delta == 400
    assert result.week_deltas[1].warning_assignment_count_delta == 2
    assert result.activating_policy_versions[0].policy_hash == "business_future_hash"
    assert trend_calls[0]["force_recompute"] is True
    assert trend_calls[1]["force_recompute"] is False
    assert trend_calls[0]["location_settings_override"] == {
        "compliance": {"minimum_rest_hours": 10, "require_structured_break_plans": False},
        "compliance_policy_hash": "location_hash_frozen",
        "compliance_policy_scope": "location",
    }


@pytest.mark.asyncio
async def test_business_compliance_scheduled_policy_drift_compares_frozen_and_scheduled_trends(monkeypatch):
    session = FakeFinanceSession()
    business_id = uuid4()
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    business = Business(
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
    location_a = Location(
        id=uuid4(),
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    location_b = Location(
        id=uuid4(),
        business_id=business_id,
        name="Santa Monica",
        display_name="Santa Monica",
        slug="santa-monica",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    start_week_date = date(2026, 5, 4)
    trend_calls: list[dict[str, object]] = []

    async def fake_active_business_locations(_session, *, business_id):
        assert business_id == business.id
        return [location_a, location_b]

    async def fake_effective_business_settings_payload(_session, *, business, as_of):
        assert business.id == business_id
        assert as_of.tzinfo is not None
        return {
            "compliance": {"minimum_rest_hours": 10},
            "compliance_policy_hash": "business_hash_frozen",
        }

    async def fake_effective_location_settings_payload(_session, *, business, location, as_of):
        assert business.id == business_id
        assert as_of.tzinfo is not None
        return {
            "compliance": {
                "minimum_rest_hours": 10,
                "require_structured_break_plans": location.id == location_b.id,
            },
            "compliance_policy_hash": f"location_hash_{location.id}",
            "compliance_policy_scope": "location",
        }

    async def fake_business_compliance_trend_snapshot(
        _session,
        *,
        business,
        end_week_start_date,
        week_count,
        business_settings_override=None,
        location_settings_overrides_by_id=None,
        force_recompute=False,
    ):
        trend_calls.append(
            {
                "business_id": business.id,
                "end_week_start_date": end_week_start_date,
                "week_count": week_count,
                "force_recompute": force_recompute,
                "business_settings_override": business_settings_override,
                "location_settings_overrides_by_id": location_settings_overrides_by_id,
            }
        )
        if force_recompute:
            return finance_reporting.BusinessComplianceTrendSnapshot(
                business_id=business.id,
                end_week_start_date=end_week_start_date,
                week_count=week_count,
                location_count=2,
                total_shift_count=20,
                total_assigned_shift_count=18,
                total_warning_assignment_count=4,
                total_blocked_assignment_count=1,
                total_unresolved_premium_assignment_count=1,
                total_override_applied_count=2,
                total_premium_cents=1800,
                top_warning_rule_codes=[],
                top_premium_rule_codes=[],
                top_unresolved_premium_rule_codes=[],
                weeks=[
                    finance_reporting.ComplianceTrendWeekRow(
                        week_start_date=start_week_date,
                        week_end_date=start_week_date + timedelta(days=6),
                        shift_count=10,
                        assigned_shift_count=9,
                        warning_assignment_count=2,
                        blocked_assignment_count=1,
                        unresolved_premium_assignment_count=1,
                        premium_total_cents=900,
                        override_applied_count=1,
                    ),
                    finance_reporting.ComplianceTrendWeekRow(
                        week_start_date=start_week_date + timedelta(days=7),
                        week_end_date=start_week_date + timedelta(days=13),
                        shift_count=10,
                        assigned_shift_count=9,
                        warning_assignment_count=2,
                        blocked_assignment_count=0,
                        unresolved_premium_assignment_count=0,
                        premium_total_cents=900,
                        override_applied_count=1,
                    ),
                ],
                locations=[
                    finance_reporting.BusinessComplianceLocationTrendRow(
                        location_id=location_a.id,
                        location_name="Downtown",
                        total_shift_count=10,
                        total_assigned_shift_count=9,
                        total_warning_assignment_count=1,
                        total_blocked_assignment_count=0,
                        total_unresolved_premium_assignment_count=0,
                        total_override_applied_count=1,
                        total_premium_cents=600,
                    ),
                    finance_reporting.BusinessComplianceLocationTrendRow(
                        location_id=location_b.id,
                        location_name="Santa Monica",
                        total_shift_count=10,
                        total_assigned_shift_count=9,
                        total_warning_assignment_count=3,
                        total_blocked_assignment_count=1,
                        total_unresolved_premium_assignment_count=1,
                        total_override_applied_count=1,
                        total_premium_cents=1200,
                    ),
                ],
            )
        return finance_reporting.BusinessComplianceTrendSnapshot(
            business_id=business.id,
            end_week_start_date=end_week_start_date,
            week_count=week_count,
            location_count=2,
            total_shift_count=20,
            total_assigned_shift_count=18,
            total_warning_assignment_count=7,
            total_blocked_assignment_count=3,
            total_unresolved_premium_assignment_count=2,
            total_override_applied_count=3,
            total_premium_cents=3100,
            top_warning_rule_codes=[],
            top_premium_rule_codes=[],
            top_unresolved_premium_rule_codes=[],
            weeks=[
                finance_reporting.ComplianceTrendWeekRow(
                    week_start_date=start_week_date,
                    week_end_date=start_week_date + timedelta(days=6),
                    shift_count=10,
                    assigned_shift_count=9,
                    warning_assignment_count=3,
                    blocked_assignment_count=2,
                    unresolved_premium_assignment_count=1,
                    premium_total_cents=1400,
                    override_applied_count=1,
                ),
                finance_reporting.ComplianceTrendWeekRow(
                    week_start_date=start_week_date + timedelta(days=7),
                    week_end_date=start_week_date + timedelta(days=13),
                    shift_count=10,
                    assigned_shift_count=9,
                    warning_assignment_count=4,
                    blocked_assignment_count=1,
                    unresolved_premium_assignment_count=1,
                    premium_total_cents=1700,
                    override_applied_count=2,
                ),
            ],
            locations=[
                finance_reporting.BusinessComplianceLocationTrendRow(
                    location_id=location_a.id,
                    location_name="Downtown",
                    total_shift_count=10,
                    total_assigned_shift_count=9,
                    total_warning_assignment_count=4,
                    total_blocked_assignment_count=2,
                    total_unresolved_premium_assignment_count=1,
                    total_override_applied_count=2,
                    total_premium_cents=2200,
                ),
                finance_reporting.BusinessComplianceLocationTrendRow(
                    location_id=location_b.id,
                    location_name="Santa Monica",
                    total_shift_count=10,
                    total_assigned_shift_count=9,
                    total_warning_assignment_count=3,
                    total_blocked_assignment_count=1,
                    total_unresolved_premium_assignment_count=1,
                    total_override_applied_count=1,
                    total_premium_cents=900,
                ),
            ],
        )

    async def fake_scheduled_policy_versions_for_window(
        _session,
        *,
        business_id,
        window_end_at,
        reference_time,
        location_id=None,
    ):
        assert business_id == business.id
        assert location_id is None
        assert reference_time.tzinfo is not None
        assert window_end_at > reference_time
        return [
            finance_reporting.CompliancePolicyActivationRow(
                policy_version_id=uuid4(),
                policy_scope="business",
                policy_hash="business_future_hash",
                effective_at=datetime(2026, 5, 10, 15, 0, tzinfo=timezone.utc),
            ),
            finance_reporting.CompliancePolicyActivationRow(
                policy_version_id=uuid4(),
                policy_scope="location",
                policy_hash="location_future_hash",
                effective_at=datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc),
                location_id=location_b.id,
                location_name="Santa Monica",
            ),
        ]

    monkeypatch.setattr(
        finance_reporting,
        "_active_business_locations",
        fake_active_business_locations,
    )
    monkeypatch.setattr(
        settings_service,
        "effective_business_settings_payload",
        fake_effective_business_settings_payload,
    )
    monkeypatch.setattr(
        settings_service,
        "effective_location_settings_payload",
        fake_effective_location_settings_payload,
    )
    monkeypatch.setattr(
        finance_reporting,
        "business_compliance_trend_snapshot",
        fake_business_compliance_trend_snapshot,
    )
    monkeypatch.setattr(
        finance_reporting,
        "_scheduled_policy_versions_for_window",
        fake_scheduled_policy_versions_for_window,
    )

    result = await finance_reporting.business_compliance_scheduled_policy_drift(
        session,
        business=business,
        start_week_date=start_week_date,
        week_count=2,
    )

    assert result.business_id == business_id
    assert result.location_count == 2
    assert result.delta.warning_assignment_count_delta == 3
    assert result.delta.blocked_assignment_count_delta == 2
    assert result.delta.unresolved_premium_assignment_count_delta == 1
    assert result.delta.override_applied_count_delta == 1
    assert result.delta.premium_total_cents_delta == 1300
    assert result.week_deltas[0].premium_total_cents_delta == 500
    assert result.location_deltas[0].location_name == "Downtown"
    assert result.location_deltas[0].premium_total_cents_delta == 1600
    assert result.location_deltas[1].location_name == "Santa Monica"
    assert result.location_deltas[1].premium_total_cents_delta == -300
    assert len(result.activating_policy_versions) == 2
    assert trend_calls[0]["force_recompute"] is True
    assert trend_calls[1]["force_recompute"] is False
    assert trend_calls[0]["location_settings_overrides_by_id"] == {
        location_a.id: {
            "compliance": {
                "minimum_rest_hours": 10,
                "require_structured_break_plans": False,
            },
            "compliance_policy_hash": f"location_hash_{location_a.id}",
            "compliance_policy_scope": "location",
        },
        location_b.id: {
            "compliance": {
                "minimum_rest_hours": 10,
                "require_structured_break_plans": True,
            },
            "compliance_policy_hash": f"location_hash_{location_b.id}",
            "compliance_policy_scope": "location",
        },
    }
