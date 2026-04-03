from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Business, LocationRole
from app.models.common import (
    AssignmentStatus,
    CandidateSource,
    CoverageOperatingMode,
    CoverageCaseStatus,
    CoverageRunStatus,
    EmployeeStatus,
    OfferStatus,
    OfferResponseChannel,
    OutboxChannel,
    OutboxStatus,
    ShiftStatus,
)
from app.models.coverage import (
    CoverageCandidate,
    CoverageCase,
    CoverageCaseRun,
    CoverageOffer,
    CoverageOfferResponse,
    OutboxEvent,
)
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee, EmployeeLocationClearance, EmployeeRole
from app.schemas.coverage import (
    CoverageCandidatePreview,
    CoverageExecutionDecision,
    CoverageExecutionDispatchRequest,
    CoverageExecutionDispatchResult,
    CoverageExecutionPlan,
    CoverageOfferActionResult,
    CoverageOfferResponseCreate,
    CoverageCaseCreate,
    Phase1CoveragePreview,
    Phase1ExecutionRequest,
    Phase1ExecutionResult,
    Phase2CoveragePreview,
    Phase2ExecutionRequest,
    Phase2ExecutionResult,
)
from app.services import delivery as delivery_service


def _normalize_candidate_score(
    *,
    reliability_score: float,
    avg_response_time_seconds: int | None,
    proficiency_level: int,
    is_primary_role: bool,
    is_home_location: bool,
    can_blast: bool,
) -> tuple[float, dict]:
    response_speed_score = 0.5
    if avg_response_time_seconds is not None:
        normalized = max(0.0, min(1.0, 1 - (avg_response_time_seconds / 1800)))
        response_speed_score = normalized

    score = max(0.0, min(1.0, reliability_score)) * 70.0
    factors = {
        "reliability_score": reliability_score,
        "avg_response_time_seconds": avg_response_time_seconds,
        "response_speed_score": response_speed_score,
        "proficiency_level": proficiency_level,
        "is_primary_role": is_primary_role,
        "is_home_location": is_home_location,
        "can_blast": can_blast,
    }
    score += response_speed_score * 10
    score += min(proficiency_level, 5) * 10
    if is_primary_role:
        score += 15
    if is_home_location:
        score += 10
    if can_blast:
        score += 5
    factors["total"] = score
    return score, factors


def _distance_miles(
    *,
    left_lat: float | None,
    left_lng: float | None,
    right_lat: float | None,
    right_lng: float | None,
) -> float | None:
    if None in {left_lat, left_lng, right_lat, right_lng}:
        return None
    earth_radius_miles = 3958.7613
    lat1 = math.radians(float(left_lat))
    lng1 = math.radians(float(left_lng))
    lat2 = math.radians(float(right_lat))
    lng2 = math.radians(float(right_lng))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_miles * c


def _coverage_settings_enabled(payload: dict | None, *keys: str) -> Optional[bool]:
    if not payload:
        return None
    coverage_settings = payload.get("coverage")
    if isinstance(coverage_settings, dict):
        for key in keys:
            value = coverage_settings.get(key)
            if isinstance(value, bool):
                return value
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _premium_cents_from_rules(payload: dict | None) -> int:
    if not payload:
        return 0
    for key in ("premium_cents", "premium_amount_cents", "default_premium_cents"):
        raw = payload.get(key)
        if raw is None:
            continue
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            continue
    return 0


