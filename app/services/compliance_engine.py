from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.models.common import ComplianceOverrideArtifactType
from app.models.scheduling import Shift
from app.services import compliance_shift_facts, labor_rules, work_permit_rules

COMPLIANCE_ENGINE_VERSION = "deterministic_compliance_engine_v1"


def evaluate_shift_assignment_compliance(
    profile: labor_rules.LaborRuleProfileSnapshot | None,
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
    reference_time: datetime,
    overtime_projection: Mapping[str, object] | None = None,
    employee_base_hourly_rate_cents: int | None = None,
    employee_date_of_birth: date | None = None,
    employee_minor_school_status: str | None = None,
    employee_work_permit_number: str | None = None,
    employee_work_permit_effective_start_on: date | None = None,
    employee_work_permit_expires_on: date | None = None,
    employee_work_permit_max_daily_minutes: int | None = None,
    employee_work_permit_max_weekly_minutes: int | None = None,
    employee_work_permit_earliest_start_local_time: time | str | None = None,
    employee_work_permit_latest_end_local_time: time | str | None = None,
    employee_work_permit_rule_profile: Mapping[str, object] | None = None,
    business_settings: Mapping[str, object] | None = None,
    location_settings: Mapping[str, object] | None = None,
) -> dict[str, object]:
    compliance_settings = _compliance_settings(
        business_settings=business_settings,
        location_settings=location_settings,
    )
    shift_facts = compliance_shift_facts.build_shift_structure_facts(candidate_shift)
    break_facts = compliance_shift_facts.list_break_facts(candidate_shift)
    if profile is None:
        policy_metadata = _policy_metadata_snapshot(
            business_settings=business_settings,
            location_settings=location_settings,
        )
        return {
            "status": "unresolved",
            "evaluation_source": COMPLIANCE_ENGINE_VERSION,
            "profile_code": None,
            "profile_version_id": None,
            "profile_payload_hash": None,
            "jurisdiction_code": None,
            "blocking_rule_codes": [],
            "warning_rule_codes": [],
            "premium_rule_codes": [],
            "premium_total_cents": 0,
            "premium_components": [],
            "unresolved_premium_rule_codes": [],
            "would_block": False,
            "requires_override": False,
            "rule_results": [],
            "policy_rule_codes": [],
            "policy_settings": _policy_settings_snapshot(compliance_settings),
            "policy_version_id": policy_metadata.get("policy_version_id"),
            "policy_hash": policy_metadata.get("policy_hash"),
            "policy_effective_at": policy_metadata.get("policy_effective_at"),
            "policy_scope": policy_metadata.get("policy_scope"),
            "shift_facts": shift_facts,
            "evaluation_reference_time": reference_time.isoformat(),
        }

    projection = dict(
        overtime_projection
        or labor_rules.evaluate_overtime_projection(
            profile,
            candidate_shift=candidate_shift,
            counted_intervals=counted_intervals,
            reference_time=reference_time,
        )
    )
    rule_results: list[dict[str, object]] = []

    overtime_result = _overtime_rule_result(projection)
    if overtime_result is not None:
        rule_results.append(overtime_result)

    rest_rule = _rest_window_rule(
        profile,
        business_settings=business_settings,
        location_settings=location_settings,
    )
    if rest_rule is not None:
        rule_results.append(
            _rest_window_rule_result(
                rest_rule,
                candidate_shift=candidate_shift,
                counted_intervals=counted_intervals,
            )
        )

    meal_rule = _meal_break_rule(
        profile,
        business_settings=business_settings,
        location_settings=location_settings,
    )
    if meal_rule is not None:
        rule_results.extend(
            _meal_break_rule_results(
                meal_rule,
                candidate_shift=candidate_shift,
                shift_facts=shift_facts,
                break_facts=break_facts,
                employee_base_hourly_rate_cents=employee_base_hourly_rate_cents,
            )
        )

    paid_rest_rule = _paid_rest_break_rule(profile)
    if paid_rest_rule is not None:
        rule_results.append(
            _paid_rest_break_rule_result(
                paid_rest_rule,
                shift_facts=shift_facts,
                break_facts=break_facts,
                employee_base_hourly_rate_cents=employee_base_hourly_rate_cents,
            )
        )

    split_shift_rule = _split_shift_rule(profile)
    if split_shift_rule is not None:
        rule_results.append(
            _split_shift_rule_result(
                split_shift_rule,
                shift_facts=shift_facts,
            )
        )

    spread_of_hours_rule = _spread_of_hours_rule(profile)
    if spread_of_hours_rule is not None:
        rule_results.append(
            _spread_of_hours_rule_result(
                spread_of_hours_rule,
                shift_facts=shift_facts,
            )
        )

    minor_labor_rule = _minor_labor_rule(profile)
    if minor_labor_rule is not None:
        rule_results.extend(
            _minor_labor_rule_results(
                minor_labor_rule,
                candidate_shift=candidate_shift,
                shift_facts=shift_facts,
                counted_intervals=counted_intervals,
                profile=profile,
                compliance_settings=compliance_settings,
                employee_date_of_birth=employee_date_of_birth,
                employee_minor_school_status=employee_minor_school_status,
                employee_work_permit_number=employee_work_permit_number,
                employee_work_permit_effective_start_on=employee_work_permit_effective_start_on,
                employee_work_permit_expires_on=employee_work_permit_expires_on,
                employee_work_permit_max_daily_minutes=employee_work_permit_max_daily_minutes,
                employee_work_permit_max_weekly_minutes=employee_work_permit_max_weekly_minutes,
                employee_work_permit_earliest_start_local_time=employee_work_permit_earliest_start_local_time,
                employee_work_permit_latest_end_local_time=employee_work_permit_latest_end_local_time,
                employee_work_permit_rule_profile=employee_work_permit_rule_profile,
            )
        )

    rule_results.extend(
        _customer_policy_rule_results(
            compliance_settings=compliance_settings,
            shift_facts=shift_facts,
            overtime_projection=projection,
            existing_rule_results=rule_results,
            meal_rule=meal_rule,
            paid_rest_rule=paid_rest_rule,
        )
    )

    blocking_rule_codes = sorted(
        result["rule_code"]
        for result in rule_results
        if str(result.get("status") or "").lower() == "block"
    )
    warning_rule_codes = sorted(
        result["rule_code"]
        for result in rule_results
        if str(result.get("status") or "").lower() == "warning"
    )
    premium_rule_codes = sorted(
        result["rule_code"]
        for result in rule_results
        if bool(result.get("premium_required"))
    )
    premium_summary = _premium_liability_summary(rule_results)
    policy_rule_codes = sorted(
        result["rule_code"]
        for result in rule_results
        if str(result.get("rule_code") or "").startswith("customer_policy_")
    )
    if blocking_rule_codes:
        status = "block"
    elif warning_rule_codes or premium_rule_codes:
        status = "warning"
    else:
        status = "clear"
    policy_metadata = _policy_metadata_snapshot(
        business_settings=business_settings,
        location_settings=location_settings,
    )

    return {
        "status": status,
        "evaluation_source": COMPLIANCE_ENGINE_VERSION,
        "profile_code": profile.code,
        "profile_version_id": str(profile.version_id),
        "profile_payload_hash": profile.payload_hash,
        "jurisdiction_code": profile.jurisdiction_code,
        "blocking_rule_codes": blocking_rule_codes,
        "warning_rule_codes": warning_rule_codes,
        "premium_rule_codes": premium_rule_codes,
        "premium_total_cents": premium_summary["premium_total_cents"],
        "premium_components": premium_summary["premium_components"],
        "unresolved_premium_rule_codes": premium_summary["unresolved_premium_rule_codes"],
        "would_block": bool(blocking_rule_codes),
        "requires_override": bool(blocking_rule_codes),
        "rule_results": rule_results,
        "policy_rule_codes": policy_rule_codes,
        "policy_settings": _policy_settings_snapshot(compliance_settings),
        "policy_version_id": policy_metadata.get("policy_version_id"),
        "policy_hash": policy_metadata.get("policy_hash"),
        "policy_effective_at": policy_metadata.get("policy_effective_at"),
        "policy_scope": policy_metadata.get("policy_scope"),
        "shift_facts": shift_facts,
        "evaluation_reference_time": reference_time.isoformat(),
    }


def compliance_rank(evaluation: Mapping[str, object] | None) -> tuple[int, int, float]:
    payload = dict(evaluation or {})
    status = str(payload.get("status") or "").strip().lower()
    status_rank = {
        "block": 4,
        "warning": 3,
        "clear": 2,
        "unresolved": 1,
    }.get(status, 0)
    blocking_count = len(payload.get("blocking_rule_codes") or [])
    rest_shortfall_hours = 0.0
    for result in payload.get("rule_results") or []:
        if not isinstance(result, Mapping):
            continue
        rest_shortfall_hours = max(
            rest_shortfall_hours,
            _as_float(result.get("missing_rest_hours")) or 0.0,
        )
    return status_rank, blocking_count, rest_shortfall_hours


def coverage_multiplier_for_evaluation(evaluation: Mapping[str, object] | None) -> float:
    if bool((evaluation or {}).get("would_block")):
        return 0.0
    return 1.0


def _overtime_rule_result(projection: Mapping[str, object]) -> dict[str, object] | None:
    status = str(projection.get("status") or "").strip().lower()
    if not status:
        return None
    projected_ot_hours = _as_float(projection.get("projected_ot_hours")) or 0.0
    projected_dt_hours = _as_float(projection.get("projected_dt_hours")) or 0.0
    projected_cost_multiplier = _as_float(projection.get("projected_cost_multiplier")) or 1.0
    warning = status in {"watch", "elevated", "high"} or projected_ot_hours > 0 or projected_dt_hours > 0
    return {
        "rule_code": "overtime_projection",
        "status": "warning" if warning else "clear",
        "reason_codes": list(projection.get("reason_codes") or []),
        "premium_required": projected_ot_hours > 0 or projected_dt_hours > 0,
        "premium_type": "cost_multiplier" if projected_ot_hours > 0 or projected_dt_hours > 0 else None,
        "projected_regular_hours": _as_float(projection.get("projected_regular_hours")) or 0.0,
        "projected_ot_hours": projected_ot_hours,
        "projected_dt_hours": projected_dt_hours,
        "projected_cost_multiplier": projected_cost_multiplier,
        "would_block": False,
    }


