from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.common import CoverageCaseStatus, EmployeeStatus, OfferStatus
from app.models.coverage import CoverageCase
from app.models.scheduling import Shift
from app.models.workforce import Employee
from app.services import coverage_state

_E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def _append_issue(
    issues: list[dict[str, Any]],
    *,
    code: str,
    severity: str,
    aggregate_type: str,
    aggregate_id: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    issues.append(
        {
            "code": code,
            "severity": severity,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "message": message,
            "metadata": metadata or {},
        }
    )


def _has_valid_e164(phone_e164: str | None) -> bool:
    if not isinstance(phone_e164, str):
        return False
    return bool(_E164_PATTERN.match(phone_e164.strip()))


def _employee_invariant_issues(employees: list[Employee]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for employee in employees:
        status_value = getattr(employee, "status", None)
        if status_value not in (None, EmployeeStatus.active):
            continue
        employee_id = str(employee.id)
        if not list(employee.availability_rules or []):
            _append_issue(
                issues,
                code="employee_missing_availability_rules",
                severity="high",
                aggregate_type="employee",
                aggregate_id=employee_id,
                message="Active employee has no recurring availability rules.",
                metadata={"employee_name": employee.full_name},
            )
        if not _has_valid_e164(employee.phone_e164):
            _append_issue(
                issues,
                code="employee_invalid_phone_e164",
                severity="high",
                aggregate_type="employee",
                aggregate_id=employee_id,
                message="Active employee is missing a valid E.164 phone number.",
                metadata={
                    "employee_name": employee.full_name,
                    "phone_e164": employee.phone_e164,
                },
            )
        approved_locations = [
            location
            for location in (employee.employee_locations or [])
            if str(getattr(location, "access_level", "") or "").strip().lower() == "approved"
        ]
        if not approved_locations:
            _append_issue(
                issues,
                code="employee_missing_location_eligibility",
                severity="medium",
                aggregate_type="employee",
                aggregate_id=employee_id,
                message="Active employee has no approved location eligibility.",
                metadata={"employee_name": employee.full_name},
            )
    return issues


def _coverage_case_invariant_issues(coverage_cases: list[CoverageCase]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for coverage_case in coverage_cases:
        case_id = str(coverage_case.id)
        offers = list(coverage_case.offers or [])
        actionable_offers = [
            offer
            for offer in offers
            if coverage_state.is_actionable_offer_status(offer.status)
        ]
        accepted_offers = [offer for offer in offers if offer.status == OfferStatus.accepted]
        shift = coverage_case.shift
        if isinstance(shift, Shift) and not str(shift.timezone or "").strip():
            _append_issue(
                issues,
                code="shift_missing_timezone",
                severity="high",
                aggregate_type="shift",
                aggregate_id=str(shift.id),
                message="Shift linked to coverage case is missing timezone.",
                metadata={"coverage_case_id": case_id},
            )
        if coverage_case.status == CoverageCaseStatus.filled and not accepted_offers:
            _append_issue(
                issues,
                code="coverage_case_filled_without_accepted_offer",
                severity="high",
                aggregate_type="coverage_case",
                aggregate_id=case_id,
                message="Coverage case is filled without an accepted offer.",
                metadata={"offer_statuses": [offer.status.value for offer in offers]},
            )
        if (
            coverage_case.status in {CoverageCaseStatus.queued, CoverageCaseStatus.running}
            and offers
            and not actionable_offers
            and not accepted_offers
        ):
            _append_issue(
                issues,
                code="coverage_case_actionable_status_without_actionable_offers",
                severity="high",
                aggregate_type="coverage_case",
                aggregate_id=case_id,
                message="Coverage case is queued or running but has no actionable offers remaining.",
                metadata={"offer_statuses": [offer.status.value for offer in offers]},
            )
        if (
            not coverage_state.is_actionable_coverage_case_status(coverage_case.status)
            and actionable_offers
        ):
            _append_issue(
                issues,
                code="coverage_case_terminal_with_actionable_offers",
                severity="high",
                aggregate_type="coverage_case",
                aggregate_id=case_id,
                message="Terminal coverage case still has actionable offers.",
                metadata={"offer_ids": [str(offer.id) for offer in actionable_offers]},
            )
        if accepted_offers and coverage_case.status != CoverageCaseStatus.filled:
            _append_issue(
                issues,
                code="coverage_case_not_filled_with_accepted_offer",
                severity="high",
                aggregate_type="coverage_case",
                aggregate_id=case_id,
                message="Coverage case has an accepted offer but is not marked filled.",
                metadata={"accepted_offer_ids": [str(offer.id) for offer in accepted_offers]},
            )
    return issues


def summarize_scheduler_coverage_invariants(
    *,
    employees: list[Employee],
    coverage_cases: list[CoverageCase],
    checked_at: datetime | None = None,
    limit_per_code: int = 25,
) -> dict[str, Any]:
    checked_at = checked_at or datetime.now(timezone.utc)
    all_issues = [
        *_employee_invariant_issues(employees),
        *_coverage_case_invariant_issues(coverage_cases),
    ]
    counts_by_code = dict(Counter(issue["code"] for issue in all_issues))
    counts_by_severity = dict(Counter(issue["severity"] for issue in all_issues))

    limited_issues: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for issue in all_issues:
        grouped[issue["code"]].append(issue)
    for code in sorted(grouped):
        limited_issues.extend(grouped[code][:limit_per_code])

    return {
        "checked_at": checked_at,
        "issue_count": len(all_issues),
        "counts_by_code": counts_by_code,
        "counts_by_severity": counts_by_severity,
        "issues": limited_issues,
    }


async def scan_scheduler_coverage_invariants(
    session: AsyncSession,
    *,
    limit_per_code: int = 25,
) -> dict[str, Any]:
    employee_rows = await session.execute(
        select(Employee)
        .options(
            selectinload(Employee.availability_rules),
            selectinload(Employee.employee_locations),
        )
        .where(Employee.status == EmployeeStatus.active)
    )
    coverage_case_rows = await session.execute(
        select(CoverageCase).options(
            selectinload(CoverageCase.offers),
            selectinload(CoverageCase.shift),
        )
    )
    employees = list(employee_rows.scalars().all())
    coverage_cases = list(coverage_case_rows.scalars().all())
    return summarize_scheduler_coverage_invariants(
        employees=employees,
        coverage_cases=coverage_cases,
        limit_per_code=limit_per_code,
    )