def _minutes_until_shift(*, shift: Shift, reference_time: datetime) -> int:
    delta = shift.starts_at - reference_time
    return max(0, int(delta.total_seconds() // 60))


def _determine_operating_mode(*, shift: Shift, reference_time: datetime) -> CoverageOperatingMode:
    minutes_until_shift = _minutes_until_shift(shift=shift, reference_time=reference_time)
    if minutes_until_shift < 60:
        return CoverageOperatingMode.blast
    if minutes_until_shift < 4 * 60:
        return CoverageOperatingMode.compressed_queue
    return CoverageOperatingMode.standard_queue


async def _get_shift_business(session: AsyncSession, business_id: UUID) -> Business:
    business = await session.get(Business, business_id)
    if business is None:
        raise LookupError("business_not_found")
    return business


async def _get_location_role_for_shift(session: AsyncSession, shift: Shift) -> LocationRole | None:
    return await session.scalar(
        select(LocationRole).where(
            LocationRole.location_id == shift.location_id,
            LocationRole.role_id == shift.role_id,
            LocationRole.is_active.is_(True),
        )
    )


async def _resolve_phase_2_policy(
    session: AsyncSession,
    *,
    business_id: UUID,
    shift: Shift,
    phase_1_candidate_count: int | None,
) -> tuple[bool, str]:
    business = await _get_shift_business(session, business_id)
    location_role = await _get_location_role_for_shift(session, shift)

    location_enabled = _coverage_settings_enabled(
        getattr(shift.location, "settings", {}) if getattr(shift, "location", None) is not None else {},
        "cross_location_enabled",
        "phase_2_enabled",
    )
    if location_enabled is False:
        return False, "location_opt_out"

    role_enabled = _coverage_settings_enabled(
        location_role.coverage_settings if location_role is not None else None,
        "cross_location_enabled",
        "phase_2_enabled",
    )
    if role_enabled is False:
        return False, "role_opt_out"

    if phase_1_candidate_count == 0:
        return True, "phase_1_exhausted"

    business_opt_in = _coverage_settings_enabled(
        business.settings,
        "cross_location_enabled",
        "phase_2_enabled",
        "cross_location_opt_in",
    )
    if business_opt_in is True or location_enabled is True or role_enabled is True:
        return True, "cross_location_opt_in"

    return False, "phase_1_candidates_available"


async def _build_execution_plan(
    session: AsyncSession,
    *,
    business_id: UUID,
    shift: Shift,
    phase: str,
    requested_dispatch_limit: int | None,
    requested_offer_ttl_minutes: int | None,
    phase_1_candidate_count: int | None = None,
) -> CoverageExecutionPlan:
    reference_time = datetime.now(timezone.utc)
    operating_mode = _determine_operating_mode(shift=shift, reference_time=reference_time)
    time_to_shift_minutes = _minutes_until_shift(shift=shift, reference_time=reference_time)

    if operating_mode == CoverageOperatingMode.standard_queue:
        default_dispatch_limit = 1
        default_offer_ttl_minutes = 5
        strategy = f"{phase}_sequential_standard"
    elif operating_mode == CoverageOperatingMode.compressed_queue:
        default_dispatch_limit = 1
        default_offer_ttl_minutes = 2
        strategy = f"{phase}_sequential_compressed"
    else:
        default_dispatch_limit = 5
        default_offer_ttl_minutes = max(1, min(5, time_to_shift_minutes or 1))
        strategy = f"{phase}_blast"

    dispatch_limit = requested_dispatch_limit if requested_dispatch_limit is not None else default_dispatch_limit
    if operating_mode == CoverageOperatingMode.blast:
        dispatch_limit = min(max(1, dispatch_limit), 8)
    else:
        dispatch_limit = min(max(1, dispatch_limit), 1)

    offer_ttl_minutes = (
        requested_offer_ttl_minutes if requested_offer_ttl_minutes is not None else default_offer_ttl_minutes
    )
    offer_ttl_minutes = max(1, offer_ttl_minutes)

    location_role = await _get_location_role_for_shift(session, shift)
    premium_cents = int(shift.premium_cents or 0)
    if premium_cents == 0 and operating_mode == CoverageOperatingMode.blast and location_role is not None:
        premium_cents = _premium_cents_from_rules(location_role.premium_rules)

    phase_2_eligible, phase_2_reason = await _resolve_phase_2_policy(
        session,
        business_id=business_id,
        shift=shift,
        phase_1_candidate_count=phase_1_candidate_count,
    )

    return CoverageExecutionPlan(
        phase=phase,
        operating_mode=operating_mode.value,
        strategy=strategy,
        time_to_shift_minutes=time_to_shift_minutes,
        dispatch_limit=dispatch_limit,
        offer_ttl_minutes=offer_ttl_minutes,
        premium_cents=premium_cents,
        phase_2_eligible=phase_2_eligible,
        phase_2_reason=phase_2_reason,
    )


def _normalized_operating_mode(value: object | None) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    text = str(value or "").strip()
    return text or CoverageOperatingMode.standard_queue.value


def _standby_queue_for_case(coverage_case: CoverageCase) -> list[dict]:
    metadata = coverage_case.case_metadata or {}
    raw_queue = metadata.get("standby_queue")
    if not isinstance(raw_queue, list):
        return []
    return [dict(item) for item in raw_queue if isinstance(item, dict)]


def _update_case_metadata(coverage_case: CoverageCase, **updates: object) -> None:
    coverage_case.case_metadata = {
        **(coverage_case.case_metadata or {}),
        **updates,
    }


async def _next_undispatched_candidates(
    session: AsyncSession,
    *,
    coverage_case_id: UUID,
    coverage_case_run_id: UUID,
    batch_size: int,
) -> list[CoverageCandidate]:
    dispatched_result = await session.execute(
        select(CoverageOffer.coverage_candidate_id).where(
            CoverageOffer.coverage_case_id == coverage_case_id,
            CoverageOffer.coverage_candidate_id.is_not(None),
        )
    )
    dispatched_candidate_ids = [candidate_id for candidate_id in dispatched_result.scalars().all() if candidate_id is not None]

    query = select(CoverageCandidate).where(CoverageCandidate.coverage_case_run_id == coverage_case_run_id)
    if dispatched_candidate_ids:
        query = query.where(~CoverageCandidate.id.in_(dispatched_candidate_ids))

    candidate_result = await session.execute(
        query.order_by(CoverageCandidate.rank.asc()).limit(max(1, batch_size))
    )
    return list(candidate_result.scalars().all())


async def _dispatch_next_offer_batch(
    session: AsyncSession,
    *,
    coverage_case: CoverageCase,
    run: CoverageCaseRun,
    shift: Shift,
    reference_time: datetime,
    channel: str,
) -> list[CoverageOffer]:
    batch_size = max(1, int(run.run_metadata.get("dispatch_limit", 1)))
    candidate_records = await _next_undispatched_candidates(
        session,
        coverage_case_id=coverage_case.id,
        coverage_case_run_id=run.id,
        batch_size=batch_size,
    )
    if not candidate_records:
        return []

    offer_ttl_minutes = max(1, int(run.run_metadata.get("offer_ttl_minutes", 15)))
    operating_mode = _normalized_operating_mode(run.run_metadata.get("operating_mode"))
    premium_cents = max(0, int(run.run_metadata.get("premium_cents", 0)))
    expires_at = reference_time + timedelta(minutes=offer_ttl_minutes)

    offers: list[CoverageOffer] = []
    for candidate_record in candidate_records:
        offers.append(
            await _create_offer_for_candidate(
                session=session,
                coverage_case_id=coverage_case.id,
                coverage_case_run_id=run.id,
                candidate_record=candidate_record,
                shift=shift,
                phase_no=run.phase_no,
                channel=channel,
                available_at=reference_time,
                expires_at=expires_at,
                operating_mode=operating_mode,
                premium_cents=premium_cents,
            )
        )
    return offers


async def advance_case_after_terminal_offer(
    session: AsyncSession,
    *,
    offer: CoverageOffer,
    reference_time: datetime,
) -> tuple[list[CoverageOffer], str | None]:
    coverage_case = await session.get(CoverageCase, offer.coverage_case_id)
    if coverage_case is None:
        return [], None

    shift = await session.get(Shift, coverage_case.shift_id)
    if shift is None:
        return [], None

    filled_seats = max(0, int(shift.seats_filled or 0))
    requested_seats = max(1, int(shift.seats_requested or 1))

    if coverage_case.status in {
        CoverageCaseStatus.filled,
        CoverageCaseStatus.cancelled,
        CoverageCaseStatus.failed,
    } or filled_seats >= requested_seats:
        return [], None

    pending_result = await session.execute(
        select(CoverageOffer.id).where(
            CoverageOffer.coverage_case_id == coverage_case.id,
            CoverageOffer.id != offer.id,
            CoverageOffer.status.in_([OfferStatus.pending, OfferStatus.delivered]),
        )
    )
    if list(pending_result.scalars().all()):
        return [], None

    if offer.coverage_case_run_id is None:
        coverage_case.status = CoverageCaseStatus.exhausted
        coverage_case.closed_at = reference_time
        return [], str(coverage_case.id)

    run = await session.get(CoverageCaseRun, offer.coverage_case_run_id)
    if run is None:
        coverage_case.status = CoverageCaseStatus.exhausted
        coverage_case.closed_at = reference_time
        return [], str(coverage_case.id)

    next_offers = await _dispatch_next_offer_batch(
        session,
        coverage_case=coverage_case,
        run=run,
        shift=shift,
        reference_time=reference_time,
        channel=offer.channel.value if hasattr(offer.channel, "value") else str(offer.channel),
    )
    if next_offers:
        coverage_case.status = CoverageCaseStatus.running
        return next_offers, None

    coverage_case.status = CoverageCaseStatus.exhausted
    coverage_case.closed_at = reference_time
    return [], str(coverage_case.id)


def _clearance_is_usable(clearance, *, shift: Shift) -> tuple[bool, dict]:
    details = {
        "access_level": clearance.access_level,
        "can_cover_last_minute": clearance.can_cover_last_minute,
        "can_blast": clearance.can_blast,
        "travel_radius_miles": clearance.travel_radius_miles,
    }
    if clearance.access_level not in {"approved", "trusted"}:
        details["reason"] = "clearance_level_not_approved"
        return False, details

    distance_miles = _distance_miles(
        left_lat=float(shift.location.latitude) if getattr(shift.location, "latitude", None) is not None else None,
        left_lng=float(shift.location.longitude) if getattr(shift.location, "longitude", None) is not None else None,
        right_lat=float(clearance.location.latitude) if getattr(clearance.location, "latitude", None) is not None else None,
        right_lng=float(clearance.location.longitude) if getattr(clearance.location, "longitude", None) is not None else None,
    )
    if distance_miles is not None:
        details["distance_miles"] = round(distance_miles, 2)
    if clearance.travel_radius_miles is not None and distance_miles is not None:
        if distance_miles > clearance.travel_radius_miles:
            details["reason"] = "outside_travel_radius"
            return False, details
    return True, details


def _time_range_covers_shift(
    starts_at_local: datetime,
    ends_at_local: datetime,
    rule_start,
    rule_end,
) -> bool:
    shift_start = starts_at_local.timetz().replace(tzinfo=None)
    shift_end = ends_at_local.timetz().replace(tzinfo=None)
    if rule_start <= rule_end:
        return rule_start <= shift_start and rule_end >= shift_end
    return shift_start >= rule_start or shift_end <= rule_end


def _is_available_for_shift(employee: Employee, shift: Shift) -> tuple[bool, dict]:
    tz = ZoneInfo(shift.timezone)
    starts_local = shift.starts_at.astimezone(tz)
    ends_local = shift.ends_at.astimezone(tz)

    snapshot = {
        "timezone": shift.timezone,
        "rule_match": False,
        "exception_override": None,
        "starts_local": starts_local.isoformat(),
        "ends_local": ends_local.isoformat(),
    }

    for exception in employee.availability_exceptions:
        overlaps = exception.starts_at < shift.ends_at and exception.ends_at > shift.starts_at
        if not overlaps:
            continue
        if exception.exception_type in {"unavailable", "blocked", "time_off"}:
            snapshot["exception_override"] = exception.exception_type
            snapshot["reason"] = "availability_exception_blocked"
            return False, snapshot
        if exception.exception_type in {"available", "override_available"}:
            snapshot["exception_override"] = exception.exception_type
            snapshot["rule_match"] = True
            return True, snapshot

    day_of_week = starts_local.weekday()
    for rule in employee.availability_rules:
        if rule.day_of_week != day_of_week:
            continue
        if rule.valid_from and starts_local.date() < rule.valid_from:
            continue
        if rule.valid_until and starts_local.date() > rule.valid_until:
            continue
        if rule.availability_type != "available":
            continue
        if _time_range_covers_shift(starts_local, ends_local, rule.start_local_time, rule.end_local_time):
            snapshot["rule_match"] = True
            snapshot["priority"] = rule.priority
            return True, snapshot

    snapshot["reason"] = "no_matching_availability_rule"
    return False, snapshot


async def list_coverage_cases(session: AsyncSession, business_id: UUID) -> list[CoverageCase]:
    result = await session.execute(
        select(CoverageCase)
        .join(Shift, CoverageCase.shift_id == Shift.id)
        .where(Shift.business_id == business_id)
        .order_by(CoverageCase.created_at.desc())
    )
    return list(result.scalars().all())


async def create_coverage_case(session: AsyncSession, business_id: UUID, payload: CoverageCaseCreate) -> CoverageCase:
    shift = await session.get(Shift, payload.shift_id)
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")

    case = CoverageCase(
        shift_id=shift.id,
        location_id=shift.location_id,
        role_id=shift.role_id,
        status=CoverageCaseStatus.queued,
        phase_target=payload.phase_target,
        reason_code=payload.reason_code,
        priority=payload.priority,
        requires_manager_approval=payload.requires_manager_approval,
        triggered_by=payload.triggered_by,
        opened_at=datetime.now(timezone.utc),
        case_metadata=payload.case_metadata,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return case


async def _load_coverage_case_shift(
    session: AsyncSession,
    business_id: UUID,
    coverage_case_id: UUID,
) -> tuple[CoverageCase, Shift]:
    case = await session.get(CoverageCase, coverage_case_id)
    if case is None:
        raise LookupError("coverage_case_not_found")

    shift = await session.scalar(
        select(Shift)
        .options(selectinload(Shift.location))
        .where(Shift.id == case.shift_id)
    )
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")
    return case, shift


async def plan_coverage_case_execution(
    session: AsyncSession,
    business_id: UUID,
    coverage_case_id: UUID,
) -> CoverageExecutionDecision:
    case, shift = await _load_coverage_case_shift(session, business_id, coverage_case_id)
    _, phase_1_candidates = await _collect_phase_1_candidates(session, business_id, shift.id)
    phase_1_plan = await _build_execution_plan(
        session,
        business_id=business_id,
        shift=shift,
        phase="phase_1",
        requested_dispatch_limit=None,
        requested_offer_ttl_minutes=None,
        phase_1_candidate_count=len(phase_1_candidates),
    )
    phase_2_plan = await _build_execution_plan(
        session,
        business_id=business_id,
        shift=shift,
        phase="phase_2",
        requested_dispatch_limit=None,
        requested_offer_ttl_minutes=None,
        phase_1_candidate_count=len(phase_1_candidates),
    )

    recommended_phase: str | None = None
    recommendation_reason = "no_candidates_available"
    phase_2_candidate_count = 0

    if phase_1_candidates:
        recommended_phase = "phase_1"
        recommendation_reason = "phase_1_candidates_available"
    elif phase_2_plan.phase_2_eligible:
        _, phase_2_candidates = await _collect_phase_2_candidates(session, business_id, shift.id)
        phase_2_candidate_count = len(phase_2_candidates)
        if phase_2_candidates:
            recommended_phase = "phase_2"
            recommendation_reason = phase_2_plan.phase_2_reason or "phase_2_available"
        else:
            recommendation_reason = "phase_2_no_candidates"
    else:
        recommendation_reason = phase_2_plan.phase_2_reason or "phase_2_not_eligible"

    return CoverageExecutionDecision(
        coverage_case_id=case.id,
        shift_id=shift.id,
        recommended_phase=recommended_phase,
        recommendation_reason=recommendation_reason,
        phase_1_candidate_count=len(phase_1_candidates),
        phase_2_candidate_count=phase_2_candidate_count,
        phase_1_plan=phase_1_plan,
        phase_2_plan=phase_2_plan,
    )


async def execute_next_coverage_phase(
    session: AsyncSession,
    business_id: UUID,
    coverage_case_id: UUID,
    payload: CoverageExecutionDispatchRequest,
) -> CoverageExecutionDispatchResult:
    decision = await plan_coverage_case_execution(session, business_id, coverage_case_id)
    selected_phase = payload.phase_override or decision.recommended_phase

    if selected_phase == "phase_1":
        result = await execute_phase_1_run(
            session,
            business_id,
            coverage_case_id,
            Phase1ExecutionRequest(
                dispatch_limit=(
                    payload.dispatch_limit
                    if payload.dispatch_limit is not None
                    else decision.phase_1_plan.dispatch_limit
                ),
                channel=payload.channel,
                offer_ttl_minutes=(
                    payload.offer_ttl_minutes
                    if payload.offer_ttl_minutes is not None
                    else decision.phase_1_plan.offer_ttl_minutes
                ),
                run_metadata=payload.run_metadata,
            ),
        )
        return CoverageExecutionDispatchResult(
            decision=decision,
            phase_executed="phase_1",
            coverage_case=result.coverage_case,
            run=result.run,
            plan=result.plan,
            candidate_count=result.candidate_count,
            offers=result.offers,
        )

    if selected_phase == "phase_2":
        result = await execute_phase_2_run(
            session,
            business_id,
            coverage_case_id,
            Phase2ExecutionRequest(
                dispatch_limit=(
                    payload.dispatch_limit
                    if payload.dispatch_limit is not None
                    else decision.phase_2_plan.dispatch_limit
                ),
                channel=payload.channel,
                offer_ttl_minutes=(
                    payload.offer_ttl_minutes
                    if payload.offer_ttl_minutes is not None
                    else decision.phase_2_plan.offer_ttl_minutes
                ),
                run_metadata=payload.run_metadata,
            ),
        )
        return CoverageExecutionDispatchResult(
            decision=decision,
            phase_executed="phase_2",
            coverage_case=result.coverage_case,
            run=result.run,
            plan=result.plan,
            candidate_count=result.candidate_count,
            offers=result.offers,
        )

    case, _shift = await _load_coverage_case_shift(session, business_id, coverage_case_id)
    case.status = CoverageCaseStatus.exhausted
    case.closed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(case)
    return CoverageExecutionDispatchResult(
        decision=decision,
        phase_executed=None,
        coverage_case=case,
    )


async def preview_phase_1_candidates(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
) -> Phase1CoveragePreview:
    shift, ranked = await _collect_phase_1_candidates(session, business_id, shift_id)
    plan = await _build_execution_plan(
        session,
        business_id=business_id,
        shift=shift,
        phase="phase_1",
        requested_dispatch_limit=None,
        requested_offer_ttl_minutes=None,
        phase_1_candidate_count=len(ranked),
    )
    return Phase1CoveragePreview(
        shift_id=shift.id,
        location_id=shift.location_id,
        role_id=shift.role_id,
        candidate_count=len(ranked),
        plan=plan,
        candidates=ranked,
    )


async def preview_phase_2_candidates(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
) -> Phase2CoveragePreview:
    phase_1_shift, phase_1_candidates = await _collect_phase_1_candidates(session, business_id, shift_id)
    plan = await _build_execution_plan(
        session,
        business_id=business_id,
        shift=phase_1_shift,
        phase="phase_2",
        requested_dispatch_limit=None,
        requested_offer_ttl_minutes=None,
        phase_1_candidate_count=len(phase_1_candidates),
    )
    if not plan.phase_2_eligible:
        return Phase2CoveragePreview(
            shift_id=phase_1_shift.id,
            location_id=phase_1_shift.location_id,
            role_id=phase_1_shift.role_id,
            candidate_count=0,
            plan=plan,
            candidates=[],
        )
    shift, ranked = await _collect_phase_2_candidates(session, business_id, shift_id)
    return Phase2CoveragePreview(
        shift_id=shift.id,
        location_id=shift.location_id,
        role_id=shift.role_id,
        candidate_count=len(ranked),
        plan=plan,
        candidates=ranked,
    )


async def _collect_phase_1_candidates(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
) -> tuple[Shift, list[CoverageCandidatePreview]]:
    shift = await session.scalar(
        select(Shift)
        .options(selectinload(Shift.location))
        .where(Shift.id == shift_id)
    )
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")

    result = await session.execute(
        select(Employee)
        .join(EmployeeRole, EmployeeRole.employee_id == Employee.id)
        .options(
            selectinload(Employee.employee_roles),
            selectinload(Employee.clearances),
            selectinload(Employee.availability_rules),
            selectinload(Employee.availability_exceptions),
        )
        .where(
            Employee.business_id == business_id,
            Employee.status == EmployeeStatus.active,
            EmployeeRole.role_id == shift.role_id,
        )
    )
    employees = list(result.scalars().unique().all())

    employee_ids = [employee.id for employee in employees]
    busy_employee_ids: set[UUID] = set()
    if employee_ids:
        busy_result = await session.execute(
            select(ShiftAssignment.employee_id)
            .join(Shift, ShiftAssignment.shift_id == Shift.id)
            .where(
                ShiftAssignment.employee_id.in_(employee_ids),
                ShiftAssignment.status.in_([AssignmentStatus.assigned, AssignmentStatus.accepted]),
                Shift.starts_at < shift.ends_at,
                Shift.ends_at > shift.starts_at,
            )
        )
        busy_employee_ids = {row for row in busy_result.scalars().all() if row is not None}

    candidates: list[CoverageCandidatePreview] = []
    for employee in employees:
        clearance = next(
            (
                record
                for record in employee.clearances
                if record.location_id == shift.location_id and record.access_level in {"approved", "trusted"}
            ),
            None,
        )
        if clearance is None:
            continue
        if employee.id in busy_employee_ids:
            continue

        available, availability_snapshot = _is_available_for_shift(employee, shift)
        if not available:
            continue

        role_match = next((record for record in employee.employee_roles if record.role_id == shift.role_id), None)
        proficiency_level = role_match.proficiency_level if role_match else 1
        is_primary_role = bool(role_match and role_match.is_primary)
        is_home_location = employee.home_location_id == shift.location_id

        score, scoring_factors = _normalize_candidate_score(
            reliability_score=float(employee.reliability_score or 0.7),
            avg_response_time_seconds=employee.avg_response_time_seconds,
            proficiency_level=proficiency_level,
            is_primary_role=is_primary_role,
            is_home_location=is_home_location,
            can_blast=clearance.can_blast,
        )

        candidates.append(
            CoverageCandidatePreview(
                employee_id=employee.id,
                employee_name=employee.full_name,
                phone_e164=employee.phone_e164,
                home_location_id=employee.home_location_id,
                rank=0,
                score=score,
                source=CandidateSource.phase_1.value,
                scoring_factors=scoring_factors,
                availability_snapshot=availability_snapshot,
            )
        )

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    ranked = [
        candidate.model_copy(update={"rank": index + 1})
        for index, candidate in enumerate(candidates)
    ]
    return shift, ranked


async def _collect_phase_2_candidates(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
) -> tuple[Shift, list[CoverageCandidatePreview]]:
    shift = await session.scalar(
        select(Shift)
        .options(selectinload(Shift.location))
        .where(Shift.id == shift_id)
    )
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")

    result = await session.execute(
        select(Employee)
        .join(EmployeeRole, EmployeeRole.employee_id == Employee.id)
        .options(
            selectinload(Employee.employee_roles),
            selectinload(Employee.clearances).selectinload(EmployeeLocationClearance.location),
            selectinload(Employee.availability_rules),
            selectinload(Employee.availability_exceptions),
        )
        .where(
            Employee.business_id == business_id,
            Employee.status == EmployeeStatus.active,
            EmployeeRole.role_id == shift.role_id,
        )
    )
    employees = list(result.scalars().unique().all())

    employee_ids = [employee.id for employee in employees]
    busy_employee_ids: set[UUID] = set()
    worked_location_counts: dict[UUID, int] = {}
    if employee_ids:
        busy_result = await session.execute(
            select(ShiftAssignment.employee_id)
            .join(Shift, ShiftAssignment.shift_id == Shift.id)
            .where(
                ShiftAssignment.employee_id.in_(employee_ids),
                ShiftAssignment.status.in_([AssignmentStatus.assigned, AssignmentStatus.accepted]),
                Shift.starts_at < shift.ends_at,
                Shift.ends_at > shift.starts_at,
            )
        )
        busy_employee_ids = {row for row in busy_result.scalars().all() if row is not None}

        historical_result = await session.execute(
            select(ShiftAssignment.employee_id, func.count(ShiftAssignment.id))
            .join(Shift, ShiftAssignment.shift_id == Shift.id)
            .where(
                ShiftAssignment.employee_id.in_(employee_ids),
                Shift.location_id == shift.location_id,
                ShiftAssignment.status.in_(
                    [
                        AssignmentStatus.assigned,
                        AssignmentStatus.accepted,
                        AssignmentStatus.completed,
                    ]
                ),
            )
            .group_by(ShiftAssignment.employee_id)
        )
        worked_location_counts = {
            employee_id: int(count)
            for employee_id, count in historical_result.all()
            if employee_id is not None
        }

    candidates: list[CoverageCandidatePreview] = []
    for employee in employees:
        if employee.home_location_id == shift.location_id:
            continue
        if employee.id in busy_employee_ids:
            continue

        clearance = next(
            (
                record
                for record in employee.clearances
                if record.location_id == shift.location_id
            ),
            None,
        )
        if clearance is None:
            continue
        clearance_ok, clearance_details = _clearance_is_usable(clearance, shift=shift)
        if not clearance_ok:
            continue

        available, availability_snapshot = _is_available_for_shift(employee, shift)
        if not available:
            continue

        role_match = next((record for record in employee.employee_roles if record.role_id == shift.role_id), None)
        proficiency_level = role_match.proficiency_level if role_match else 1
        is_primary_role = bool(role_match and role_match.is_primary)
        prior_location_count = worked_location_counts.get(employee.id, 0)
        location_affinity_bonus = min(prior_location_count, 5) * 2

        score, scoring_factors = _normalize_candidate_score(
            reliability_score=float(employee.reliability_score or 0.7),
            avg_response_time_seconds=employee.avg_response_time_seconds,
            proficiency_level=proficiency_level,
            is_primary_role=is_primary_role,
            is_home_location=False,
            can_blast=clearance.can_blast,
        )
        score += location_affinity_bonus
        scoring_factors["location_affinity_count"] = prior_location_count
        scoring_factors["location_affinity_bonus"] = location_affinity_bonus
        scoring_factors["clearance"] = clearance_details
        scoring_factors["total"] = score

        candidates.append(
            CoverageCandidatePreview(
                employee_id=employee.id,
                employee_name=employee.full_name,
                phone_e164=employee.phone_e164,
                home_location_id=employee.home_location_id,
                rank=0,
                score=score,
                source=CandidateSource.phase_2.value,
                scoring_factors=scoring_factors,
                availability_snapshot={
                    **availability_snapshot,
                    "phase_2": True,
                    "prior_location_count": prior_location_count,
                },
            )
        )

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    ranked = [
        candidate.model_copy(update={"rank": index + 1})
        for index, candidate in enumerate(candidates)
    ]
    return shift, ranked


async def execute_phase_1_run(
    session: AsyncSession,
    business_id: UUID,
    coverage_case_id: UUID,
    payload: Phase1ExecutionRequest,
) -> Phase1ExecutionResult:
    case = await session.get(CoverageCase, coverage_case_id)
    if case is None:
        raise LookupError("coverage_case_not_found")

    shift = await session.scalar(
        select(Shift)
        .options(selectinload(Shift.location))
        .where(Shift.id == case.shift_id)
    )
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")

    _, ranked = await _collect_phase_1_candidates(session, business_id, shift.id)
    plan = await _build_execution_plan(
        session,
        business_id=business_id,
        shift=shift,
        phase="phase_1",
        requested_dispatch_limit=payload.dispatch_limit,
        requested_offer_ttl_minutes=payload.offer_ttl_minutes,
        phase_1_candidate_count=len(ranked),
    )

    current_phase_no = await session.scalar(
        select(func.coalesce(func.max(CoverageCaseRun.phase_no), 0)).where(
            CoverageCaseRun.coverage_case_id == coverage_case_id
        )
    )
    phase_no = int(current_phase_no or 0) + 1
    started_at = datetime.now(timezone.utc)

    run = CoverageCaseRun(
        coverage_case_id=coverage_case_id,
        phase_no=phase_no,
        strategy=plan.strategy,
        status=CoverageRunStatus.running,
        started_at=started_at,
        run_metadata={
            **payload.run_metadata,
            "phase": plan.phase,
            "operating_mode": plan.operating_mode,
            "dispatch_limit": plan.dispatch_limit,
            "offer_ttl_minutes": plan.offer_ttl_minutes,
            "premium_cents": plan.premium_cents,
            "phase_2_eligible": plan.phase_2_eligible,
            "phase_2_reason": plan.phase_2_reason,
        },
    )
    session.add(run)
    await session.flush()

    candidate_records: list[CoverageCandidate] = []
    for candidate in ranked:
        record = CoverageCandidate(
            coverage_case_run_id=run.id,
            employee_id=candidate.employee_id,
            source=CandidateSource.phase_1,
            rank=candidate.rank,
            score=candidate.score,
            qualification_status=candidate.qualification_status,
            exclusion_reasons=candidate.exclusion_reasons,
            scoring_factors=candidate.scoring_factors,
            availability_snapshot=candidate.availability_snapshot,
            candidate_metadata={
                "employee_name": candidate.employee_name,
                "phone_e164": candidate.phone_e164,
                "home_location_id": str(candidate.home_location_id) if candidate.home_location_id else None,
            },
        )
        session.add(record)
        candidate_records.append(record)

    await session.flush()

    dispatch_limit = max(0, plan.dispatch_limit)
    selected = candidate_records[:dispatch_limit]
    offers: list[CoverageOffer] = []
    offer_expires_at = started_at + timedelta(minutes=plan.offer_ttl_minutes)
    for candidate_record in selected:
        offer = await _create_offer_for_candidate(
            session=session,
            coverage_case_id=coverage_case_id,
            coverage_case_run_id=run.id,
            candidate_record=candidate_record,
            shift=shift,
            phase_no=phase_no,
            channel=payload.channel,
            available_at=started_at,
            expires_at=offer_expires_at,
            operating_mode=plan.operating_mode,
            premium_cents=plan.premium_cents,
        )
        offers.append(offer)

    run.candidate_count = len(candidate_records)
    run.status = CoverageRunStatus.completed
    run.finished_at = datetime.now(timezone.utc)

    case.status = CoverageCaseStatus.running if offers else CoverageCaseStatus.exhausted
    if not offers:
        case.closed_at = run.finished_at

    await session.commit()
    await session.refresh(case)
    await session.refresh(run)
    for offer in offers:
        await session.refresh(offer)

    return Phase1ExecutionResult(
        coverage_case=case,
        run=run,
        plan=plan,
        candidate_count=len(ranked),
        candidates=ranked,
        offers=offers,
    )


async def execute_phase_2_run(
    session: AsyncSession,
    business_id: UUID,
    coverage_case_id: UUID,
    payload: Phase2ExecutionRequest,
) -> Phase2ExecutionResult:
    case = await session.get(CoverageCase, coverage_case_id)
    if case is None:
        raise LookupError("coverage_case_not_found")

    shift = await session.scalar(
        select(Shift)
        .options(selectinload(Shift.location))
        .where(Shift.id == case.shift_id)
    )
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")

    _, phase_1_candidates = await _collect_phase_1_candidates(session, business_id, shift.id)
    plan = await _build_execution_plan(
        session,
        business_id=business_id,
        shift=shift,
        phase="phase_2",
        requested_dispatch_limit=payload.dispatch_limit,
        requested_offer_ttl_minutes=payload.offer_ttl_minutes,
        phase_1_candidate_count=len(phase_1_candidates),
    )
    if not plan.phase_2_eligible:
        raise ValueError(f"phase_2_not_allowed:{plan.phase_2_reason}")

    _, ranked = await _collect_phase_2_candidates(session, business_id, shift.id)

    current_phase_no = await session.scalar(
        select(func.coalesce(func.max(CoverageCaseRun.phase_no), 0)).where(
            CoverageCaseRun.coverage_case_id == coverage_case_id
        )
    )
    phase_no = int(current_phase_no or 0) + 1
    started_at = datetime.now(timezone.utc)

    run = CoverageCaseRun(
        coverage_case_id=coverage_case_id,
        phase_no=phase_no,
        strategy=plan.strategy,
        status=CoverageRunStatus.running,
        started_at=started_at,
        run_metadata={
            **payload.run_metadata,
            "phase": plan.phase,
            "operating_mode": plan.operating_mode,
            "dispatch_limit": plan.dispatch_limit,
            "offer_ttl_minutes": plan.offer_ttl_minutes,
            "premium_cents": plan.premium_cents,
            "phase_2_eligible": plan.phase_2_eligible,
            "phase_2_reason": plan.phase_2_reason,
        },
    )
    session.add(run)
    await session.flush()

    candidate_records: list[CoverageCandidate] = []
    for candidate in ranked:
        record = CoverageCandidate(
            coverage_case_run_id=run.id,
            employee_id=candidate.employee_id,
            source=CandidateSource.phase_2,
            rank=candidate.rank,
            score=candidate.score,
            qualification_status=candidate.qualification_status,
            exclusion_reasons=candidate.exclusion_reasons,
            scoring_factors=candidate.scoring_factors,
            availability_snapshot=candidate.availability_snapshot,
            candidate_metadata={
                "employee_name": candidate.employee_name,
                "phone_e164": candidate.phone_e164,
                "home_location_id": str(candidate.home_location_id) if candidate.home_location_id else None,
            },
        )
        session.add(record)
        candidate_records.append(record)

    await session.flush()

    dispatch_limit = max(0, plan.dispatch_limit)
    selected = candidate_records[:dispatch_limit]
    offers: list[CoverageOffer] = []
    offer_expires_at = started_at + timedelta(minutes=plan.offer_ttl_minutes)
    for candidate_record in selected:
        offer = await _create_offer_for_candidate(
            session=session,
            coverage_case_id=coverage_case_id,
            coverage_case_run_id=run.id,
            candidate_record=candidate_record,
            shift=shift,
            phase_no=phase_no,
            channel=payload.channel,
            available_at=started_at,
            expires_at=offer_expires_at,
            operating_mode=plan.operating_mode,
            premium_cents=plan.premium_cents,
        )
        offers.append(offer)

    run.candidate_count = len(candidate_records)
    run.status = CoverageRunStatus.completed
    run.finished_at = datetime.now(timezone.utc)

    case.status = CoverageCaseStatus.running if offers else CoverageCaseStatus.exhausted
    if not offers:
        case.closed_at = run.finished_at

    await session.commit()
    await session.refresh(case)
    await session.refresh(run)
    for offer in offers:
        await session.refresh(offer)

    return Phase2ExecutionResult(
        coverage_case=case,
        run=run,
        plan=plan,
        candidate_count=len(ranked),
        candidates=ranked,
        offers=offers,
    )


async def _create_offer_for_candidate(
    *,
    session: AsyncSession,
    coverage_case_id: UUID,
    coverage_case_run_id: UUID,
    candidate_record: CoverageCandidate,
    shift: Shift,
    phase_no: int,
    channel: str,
    available_at: datetime,
    expires_at: datetime,
    operating_mode: str,
    premium_cents: int = 0,
) -> CoverageOffer:
    offer = CoverageOffer(
        coverage_case_id=coverage_case_id,
        coverage_case_run_id=coverage_case_run_id,
        coverage_candidate_id=candidate_record.id,
        employee_id=candidate_record.employee_id,
        channel=OutboxChannel(channel),
        status=OfferStatus.pending,
        idempotency_key=f"{coverage_case_id}:{phase_no}:{candidate_record.employee_id}:{channel}",
        expires_at=expires_at,
        offer_metadata={
            "phase_no": phase_no,
            "shift_id": str(shift.id),
            "location_id": str(shift.location_id),
            "role_id": str(shift.role_id),
            "operating_mode": operating_mode,
            "premium_cents": premium_cents,
            "phone_e164": candidate_record.candidate_metadata.get("phone_e164"),
        },
    )
    session.add(offer)
    await session.flush()
    session.add(
        OutboxEvent(
            aggregate_type="coverage_offer",
            aggregate_id=offer.id,
            topic="coverage.offer.created",
            channel=OutboxChannel(channel),
            status=OutboxStatus.pending,
            available_at=available_at,
            payload={
                "offer_id": str(offer.id),
                "coverage_case_id": str(coverage_case_id),
                "coverage_case_run_id": str(coverage_case_run_id),
                "employee_id": str(candidate_record.employee_id),
                "shift_id": str(shift.id),
                "channel": channel,
                "operating_mode": operating_mode,
                "premium_cents": premium_cents,
                "phone_e164": candidate_record.candidate_metadata.get("phone_e164"),
            },
        )
    )
    return offer


async def respond_to_offer(
    session: AsyncSession,
    business_id: UUID,
    offer_id: UUID,
    payload: CoverageOfferResponseCreate,
) -> CoverageOfferActionResult:
    offer = await session.get(CoverageOffer, offer_id)
    if offer is None:
        raise LookupError("offer_not_found")

    coverage_case = await session.get(CoverageCase, offer.coverage_case_id)
    if coverage_case is None:
        raise LookupError("coverage_case_not_found")

    shift = await session.get(Shift, coverage_case.shift_id)
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")

    action = payload.response.strip().lower()
    if action not in {"accepted", "declined"}:
        raise ValueError("response must be accepted or declined")
    if offer.status not in {OfferStatus.pending, OfferStatus.delivered}:
        raise ValueError("offer is no longer actionable")

    responded_at = datetime.now(timezone.utc)
    response = CoverageOfferResponse(
        coverage_offer_id=offer.id,
        response_channel=OfferResponseChannel(payload.response_channel),
        response_code=payload.response_code,
        response_text=payload.response_text,
        response_payload=payload.response_payload,
        responded_at=responded_at,
    )
    session.add(response)

    assignment: ShiftAssignment | None = None
    assignment_status: str | None = None
    if action == "accepted":
        offer.status = OfferStatus.accepted
        offer.accepted_at = responded_at
        if shift.seats_filled >= shift.seats_requested:
            shift.status = ShiftStatus.covered
            coverage_case.status = CoverageCaseStatus.filled
            coverage_case.closed_at = coverage_case.closed_at or responded_at
            standby_queue = _standby_queue_for_case(coverage_case)
            standby_position = next(
                (
                    int(entry.get("position", index + 1))
                    for index, entry in enumerate(standby_queue)
                    if str(entry.get("employee_id")) == str(offer.employee_id)
                ),
                len(standby_queue) + 1,
            )
            if standby_position > len(standby_queue):
                standby_queue.append(
                    {
                        "position": standby_position,
                        "employee_id": str(offer.employee_id),
                        "offer_id": str(offer.id),
                        "responded_at": responded_at.isoformat(),
                        "response_channel": payload.response_channel,
                    }
                )
            _update_case_metadata(coverage_case, standby_queue=standby_queue)
            offer.offer_metadata = {
                **offer.offer_metadata,
                "accepted_as_standby": True,
                "standby_position": standby_position,
            }
            assignment_status = "standby"
        else:
            current_sequence = await session.scalar(
                select(func.coalesce(func.max(ShiftAssignment.sequence_no), 0)).where(
                    ShiftAssignment.shift_id == shift.id
                )
            )
            assignment = ShiftAssignment(
                shift_id=shift.id,
                employee_id=offer.employee_id,
                assigned_via="coverage_offer",
                status=AssignmentStatus.accepted,
                sequence_no=int(current_sequence or 0) + 1,
                accepted_at=responded_at,
                assignment_metadata={
                    "coverage_case_id": str(coverage_case.id),
                    "coverage_offer_id": str(offer.id),
                },
            )
            session.add(assignment)
            assignment_status = AssignmentStatus.accepted.value

            shift.seats_filled += 1
            if shift.seats_filled >= shift.seats_requested:
                shift.status = ShiftStatus.covered
                coverage_case.status = CoverageCaseStatus.filled
                coverage_case.closed_at = responded_at
                _update_case_metadata(
                    coverage_case,
                    confirmed_offer_id=str(offer.id),
                    confirmed_employee_id=str(offer.employee_id),
                )
            else:
                shift.status = ShiftStatus.filling
                coverage_case.status = CoverageCaseStatus.running

            sibling_result = await session.execute(
                select(CoverageOffer).where(
                    CoverageOffer.coverage_case_id == coverage_case.id,
                    CoverageOffer.id != offer.id,
                    CoverageOffer.status.in_([OfferStatus.pending, OfferStatus.delivered]),
                )
            )
            for sibling in sibling_result.scalars().all():
                sibling.status = OfferStatus.cancelled
                await delivery_service.mark_offer_attempt_outcome(
                    session,
                    sibling,
                    status=delivery_service.CoverageAttemptStatus.cancelled,
                    occurred_at=responded_at,
                )

            from app.services import scheduler_sync

            await scheduler_sync.enqueue_writeback(session, shift_id=shift.id)

    else:
        offer.status = OfferStatus.declined
        offer.declined_at = responded_at

        next_offers, exhausted_case_id = await advance_case_after_terminal_offer(
            session,
            offer=offer,
            reference_time=responded_at,
        )
        if next_offers:
            offer.offer_metadata = {
                **offer.offer_metadata,
                "next_offer_ids": [str(next_offer.id) for next_offer in next_offers],
            }
        elif exhausted_case_id is not None:
            coverage_case.status = CoverageCaseStatus.exhausted
            coverage_case.closed_at = responded_at

    if action == "accepted":
        await delivery_service.mark_offer_attempt_outcome(
            session,
            offer,
            status=delivery_service.CoverageAttemptStatus.accepted,
            occurred_at=responded_at,
            response_payload=payload.response_payload,
        )
    else:
        await delivery_service.mark_offer_attempt_outcome(
            session,
            offer,
            status=delivery_service.CoverageAttemptStatus.declined,
            occurred_at=responded_at,
            response_payload=payload.response_payload,
        )
    await delivery_service.refresh_employee_reliability(session, offer.employee_id, now=responded_at)

    await session.commit()
    await session.refresh(offer)
    await session.refresh(response)
    await session.refresh(coverage_case)
    if assignment is not None:
        await session.refresh(assignment)

    return CoverageOfferActionResult(
        offer=offer,
        response=response,
        coverage_case=coverage_case,
        shift_id=shift.id,
        assignment_id=assignment.id if assignment is not None else None,
        assignment_status=assignment_status or (assignment.status if assignment is not None else None),
    )