def _rest_window_rule(
    profile: labor_rules.LaborRuleProfileSnapshot,
    *,
    business_settings: Mapping[str, object] | None,
    location_settings: Mapping[str, object] | None,
) -> dict[str, object] | None:
    compliance_settings = _compliance_settings(
        business_settings=business_settings,
        location_settings=location_settings,
    )
    legal_minimum_rest_hours = _as_float(profile.rules_json.get("minimum_rest_hours"))
    policy_minimum_rest_hours = _as_float(compliance_settings.get("minimum_rest_hours"))
    raw_hours = legal_minimum_rest_hours
    if raw_hours is None:
        raw_hours = profile.rules_json.get("clopening_min_rest_hours")
    if raw_hours is None:
        raw_hours = profile.rules_json.get("rest_between_shifts_hours")
    minimum_rest_hours = _as_float(raw_hours)
    if policy_minimum_rest_hours is not None:
        minimum_rest_hours = max(minimum_rest_hours or 0.0, policy_minimum_rest_hours)
    if minimum_rest_hours is None or minimum_rest_hours <= 0:
        return None

    legal_written_consent_allowed = _as_bool(profile.rules_json.get("written_consent_allowed"))
    policy_written_consent_allowed = compliance_settings.get("written_consent_allowed")
    return {
        "rule_code": str(
            profile.rules_json.get("rest_window_rule_code")
            or profile.rules_json.get("rule_code")
            or "minimum_rest_window"
        ),
        "minimum_rest_hours": minimum_rest_hours,
        "written_consent_allowed": (
            legal_written_consent_allowed
            if policy_written_consent_allowed is not False
            else False
        ),
        "premium_cents": _as_int(
            profile.rules_json.get("rest_window_premium_cents")
            if profile.rules_json.get("rest_window_premium_cents") is not None
            else profile.rules_json.get("clopening_premium_cents")
        ),
    }


def _meal_break_rule(
    profile: labor_rules.LaborRuleProfileSnapshot,
    *,
    business_settings: Mapping[str, object] | None,
    location_settings: Mapping[str, object] | None,
) -> dict[str, object] | None:
    rules_json = profile.rules_json if isinstance(profile.rules_json, Mapping) else {}
    compliance_settings = _compliance_settings(
        business_settings=business_settings,
        location_settings=location_settings,
    )
    raw_ruleset = str(rules_json.get("meal_break_ruleset") or "").strip().lower()
    enabled = _as_bool(rules_json.get("meal_breaks_required")) or raw_ruleset in {
        "ca_v1",
        "california_v1",
    }
    if not enabled:
        return None

    return {
        "first_rule_code": str(rules_json.get("first_meal_rule_code") or "meal_break_first_window"),
        "second_rule_code": str(rules_json.get("second_meal_rule_code") or "meal_break_second_window"),
        "first_trigger_minutes": _as_int(rules_json.get("first_meal_trigger_minutes")) or 300,
        "first_deadline_minutes": _as_int(rules_json.get("first_meal_deadline_minutes")) or 300,
        "first_min_break_minutes": _as_int(rules_json.get("first_meal_min_break_minutes")) or 30,
        "first_waiver_max_minutes": _as_int(rules_json.get("first_meal_waiver_max_minutes")) or 360,
        "first_waiver_allowed": compliance_settings.get("first_meal_waiver_allowed") is not False,
        "second_trigger_minutes": _as_int(rules_json.get("second_meal_trigger_minutes")) or 600,
        "second_deadline_minutes": _as_int(rules_json.get("second_meal_deadline_minutes")) or 600,
        "second_min_break_minutes": _as_int(rules_json.get("second_meal_min_break_minutes")) or 30,
        "second_waiver_max_minutes": _as_int(rules_json.get("second_meal_waiver_max_minutes")) or 720,
        "second_waiver_allowed": compliance_settings.get("second_meal_waiver_allowed") is not False,
        "first_premium_cents": _as_int(
            rules_json.get("first_meal_premium_cents")
            if rules_json.get("first_meal_premium_cents") is not None
            else rules_json.get("meal_break_premium_cents")
        ),
        "second_premium_cents": _as_int(
            rules_json.get("second_meal_premium_cents")
            if rules_json.get("second_meal_premium_cents") is not None
            else rules_json.get("meal_break_premium_cents")
        ),
    }


def _paid_rest_break_rule(
    profile: labor_rules.LaborRuleProfileSnapshot,
) -> dict[str, object] | None:
    rules_json = profile.rules_json if isinstance(profile.rules_json, Mapping) else {}
    raw_ruleset = str(rules_json.get("rest_break_ruleset") or "").strip().lower()
    enabled = _as_bool(rules_json.get("rest_breaks_required")) or raw_ruleset in {
        "ca_v1",
        "california_v1",
    }
    if not enabled:
        return None
    return {
        "rule_code": str(rules_json.get("rest_break_rule_code") or "paid_rest_break_quota"),
        "min_break_minutes": _as_int(rules_json.get("rest_break_min_minutes")) or 10,
        "premium_cents": _as_int(rules_json.get("rest_break_premium_cents")),
    }


def _split_shift_rule(
    profile: labor_rules.LaborRuleProfileSnapshot,
) -> dict[str, object] | None:
    rules_json = profile.rules_json if isinstance(profile.rules_json, Mapping) else {}
    raw_ruleset = str(rules_json.get("split_shift_ruleset") or "").strip().lower()
    enabled = _as_bool(rules_json.get("split_shift_premium_required")) or raw_ruleset in {
        "ca_v1",
        "california_v1",
    }
    if not enabled:
        return None
    return {
        "rule_code": str(rules_json.get("split_shift_rule_code") or "split_shift_premium"),
        "min_gap_minutes": _as_int(rules_json.get("split_shift_min_gap_minutes")) or 1,
        "premium_cents": _as_int(rules_json.get("split_shift_premium_cents")),
    }


def _spread_of_hours_rule(
    profile: labor_rules.LaborRuleProfileSnapshot,
) -> dict[str, object] | None:
    rules_json = profile.rules_json if isinstance(profile.rules_json, Mapping) else {}
    raw_ruleset = str(rules_json.get("spread_of_hours_ruleset") or "").strip().lower()
    enabled = _as_bool(rules_json.get("spread_of_hours_required")) or raw_ruleset in {
        "ny_v1",
        "new_york_v1",
    }
    if not enabled:
        return None
    configured_premium_cents = _as_int(rules_json.get("spread_of_hours_premium_cents"))
    minimum_wage_cents = _as_int(
        rules_json.get("spread_of_hours_minimum_wage_cents")
        if rules_json.get("spread_of_hours_minimum_wage_cents") is not None
        else rules_json.get("minimum_wage_cents")
    )
    return {
        "rule_code": str(rules_json.get("spread_of_hours_rule_code") or "spread_of_hours_premium"),
        "threshold_minutes": _as_int(rules_json.get("spread_of_hours_threshold_minutes")) or 600,
        "premium_cents": configured_premium_cents if configured_premium_cents > 0 else minimum_wage_cents,
    }


def _rest_window_rule_result(
    rest_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
) -> dict[str, object]:
    minimum_rest_hours = _as_float(rest_rule.get("minimum_rest_hours")) or 0.0
    previous_interval = _latest_interval_before_shift(
        candidate_shift=candidate_shift,
        counted_intervals=counted_intervals,
    )
    if previous_interval is None:
        return {
            "rule_code": str(rest_rule.get("rule_code") or "minimum_rest_window"),
            "status": "clear",
            "reason_codes": ["no_prior_shift_interval"],
            "premium_required": False,
            "would_block": False,
            "minimum_rest_hours": minimum_rest_hours,
        }

    actual_rest_gap_hours = round(
        max(0.0, (candidate_shift.starts_at - previous_interval.end_at).total_seconds() / 3600.0),
        4,
    )
    if actual_rest_gap_hours >= minimum_rest_hours:
        return {
            "rule_code": str(rest_rule.get("rule_code") or "minimum_rest_window"),
            "status": "clear",
            "reason_codes": ["minimum_rest_satisfied"],
            "premium_required": False,
            "would_block": False,
            "minimum_rest_hours": minimum_rest_hours,
            "actual_rest_gap_hours": actual_rest_gap_hours,
            "previous_shift_end_at": previous_interval.end_at.isoformat(),
        }

    reason_codes = ["minimum_rest_window_violation"]
    if _as_bool(rest_rule.get("written_consent_allowed")):
        reason_codes.append("written_consent_required")
    if _as_int(rest_rule.get("premium_cents")):
        reason_codes.append("premium_required_if_overridden")
    return {
        "rule_code": str(rest_rule.get("rule_code") or "minimum_rest_window"),
        "status": "block",
        "reason_codes": reason_codes,
        "premium_required": _as_int(rest_rule.get("premium_cents")) > 0,
        "premium_type": "fixed_cents" if _as_int(rest_rule.get("premium_cents")) > 0 else None,
        "would_block": True,
        "minimum_rest_hours": minimum_rest_hours,
        "actual_rest_gap_hours": actual_rest_gap_hours,
        "missing_rest_hours": round(minimum_rest_hours - actual_rest_gap_hours, 4),
        "previous_shift_end_at": previous_interval.end_at.isoformat(),
        "candidate_shift_start_at": candidate_shift.starts_at.isoformat(),
        "written_consent_allowed": _as_bool(rest_rule.get("written_consent_allowed")),
        "artifact_type_allowed": (
            ComplianceOverrideArtifactType.written_consent.value
            if _as_bool(rest_rule.get("written_consent_allowed"))
            else None
        ),
        "premium_cents": _as_int(rest_rule.get("premium_cents")),
    }


