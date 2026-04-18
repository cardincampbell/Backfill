from __future__ import annotations

from datetime import datetime, time, timezone
from uuid import uuid4

from app.models.business import Location, Role
from app.models.common import CoverageCaseStatus, OfferStatus, ShiftStatus
from app.models.coverage import CoverageCase, CoverageOffer
from app.models.scheduling import Shift
from app.models.workforce import Employee, EmployeeAvailabilityRule, EmployeeLocation
from app.services import invariants


def test_summarize_scheduler_coverage_invariants_flags_employee_setup_issues():
    business_id = uuid4()
    location_id = uuid4()
    employee = Employee(
        id=uuid4(),
        business_id=business_id,
        full_name="Taylor Smith",
        phone_e164="555-0100",
        response_profile={},
        employee_metadata={},
    )
    employee.availability_rules = []
    employee.employee_locations = [
        EmployeeLocation(
            id=uuid4(),
            employee_id=employee.id,
            location_id=location_id,
            access_level="pending",
            location_metadata={},
        )
    ]

    summary = invariants.summarize_scheduler_coverage_invariants(
        employees=[employee],
        coverage_cases=[],
        checked_at=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
    )

    assert summary["issue_count"] == 3
    assert summary["counts_by_code"]["employee_missing_availability_rules"] == 1
    assert summary["counts_by_code"]["employee_invalid_phone_e164"] == 1
    assert summary["counts_by_code"]["employee_missing_location_eligibility"] == 1


def test_summarize_scheduler_coverage_invariants_flags_case_offer_state_drift():
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    now = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)

    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        slug="downtown",
        timezone="America/Los_Angeles",
    )
    role = Role(
        id=role_id,
        business_id=business_id,
        code="server",
        name="Server",
    )
    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now,
        status=ShiftStatus.open,
    )
    shift.location = location
    shift.role = role

    pending_offer = CoverageOffer(
        id=uuid4(),
        coverage_case_id=uuid4(),
        employee_id=uuid4(),
        channel="voice",
        status=OfferStatus.pending,
        idempotency_key="pending-offer",
        offer_metadata={},
    )
    accepted_offer = CoverageOffer(
        id=uuid4(),
        coverage_case_id=uuid4(),
        employee_id=uuid4(),
        channel="voice",
        status=OfferStatus.accepted,
        idempotency_key="accepted-offer",
        offer_metadata={},
    )
    terminal_case = CoverageCase(
        id=uuid4(),
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.exhausted,
        case_metadata={},
    )
    terminal_case.shift = shift
    terminal_case.offers = [pending_offer]

    accepted_not_filled_case = CoverageCase(
        id=uuid4(),
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.running,
        case_metadata={},
    )
    accepted_not_filled_case.shift = shift
    accepted_not_filled_case.offers = [accepted_offer]

    summary = invariants.summarize_scheduler_coverage_invariants(
        employees=[],
        coverage_cases=[terminal_case, accepted_not_filled_case],
        checked_at=now,
    )

    assert summary["counts_by_code"]["coverage_case_terminal_with_actionable_offers"] == 1
    assert summary["counts_by_code"]["coverage_case_not_filled_with_accepted_offer"] == 1
