from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Business, LocationRole
from app.models.common import (
    AuditActorType,
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
    ShiftLifecycleStatus,
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
from app.models.workforce import Employee, EmployeeLocation, EmployeeRole
from app.schemas.coverage import (
    CoverageCandidatePreview,
    CoverageCampaignCreate,
    CoverageCampaignDispatchRequest,
    CoverageCampaignDispatchResult,
    CoverageCampaignExecutionDecision,
    CoverageExecutionDispatchRequest,
    CoverageExecutionPlan,
    CoverageOfferActionResult,
    CoverageOfferResponseCreate,
    Phase1CoveragePreview,
    Phase1ExecutionRequest,
    Phase1ExecutionResult,
    Phase2CoveragePreview,
    Phase2ExecutionRequest,
    Phase2ExecutionResult,
)
from app.services import (
    coverage_transitions,
    delivery as delivery_service,
    outreach as outreach_service,
    platform_events,
    runtime_projections,
)

_COVERAGE_POLICY_VERSION = "coverage_policy_v1"
_COVERAGE_POLICY_INPUTS_VERSION = "runtime_projection_inputs_v1"
_SAME_DAY_SECOND_SHIFT_PENALTY_MULTIPLIER = 0.6
_DEFAULT_SAME_DAY_SECOND_SHIFT_ALLOWED = True
_DEFAULT_SAME_LOCATION_OVERLAP_MINUTES = 0
_DEFAULT_CROSS_LOCATION_SHIFT_COVERAGE_ALLOWED = False
_DEFAULT_CROSS_LOCATION_MIN_GAP_MINUTES = 60
_DEFAULT_CROSS_LOCATION_MAX_RADIUS_MILES = 20


def _shift_amendment_metadata(shift: Shift) -> dict:
    shift_metadata = shift.shift_metadata if isinstance(shift.shift_metadata, dict) else {}
    raw = shift_metadata.get("published_amendment")
    return dict(raw) if isinstance(raw, dict) else {}


def _shift_amended_from_published(shift: Shift) -> bool:
    return bool(_shift_amendment_metadata(shift).get("amended_from_published"))


def _shift_schedule_break(shift: Shift) -> bool:
    return bool(_shift_amendment_metadata(shift).get("schedule_break"))


def _should_accept_via_published_reassignment(shift: Shift) -> bool:
    return (
        shift.lifecycle_status in {ShiftLifecycleStatus.scheduled, ShiftLifecycleStatus.in_progress}
        and _shift_amended_from_published(shift)
        and _shift_schedule_break(shift)
        and shift.seats_filled < shift.seats_requested
    )


def _policy_explanation_metadata(*, generated_at: datetime) -> dict[str, str]:
    return {
        "policy_version": _COVERAGE_POLICY_VERSION,
        "snapshot_generated_at": generated_at.isoformat(),
        "inputs_version": _COVERAGE_POLICY_INPUTS_VERSION,
    }


@dataclass(frozen=True)
class _CoverageBusinessPolicy:
    same_day_second_shift_allowed: bool = _DEFAULT_SAME_DAY_SECOND_SHIFT_ALLOWED
    same_location_overlap_minutes: int = _DEFAULT_SAME_LOCATION_OVERLAP_MINUTES
    cross_location_shift_coverage_allowed: bool = _DEFAULT_CROSS_LOCATION_SHIFT_COVERAGE_ALLOWED
    cross_location_min_gap_minutes: int = _DEFAULT_CROSS_LOCATION_MIN_GAP_MINUTES
    cross_location_max_radius_miles: int = _DEFAULT_CROSS_LOCATION_MAX_RADIUS_MILES


@dataclass(frozen=True)
class _SameDayShiftPolicyResult:
    eligible: bool
    second_shift_detected: bool
    penalty_multiplier: float
    details: dict[str, object]


def _coverage_assignment_source(response_channel: str) -> str:
    normalized = str(response_channel or "").strip().lower()
    if normalized == "voice":
        return "retell_voice"
    if normalized == "sms":
        return "sms_automation"
    return "copilot"


def _shift_calendar_day_window(shift: Shift) -> tuple[datetime, datetime]:
    shift_zone = ZoneInfo(shift.timezone)
    local_date = shift.starts_at.astimezone(shift_zone).date()
    local_start = datetime.combine(local_date, time.min, tzinfo=shift_zone)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _normalize_candidate_score(
    *,
    reliability_score: float,
    avg_response_time_seconds: int | None,
    proficiency_level: int,
    is_primary_role: bool,
    is_primary_location: bool,
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
        "is_primary_location": is_primary_location,
        "can_blast": can_blast,
    }
    score += response_speed_score * 10
    score += min(proficiency_level, 5) * 10
    if is_primary_role:
        score += 15
    if is_primary_location:
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


def _location_identity_key(location) -> tuple[str, str, str] | None:
    locality = str(getattr(location, "locality", "") or "").strip().lower()
    region = str(getattr(location, "region", "") or "").strip().lower()
    country_code = str(getattr(location, "country_code", "") or "").strip().lower()
    if not locality or not region:
        return None
    return locality, region, country_code


def _same_day_shift_overlap_minutes(left: Shift, right: Shift) -> float:
    overlap_seconds = min(left.ends_at, right.ends_at) - max(left.starts_at, right.starts_at)
    return max(0.0, overlap_seconds.total_seconds() / 60)


def _same_day_shift_gap_minutes(left: Shift, right: Shift) -> float:
    if left.ends_at <= right.starts_at:
        return max(0.0, (right.starts_at - left.ends_at).total_seconds() / 60)
    if right.ends_at <= left.starts_at:
        return max(0.0, (left.starts_at - right.ends_at).total_seconds() / 60)
    return 0.0


async def _load_same_day_assignments(
    session: AsyncSession,
    *,
    employee_ids: list[UUID],
    shift: Shift,
) -> dict[UUID, list[ShiftAssignment]]:
    if not employee_ids:
        return {}

    day_starts_at, day_ends_at = _shift_calendar_day_window(shift)
    assignment_result = await session.execute(
        select(ShiftAssignment)
        .join(Shift, ShiftAssignment.shift_id == Shift.id)
        .options(selectinload(ShiftAssignment.shift).selectinload(Shift.location))
        .where(
            ShiftAssignment.employee_id.in_(employee_ids),
            ShiftAssignment.status.in_([AssignmentStatus.assigned, AssignmentStatus.accepted]),
            Shift.id != shift.id,
            Shift.starts_at < day_ends_at,
            Shift.ends_at > day_starts_at,
        )
    )
    assignments_by_employee: dict[UUID, list[ShiftAssignment]] = {}
    for assignment in assignment_result.scalars().all():
        if assignment.employee_id is None:
            continue
        assignments_by_employee.setdefault(assignment.employee_id, []).append(assignment)
    return assignments_by_employee


def _evaluate_same_day_shift_policy(
    *,
    shift: Shift,
    assignments: list[ShiftAssignment],
    policy: _CoverageBusinessPolicy,
) -> _SameDayShiftPolicyResult:
    if not assignments:
        return _SameDayShiftPolicyResult(
            eligible=True,
            second_shift_detected=False,
            penalty_multiplier=1.0,
            details={"second_shift_detected": False, "assignments_considered": 0},
        )

    details: dict[str, object] = {
        "second_shift_detected": True,
        "assignments_considered": len(assignments),
        "same_location_overlap_limit_minutes": policy.same_location_overlap_minutes,
        "cross_location_min_gap_minutes": policy.cross_location_min_gap_minutes,
        "cross_location_max_radius_miles": policy.cross_location_max_radius_miles,
        "cross_location_same_locality_required": True,
        "existing_assignments": [],
    }
    if not policy.same_day_second_shift_allowed:
        details["reason"] = "same_day_second_shift_disabled"
        return _SameDayShiftPolicyResult(
            eligible=False,
            second_shift_detected=True,
            penalty_multiplier=1.0,
            details=details,
        )

    for assignment in assignments:
        existing_shift = assignment.shift
        if existing_shift is None:
            details["reason"] = "existing_assignment_missing_shift"
            return _SameDayShiftPolicyResult(
                eligible=False,
                second_shift_detected=True,
                penalty_multiplier=1.0,
                details=details,
            )

        overlap_minutes = _same_day_shift_overlap_minutes(existing_shift, shift)
        gap_minutes = _same_day_shift_gap_minutes(existing_shift, shift)
        same_location = existing_shift.location_id == shift.location_id
        assignment_details: dict[str, object] = {
            "shift_id": str(existing_shift.id),
            "location_id": str(existing_shift.location_id),
            "same_location": same_location,
            "overlap_minutes": round(overlap_minutes, 2),
            "gap_minutes": round(gap_minutes, 2),
        }

        if same_location:
            if overlap_minutes > float(policy.same_location_overlap_minutes):
                assignment_details["reason"] = "same_location_overlap_exceeds_limit"
                details["existing_assignments"].append(assignment_details)
                details["reason"] = "same_location_overlap_exceeds_limit"
                return _SameDayShiftPolicyResult(
                    eligible=False,
                    second_shift_detected=True,
                    penalty_multiplier=1.0,
                    details=details,
                )
            details["existing_assignments"].append(assignment_details)
            continue

        if not policy.cross_location_shift_coverage_allowed:
            assignment_details["reason"] = "cross_location_shift_coverage_disabled"
            details["existing_assignments"].append(assignment_details)
            details["reason"] = "cross_location_shift_coverage_disabled"
            return _SameDayShiftPolicyResult(
                eligible=False,
                second_shift_detected=True,
                penalty_multiplier=1.0,
                details=details,
            )

        if overlap_minutes > 0:
            assignment_details["reason"] = "cross_location_overlap_not_allowed"
            details["existing_assignments"].append(assignment_details)
            details["reason"] = "cross_location_overlap_not_allowed"
            return _SameDayShiftPolicyResult(
                eligible=False,
                second_shift_detected=True,
                penalty_multiplier=1.0,
                details=details,
            )

        if gap_minutes < float(policy.cross_location_min_gap_minutes):
            assignment_details["reason"] = "cross_location_gap_below_minimum"
            details["existing_assignments"].append(assignment_details)
            details["reason"] = "cross_location_gap_below_minimum"
            return _SameDayShiftPolicyResult(
                eligible=False,
                second_shift_detected=True,
                penalty_multiplier=1.0,
                details=details,
            )

        other_location = getattr(existing_shift, "location", None)
        if other_location is None:
            assignment_details["reason"] = "cross_location_missing_location"
            details["existing_assignments"].append(assignment_details)
            details["reason"] = "cross_location_missing_location"
            return _SameDayShiftPolicyResult(
                eligible=False,
                second_shift_detected=True,
                penalty_multiplier=1.0,
                details=details,
            )

        open_location_key = _location_identity_key(shift.location)
        other_location_key = _location_identity_key(other_location)
        assignment_details["same_locality"] = (
            open_location_key is not None and other_location_key is not None and open_location_key == other_location_key
        )
        if not assignment_details["same_locality"]:
            assignment_details["reason"] = "cross_location_locality_mismatch"
            details["existing_assignments"].append(assignment_details)
            details["reason"] = "cross_location_locality_mismatch"
            return _SameDayShiftPolicyResult(
                eligible=False,
                second_shift_detected=True,
                penalty_multiplier=1.0,
                details=details,
            )

        distance_miles = _distance_miles(
            left_lat=float(shift.location.latitude) if getattr(shift.location, "latitude", None) is not None else None,
            left_lng=float(shift.location.longitude) if getattr(shift.location, "longitude", None) is not None else None,
            right_lat=float(other_location.latitude) if getattr(other_location, "latitude", None) is not None else None,
            right_lng=float(other_location.longitude) if getattr(other_location, "longitude", None) is not None else None,
        )
        assignment_details["distance_miles"] = round(distance_miles, 2) if distance_miles is not None else None
        if distance_miles is None:
            assignment_details["reason"] = "cross_location_distance_unknown"
            details["existing_assignments"].append(assignment_details)
            details["reason"] = "cross_location_distance_unknown"
            return _SameDayShiftPolicyResult(
                eligible=False,
                second_shift_detected=True,
                penalty_multiplier=1.0,
                details=details,
            )

        if distance_miles > float(policy.cross_location_max_radius_miles):
            assignment_details["reason"] = "cross_location_outside_radius"
            details["existing_assignments"].append(assignment_details)
            details["reason"] = "cross_location_outside_radius"
            return _SameDayShiftPolicyResult(
                eligible=False,
                second_shift_detected=True,
                penalty_multiplier=1.0,
                details=details,
            )

        details["existing_assignments"].append(assignment_details)

    details["penalty_multiplier"] = _SAME_DAY_SECOND_SHIFT_PENALTY_MULTIPLIER
    return _SameDayShiftPolicyResult(
        eligible=True,
        second_shift_detected=True,
        penalty_multiplier=_SAME_DAY_SECOND_SHIFT_PENALTY_MULTIPLIER,
        details=details,
    )


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


def _coverage_settings_int(payload: dict | None, *keys: str) -> Optional[int]:
    if not payload:
        return None
    coverage_settings = payload.get("coverage")
    if isinstance(coverage_settings, dict):
        for key in keys:
            value = coverage_settings.get(key)
            try:
                if value is not None:
                    return max(0, int(value))
            except (TypeError, ValueError):
                continue
    for key in keys:
        value = payload.get(key)
        try:
            if value is not None:
                return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return None


def _coverage_business_policy(payload: dict | None) -> _CoverageBusinessPolicy:
    same_day_second_shift_allowed = _coverage_settings_enabled(
        payload,
        "same_day_second_shift_allowed",
    )
    same_location_overlap_minutes = _coverage_settings_int(
        payload,
        "same_location_overlap_minutes",
    )
    cross_location_shift_coverage_allowed = _coverage_settings_enabled(
        payload,
        "cross_location_shift_coverage_allowed",
        "cross_location_enabled",
        "phase_2_enabled",
        "cross_location_opt_in",
    )
    cross_location_min_gap_minutes = _coverage_settings_int(
        payload,
        "cross_location_min_gap_minutes",
    )
    cross_location_max_radius_miles = _coverage_settings_int(
        payload,
        "cross_location_max_radius_miles",
    )
    return _CoverageBusinessPolicy(
        same_day_second_shift_allowed=(
            _DEFAULT_SAME_DAY_SECOND_SHIFT_ALLOWED
            if same_day_second_shift_allowed is None
            else same_day_second_shift_allowed
        ),
        same_location_overlap_minutes=(
            _DEFAULT_SAME_LOCATION_OVERLAP_MINUTES
            if same_location_overlap_minutes is None
            else same_location_overlap_minutes
        ),
        cross_location_shift_coverage_allowed=(
            _DEFAULT_CROSS_LOCATION_SHIFT_COVERAGE_ALLOWED
            if cross_location_shift_coverage_allowed is None
            else cross_location_shift_coverage_allowed
        ),
        cross_location_min_gap_minutes=(
            _DEFAULT_CROSS_LOCATION_MIN_GAP_MINUTES
            if cross_location_min_gap_minutes is None
            else cross_location_min_gap_minutes
        ),
        cross_location_max_radius_miles=(
            _DEFAULT_CROSS_LOCATION_MAX_RADIUS_MILES
            if cross_location_max_radius_miles is None
            else cross_location_max_radius_miles
        ),
    )


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
    business_policy = _coverage_business_policy(business.settings)
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

    if not business_policy.cross_location_shift_coverage_allowed:
        return False, "business_cross_location_disabled"

    if phase_1_candidate_count == 0:
        return True, "phase_1_exhausted"

    if location_enabled is True or role_enabled is True:
        return True, "cross_location_enabled"

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
    queue = [dict(item) for item in raw_queue if isinstance(item, dict)]
    queue.sort(key=lambda item: int(item.get("position", 0) or 0))
    return queue


def _standby_entry_status(entry: dict) -> str:
    return str(entry.get("status") or "ready").strip().lower() or "ready"


def _parse_uuid(value: object | None) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _is_standby_activation_offer(offer: CoverageOffer) -> bool:
    return bool((offer.offer_metadata or {}).get("standby_activation"))


def _record_standby_queue_result(
    coverage_case: CoverageCase,
    offer: CoverageOffer,
    *,
    status: str,
    occurred_at: datetime,
    assignment: ShiftAssignment | None = None,
) -> None:
    standby_queue = _standby_queue_for_case(coverage_case)
    if not standby_queue:
        return

    source_offer_id = str((offer.offer_metadata or {}).get("standby_source_offer_id") or "").strip()
    updated = False
    for entry in standby_queue:
        activation_offer_id = str(entry.get("activation_offer_id") or "").strip()
        original_offer_id = str(entry.get("offer_id") or "").strip()
        if activation_offer_id == str(offer.id) or (
            source_offer_id and original_offer_id == source_offer_id
        ):
            entry["status"] = status
            entry["last_status_at"] = occurred_at.isoformat()
            if status == "promoted":
                entry["promoted_at"] = occurred_at.isoformat()
                entry["promotion_offer_id"] = str(offer.id)
                if assignment is not None:
                    entry["promotion_assignment_id"] = str(assignment.id)
            else:
                entry["last_terminal_offer_id"] = str(offer.id)
            updated = True
            break

    if updated:
        _update_case_metadata(coverage_case, standby_queue=standby_queue)


def _update_case_metadata(coverage_case: CoverageCase, **updates: object) -> None:
    coverage_case.case_metadata = {
        **(coverage_case.case_metadata or {}),
        **updates,
    }


def _excluded_employee_ids_for_case(coverage_case: CoverageCase | None) -> set[UUID]:
    if coverage_case is None:
        return set()
    metadata = coverage_case.case_metadata if isinstance(coverage_case.case_metadata, dict) else {}
    raw_ids = metadata.get("excluded_employee_ids")
    if not isinstance(raw_ids, list):
        return set()
    excluded: set[UUID] = set()
    for raw in raw_ids:
        parsed = _parse_uuid(raw)
        if parsed is not None:
            excluded.add(parsed)
    return excluded


def _filter_candidates_for_case(
    coverage_case: CoverageCase | None,
    candidates: list[CoverageCandidatePreview],
) -> list[CoverageCandidatePreview]:
    excluded_employee_ids = _excluded_employee_ids_for_case(coverage_case)
    if not excluded_employee_ids:
        return candidates
    filtered = [
        candidate
        for candidate in candidates
        if candidate.employee_id not in excluded_employee_ids
    ]
    return [
        candidate.model_copy(update={"rank": index + 1})
        for index, candidate in enumerate(filtered)
    ]


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


async def activate_standby_queue(
    session: AsyncSession,
    *,
    coverage_case: CoverageCase,
    shift: Shift,
    reference_time: datetime,
    channel: str | None = None,
    dispatch_limit: int = 1,
) -> list[CoverageOffer]:
    standby_queue = _standby_queue_for_case(coverage_case)
    if not standby_queue:
        return []

    offers_result = await session.execute(
        select(CoverageOffer).where(CoverageOffer.coverage_case_id == coverage_case.id)
    )
    existing_offers = list(offers_result.scalars().all())
    offers_by_id = {offer.id: offer for offer in existing_offers}

    created: list[CoverageOffer] = []
    for entry in standby_queue:
        if len(created) >= max(1, dispatch_limit):
            break

        status = _standby_entry_status(entry)
        if status not in {"ready", "accepted"}:
            continue

        employee_id = _parse_uuid(entry.get("employee_id"))
        source_offer = offers_by_id.get(_parse_uuid(entry.get("offer_id")) or UUID(int=0))
        if source_offer is None:
            source_offer = next(
                (
                    item
                    for item in existing_offers
                    if str(item.employee_id) == str(employee_id)
                    and item.offer_metadata.get("accepted_as_standby") is True
                ),
                None,
            )
        if employee_id is None or source_offer is None:
            entry["status"] = "invalid"
            continue

        active_offer = next(
            (
                item
                for item in existing_offers
                if item.employee_id == employee_id
                and item.status in {OfferStatus.pending, OfferStatus.delivered}
            ),
            None,
        )
        if active_offer is not None:
            continue

        channel_value = channel or (
            source_offer.channel.value if hasattr(source_offer.channel, "value") else str(source_offer.channel)
        )
        premium_cents = int((source_offer.offer_metadata or {}).get("premium_cents", 0) or 0)
        standby_position = int(entry.get("position", len(created) + 1) or (len(created) + 1))
        activation_count = sum(
            1
            for item in existing_offers
            if str((item.offer_metadata or {}).get("standby_source_offer_id") or "") == str(source_offer.id)
        ) + 1
        expires_at = reference_time + timedelta(minutes=5)
        reactivation_offer = CoverageOffer(
            coverage_case_id=coverage_case.id,
            coverage_case_run_id=source_offer.coverage_case_run_id,
            coverage_candidate_id=source_offer.coverage_candidate_id,
            employee_id=employee_id,
            channel=OutboxChannel(channel_value),
            status=OfferStatus.pending,
            idempotency_key=f"{coverage_case.id}:standby:{source_offer.id}:{activation_count}:{channel_value}",
            expires_at=expires_at,
            offer_metadata={
                **(source_offer.offer_metadata or {}),
                "operating_mode": "standby_queue",
                "standby_activation": True,
                "standby_source_offer_id": str(source_offer.id),
                "standby_position": standby_position,
                "reactivated_from_standby": True,
                "premium_cents": premium_cents,
            },
        )
        session.add(reactivation_offer)
        await session.flush()
        session.add(
            OutboxEvent(
                aggregate_type="coverage_offer",
                aggregate_id=reactivation_offer.id,
                topic="coverage.offer.created",
                channel=OutboxChannel(channel_value),
                status=OutboxStatus.pending,
                available_at=reference_time,
                payload={
                    "offer_id": str(reactivation_offer.id),
                    "coverage_case_id": str(coverage_case.id),
                    "coverage_case_run_id": str(source_offer.coverage_case_run_id)
                    if source_offer.coverage_case_run_id is not None
                    else None,
                    "employee_id": str(employee_id),
                    "shift_id": str(shift.id),
                    "channel": channel_value,
                    "operating_mode": "standby_queue",
                    "premium_cents": premium_cents,
                    "phone_e164": reactivation_offer.offer_metadata.get("phone_e164"),
                },
            )
        )
        await outreach_service.append_outreach_attempt_event(
            session,
            event_type=platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_QUEUED,
            compatibility_event_name="coverage.offer.created",
            offer=reactivation_offer,
            business_id=shift.business_id,
            location_id=shift.location_id,
            shift_id=shift.id,
            metadata={
                "channel": "coverage_service",
                "operating_mode": "standby_queue",
            },
        )
        entry["status"] = "activated"
        entry["activation_offer_id"] = str(reactivation_offer.id)
        entry["activation_requested_at"] = reference_time.isoformat()
        entry["activation_count"] = int(entry.get("activation_count", 0) or 0) + 1
        created.append(reactivation_offer)

    if created:
        coverage_transitions.mark_case_running(coverage_case)
        _update_case_metadata(
            coverage_case,
            standby_queue=standby_queue,
            standby_last_activated_at=reference_time.isoformat(),
        )
        await session.flush()
    return created


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

    if _is_standby_activation_offer(offer):
        terminal_status = str(offer.status.value if hasattr(offer.status, "value") else offer.status)
        _record_standby_queue_result(
            coverage_case,
            offer,
            status=terminal_status,
            occurred_at=reference_time,
        )

    standby_offers = await activate_standby_queue(
        session,
        coverage_case=coverage_case,
        shift=shift,
        reference_time=reference_time,
        channel=offer.channel.value if hasattr(offer.channel, "value") else str(offer.channel),
        dispatch_limit=1,
    )
    if standby_offers:
        coverage_transitions.mark_case_running(coverage_case)
        return standby_offers, None

    if offer.coverage_case_run_id is None:
        coverage_transitions.mark_case_exhausted(coverage_case, occurred_at=reference_time)
        return [], str(coverage_case.id)

    run = await session.get(CoverageCaseRun, offer.coverage_case_run_id)
    if run is None:
        coverage_transitions.mark_case_exhausted(coverage_case, occurred_at=reference_time)
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
        coverage_transitions.mark_case_running(coverage_case)
        return next_offers, None

    coverage_transitions.mark_case_exhausted(coverage_case, occurred_at=reference_time)
    return [], str(coverage_case.id)


def _employee_location_is_usable(
    employee_location,
    *,
    shift: Shift,
) -> tuple[bool, dict]:
    details = {
        "access_level": employee_location.access_level,
        "can_cover_last_minute": employee_location.can_cover_last_minute,
        "can_blast": employee_location.can_blast,
        "travel_radius_miles": employee_location.travel_radius_miles,
    }
    if employee_location.access_level not in {"approved", "trusted"}:
        details["reason"] = "employee_location_not_approved"
        return False, details

    distance_miles = _distance_miles(
        left_lat=float(shift.location.latitude) if getattr(shift.location, "latitude", None) is not None else None,
        left_lng=float(shift.location.longitude) if getattr(shift.location, "longitude", None) is not None else None,
        right_lat=float(employee_location.location.latitude)
        if getattr(employee_location.location, "latitude", None) is not None
        else None,
        right_lng=float(employee_location.location.longitude)
        if getattr(employee_location.location, "longitude", None) is not None
        else None,
    )
    if distance_miles is not None:
        details["distance_miles"] = round(distance_miles, 2)
    if employee_location.travel_radius_miles is not None and distance_miles is not None:
        if distance_miles > employee_location.travel_radius_miles:
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


def _excluded_employee_ids_for_shift(shift: Shift) -> set[UUID]:
    metadata = shift.shift_metadata if isinstance(shift.shift_metadata, dict) else {}
    excluded: set[UUID] = set()

    published_amendment = metadata.get("published_amendment")
    if isinstance(published_amendment, dict):
        employee_id = published_amendment.get("employee_id")
        if employee_id not in (None, ""):
            try:
                excluded.add(UUID(str(employee_id).strip()))
            except (TypeError, ValueError):
                pass

        amended_employee_ids = published_amendment.get("amended_employee_ids")
        if isinstance(amended_employee_ids, list):
            for employee_id in amended_employee_ids:
                if employee_id in (None, ""):
                    continue
                try:
                    excluded.add(UUID(str(employee_id).strip()))
                except (TypeError, ValueError):
                    continue

    coverage_metadata = metadata.get("coverage")
    if isinstance(coverage_metadata, dict):
        excluded_employee_ids = coverage_metadata.get("excluded_employee_ids")
        if isinstance(excluded_employee_ids, list):
            for employee_id in excluded_employee_ids:
                if employee_id in (None, ""):
                    continue
                try:
                    excluded.add(UUID(str(employee_id).strip()))
                except (TypeError, ValueError):
                    continue

    return excluded


async def list_campaigns(session: AsyncSession, business_id: UUID) -> list[CoverageCase]:
    result = await session.execute(
        select(CoverageCase)
        .join(Shift, CoverageCase.shift_id == Shift.id)
        .where(Shift.business_id == business_id)
        .order_by(CoverageCase.created_at.desc())
    )
    return list(result.scalars().all())


async def create_campaign(
    session: AsyncSession,
    business_id: UUID,
    payload: CoverageCampaignCreate,
) -> CoverageCase:
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
        case_metadata=payload.campaign_metadata,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return case


async def _load_campaign_shift(
    session: AsyncSession,
    business_id: UUID,
    campaign_id: UUID,
) -> tuple[CoverageCase, Shift]:
    case = await session.get(CoverageCase, campaign_id)
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


async def plan_campaign_execution(
    session: AsyncSession,
    business_id: UUID,
    campaign_id: UUID,
) -> CoverageCampaignExecutionDecision:
    case, shift = await _load_campaign_shift(session, business_id, campaign_id)
    _, phase_1_candidates = await _collect_phase_1_candidates(session, business_id, shift.id)
    phase_1_candidates = _filter_candidates_for_case(case, phase_1_candidates)
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
        phase_2_candidates = _filter_candidates_for_case(case, phase_2_candidates)
        phase_2_candidate_count = len(phase_2_candidates)
        if phase_2_candidates:
            recommended_phase = "phase_2"
            recommendation_reason = phase_2_plan.phase_2_reason or "phase_2_available"
        else:
            recommendation_reason = "phase_2_no_candidates"
    else:
        recommendation_reason = phase_2_plan.phase_2_reason or "phase_2_not_eligible"

    return CoverageCampaignExecutionDecision(
        campaign_id=case.id,
        shift_id=shift.id,
        recommended_phase=recommended_phase,
        recommendation_reason=recommendation_reason,
        phase_1_candidate_count=len(phase_1_candidates),
        phase_2_candidate_count=phase_2_candidate_count,
        phase_1_plan=phase_1_plan,
        phase_2_plan=phase_2_plan,
    )


async def execute_next_campaign_phase(
    session: AsyncSession,
    business_id: UUID,
    campaign_id: UUID,
    payload: CoverageCampaignDispatchRequest,
) -> CoverageCampaignDispatchResult:
    decision = await plan_campaign_execution(session, business_id, campaign_id)
    selected_phase = payload.phase_override or decision.recommended_phase

    if selected_phase == "phase_1":
        result = await execute_phase_1_run(
            session,
            business_id,
            campaign_id,
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
        return CoverageCampaignDispatchResult(
            decision=decision,
            phase_executed="phase_1",
            campaign=result.campaign,
            run=result.run,
            plan=result.plan,
            candidate_count=result.candidate_count,
            outreach_attempts=result.outreach_attempts,
            offers=result.offers,
        )

    if selected_phase == "phase_2":
        result = await execute_phase_2_run(
            session,
            business_id,
            campaign_id,
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
        return CoverageCampaignDispatchResult(
            decision=decision,
            phase_executed="phase_2",
            campaign=result.campaign,
            run=result.run,
            plan=result.plan,
            candidate_count=result.candidate_count,
            outreach_attempts=result.outreach_attempts,
            offers=result.offers,
        )

    case, _shift = await _load_campaign_shift(session, business_id, campaign_id)
    coverage_transitions.mark_case_exhausted(case, occurred_at=datetime.now(timezone.utc))
    await session.commit()
    await session.refresh(case)
    return CoverageCampaignDispatchResult(
        decision=decision,
        phase_executed=None,
        campaign=case,
        outreach_attempts=[],
    )


async def list_coverage_cases(session: AsyncSession, business_id: UUID) -> list[CoverageCase]:
    return await list_campaigns(session, business_id)


async def create_coverage_case(
    session: AsyncSession,
    business_id: UUID,
    payload: CoverageCampaignCreate,
) -> CoverageCase:
    return await create_campaign(session, business_id, payload)


async def _load_coverage_case_shift(
    session: AsyncSession,
    business_id: UUID,
    coverage_case_id: UUID,
) -> tuple[CoverageCase, Shift]:
    return await _load_campaign_shift(session, business_id, coverage_case_id)


async def plan_coverage_case_execution(
    session: AsyncSession,
    business_id: UUID,
    coverage_case_id: UUID,
) -> CoverageCampaignExecutionDecision:
    return await plan_campaign_execution(session, business_id, coverage_case_id)


async def execute_next_coverage_phase(
    session: AsyncSession,
    business_id: UUID,
    coverage_case_id: UUID,
    payload: CoverageCampaignDispatchRequest,
) -> CoverageCampaignDispatchResult:
    return await execute_next_campaign_phase(session, business_id, coverage_case_id, payload)


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

    business = await _get_shift_business(session, business_id)
    business_policy = _coverage_business_policy(business.settings)
    excluded_employee_ids = _excluded_employee_ids_for_shift(shift)

    result = await session.execute(
        select(Employee)
        .join(EmployeeRole, EmployeeRole.employee_id == Employee.id)
        .options(
            selectinload(Employee.employee_roles),
            selectinload(Employee.employee_locations),
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
    same_day_assignments_by_employee = await _load_same_day_assignments(
        session,
        employee_ids=employee_ids,
        shift=shift,
    )

    reference_time = datetime.now(timezone.utc)
    policy_metadata = _policy_explanation_metadata(generated_at=reference_time)
    score_snapshot_states = await runtime_projections.refresh_employee_score_snapshots(
        session,
        employees,
        now=reference_time,
    )

    outreach_guardrails = await runtime_projections.build_outreach_guardrail_snapshots(
        session,
        employees,
        shift=shift,
        now=reference_time,
    )

    candidates: list[CoverageCandidatePreview] = []
    for employee in employees:
        if employee.id in excluded_employee_ids:
            continue
        employee_location = next(
            (
                record
                for record in employee.employee_locations
                if record.location_id == shift.location_id
                and record.access_level in {"approved", "trusted"}
            ),
            None,
        )
        if employee_location is None:
            continue

        available, availability_snapshot = _is_available_for_shift(employee, shift)
        if not available:
            continue

        role_match = next((record for record in employee.employee_roles if record.role_id == shift.role_id), None)
        proficiency_level = role_match.proficiency_level if role_match else 1
        is_primary_role = bool(role_match and role_match.is_primary)
        is_primary_location = employee.primary_location_id == shift.location_id

        score, scoring_factors = _normalize_candidate_score(
            reliability_score=float(employee.reliability_score or 0.7),
            avg_response_time_seconds=employee.avg_response_time_seconds,
            proficiency_level=proficiency_level,
            is_primary_role=is_primary_role,
            is_primary_location=is_primary_location,
            can_blast=employee_location.can_blast,
        )
        guardrails = outreach_guardrails.get(employee.id, {})
        if bool(guardrails.get("hard_excluded")):
            continue
        guardrail_multiplier = float(guardrails.get("overall_multiplier") or 1.0)
        scoring_factors["outreach_guardrails"] = guardrails
        scoring_factors["guardrail_multiplier"] = guardrail_multiplier
        if isinstance(guardrails.get("overtime_projection"), dict):
            scoring_factors["overtime_projection"] = guardrails["overtime_projection"]
        same_day_policy = _evaluate_same_day_shift_policy(
            shift=shift,
            assignments=same_day_assignments_by_employee.get(employee.id, []),
            policy=business_policy,
        )
        if not same_day_policy.eligible:
            continue
        second_shift_multiplier = float(same_day_policy.penalty_multiplier or 1.0)
        score = round(score * second_shift_multiplier, 3)
        score = round(score * guardrail_multiplier, 3)
        scoring_factors["same_day_shift_policy"] = same_day_policy.details
        scoring_factors["same_day_shift_penalty_multiplier"] = second_shift_multiplier
        scoring_factors["score_snapshot"] = score_snapshot_states.get(
            employee.id,
            runtime_projections.score_snapshot_state(employee, now=reference_time),
        )
        scoring_factors.update(policy_metadata)
        scoring_factors["total"] = score

        candidates.append(
            CoverageCandidatePreview(
                employee_id=employee.id,
                employee_name=employee.full_name,
                phone_e164=employee.phone_e164,
                primary_location_id=employee.primary_location_id,
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

    business = await _get_shift_business(session, business_id)
    business_policy = _coverage_business_policy(business.settings)
    excluded_employee_ids = _excluded_employee_ids_for_shift(shift)

    result = await session.execute(
        select(Employee)
        .join(EmployeeRole, EmployeeRole.employee_id == Employee.id)
        .options(
            selectinload(Employee.employee_roles),
            selectinload(Employee.employee_locations).selectinload(EmployeeLocation.location),
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
    worked_location_counts: dict[UUID, int] = {}
    if employee_ids:
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
    same_day_assignments_by_employee = await _load_same_day_assignments(
        session,
        employee_ids=employee_ids,
        shift=shift,
    )

    reference_time = datetime.now(timezone.utc)
    policy_metadata = _policy_explanation_metadata(generated_at=reference_time)
    score_snapshot_states = await runtime_projections.refresh_employee_score_snapshots(
        session,
        employees,
        now=reference_time,
    )

    outreach_guardrails = await runtime_projections.build_outreach_guardrail_snapshots(
        session,
        employees,
        shift=shift,
        now=reference_time,
    )

    candidates: list[CoverageCandidatePreview] = []
    for employee in employees:
        if employee.id in excluded_employee_ids:
            continue
        if employee.primary_location_id == shift.location_id:
            continue

        employee_location = next(
            (
                record
                for record in employee.employee_locations
                if record.location_id == shift.location_id
            ),
            None,
        )
        if employee_location is None:
            continue
        employee_location_ok, employee_location_details = _employee_location_is_usable(
            employee_location,
            shift=shift,
        )
        if not employee_location_ok:
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
            is_primary_location=False,
            can_blast=employee_location.can_blast,
        )
        score += location_affinity_bonus
        scoring_factors["location_affinity_count"] = prior_location_count
        scoring_factors["location_affinity_bonus"] = location_affinity_bonus
        scoring_factors["employee_location"] = employee_location_details
        guardrails = outreach_guardrails.get(employee.id, {})
        if bool(guardrails.get("hard_excluded")):
            continue
        guardrail_multiplier = float(guardrails.get("overall_multiplier") or 1.0)
        scoring_factors["outreach_guardrails"] = guardrails
        scoring_factors["guardrail_multiplier"] = guardrail_multiplier
        if isinstance(guardrails.get("overtime_projection"), dict):
            scoring_factors["overtime_projection"] = guardrails["overtime_projection"]
        same_day_policy = _evaluate_same_day_shift_policy(
            shift=shift,
            assignments=same_day_assignments_by_employee.get(employee.id, []),
            policy=business_policy,
        )
        if not same_day_policy.eligible:
            continue
        second_shift_multiplier = float(same_day_policy.penalty_multiplier or 1.0)
        score = round(score * second_shift_multiplier, 3)
        score = round(score * guardrail_multiplier, 3)
        scoring_factors["same_day_shift_policy"] = same_day_policy.details
        scoring_factors["same_day_shift_penalty_multiplier"] = second_shift_multiplier
        scoring_factors["score_snapshot"] = score_snapshot_states.get(
            employee.id,
            runtime_projections.score_snapshot_state(employee, now=reference_time),
        )
        scoring_factors.update(policy_metadata)
        scoring_factors["total"] = score

        candidates.append(
            CoverageCandidatePreview(
                employee_id=employee.id,
                employee_name=employee.full_name,
                phone_e164=employee.phone_e164,
                primary_location_id=employee.primary_location_id,
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
    ranked = _filter_candidates_for_case(case, ranked)
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
            "runtime_projections": runtime_projections.build_runtime_projection_metadata(ranked),
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
                "primary_location_id": str(candidate.primary_location_id) if candidate.primary_location_id else None,
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

    if offers:
        coverage_transitions.mark_case_running(case)
    else:
        coverage_transitions.mark_case_exhausted(case, occurred_at=run.finished_at or started_at)

    await session.commit()
    await session.refresh(case)
    await session.refresh(run)
    for offer in offers:
        await session.refresh(offer)

    return Phase1ExecutionResult(
        campaign=case,
        run=run,
        plan=plan,
        candidate_count=len(ranked),
        candidates=ranked,
        outreach_attempts=outreach_service.outreach_attempt_reads_from_offers(offers),
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
    phase_1_candidates = _filter_candidates_for_case(case, phase_1_candidates)
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
    ranked = _filter_candidates_for_case(case, ranked)

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
            "runtime_projections": runtime_projections.build_runtime_projection_metadata(ranked),
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
                "primary_location_id": str(candidate.primary_location_id) if candidate.primary_location_id else None,
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

    if offers:
        coverage_transitions.mark_case_running(case)
    else:
        coverage_transitions.mark_case_exhausted(case, occurred_at=run.finished_at or started_at)

    await session.commit()
    await session.refresh(case)
    await session.refresh(run)
    for offer in offers:
        await session.refresh(offer)

    return Phase2ExecutionResult(
        campaign=case,
        run=run,
        plan=plan,
        candidate_count=len(ranked),
        candidates=ranked,
        outreach_attempts=outreach_service.outreach_attempt_reads_from_offers(offers),
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
    await outreach_service.append_outreach_attempt_event(
        session,
        event_type=platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_QUEUED,
        compatibility_event_name="coverage.offer.created",
        offer=offer,
        business_id=shift.business_id,
        location_id=shift.location_id,
        shift_id=shift.id,
        metadata={
            "channel": "coverage_service",
            "phase_no": phase_no,
            "operating_mode": operating_mode,
        },
    )
    return offer


async def respond_to_offer(
    session: AsyncSession,
    business_id: UUID,
    offer_id: UUID,
    payload: CoverageOfferResponseCreate,
    *,
    actor_type: AuditActorType = AuditActorType.system,
    actor_user_id: UUID | None = None,
    actor_membership_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
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
    if not coverage_transitions.coverage_state.is_actionable_offer_status(offer.status):
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
    publish_note: str | None = None
    if action == "accepted":
        coverage_transitions.mark_offer_accepted(offer, occurred_at=responded_at)
        if shift.seats_filled >= shift.seats_requested:
            shift.status = ShiftStatus.covered
            coverage_transitions.mark_case_filled(coverage_case, occurred_at=responded_at)
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
                        "status": "ready",
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
            if _should_accept_via_published_reassignment(shift):
                from app.services import scheduling as scheduling_service

                amendment_result = await scheduling_service.apply_published_shift_amendment(
                    session,
                    business_id,
                    shift.id,
                    scheduling_service.PublishedShiftAmendmentWrite(
                        action="reassign_shift",
                        reason_code="reassignment",
                        target_employee_id=offer.employee_id,
                        source=_coverage_assignment_source(payload.response_channel),
                        note=payload.response_text or None,
                    ),
                    cancel_active_automation=False,
                )
                assignment = amendment_result.current_assignment
                assignment_status = (
                    assignment.status.value if assignment is not None and hasattr(assignment.status, "value") else None
                )
                if _is_standby_activation_offer(offer):
                    _record_standby_queue_result(
                        coverage_case,
                        offer,
                        status="promoted",
                        occurred_at=responded_at,
                        assignment=assignment,
                    )
                coverage_transitions.mark_case_filled(coverage_case, occurred_at=responded_at)
                _update_case_metadata(
                    coverage_case,
                    confirmed_offer_id=str(offer.id),
                    confirmed_employee_id=str(offer.employee_id),
                    resolution="reassigned",
                )
                publish_note = "Automatically republished after coverage reassignment."
                try:
                    republish_result = await scheduling_service.publish_schedule_week(
                        session,
                        business_id,
                        shift.location_id,
                        amendment_result.week_start_date,
                        scheduling_service.ScheduleWeekPublishWrite(
                            source="coverage_automation",
                            notify_channels=["email"],
                            expected_shift_ids=[],
                            note=publish_note,
                        ),
                    )
                except scheduling_service.ScheduleWeekPublishConflictError as exc:
                    _update_case_metadata(
                        coverage_case,
                        auto_republish_status="skipped_due_to_draft_conflict",
                        auto_republish_week_start_date=exc.week_start_date.isoformat(),
                        auto_republish_draft_shift_count=exc.draft_shift_count,
                    )
                else:
                    _update_case_metadata(
                        coverage_case,
                        auto_republish_status="published",
                        auto_republish_week_start_date=republish_result.week_start_date.isoformat(),
                        auto_republish_notification_employee_count=(
                            republish_result.notification_enqueued_employee_count
                        ),
                    )
                    await platform_events.append(
                        session,
                        event_type=platform_events.PlatformEventType.SCHEDULE_WEEK_PUBLISHED,
                        target_type="location",
                        target_id=shift.location_id,
                        business_id=business_id,
                        location_id=coverage_case.location_id,
                        actor_type=AuditActorType.system,
                        payload=scheduling_service.build_schedule_week_publish_response(
                            republish_result
                        ).model_dump(mode="json"),
                        metadata={
                            "source": "coverage_automation",
                            "note": publish_note,
                        },
                    )
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

                if _is_standby_activation_offer(offer):
                    _record_standby_queue_result(
                        coverage_case,
                        offer,
                        status="promoted",
                        occurred_at=responded_at,
                        assignment=assignment,
                    )

                shift.seats_filled += 1
                if shift.seats_filled >= shift.seats_requested:
                    shift.status = ShiftStatus.covered
                    coverage_transitions.mark_case_filled(coverage_case, occurred_at=responded_at)
                    _update_case_metadata(
                        coverage_case,
                        confirmed_offer_id=str(offer.id),
                        confirmed_employee_id=str(offer.employee_id),
                    )
                else:
                    shift.status = ShiftStatus.filling
                    coverage_transitions.mark_case_running(coverage_case)

            sibling_result = await session.execute(
                select(CoverageOffer).where(
                    CoverageOffer.coverage_case_id == coverage_case.id,
                    CoverageOffer.id != offer.id,
                    CoverageOffer.status.in_([OfferStatus.pending, OfferStatus.delivered]),
                )
            )
            for sibling in sibling_result.scalars().all():
                coverage_transitions.mark_offer_cancelled(
                    sibling,
                    occurred_at=responded_at,
                    reason="shift_filled",
                )
                await delivery_service.mark_offer_attempt_outcome(
                    session,
                    sibling,
                    status=delivery_service.CoverageAttemptStatus.cancelled,
                    occurred_at=responded_at,
                )
                await outreach_service.append_outreach_attempt_event(
                    session,
                    event_type=platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_CANCELLED,
                    compatibility_event_name="coverage.offer.cancelled",
                    offer=sibling,
                    business_id=business_id,
                    location_id=coverage_case.location_id,
                    shift_id=shift.id,
                    metadata={
                        "channel": "coverage_response",
                        "reason": "shift_filled",
                    },
                )

            from app.services import scheduler_sync

            await scheduler_sync.enqueue_writeback(session, shift_id=shift.id)

    else:
        coverage_transitions.mark_offer_declined(offer, occurred_at=responded_at)

        if _is_standby_activation_offer(offer):
            _record_standby_queue_result(
                coverage_case,
                offer,
                status="declined",
                occurred_at=responded_at,
            )

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
            coverage_transitions.mark_case_exhausted(coverage_case, occurred_at=responded_at)

    if action == "accepted":
        contact_attempt = await delivery_service.mark_offer_attempt_outcome(
            session,
            offer,
            status=delivery_service.CoverageAttemptStatus.accepted,
            occurred_at=responded_at,
            response_payload=payload.response_payload,
        )
    else:
        contact_attempt = await delivery_service.mark_offer_attempt_outcome(
            session,
            offer,
            status=delivery_service.CoverageAttemptStatus.declined,
            occurred_at=responded_at,
            response_payload=payload.response_payload,
        )
    await delivery_service.refresh_employee_reliability(session, offer.employee_id, now=responded_at)
    await outreach_service.append_outreach_attempt_event(
        session,
        event_type=(
            platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_ACCEPTED
            if action == "accepted"
            else platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_DECLINED
        ),
        compatibility_event_name=(
            platform_events.PlatformEventType.COVERAGE_OFFER_ACCEPTED
            if action == "accepted"
            else platform_events.PlatformEventType.COVERAGE_OFFER_DECLINED
        ),
        offer=offer,
        attempt=contact_attempt,
        business_id=business_id,
        location_id=coverage_case.location_id,
        shift_id=shift.id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        actor_membership_id=actor_membership_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={
            "channel": payload.response_channel,
            "response_code": payload.response_code,
        },
    )

    await session.commit()
    await session.refresh(offer)
    await session.refresh(response)
    await session.refresh(coverage_case)
    if assignment is not None:
        await session.refresh(assignment)

    return CoverageOfferActionResult(
        offer=offer,
        outreach_attempt=outreach_service.outreach_attempt_read_from_offer(offer, attempt=contact_attempt),
        response=response,
        campaign=coverage_case,
        shift_id=shift.id,
        assignment_id=assignment.id if assignment is not None else None,
        assignment_status=assignment_status or (assignment.status if assignment is not None else None),
    )