def _meal_break_rule_results(
    meal_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
    employee_base_hourly_rate_cents: int | None,
) -> list[dict[str, object]]:
    scheduled_span_minutes = _as_int(shift_facts.get("scheduled_span_minutes"))
    has_structured_segments = _as_bool(shift_facts.get("has_structured_segments"))
    qualifying_meal_breaks = [
        break_fact
        for break_fact in break_facts
        if str(break_fact.get("break_type") or "") == "meal"
        and not _as_bool(break_fact.get("is_paid"))
        and _as_int(break_fact.get("duration_minutes")) >= _as_int(meal_rule.get("first_min_break_minutes"))
    ]

    results: list[dict[str, object]] = []

    first_trigger_minutes = _as_int(meal_rule.get("first_trigger_minutes"))
    first_deadline_minutes = _as_int(meal_rule.get("first_deadline_minutes"))
    first_waiver_max_minutes = _as_int(meal_rule.get("first_waiver_max_minutes"))
    first_waiver_allowed = _as_bool(meal_rule.get("first_waiver_allowed")) or meal_rule.get("first_waiver_allowed") is True
    first_rule_code = str(meal_rule.get("first_rule_code") or "meal_break_first_window")

    if scheduled_span_minutes > first_trigger_minutes:
        first_meal = next(
            (
                break_fact
                for break_fact in qualifying_meal_breaks
                if _as_int(break_fact.get("start_offset_minutes")) <= first_deadline_minutes
            ),
            None,
        )
        if first_meal is not None:
            results.append(
                {
                    "rule_code": first_rule_code,
                    "status": "clear",
                    "reason_codes": ["first_meal_break_scheduled"],
                    "premium_required": False,
                    "would_block": False,
                    "required_break_minutes": _as_int(meal_rule.get("first_min_break_minutes")),
                    "scheduled_break_minutes": _as_int(first_meal.get("duration_minutes")),
                    "break_start_offset_minutes": _as_int(first_meal.get("start_offset_minutes")),
                }
            )
        else:
            waiver_possible = first_waiver_allowed and scheduled_span_minutes <= first_waiver_max_minutes
            results.append(
                {
                    "rule_code": first_rule_code,
                    "status": (
                        "warning"
                        if waiver_possible or not has_structured_segments
                        else "block"
                    ),
                    "reason_codes": _meal_reason_codes(
                        base_code="first_meal_break_missing",
                        has_structured_segments=has_structured_segments,
                        waiver_possible=waiver_possible,
                        waiver_allowed=first_waiver_allowed,
                    ),
                    "premium_required": True,
                    "premium_type": _resolved_premium_type(
                        configured_premium_cents=_as_int(meal_rule.get("first_premium_cents")),
                        employee_base_hourly_rate_cents=employee_base_hourly_rate_cents,
                    ),
                    "premium_cents": _resolved_premium_cents(
                        configured_premium_cents=_as_int(meal_rule.get("first_premium_cents")),
                        employee_base_hourly_rate_cents=employee_base_hourly_rate_cents,
                    ),
                    "would_block": has_structured_segments and not waiver_possible,
                    "required_break_minutes": _as_int(meal_rule.get("first_min_break_minutes")),
                    "meal_break_window_deadline_minutes": first_deadline_minutes,
                    "waiver_possible": waiver_possible,
                    "artifact_type_allowed": (
                        ComplianceOverrideArtifactType.meal_waiver.value
                        if waiver_possible
                        else None
                    ),
                }
            )

    second_trigger_minutes = _as_int(meal_rule.get("second_trigger_minutes"))
    second_deadline_minutes = _as_int(meal_rule.get("second_deadline_minutes"))
    second_waiver_max_minutes = _as_int(meal_rule.get("second_waiver_max_minutes"))
    second_waiver_allowed = _as_bool(meal_rule.get("second_waiver_allowed")) or meal_rule.get("second_waiver_allowed") is True
    second_rule_code = str(meal_rule.get("second_rule_code") or "meal_break_second_window")
    second_min_break_minutes = _as_int(meal_rule.get("second_min_break_minutes")) or _as_int(
        meal_rule.get("first_min_break_minutes")
    )

    if scheduled_span_minutes > second_trigger_minutes:
        qualifying_second_meal = next(
            (
                break_fact
                for break_fact in qualifying_meal_breaks
                if _as_int(break_fact.get("start_offset_minutes")) <= second_deadline_minutes
            ),
            None,
        )
        if len(qualifying_meal_breaks) >= 2:
            qualifying_second_meal = qualifying_meal_breaks[1]
        if qualifying_second_meal is not None and _as_int(
            qualifying_second_meal.get("duration_minutes")
        ) >= second_min_break_minutes:
            results.append(
                {
                    "rule_code": second_rule_code,
                    "status": "clear",
                    "reason_codes": ["second_meal_break_scheduled"],
                    "premium_required": False,
                    "would_block": False,
                    "required_break_minutes": second_min_break_minutes,
                    "scheduled_break_minutes": _as_int(qualifying_second_meal.get("duration_minutes")),
                    "break_start_offset_minutes": _as_int(qualifying_second_meal.get("start_offset_minutes")),
                }
            )
        else:
            waiver_possible = (
                second_waiver_allowed
                and scheduled_span_minutes <= second_waiver_max_minutes
                and len(qualifying_meal_breaks) >= 1
            )
            results.append(
                {
                    "rule_code": second_rule_code,
                    "status": (
                        "warning"
                        if waiver_possible or not has_structured_segments
                        else "block"
                    ),
                    "reason_codes": _meal_reason_codes(
                        base_code="second_meal_break_missing",
                        has_structured_segments=has_structured_segments,
                        waiver_possible=waiver_possible,
                        waiver_allowed=second_waiver_allowed,
                    ),
                    "premium_required": True,
                    "premium_type": _resolved_premium_type(
                        configured_premium_cents=_as_int(meal_rule.get("second_premium_cents")),
                        employee_base_hourly_rate_cents=employee_base_hourly_rate_cents,
                    ),
                    "premium_cents": _resolved_premium_cents(
                        configured_premium_cents=_as_int(meal_rule.get("second_premium_cents")),
                        employee_base_hourly_rate_cents=employee_base_hourly_rate_cents,
                    ),
                    "would_block": has_structured_segments and not waiver_possible,
                    "required_break_minutes": second_min_break_minutes,
                    "meal_break_window_deadline_minutes": second_deadline_minutes,
                    "waiver_possible": waiver_possible,
                    "artifact_type_allowed": (
                        ComplianceOverrideArtifactType.meal_waiver.value
                        if waiver_possible
                        else None
                    ),
                }
            )

    return results


def _paid_rest_break_rule_result(
    paid_rest_rule: Mapping[str, object],
    *,
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
    employee_base_hourly_rate_cents: int | None,
) -> dict[str, object]:
    net_active_work_minutes = _as_int(shift_facts.get("net_active_work_minutes"))
    has_structured_segments = _as_bool(shift_facts.get("has_structured_segments"))
    required_break_count = _required_california_rest_break_count(net_active_work_minutes)
    min_break_minutes = _as_int(paid_rest_rule.get("min_break_minutes")) or 10
    actual_break_count = len(
        [
            break_fact
            for break_fact in break_facts
            if str(break_fact.get("break_type") or "") == "rest"
            and _as_bool(break_fact.get("is_paid"))
            and _as_int(break_fact.get("duration_minutes")) >= min_break_minutes
        ]
    )
    if required_break_count <= 0:
        return {
            "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
            "status": "clear",
            "reason_codes": ["rest_break_not_required"],
            "premium_required": False,
            "would_block": False,
            "required_break_count": 0,
            "actual_break_count": actual_break_count,
        }

    if actual_break_count >= required_break_count:
        return {
            "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
            "status": "clear",
            "reason_codes": ["rest_break_quota_satisfied"],
            "premium_required": False,
            "would_block": False,
            "required_break_count": required_break_count,
            "actual_break_count": actual_break_count,
            "required_break_minutes": min_break_minutes,
        }

    reason_codes = ["rest_break_quota_missing"]
    if not has_structured_segments:
        reason_codes.append("structured_break_plan_missing")
    return {
        "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
        "status": "warning",
        "reason_codes": reason_codes,
        "premium_required": True,
        "premium_type": _resolved_premium_type(
            configured_premium_cents=_as_int(paid_rest_rule.get("premium_cents")),
            employee_base_hourly_rate_cents=employee_base_hourly_rate_cents,
        ),
        "premium_cents": _resolved_premium_cents(
            configured_premium_cents=_as_int(paid_rest_rule.get("premium_cents")),
            employee_base_hourly_rate_cents=employee_base_hourly_rate_cents,
        ),
        "would_block": False,
        "required_break_count": required_break_count,
        "actual_break_count": actual_break_count,
        "missing_break_count": max(0, required_break_count - actual_break_count),
        "required_break_minutes": min_break_minutes,
    }


def _split_shift_rule_result(
    split_shift_rule: Mapping[str, object],
    *,
    shift_facts: Mapping[str, object],
) -> dict[str, object]:
    rule_code = str(split_shift_rule.get("rule_code") or "split_shift_premium")
    split_shift_detected = _as_bool(shift_facts.get("split_shift_detected"))
    split_shift_gap_count = _as_int(shift_facts.get("split_shift_gap_count"))
    inter_segment_gap_minutes = _as_int(shift_facts.get("inter_segment_gap_minutes"))
    longest_gap_minutes = _as_int(shift_facts.get("longest_inter_segment_gap_minutes"))
    min_gap_minutes = _as_int(split_shift_rule.get("min_gap_minutes")) or 1
    qualifies = split_shift_detected and longest_gap_minutes >= min_gap_minutes
    if not qualifies:
        return {
            "rule_code": rule_code,
            "status": "clear",
            "reason_codes": ["split_shift_not_detected"],
            "premium_required": False,
            "would_block": False,
            "split_shift_gap_count": split_shift_gap_count,
            "inter_segment_gap_minutes": inter_segment_gap_minutes,
            "longest_gap_minutes": longest_gap_minutes,
            "min_gap_minutes": min_gap_minutes,
        }

    premium_cents = _as_int(split_shift_rule.get("premium_cents"))
    premium_type = "fixed_cents" if premium_cents > 0 else "wage_dependent_unresolved"
    reason_codes = ["split_shift_detected"]
    if premium_type == "wage_dependent_unresolved":
        reason_codes.append("wage_dependent_premium_unresolved")
    return {
        "rule_code": rule_code,
        "status": "warning",
        "reason_codes": reason_codes,
        "premium_required": True,
        "premium_type": premium_type,
        "premium_cents": premium_cents,
        "would_block": False,
        "split_shift_gap_count": split_shift_gap_count,
        "inter_segment_gap_minutes": inter_segment_gap_minutes,
        "longest_gap_minutes": longest_gap_minutes,
        "min_gap_minutes": min_gap_minutes,
    }


def _spread_of_hours_rule_result(
    spread_of_hours_rule: Mapping[str, object],
    *,
    shift_facts: Mapping[str, object],
) -> dict[str, object]:
    rule_code = str(spread_of_hours_rule.get("rule_code") or "spread_of_hours_premium")
    scheduled_span_minutes = _as_int(shift_facts.get("scheduled_span_minutes"))
    threshold_minutes = _as_int(spread_of_hours_rule.get("threshold_minutes")) or 600
    qualifies = scheduled_span_minutes > threshold_minutes
    if not qualifies:
        return {
            "rule_code": rule_code,
            "status": "clear",
            "reason_codes": ["spread_of_hours_not_triggered"],
            "premium_required": False,
            "would_block": False,
            "scheduled_span_minutes": scheduled_span_minutes,
            "threshold_minutes": threshold_minutes,
        }

    premium_cents = _as_int(spread_of_hours_rule.get("premium_cents"))
    premium_type = "fixed_cents" if premium_cents > 0 else "wage_dependent_unresolved"
    reason_codes = ["spread_of_hours_detected"]
    if premium_type == "wage_dependent_unresolved":
        reason_codes.append("wage_dependent_premium_unresolved")
    return {
        "rule_code": rule_code,
        "status": "warning",
        "reason_codes": reason_codes,
        "premium_required": True,
        "premium_type": premium_type,
        "premium_cents": premium_cents,
        "would_block": False,
        "scheduled_span_minutes": scheduled_span_minutes,
        "threshold_minutes": threshold_minutes,
        "excess_minutes": max(0, scheduled_span_minutes - threshold_minutes),
    }


def _minor_labor_rule(profile: labor_rules.LaborRuleProfileSnapshot) -> dict[str, object] | None:
    rules_json = profile.rules_json if isinstance(profile.rules_json, Mapping) else {}
    raw_ruleset = str(rules_json.get("minor_ruleset") or "").strip().lower()
    work_permit_required = (
        _as_bool(rules_json.get("minor_work_permit_required"))
        or raw_ruleset in {"ca_v1", "california_v1"}
    )
    daily_max_minutes = _as_int(rules_json.get("minor_daily_max_minutes"))
    weekly_max_minutes = _as_int(rules_json.get("minor_weekly_max_minutes"))
    earliest_start_local_time = _parse_local_time(rules_json.get("minor_earliest_start_local_time"))
    latest_end_local_time = _parse_local_time(rules_json.get("minor_latest_end_local_time"))
    school_status_age_min_years = _as_int(rules_json.get("minor_school_status_age_min_years")) or 14
    school_status_age_max_years = _as_int(rules_json.get("minor_school_status_age_max_years")) or 15
    daily_max_minutes_in_session = _as_int(rules_json.get("minor_daily_max_minutes_in_session"))
    daily_max_minutes_summer_break = _as_int(rules_json.get("minor_daily_max_minutes_summer_break"))
    weekly_max_minutes_in_session = _as_int(rules_json.get("minor_weekly_max_minutes_in_session"))
    weekly_max_minutes_summer_break = _as_int(rules_json.get("minor_weekly_max_minutes_summer_break"))
    daily_max_minutes_school_day = _as_int(rules_json.get("minor_daily_max_minutes_school_day"))
    daily_max_minutes_non_school_day = _as_int(rules_json.get("minor_daily_max_minutes_non_school_day"))
    weekly_max_minutes_school_week = _as_int(rules_json.get("minor_weekly_max_minutes_school_week"))
    weekly_max_minutes_non_school_week = _as_int(rules_json.get("minor_weekly_max_minutes_non_school_week"))
    earliest_start_local_time_school_day = _parse_local_time(
        rules_json.get("minor_earliest_start_local_time_school_day")
    )
    earliest_start_local_time_non_school_day = _parse_local_time(
        rules_json.get("minor_earliest_start_local_time_non_school_day")
    )
    latest_end_local_time_in_session = _parse_local_time(
        rules_json.get("minor_latest_end_local_time_in_session")
    )
    latest_end_local_time_summer_break = _parse_local_time(
        rules_json.get("minor_latest_end_local_time_summer_break")
    )
    latest_end_local_time_school_day = _parse_local_time(
        rules_json.get("minor_latest_end_local_time_school_day")
    )
    latest_end_local_time_non_school_day = _parse_local_time(
        rules_json.get("minor_latest_end_local_time_non_school_day")
    )
    if (
        not work_permit_required
        and daily_max_minutes <= 0
        and weekly_max_minutes <= 0
        and earliest_start_local_time is None
        and latest_end_local_time is None
        and daily_max_minutes_in_session <= 0
        and daily_max_minutes_summer_break <= 0
        and weekly_max_minutes_in_session <= 0
        and weekly_max_minutes_summer_break <= 0
        and daily_max_minutes_school_day <= 0
        and daily_max_minutes_non_school_day <= 0
        and weekly_max_minutes_school_week <= 0
        and weekly_max_minutes_non_school_week <= 0
        and earliest_start_local_time_school_day is None
        and earliest_start_local_time_non_school_day is None
        and latest_end_local_time_in_session is None
        and latest_end_local_time_summer_break is None
        and latest_end_local_time_school_day is None
        and latest_end_local_time_non_school_day is None
    ):
        return None
    return {
        "age_threshold_years": _as_int(rules_json.get("minor_age_threshold_years")) or 18,
        "school_status_age_min_years": school_status_age_min_years,
        "school_status_age_max_years": school_status_age_max_years,
        "work_permit_required": work_permit_required,
        "work_permit_rule_code": str(
            rules_json.get("minor_work_permit_rule_code") or "minor_work_permit_required"
        ),
        "daily_max_minutes": daily_max_minutes,
        "weekly_max_minutes": weekly_max_minutes,
        "daily_max_minutes_in_session": daily_max_minutes_in_session,
        "daily_max_minutes_summer_break": daily_max_minutes_summer_break,
        "weekly_max_minutes_in_session": weekly_max_minutes_in_session,
        "weekly_max_minutes_summer_break": weekly_max_minutes_summer_break,
        "daily_max_minutes_school_day": daily_max_minutes_school_day,
        "daily_max_minutes_non_school_day": daily_max_minutes_non_school_day,
        "weekly_max_minutes_school_week": weekly_max_minutes_school_week,
        "weekly_max_minutes_non_school_week": weekly_max_minutes_non_school_week,
        "daily_limit_rule_code": str(
            rules_json.get("minor_daily_limit_rule_code") or "minor_daily_hours_limit"
        ),
        "weekly_limit_rule_code": str(
            rules_json.get("minor_weekly_limit_rule_code") or "minor_weekly_hours_limit"
        ),
        "earliest_start_local_time": earliest_start_local_time,
        "earliest_start_local_time_school_day": earliest_start_local_time_school_day,
        "earliest_start_local_time_non_school_day": earliest_start_local_time_non_school_day,
        "latest_end_local_time": latest_end_local_time,
        "latest_end_local_time_in_session": latest_end_local_time_in_session,
        "latest_end_local_time_summer_break": latest_end_local_time_summer_break,
        "latest_end_local_time_school_day": latest_end_local_time_school_day,
        "latest_end_local_time_non_school_day": latest_end_local_time_non_school_day,
        "time_window_rule_code": str(
            rules_json.get("minor_time_window_rule_code") or "minor_time_window_restricted"
        ),
    }


def _minor_labor_rule_results(
    minor_labor_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    shift_facts: Mapping[str, object],
    counted_intervals: Sequence[labor_rules.CountedInterval],
    profile: labor_rules.LaborRuleProfileSnapshot,
    compliance_settings: Mapping[str, object],
    employee_date_of_birth: date | None,
    employee_minor_school_status: str | None,
    employee_work_permit_number: str | None,
    employee_work_permit_effective_start_on: date | None,
    employee_work_permit_expires_on: date | None,
    employee_work_permit_max_daily_minutes: int | None,
    employee_work_permit_max_weekly_minutes: int | None,
    employee_work_permit_earliest_start_local_time: time | str | None,
    employee_work_permit_latest_end_local_time: time | str | None,
    employee_work_permit_rule_profile: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    if employee_date_of_birth is None:
        return []

    shift_timezone = _shift_timezone(candidate_shift)
    shift_local_start = candidate_shift.starts_at.astimezone(shift_timezone)
    shift_local_end = candidate_shift.ends_at.astimezone(shift_timezone)
    shift_local_date = shift_local_start.date()
    age_years = _employee_age_on_date(employee_date_of_birth, shift_local_date)
    age_threshold_years = _as_int(minor_labor_rule.get("age_threshold_years")) or 18
    if age_years is None or age_years >= age_threshold_years:
        return []

    results: list[dict[str, object]] = []
    resolved_school_status = _resolved_minor_school_status(employee_minor_school_status)
    is_school_day = _minor_school_day_status(
        compliance_settings=compliance_settings,
        shift_local_date=shift_local_date,
        school_status=resolved_school_status,
    )
    workweek_has_school_day = _minor_workweek_has_school_day(
        profile=profile,
        candidate_shift=candidate_shift,
        compliance_settings=compliance_settings,
        school_status=resolved_school_status,
    )
    precedes_non_school_day = _minor_precedes_non_school_day(
        compliance_settings=compliance_settings,
        shift_local_date=shift_local_date,
        school_status=resolved_school_status,
    )
    normalized_work_permit_number = str(employee_work_permit_number or "").strip()
    work_permit_is_active = bool(normalized_work_permit_number)
    if employee_work_permit_effective_start_on is not None and employee_work_permit_effective_start_on > shift_local_date:
        work_permit_is_active = False
    if employee_work_permit_expires_on is not None and employee_work_permit_expires_on < shift_local_date:
        work_permit_is_active = False
    work_permit_rule_code = str(
        minor_labor_rule.get("work_permit_rule_code") or "minor_work_permit_required"
    )
    if _as_bool(minor_labor_rule.get("work_permit_required")):
        work_permit_reason_codes = ["employee_is_minor"]
        if not normalized_work_permit_number:
            work_permit_reason_codes.append("work_permit_missing")
        elif (
            employee_work_permit_effective_start_on is not None
            and employee_work_permit_effective_start_on > shift_local_date
        ):
            work_permit_reason_codes.append("work_permit_not_yet_effective")
        elif (
            employee_work_permit_expires_on is not None
            and employee_work_permit_expires_on < shift_local_date
        ):
            work_permit_reason_codes.append("work_permit_expired")
        if len(work_permit_reason_codes) > 1:
            results.append(
                {
                    "rule_code": work_permit_rule_code,
                    "status": "block",
                    "reason_codes": work_permit_reason_codes,
                    "premium_required": False,
                    "would_block": True,
                }
            )
        else:
            results.append(
                {
                    "rule_code": work_permit_rule_code,
                    "status": "clear",
                    "reason_codes": ["employee_is_minor", "work_permit_valid"],
                    "premium_required": False,
                    "would_block": False,
                    "effective_start_on": (
                        employee_work_permit_effective_start_on.isoformat()
                        if employee_work_permit_effective_start_on is not None
                        else None
                    ),
                    "expires_on": (
                        employee_work_permit_expires_on.isoformat()
                        if employee_work_permit_expires_on is not None
                        else None
                    ),
                }
            )

    permit_rule_profile = _normalized_work_permit_rule_profile(
        employee_work_permit_rule_profile
    )
    allowed_permit_weekdays = _resolved_work_permit_allowed_weekdays(
        permit_rule_profile
    )
    if work_permit_is_active and allowed_permit_weekdays:
        shift_weekday = _weekday_name_from_date(shift_local_date)
        allowed_weekday_names = [
            _weekday_name_from_number(weekday_number)
            for weekday_number in sorted(allowed_permit_weekdays)
        ]
        if shift_local_date.weekday() not in allowed_permit_weekdays:
            results.append(
                {
                    "rule_code": "minor_work_permit_weekday_restriction",
                    "status": "block",
                    "reason_codes": [
                        "employee_is_minor",
                        "active_work_permit_restriction_applied",
                        "work_permit_weekday_not_allowed",
                    ],
                    "premium_required": False,
                    "would_block": True,
                    "shift_weekday": shift_weekday,
                    "allowed_weekdays": allowed_weekday_names,
                    "permit_number": normalized_work_permit_number,
                }
            )
        else:
            results.append(
                {
                    "rule_code": "minor_work_permit_weekday_restriction",
                    "status": "clear",
                    "reason_codes": [
                        "employee_is_minor",
                        "active_work_permit_restriction_applied",
                        "work_permit_weekday_allowed",
                    ],
                    "premium_required": False,
                    "would_block": False,
                    "shift_weekday": shift_weekday,
                    "allowed_weekdays": allowed_weekday_names,
                    "permit_number": normalized_work_permit_number,
                }
            )

    permit_daily_max_minutes = _resolved_work_permit_daily_max_minutes(
        permit_rule_profile,
        school_status=resolved_school_status,
        is_school_day=is_school_day,
        precedes_non_school_day=precedes_non_school_day,
        fallback_minutes=employee_work_permit_max_daily_minutes,
    )
    if work_permit_is_active and permit_daily_max_minutes > 0:
        projected_minutes = _projected_local_day_minutes(
            candidate_shift=candidate_shift,
            counted_intervals=counted_intervals,
        )
        if projected_minutes > permit_daily_max_minutes:
            results.append(
                {
                    "rule_code": "minor_work_permit_daily_hours_limit",
                    "status": "block",
                    "reason_codes": ["employee_is_minor", "active_work_permit_restriction_applied", "work_permit_daily_minutes_exceeded"],
                    "premium_required": False,
                    "would_block": True,
                    "projected_minutes": projected_minutes,
                    "daily_max_minutes": permit_daily_max_minutes,
                    "excess_minutes": max(0, projected_minutes - permit_daily_max_minutes),
                    "permit_number": normalized_work_permit_number,
                    "minor_school_status": resolved_school_status,
                    "minor_school_day": is_school_day,
                    "minor_precedes_non_school_day": precedes_non_school_day,
                }
            )
        else:
            results.append(
                {
                    "rule_code": "minor_work_permit_daily_hours_limit",
                    "status": "clear",
                    "reason_codes": ["employee_is_minor", "active_work_permit_restriction_applied", "work_permit_daily_minutes_within_limit"],
                    "premium_required": False,
                    "would_block": False,
                    "projected_minutes": projected_minutes,
                    "daily_max_minutes": permit_daily_max_minutes,
                    "permit_number": normalized_work_permit_number,
                    "minor_school_status": resolved_school_status,
                    "minor_school_day": is_school_day,
                    "minor_precedes_non_school_day": precedes_non_school_day,
                }
            )

    permit_weekly_max_minutes = _resolved_work_permit_weekly_max_minutes(
        permit_rule_profile,
        school_status=resolved_school_status,
        workweek_has_school_day=workweek_has_school_day,
        fallback_minutes=employee_work_permit_max_weekly_minutes,
    )
    if work_permit_is_active and permit_weekly_max_minutes > 0:
        projected_weekly_minutes = _projected_workweek_minutes(
            profile=profile,
            candidate_shift=candidate_shift,
            counted_intervals=counted_intervals,
        )
        if projected_weekly_minutes > permit_weekly_max_minutes:
            results.append(
                {
                    "rule_code": "minor_work_permit_weekly_hours_limit",
                    "status": "block",
                    "reason_codes": ["employee_is_minor", "active_work_permit_restriction_applied", "work_permit_weekly_minutes_exceeded"],
                    "premium_required": False,
                    "would_block": True,
                    "projected_minutes": projected_weekly_minutes,
                    "weekly_max_minutes": permit_weekly_max_minutes,
                    "excess_minutes": max(0, projected_weekly_minutes - permit_weekly_max_minutes),
                    "permit_number": normalized_work_permit_number,
                    "minor_school_status": resolved_school_status,
                    "minor_school_week": workweek_has_school_day,
                }
            )
        else:
            results.append(
                {
                    "rule_code": "minor_work_permit_weekly_hours_limit",
                    "status": "clear",
                    "reason_codes": ["employee_is_minor", "active_work_permit_restriction_applied", "work_permit_weekly_minutes_within_limit"],
                    "premium_required": False,
                    "would_block": False,
                    "projected_minutes": projected_weekly_minutes,
                    "weekly_max_minutes": permit_weekly_max_minutes,
                    "permit_number": normalized_work_permit_number,
                    "minor_school_status": resolved_school_status,
                    "minor_school_week": workweek_has_school_day,
                }
            )

    permit_earliest_start_local_time = _resolved_work_permit_earliest_start_local_time(
        permit_rule_profile,
        school_status=resolved_school_status,
        is_school_day=is_school_day,
        fallback_time=employee_work_permit_earliest_start_local_time,
    )
    permit_latest_end_local_time = _resolved_work_permit_latest_end_local_time(
        permit_rule_profile,
        school_status=resolved_school_status,
        is_school_day=is_school_day,
        precedes_non_school_day=precedes_non_school_day,
        fallback_time=employee_work_permit_latest_end_local_time,
    )
    if work_permit_is_active and (
        isinstance(permit_earliest_start_local_time, time)
        or isinstance(permit_latest_end_local_time, time)
    ):
        time_window_reason_codes = ["employee_is_minor", "active_work_permit_restriction_applied"]
        if (
            isinstance(permit_earliest_start_local_time, time)
            and shift_local_start.timetz().replace(tzinfo=None) < permit_earliest_start_local_time
        ):
            time_window_reason_codes.append("work_permit_shift_starts_too_early")
        if (
            isinstance(permit_latest_end_local_time, time)
            and _shift_ends_after_local_time_limit(
                shift_local_start=shift_local_start,
                shift_local_end=shift_local_end,
                latest_end_local_time=permit_latest_end_local_time,
            )
        ):
            time_window_reason_codes.append("work_permit_shift_ends_too_late")
        if len(time_window_reason_codes) > 2:
            results.append(
                {
                    "rule_code": "minor_work_permit_time_window",
                    "status": "block",
                    "reason_codes": time_window_reason_codes,
                    "premium_required": False,
                    "would_block": True,
                    "earliest_start_local_time": (
                        permit_earliest_start_local_time.isoformat()
                        if isinstance(permit_earliest_start_local_time, time)
                        else None
                    ),
                    "latest_end_local_time": (
                        permit_latest_end_local_time.isoformat()
                        if isinstance(permit_latest_end_local_time, time)
                        else None
                    ),
                    "permit_number": normalized_work_permit_number,
                    "minor_school_status": resolved_school_status,
                    "minor_school_day": is_school_day,
                    "minor_precedes_non_school_day": precedes_non_school_day,
                }
            )
        else:
            results.append(
                {
                    "rule_code": "minor_work_permit_time_window",
                    "status": "clear",
                    "reason_codes": ["employee_is_minor", "active_work_permit_restriction_applied", "work_permit_time_window_satisfied"],
                    "premium_required": False,
                    "would_block": False,
                    "earliest_start_local_time": (
                        permit_earliest_start_local_time.isoformat()
                        if isinstance(permit_earliest_start_local_time, time)
                        else None
                    ),
                    "latest_end_local_time": (
                        permit_latest_end_local_time.isoformat()
                        if isinstance(permit_latest_end_local_time, time)
                        else None
                    ),
                    "permit_number": normalized_work_permit_number,
                    "minor_school_status": resolved_school_status,
                    "minor_school_day": is_school_day,
                    "minor_precedes_non_school_day": precedes_non_school_day,
                }
            )

    daily_max_minutes = _resolved_minor_daily_max_minutes(
        minor_labor_rule,
        age_years=age_years,
        school_status=resolved_school_status,
        is_school_day=is_school_day,
    )
    if daily_max_minutes > 0:
        projected_minutes = _projected_local_day_minutes(
            candidate_shift=candidate_shift,
            counted_intervals=counted_intervals,
        )
        if projected_minutes > daily_max_minutes:
            results.append(
                {
                    "rule_code": str(
                        minor_labor_rule.get("daily_limit_rule_code") or "minor_daily_hours_limit"
                    ),
                    "status": "block",
                    "reason_codes": ["employee_is_minor", "minor_daily_minutes_exceeded"],
                    "premium_required": False,
                    "would_block": True,
                    "projected_minutes": projected_minutes,
                    "daily_max_minutes": daily_max_minutes,
                    "excess_minutes": max(0, projected_minutes - daily_max_minutes),
                    "minor_school_status": resolved_school_status,
                    "minor_school_day": is_school_day,
                }
            )
        else:
            results.append(
                {
                    "rule_code": str(
                        minor_labor_rule.get("daily_limit_rule_code") or "minor_daily_hours_limit"
                    ),
                    "status": "clear",
                    "reason_codes": ["employee_is_minor", "minor_daily_minutes_within_limit"],
                    "premium_required": False,
                    "would_block": False,
                    "projected_minutes": projected_minutes,
                    "daily_max_minutes": daily_max_minutes,
                    "minor_school_status": resolved_school_status,
                    "minor_school_day": is_school_day,
                }
            )

    weekly_max_minutes = _resolved_minor_weekly_max_minutes(
        minor_labor_rule,
        age_years=age_years,
        school_status=resolved_school_status,
        workweek_has_school_day=workweek_has_school_day,
    )
    if weekly_max_minutes > 0:
        projected_weekly_minutes = _projected_workweek_minutes(
            profile=profile,
            candidate_shift=candidate_shift,
            counted_intervals=counted_intervals,
        )
        if projected_weekly_minutes > weekly_max_minutes:
            results.append(
                {
                    "rule_code": str(
                        minor_labor_rule.get("weekly_limit_rule_code") or "minor_weekly_hours_limit"
                    ),
                    "status": "block",
                    "reason_codes": ["employee_is_minor", "minor_weekly_minutes_exceeded"],
                    "premium_required": False,
                    "would_block": True,
                    "projected_minutes": projected_weekly_minutes,
                    "weekly_max_minutes": weekly_max_minutes,
                    "excess_minutes": max(0, projected_weekly_minutes - weekly_max_minutes),
                    "minor_school_status": resolved_school_status,
                    "minor_school_week": workweek_has_school_day,
                }
            )
        else:
            results.append(
                {
                    "rule_code": str(
                        minor_labor_rule.get("weekly_limit_rule_code") or "minor_weekly_hours_limit"
                    ),
                    "status": "clear",
                    "reason_codes": ["employee_is_minor", "minor_weekly_minutes_within_limit"],
                    "premium_required": False,
                    "would_block": False,
                    "projected_minutes": projected_weekly_minutes,
                    "weekly_max_minutes": weekly_max_minutes,
                    "minor_school_status": resolved_school_status,
                    "minor_school_week": workweek_has_school_day,
                }
            )

    earliest_start_local_time = _resolved_minor_earliest_start_local_time(
        minor_labor_rule,
        age_years=age_years,
        school_status=resolved_school_status,
        is_school_day=is_school_day,
    )
    latest_end_local_time = _resolved_minor_latest_end_local_time(
        minor_labor_rule,
        age_years=age_years,
        school_status=resolved_school_status,
        is_school_day=is_school_day,
    )
    if isinstance(earliest_start_local_time, time) or isinstance(latest_end_local_time, time):
        time_window_reason_codes = ["employee_is_minor"]
        if (
            isinstance(earliest_start_local_time, time)
            and shift_local_start.timetz().replace(tzinfo=None) < earliest_start_local_time
        ):
            time_window_reason_codes.append("minor_shift_starts_too_early")
        if (
            isinstance(latest_end_local_time, time)
            and _shift_ends_after_local_time_limit(
                shift_local_start=shift_local_start,
                shift_local_end=shift_local_end,
                latest_end_local_time=latest_end_local_time,
            )
        ):
            time_window_reason_codes.append("minor_shift_ends_too_late")
        if len(time_window_reason_codes) > 1:
            results.append(
                {
                    "rule_code": str(
                        minor_labor_rule.get("time_window_rule_code") or "minor_time_window_restricted"
                    ),
                    "status": "block",
                    "reason_codes": time_window_reason_codes,
                    "premium_required": False,
                    "would_block": True,
                    "earliest_start_local_time": (
                        earliest_start_local_time.isoformat()
                        if isinstance(earliest_start_local_time, time)
                        else None
                    ),
                    "latest_end_local_time": (
                        latest_end_local_time.isoformat()
                        if isinstance(latest_end_local_time, time)
                        else None
                    ),
                    "minor_school_day": is_school_day,
                }
            )
        else:
            results.append(
                {
                    "rule_code": str(
                        minor_labor_rule.get("time_window_rule_code") or "minor_time_window_restricted"
                    ),
                    "status": "clear",
                    "reason_codes": ["employee_is_minor", "minor_time_window_satisfied"],
                    "premium_required": False,
                    "would_block": False,
                    "earliest_start_local_time": (
                        earliest_start_local_time.isoformat()
                        if isinstance(earliest_start_local_time, time)
                        else None
                    ),
                    "latest_end_local_time": (
                        latest_end_local_time.isoformat()
                        if isinstance(latest_end_local_time, time)
                        else None
                    ),
                    "minor_school_day": is_school_day,
                }
            )

    return results


def _resolved_minor_school_status(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"in_session", "summer_break", "not_enrolled", "unknown"}:
        return normalized
    return None


def _minor_school_status_rule_applies(
    minor_labor_rule: Mapping[str, object],
    *,
    age_years: int,
    school_status: str | None,
) -> bool:
    if school_status is None:
        return False
    min_years = _as_int(minor_labor_rule.get("school_status_age_min_years")) or 14
    max_years = _as_int(minor_labor_rule.get("school_status_age_max_years")) or 15
    return min_years <= age_years <= max_years


def _resolved_minor_daily_max_minutes(
    minor_labor_rule: Mapping[str, object],
    *,
    age_years: int,
    school_status: str | None,
    is_school_day: bool | None,
) -> int:
    if school_status == "in_session" and is_school_day is not None:
        if is_school_day:
            configured = _as_int(minor_labor_rule.get("daily_max_minutes_school_day"))
            if configured > 0:
                return configured
        else:
            configured = _as_int(minor_labor_rule.get("daily_max_minutes_non_school_day"))
            if configured > 0:
                return configured
    if _minor_school_status_rule_applies(minor_labor_rule, age_years=age_years, school_status=school_status):
        if school_status == "in_session":
            configured = _as_int(minor_labor_rule.get("daily_max_minutes_in_session"))
            if configured > 0:
                return configured
        if school_status in {"summer_break", "not_enrolled"}:
            configured = _as_int(minor_labor_rule.get("daily_max_minutes_summer_break"))
            if configured > 0:
                return configured
    return _as_int(minor_labor_rule.get("daily_max_minutes"))


def _resolved_minor_weekly_max_minutes(
    minor_labor_rule: Mapping[str, object],
    *,
    age_years: int,
    school_status: str | None,
    workweek_has_school_day: bool | None,
) -> int:
    if school_status == "in_session" and workweek_has_school_day is not None:
        if workweek_has_school_day:
            configured = _as_int(minor_labor_rule.get("weekly_max_minutes_school_week"))
            if configured > 0:
                return configured
        else:
            configured = _as_int(minor_labor_rule.get("weekly_max_minutes_non_school_week"))
            if configured > 0:
                return configured
    if _minor_school_status_rule_applies(minor_labor_rule, age_years=age_years, school_status=school_status):
        if school_status == "in_session":
            configured = _as_int(minor_labor_rule.get("weekly_max_minutes_in_session"))
            if configured > 0:
                return configured
        if school_status in {"summer_break", "not_enrolled"}:
            configured = _as_int(minor_labor_rule.get("weekly_max_minutes_summer_break"))
            if configured > 0:
                return configured
    return _as_int(minor_labor_rule.get("weekly_max_minutes"))


def _resolved_minor_earliest_start_local_time(
    minor_labor_rule: Mapping[str, object],
    *,
    age_years: int,
    school_status: str | None,
    is_school_day: bool | None,
) -> time | None:
    if school_status == "in_session" and is_school_day is not None:
        if is_school_day:
            configured = minor_labor_rule.get("earliest_start_local_time_school_day")
            if isinstance(configured, time):
                return configured
        else:
            configured = minor_labor_rule.get("earliest_start_local_time_non_school_day")
            if isinstance(configured, time):
                return configured
    configured = minor_labor_rule.get("earliest_start_local_time")
    return configured if isinstance(configured, time) else None


def _resolved_minor_latest_end_local_time(
    minor_labor_rule: Mapping[str, object],
    *,
    age_years: int,
    school_status: str | None,
    is_school_day: bool | None,
) -> time | None:
    if school_status == "in_session" and is_school_day is not None:
        if is_school_day:
            configured = minor_labor_rule.get("latest_end_local_time_school_day")
            if isinstance(configured, time):
                return configured
        else:
            configured = minor_labor_rule.get("latest_end_local_time_non_school_day")
            if isinstance(configured, time):
                return configured
    if _minor_school_status_rule_applies(minor_labor_rule, age_years=age_years, school_status=school_status):
        if school_status == "in_session":
            configured = minor_labor_rule.get("latest_end_local_time_in_session")
            if isinstance(configured, time):
                return configured
        if school_status in {"summer_break", "not_enrolled"}:
            configured = minor_labor_rule.get("latest_end_local_time_summer_break")
            if isinstance(configured, time):
                return configured
    configured = minor_labor_rule.get("latest_end_local_time")
    return configured if isinstance(configured, time) else None


def _normalized_work_permit_rule_profile(
    value: object | None,
) -> dict[str, object]:
    resolved_payload = work_permit_rules.resolve_work_permit_rule_profile_payload(value)
    if not isinstance(resolved_payload, Mapping):
        return {}
    weekday_names = resolved_payload.get("allowed_weekdays")
    normalized_weekdays = []
    if isinstance(weekday_names, list):
        normalized_weekdays = sorted(
            {
                str(item or "").strip().lower()
                for item in weekday_names
                if _weekday_number_from_name(str(item or "").strip().lower()) is not None
            },
            key=lambda item: _weekday_number_from_name(item) or 99,
        )
    return {
        "allowed_weekdays": normalized_weekdays,
        "daily_max_minutes": _as_int(resolved_payload.get("daily_max_minutes")),
        "daily_max_minutes_in_session": _as_int(
            resolved_payload.get("daily_max_minutes_in_session")
        ),
        "daily_max_minutes_summer_break": _as_int(
            resolved_payload.get("daily_max_minutes_summer_break")
        ),
        "daily_max_minutes_school_day": _as_int(
            resolved_payload.get("daily_max_minutes_school_day")
        ),
        "daily_max_minutes_non_school_day": _as_int(
            resolved_payload.get("daily_max_minutes_non_school_day")
        ),
        "daily_max_minutes_preceding_non_school_day": _as_int(
            resolved_payload.get("daily_max_minutes_preceding_non_school_day")
        ),
        "weekly_max_minutes": _as_int(resolved_payload.get("weekly_max_minutes")),
        "weekly_max_minutes_in_session": _as_int(
            resolved_payload.get("weekly_max_minutes_in_session")
        ),
        "weekly_max_minutes_summer_break": _as_int(
            resolved_payload.get("weekly_max_minutes_summer_break")
        ),
        "weekly_max_minutes_school_week": _as_int(
            resolved_payload.get("weekly_max_minutes_school_week")
        ),
        "weekly_max_minutes_non_school_week": _as_int(
            resolved_payload.get("weekly_max_minutes_non_school_week")
        ),
        "earliest_start_local_time": _parse_local_time(
            resolved_payload.get("earliest_start_local_time")
        ),
        "earliest_start_local_time_school_day": _parse_local_time(
            resolved_payload.get("earliest_start_local_time_school_day")
        ),
        "earliest_start_local_time_non_school_day": _parse_local_time(
            resolved_payload.get("earliest_start_local_time_non_school_day")
        ),
        "latest_end_local_time": _parse_local_time(
            resolved_payload.get("latest_end_local_time")
        ),
        "latest_end_local_time_in_session": _parse_local_time(
            resolved_payload.get("latest_end_local_time_in_session")
        ),
        "latest_end_local_time_summer_break": _parse_local_time(
            resolved_payload.get("latest_end_local_time_summer_break")
        ),
        "latest_end_local_time_school_day": _parse_local_time(
            resolved_payload.get("latest_end_local_time_school_day")
        ),
        "latest_end_local_time_non_school_day": _parse_local_time(
            resolved_payload.get("latest_end_local_time_non_school_day")
        ),
        "latest_end_local_time_preceding_non_school_day": _parse_local_time(
            resolved_payload.get("latest_end_local_time_preceding_non_school_day")
        ),
        "template_code": str(resolved_payload.get("template_code") or "").strip()
        or None,
        "jurisdiction_code": str(resolved_payload.get("jurisdiction_code") or "").strip()
        or None,
        "source_url": str(resolved_payload.get("source_url") or "").strip()
        or None,
    }


def _resolved_work_permit_allowed_weekdays(
    work_permit_rule_profile: Mapping[str, object],
) -> set[int]:
    return {
        weekday_number
        for weekday_number in (
            _weekday_number_from_name(str(item or "").strip().lower())
            for item in work_permit_rule_profile.get("allowed_weekdays") or []
        )
        if weekday_number is not None
    }


def _resolved_work_permit_daily_max_minutes(
    work_permit_rule_profile: Mapping[str, object],
    *,
    school_status: str | None,
    is_school_day: bool | None,
    precedes_non_school_day: bool | None,
    fallback_minutes: int | None,
) -> int:
    if school_status == "in_session" and precedes_non_school_day:
        configured = _as_int(
            work_permit_rule_profile.get("daily_max_minutes_preceding_non_school_day")
        )
        if configured > 0:
            return configured
    if school_status == "in_session" and is_school_day is not None:
        key = "daily_max_minutes_school_day" if is_school_day else "daily_max_minutes_non_school_day"
        configured = _as_int(work_permit_rule_profile.get(key))
        if configured > 0:
            return configured
    if school_status == "in_session":
        configured = _as_int(work_permit_rule_profile.get("daily_max_minutes_in_session"))
        if configured > 0:
            return configured
    if school_status in {"summer_break", "not_enrolled"}:
        configured = _as_int(work_permit_rule_profile.get("daily_max_minutes_summer_break"))
        if configured > 0:
            return configured
    configured = _as_int(work_permit_rule_profile.get("daily_max_minutes"))
    if configured > 0:
        return configured
    return _as_int(fallback_minutes)


def _resolved_work_permit_weekly_max_minutes(
    work_permit_rule_profile: Mapping[str, object],
    *,
    school_status: str | None,
    workweek_has_school_day: bool | None,
    fallback_minutes: int | None,
) -> int:
    if school_status == "in_session" and workweek_has_school_day is not None:
        key = (
            "weekly_max_minutes_school_week"
            if workweek_has_school_day
            else "weekly_max_minutes_non_school_week"
        )
        configured = _as_int(work_permit_rule_profile.get(key))
        if configured > 0:
            return configured
    if school_status == "in_session":
        configured = _as_int(
            work_permit_rule_profile.get("weekly_max_minutes_in_session")
        )
        if configured > 0:
            return configured
    if school_status in {"summer_break", "not_enrolled"}:
        configured = _as_int(
            work_permit_rule_profile.get("weekly_max_minutes_summer_break")
        )
        if configured > 0:
            return configured
    configured = _as_int(work_permit_rule_profile.get("weekly_max_minutes"))
    if configured > 0:
        return configured
    return _as_int(fallback_minutes)


def _resolved_work_permit_earliest_start_local_time(
    work_permit_rule_profile: Mapping[str, object],
    *,
    school_status: str | None,
    is_school_day: bool | None,
    fallback_time: time | str | None,
) -> time | None:
    if school_status == "in_session" and is_school_day is not None:
        key = (
            "earliest_start_local_time_school_day"
            if is_school_day
            else "earliest_start_local_time_non_school_day"
        )
        configured = work_permit_rule_profile.get(key)
        if isinstance(configured, time):
            return configured
    configured = work_permit_rule_profile.get("earliest_start_local_time")
    if isinstance(configured, time):
        return configured
    return _parse_local_time(fallback_time)


def _resolved_work_permit_latest_end_local_time(
    work_permit_rule_profile: Mapping[str, object],
    *,
    school_status: str | None,
    is_school_day: bool | None,
    precedes_non_school_day: bool | None,
    fallback_time: time | str | None,
) -> time | None:
    if school_status == "in_session" and precedes_non_school_day:
        configured = work_permit_rule_profile.get(
            "latest_end_local_time_preceding_non_school_day"
        )
        if isinstance(configured, time):
            return configured
    if school_status == "in_session" and is_school_day is not None:
        key = (
            "latest_end_local_time_school_day"
            if is_school_day
            else "latest_end_local_time_non_school_day"
        )
        configured = work_permit_rule_profile.get(key)
        if isinstance(configured, time):
            return configured
    if school_status == "in_session":
        configured = work_permit_rule_profile.get("latest_end_local_time_in_session")
        if isinstance(configured, time):
            return configured
    if school_status in {"summer_break", "not_enrolled"}:
        configured = work_permit_rule_profile.get("latest_end_local_time_summer_break")
        if isinstance(configured, time):
            return configured
    configured = work_permit_rule_profile.get("latest_end_local_time")
    if isinstance(configured, time):
        return configured
    return _parse_local_time(fallback_time)


def _resolved_premium_type(
    *,
    configured_premium_cents: int,
    employee_base_hourly_rate_cents: int | None,
) -> str:
    if configured_premium_cents > 0:
        return "fixed_cents"
    if (employee_base_hourly_rate_cents or 0) > 0:
        return "fixed_cents"
    return "wage_dependent_unresolved"


def _resolved_premium_cents(
    *,
    configured_premium_cents: int,
    employee_base_hourly_rate_cents: int | None,
) -> int:
    if configured_premium_cents > 0:
        return configured_premium_cents
    return max(0, int(employee_base_hourly_rate_cents or 0))


def _customer_policy_rule_results(
    *,
    compliance_settings: Mapping[str, object],
    shift_facts: Mapping[str, object],
    overtime_projection: Mapping[str, object],
    existing_rule_results: Sequence[Mapping[str, object]],
    meal_rule: Mapping[str, object] | None,
    paid_rest_rule: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    rule_results: list[dict[str, object]] = []

    structured_break_result = _structured_break_plan_policy_rule_result(
        compliance_settings=compliance_settings,
        shift_facts=shift_facts,
        meal_rule=meal_rule,
        paid_rest_rule=paid_rest_rule,
    )
    if structured_break_result is not None:
        rule_results.append(structured_break_result)

    max_day_result = _maximum_minutes_policy_rule_result(
        rule_code="customer_policy_max_daily_work_minutes",
        configured_minutes=_as_int(compliance_settings.get("max_daily_minutes")),
        projected_minutes=_hours_to_minutes(overtime_projection.get("projected_max_day_hours")),
        reason_code="max_daily_minutes_exceeded_by_policy",
    )
    if max_day_result is not None:
        rule_results.append(max_day_result)

    max_week_result = _maximum_minutes_policy_rule_result(
        rule_code="customer_policy_max_weekly_work_minutes",
        configured_minutes=_as_int(compliance_settings.get("max_weekly_minutes")),
        projected_minutes=_hours_to_minutes(overtime_projection.get("projected_total_hours")),
        reason_code="max_weekly_minutes_exceeded_by_policy",
    )
    if max_week_result is not None:
        rule_results.append(max_week_result)

    unresolved_premium_result = _unresolved_premium_policy_rule_result(
        compliance_settings=compliance_settings,
        existing_rule_results=existing_rule_results,
    )
    if unresolved_premium_result is not None:
        rule_results.append(unresolved_premium_result)

    return rule_results


def _structured_break_plan_policy_rule_result(
    *,
    compliance_settings: Mapping[str, object],
    shift_facts: Mapping[str, object],
    meal_rule: Mapping[str, object] | None,
    paid_rest_rule: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if not _as_bool(compliance_settings.get("require_structured_break_plans")):
        return None
    if meal_rule is None and paid_rest_rule is None:
        return None
    if _as_bool(shift_facts.get("has_structured_segments")):
        return None
    return {
        "rule_code": "customer_policy_structured_break_plan",
        "status": "block",
        "reason_codes": ["structured_break_plan_required_by_policy"],
        "premium_required": False,
        "would_block": True,
    }


def _maximum_minutes_policy_rule_result(
    *,
    rule_code: str,
    configured_minutes: int,
    projected_minutes: int,
    reason_code: str,
) -> dict[str, object] | None:
    if configured_minutes <= 0 or projected_minutes <= configured_minutes:
        return None
    return {
        "rule_code": rule_code,
        "status": "block",
        "reason_codes": [reason_code],
        "premium_required": False,
        "would_block": True,
        "configured_minutes": configured_minutes,
        "projected_minutes": projected_minutes,
        "excess_minutes": max(0, projected_minutes - configured_minutes),
    }


def _unresolved_premium_policy_rule_result(
    *,
    compliance_settings: Mapping[str, object],
    existing_rule_results: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    if not _as_bool(compliance_settings.get("block_unresolved_premiums")):
        return None
    unresolved_rule_codes = sorted(
        str(result.get("rule_code") or "").strip()
        for result in existing_rule_results
        if str(result.get("premium_type") or "").strip().lower() == "wage_dependent_unresolved"
        and str(result.get("rule_code") or "").strip()
    )
    if not unresolved_rule_codes:
        return None
    return {
        "rule_code": "customer_policy_unresolved_premium",
        "status": "block",
        "reason_codes": ["unresolved_premium_blocked_by_policy"],
        "premium_required": False,
        "would_block": True,
        "unresolved_rule_codes": unresolved_rule_codes,
    }


def _latest_interval_before_shift(
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
) -> labor_rules.CountedInterval | None:
    latest: labor_rules.CountedInterval | None = None
    for interval in counted_intervals:
        if interval.end_at > candidate_shift.starts_at:
            continue
        if latest is None or interval.end_at > latest.end_at:
            latest = interval
    return latest


def _meal_reason_codes(
    *,
    base_code: str,
    has_structured_segments: bool,
    waiver_possible: bool,
    waiver_allowed: bool,
) -> list[str]:
    reason_codes = [base_code]
    if not has_structured_segments:
        reason_codes.append("structured_break_plan_missing")
    if waiver_possible:
        reason_codes.append("waiver_possible_but_not_modelled")
    elif not waiver_allowed:
        reason_codes.append("waiver_disabled_by_policy")
    return reason_codes


def _premium_liability_summary(
    rule_results: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    premium_total_cents = 0
    premium_components: list[dict[str, object]] = []
    unresolved_premium_rule_codes: list[str] = []

    for result in rule_results:
        if not bool(result.get("premium_required")):
            continue
        rule_code = str(result.get("rule_code") or "").strip()
        premium_type = str(result.get("premium_type") or "").strip().lower()
        premium_cents = _as_int(result.get("premium_cents"))
        component = {
            "rule_code": rule_code,
            "premium_type": premium_type or None,
            "premium_cents": premium_cents,
            "status": str(result.get("status") or ""),
            "reason_codes": list(result.get("reason_codes") or []),
        }
        if "projected_cost_multiplier" in result:
            component["projected_cost_multiplier"] = _as_float(result.get("projected_cost_multiplier")) or 1.0
        premium_components.append(component)
        if premium_type == "fixed_cents":
            premium_total_cents += premium_cents
        elif premium_type == "wage_dependent_unresolved" and rule_code:
            unresolved_premium_rule_codes.append(rule_code)

    return {
        "premium_total_cents": premium_total_cents,
        "premium_components": premium_components,
        "unresolved_premium_rule_codes": sorted(set(unresolved_premium_rule_codes)),
    }


def _required_california_rest_break_count(net_active_work_minutes: int) -> int:
    if net_active_work_minutes < 210:
        return 0
    full_blocks = net_active_work_minutes // 240
    remainder = net_active_work_minutes % 240
    return full_blocks + (1 if remainder > 120 else 0)


def _policy_settings_snapshot(compliance_settings: Mapping[str, object]) -> dict[str, object]:
    return {
        str(key): value
        for key, value in compliance_settings.items()
        if value is not None
    }


def _policy_metadata_from_settings(raw_settings: Mapping[str, object] | None) -> dict[str, object]:
    if not isinstance(raw_settings, Mapping):
        return {}
    if not (
        raw_settings.get("compliance_policy_version_id") is not None
        or raw_settings.get("compliance_policy_hash") is not None
        or raw_settings.get("compliance_policy_scope") is not None
        or raw_settings.get("compliance_policy_clears_parent") is not None
    ):
        return {}
    return {
        "policy_version_id": raw_settings.get("compliance_policy_version_id"),
        "policy_hash": raw_settings.get("compliance_policy_hash"),
        "policy_effective_at": raw_settings.get("compliance_policy_effective_at"),
        "policy_scope": raw_settings.get("compliance_policy_scope"),
        "policy_clears_parent": bool(raw_settings.get("compliance_policy_clears_parent")),
    }


def _policy_metadata_snapshot(
    *,
    business_settings: Mapping[str, object] | None,
    location_settings: Mapping[str, object] | None,
) -> dict[str, object]:
    location_metadata = _policy_metadata_from_settings(location_settings)
    if location_metadata:
        return location_metadata
    business_metadata = _policy_metadata_from_settings(business_settings)
    if business_metadata:
        return business_metadata
    return {}


def _compliance_settings(
    *,
    business_settings: Mapping[str, object] | None,
    location_settings: Mapping[str, object] | None,
) -> dict[str, object]:
    settings_payload: dict[str, object] = {}
    if isinstance(business_settings, Mapping):
        compliance = business_settings.get("compliance")
        if isinstance(compliance, Mapping):
            settings_payload.update(dict(compliance))
    if isinstance(location_settings, Mapping):
        if _as_bool(location_settings.get("compliance_policy_clears_parent")):
            settings_payload = {}
        compliance = location_settings.get("compliance")
        if isinstance(compliance, Mapping):
            settings_payload.update(dict(compliance))
    return settings_payload


def _minor_school_day_status(
    *,
    compliance_settings: Mapping[str, object],
    shift_local_date: date,
    school_status: str | None,
) -> bool | None:
    if school_status != "in_session":
        return None
    school_dates = {
        parsed
        for parsed in (
            _parse_policy_date(item)
            for item in compliance_settings.get("school_dates") or []
        )
        if parsed is not None
    }
    non_school_dates = {
        parsed
        for parsed in (
            _parse_policy_date(item)
            for item in compliance_settings.get("non_school_dates") or []
        )
        if parsed is not None
    }
    if shift_local_date in non_school_dates:
        return False
    if shift_local_date in school_dates:
        return True
    school_day_weekdays = _configured_school_day_weekdays(compliance_settings)
    return shift_local_date.weekday() in school_day_weekdays


def _minor_workweek_has_school_day(
    *,
    profile: labor_rules.LaborRuleProfileSnapshot,
    candidate_shift: Shift,
    compliance_settings: Mapping[str, object],
    school_status: str | None,
) -> bool | None:
    if school_status != "in_session":
        return None
    shift_timezone = _shift_timezone(candidate_shift)
    workweek_start, workweek_end = labor_rules.workweek_window_for_shift(profile, shift=candidate_shift)
    current_date = workweek_start.astimezone(shift_timezone).date()
    end_date = (workweek_end - timedelta(minutes=1)).astimezone(shift_timezone).date()
    while current_date <= end_date:
        if _minor_school_day_status(
            compliance_settings=compliance_settings,
            shift_local_date=current_date,
            school_status=school_status,
        ):
            return True
        current_date += timedelta(days=1)
    return False


def _minor_precedes_non_school_day(
    *,
    compliance_settings: Mapping[str, object],
    shift_local_date: date,
    school_status: str | None,
) -> bool | None:
    if school_status != "in_session":
        return None
    next_local_date = shift_local_date + timedelta(days=1)
    next_day_is_school_day = _minor_school_day_status(
        compliance_settings=compliance_settings,
        shift_local_date=next_local_date,
        school_status=school_status,
    )
    if next_day_is_school_day is None:
        return None
    return not next_day_is_school_day


def _shift_ends_after_local_time_limit(
    *,
    shift_local_start: datetime,
    shift_local_end: datetime,
    latest_end_local_time: time,
) -> bool:
    allowed_end = shift_local_start.replace(
        hour=latest_end_local_time.hour,
        minute=latest_end_local_time.minute,
        second=latest_end_local_time.second,
        microsecond=latest_end_local_time.microsecond,
    )
    if latest_end_local_time < shift_local_start.timetz().replace(tzinfo=None):
        allowed_end += timedelta(days=1)
    return shift_local_end > allowed_end


def _weekday_number_from_name(value: str | None) -> int | None:
    lookup = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    normalized = str(value or "").strip().lower()
    return lookup.get(normalized)


def _weekday_name_from_number(value: int) -> str:
    lookup = {
        0: "monday",
        1: "tuesday",
        2: "wednesday",
        3: "thursday",
        4: "friday",
        5: "saturday",
        6: "sunday",
    }
    return lookup.get(value, "unknown")


def _weekday_name_from_date(value: date) -> str:
    return _weekday_name_from_number(value.weekday())


def _configured_school_day_weekdays(
    compliance_settings: Mapping[str, object],
) -> set[int]:
    weekday_names = compliance_settings.get("school_day_weekdays")
    if not isinstance(weekday_names, list) or not weekday_names:
        return {0, 1, 2, 3, 4}
    configured = {
        _weekday_number_from_name(normalized)
        for normalized in (
            str(item or "").strip().lower()
            for item in weekday_names
        )
        if _weekday_number_from_name(normalized) is not None
    }
    return {item for item in configured if item is not None} or {0, 1, 2, 3, 4}


def _parse_policy_date(value: object | None) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _projected_local_day_minutes(
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
) -> int:
    tz = _shift_timezone(candidate_shift)
    shift_local_start = candidate_shift.starts_at.astimezone(tz)
    day_window_start = datetime.combine(shift_local_start.date(), time.min, tzinfo=tz).astimezone(
        candidate_shift.starts_at.tzinfo
    )
    day_window_end = (datetime.combine(shift_local_start.date(), time.min, tzinfo=tz) + timedelta(days=1)).astimezone(
        candidate_shift.starts_at.tzinfo
    )
    return _projected_interval_minutes(
        counted_intervals=[*counted_intervals, _candidate_counted_interval(candidate_shift)],
        start_at=day_window_start,
        end_at=day_window_end,
    )


def _projected_workweek_minutes(
    *,
    profile: labor_rules.LaborRuleProfileSnapshot,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
) -> int:
    workweek_start, workweek_end = labor_rules.workweek_window_for_shift(profile, shift=candidate_shift)
    return _projected_interval_minutes(
        counted_intervals=[*counted_intervals, _candidate_counted_interval(candidate_shift)],
        start_at=workweek_start,
        end_at=workweek_end,
    )


def _candidate_counted_interval(candidate_shift: Shift) -> labor_rules.CountedInterval:
    return labor_rules.CountedInterval(
        start_at=candidate_shift.starts_at,
        end_at=candidate_shift.ends_at,
        shift_id=candidate_shift.id,
        assignment_status="candidate",
    )


def _projected_interval_minutes(
    *,
    counted_intervals: Sequence[labor_rules.CountedInterval],
    start_at: datetime,
    end_at: datetime,
) -> int:
    clipped = []
    for interval in counted_intervals:
        clipped_start = max(interval.start_at, start_at)
        clipped_end = min(interval.end_at, end_at)
        if clipped_end <= clipped_start:
            continue
        clipped.append((clipped_start, clipped_end))
    if not clipped:
        return 0
    clipped.sort(key=lambda item: (item[0], item[1]))
    merged: list[tuple[datetime, datetime]] = [clipped[0]]
    for interval_start, interval_end in clipped[1:]:
        current_start, current_end = merged[-1]
        if interval_start <= current_end:
            merged[-1] = (current_start, max(current_end, interval_end))
            continue
        merged.append((interval_start, interval_end))
    total_seconds = sum((interval_end - interval_start).total_seconds() for interval_start, interval_end in merged)
    return max(0, int(round(total_seconds / 60.0)))


def _hours_to_minutes(value: object | None) -> int:
    hours = _as_float(value)
    if hours is None or hours <= 0:
        return 0
    return max(0, int(round(hours * 60.0)))


def _parse_local_time(value: object | None) -> time | None:
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    normalized = str(value or "").strip()
    if not normalized:
        return None
    for candidate in (normalized, f"{normalized}:00"):
        try:
            return time.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _shift_timezone(shift: Shift) -> ZoneInfo:
    timezone_name = str(getattr(shift, "timezone", "") or "").strip() or "UTC"
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("UTC")


def _employee_age_on_date(date_of_birth: date, reference_date: date) -> int | None:
    if date_of_birth > reference_date:
        return None
    return reference_date.year - date_of_birth.year - (
        (reference_date.month, reference_date.day) < (date_of_birth.month, date_of_birth.day)
    )


def _as_float(value: object | None) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _as_int(value: object | None) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _as_bool(value: object | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False
