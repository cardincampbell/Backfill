from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

from app.models.common import ComplianceOverrideArtifactType
from app.models.scheduling import Shift
from app.services import (
    compliance_shift_facts,
    compliance_source_references,
    labor_rules,
    work_permit_rules,
)

COMPLIANCE_ENGINE_VERSION = "deterministic_compliance_engine_v1"


def evaluate_shift_assignment_compliance(
    profile: labor_rules.LaborRuleProfileSnapshot | None,
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
    reference_time: datetime,
    overtime_projection: Mapping[str, object] | None = None,
    employee_base_hourly_rate_cents: int | None = None,
    employee_premium_hourly_rate_cents: int | None = None,
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
    work_permit_source_payload = (
        work_permit_rules.resolve_work_permit_rule_profile_payload(
            employee_work_permit_rule_profile
        )
        or {}
    )
    shift_facts = compliance_shift_facts.build_shift_structure_facts(candidate_shift)
    break_facts = compliance_shift_facts.list_break_facts(candidate_shift)
    resolved_premium_rate_context = _resolved_employee_premium_rate_context(
        employee_base_hourly_rate_cents=employee_base_hourly_rate_cents,
        employee_premium_hourly_rate_cents=employee_premium_hourly_rate_cents,
    )
    resolved_premium_hourly_rate_cents = _as_int(
        resolved_premium_rate_context.get("premium_rate_hourly_cents")
    )
    resolved_premium_rate_basis = _normalized_optional_string(
        resolved_premium_rate_context.get("premium_rate_basis")
    )
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
            "profile_display_name": None,
            "profile_source_version": None,
            "profile_source_hash": None,
            "profile_source_urls": [],
            "jurisdiction_code": None,
            "work_permit_template_code": _normalized_optional_string(
                work_permit_source_payload.get("template_code")
            ),
            "work_permit_template_label": _normalized_optional_string(
                work_permit_source_payload.get("label")
            ),
            "work_permit_jurisdiction_code": _normalized_optional_string(
                work_permit_source_payload.get("jurisdiction_code")
            ),
            "work_permit_source_document_title": _normalized_optional_string(
                work_permit_source_payload.get("source_document_title")
            ),
            "work_permit_source_urls": _normalized_string_list(
                [work_permit_source_payload.get("source_url")]
                if work_permit_source_payload.get("source_url")
                else []
            ),
            "work_permit_source_version": _normalized_optional_string(
                work_permit_source_payload.get("source_version")
            ),
            "work_permit_source_hash": _normalized_optional_string(
                work_permit_source_payload.get("source_hash")
            ),
            "work_permit_payload_hash": work_permit_rules.rule_profile_payload_hash(
                work_permit_source_payload
            ),
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
            "rule_source_references": [],
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
                profile,
                meal_rule,
                candidate_shift=candidate_shift,
                counted_intervals=counted_intervals,
                shift_facts=shift_facts,
                break_facts=break_facts,
                employee_premium_hourly_rate_cents=resolved_premium_hourly_rate_cents,
                employee_premium_rate_basis=resolved_premium_rate_basis,
            )
        )

    paid_rest_rule = _paid_rest_break_rule(profile)
    if paid_rest_rule is not None:
        rule_results.append(
            _paid_rest_break_rule_result(
                profile,
                paid_rest_rule,
                candidate_shift=candidate_shift,
                counted_intervals=counted_intervals,
                shift_facts=shift_facts,
                break_facts=break_facts,
                employee_premium_hourly_rate_cents=resolved_premium_hourly_rate_cents,
                employee_premium_rate_basis=resolved_premium_rate_basis,
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

    day_of_rest_rule = _day_of_rest_rule(profile)
    if day_of_rest_rule is not None:
        rule_results.append(
            _day_of_rest_rule_result(
                day_of_rest_rule,
                candidate_shift=candidate_shift,
                counted_intervals=counted_intervals,
            )
        )

    day_of_rest_workweek_rule = _day_of_rest_workweek_rule(profile)
    if day_of_rest_workweek_rule is not None:
        rule_results.append(
            _day_of_rest_workweek_rule_result(
                profile,
                day_of_rest_workweek_rule,
                candidate_shift=candidate_shift,
                counted_intervals=counted_intervals,
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
            profile=profile,
            compliance_settings=compliance_settings,
            shift_facts=shift_facts,
            candidate_shift=candidate_shift,
            counted_intervals=counted_intervals,
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
    relevant_rule_codes = sorted(
        set(
            blocking_rule_codes
            + warning_rule_codes
            + premium_rule_codes
            + premium_summary["unresolved_premium_rule_codes"]
        )
    )

    return {
        "status": status,
        "evaluation_source": COMPLIANCE_ENGINE_VERSION,
        "profile_code": profile.code,
        "profile_version_id": str(profile.version_id),
        "profile_payload_hash": profile.payload_hash,
        "profile_display_name": profile.display_name,
        "profile_source_version": profile.source_version,
        "profile_source_hash": profile.source_hash,
        "profile_source_urls": list(profile.source_urls),
        "jurisdiction_code": profile.jurisdiction_code,
        "work_permit_template_code": _normalized_optional_string(
            work_permit_source_payload.get("template_code")
        ),
        "work_permit_template_label": _normalized_optional_string(
            work_permit_source_payload.get("label")
        ),
        "work_permit_jurisdiction_code": _normalized_optional_string(
            work_permit_source_payload.get("jurisdiction_code")
        ),
        "work_permit_source_document_title": _normalized_optional_string(
            work_permit_source_payload.get("source_document_title")
        ),
        "work_permit_source_urls": _normalized_string_list(
            [work_permit_source_payload.get("source_url")]
            if work_permit_source_payload.get("source_url")
            else []
        ),
        "work_permit_source_version": _normalized_optional_string(
            work_permit_source_payload.get("source_version")
        ),
        "work_permit_source_hash": _normalized_optional_string(
            work_permit_source_payload.get("source_hash")
        ),
        "work_permit_payload_hash": work_permit_rules.rule_profile_payload_hash(
            work_permit_source_payload
        ),
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
        "rule_source_references": compliance_source_references.build_rule_source_references(
            rule_codes=relevant_rule_codes,
            profile_code=profile.code,
            profile_display_name=profile.display_name,
            profile_version_id=str(profile.version_id),
            profile_payload_hash=profile.payload_hash,
            profile_source_version=profile.source_version,
            profile_source_hash=profile.source_hash,
            profile_source_urls=list(profile.source_urls),
            jurisdiction_code=profile.jurisdiction_code,
            policy_version_id=policy_metadata.get("policy_version_id"),
            policy_hash=policy_metadata.get("policy_hash"),
            policy_effective_at=policy_metadata.get("policy_effective_at"),
            policy_scope=policy_metadata.get("policy_scope"),
            work_permit_template_code=work_permit_source_payload.get("template_code"),
            work_permit_template_label=work_permit_source_payload.get("label"),
            work_permit_jurisdiction_code=work_permit_source_payload.get("jurisdiction_code"),
            work_permit_source_document_title=work_permit_source_payload.get("source_document_title"),
            work_permit_source_urls=(
                [work_permit_source_payload.get("source_url")]
                if work_permit_source_payload.get("source_url")
                else []
            ),
            work_permit_source_version=work_permit_source_payload.get("source_version"),
            work_permit_source_hash=work_permit_source_payload.get("source_hash"),
            work_permit_payload_hash=work_permit_rules.rule_profile_payload_hash(
                work_permit_source_payload
            ),
        ),
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


def _normalized_optional_string(value: object | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalized_string_list(value: object | None) -> list[str]:
    normalized = []
    seen: set[str] = set()
    for item in value or []:
        text = _normalized_optional_string(item)
        if text is None or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


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
        "premium_rate_basis": (
            "projected_cost_multiplier"
            if projected_ot_hours > 0 or projected_dt_hours > 0
            else None
        ),
        "premium_rate_hourly_cents": None,
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
        "co_v1",
        "colorado_v1",
        "or_v1",
        "oregon_v1",
        "ny_non_factory_v1",
        "new_york_non_factory_v1",
        "ny_hospitality_v1",
        "ny_factory_v1",
        "new_york_factory_v1",
        "wa_v1",
        "washington_v1",
    }
    if not enabled:
        return None

    if raw_ruleset in {"co_v1", "colorado_v1"}:
        return {
            "mode": "co_windowed",
            "first_rule_code": str(rules_json.get("first_meal_rule_code") or "meal_break_first_window"),
            "first_trigger_minutes": _as_int(rules_json.get("first_meal_trigger_minutes")) or 300,
            "first_window_start_minutes": _as_int(rules_json.get("first_meal_window_start_minutes")) or 60,
            "first_window_end_offset_minutes": _as_int(rules_json.get("first_meal_window_end_offset_minutes")) or 60,
            "first_min_break_minutes": _as_int(rules_json.get("first_meal_min_break_minutes")) or 30,
            "allows_on_duty_paid_meal": True,
        }

    if raw_ruleset in {"or_v1", "oregon_v1"}:
        return {
            "mode": "or_windowed",
            "first_rule_code": str(rules_json.get("first_meal_rule_code") or "meal_break_first_window"),
            "additional_rule_code": str(
                rules_json.get("additional_meal_rule_code") or "meal_break_additional_window"
            ),
            "first_short_shift_max_minutes": _as_int(rules_json.get("first_meal_short_shift_max_minutes")) or 420,
            "first_short_window_start_minutes": _as_int(rules_json.get("first_meal_short_window_start_minutes")) or 120,
            "first_short_window_end_minutes": _as_int(rules_json.get("first_meal_short_window_end_minutes")) or 300,
            "first_long_window_start_minutes": _as_int(rules_json.get("first_meal_long_window_start_minutes")) or 180,
            "first_long_window_end_minutes": _as_int(rules_json.get("first_meal_long_window_end_minutes")) or 360,
            "first_min_break_minutes": _as_int(rules_json.get("first_meal_min_break_minutes")) or 30,
        }

    if raw_ruleset in {
        "ny_non_factory_v1",
        "new_york_non_factory_v1",
        "ny_hospitality_v1",
        "ny_factory_v1",
        "new_york_factory_v1",
    }:
        is_factory = raw_ruleset in {"ny_factory_v1", "new_york_factory_v1"}
        return {
            "mode": "ny_non_factory_windowed",
            "midday_rule_code": str(rules_json.get("midday_meal_rule_code") or "meal_break_midday_window"),
            "midday_trigger_minutes": _as_int(rules_json.get("midday_meal_trigger_minutes")) or 360,
            "midday_window_start_local": str(rules_json.get("midday_meal_window_start_local") or "11:00"),
            "midday_window_end_local": str(rules_json.get("midday_meal_window_end_local") or "14:00"),
            "midday_min_break_minutes": _as_int(rules_json.get("midday_meal_min_break_minutes")) or (60 if is_factory else 30),
            "evening_rule_code": str(rules_json.get("evening_meal_rule_code") or "meal_break_evening_window"),
            "evening_required_if_starts_before_local": str(
                rules_json.get("evening_meal_required_if_starts_before_local") or "11:00"
            ),
            "evening_required_if_ends_after_local": str(
                rules_json.get("evening_meal_required_if_ends_after_local") or "19:00"
            ),
            "evening_window_start_local": str(rules_json.get("evening_meal_window_start_local") or "17:00"),
            "evening_window_end_local": str(rules_json.get("evening_meal_window_end_local") or "19:00"),
            "evening_min_break_minutes": _as_int(rules_json.get("evening_meal_min_break_minutes")) or 20,
            "midshift_rule_code": str(rules_json.get("midshift_meal_rule_code") or "meal_break_midshift_window"),
            "midshift_trigger_minutes": _as_int(rules_json.get("midshift_meal_trigger_minutes")) or 360,
            "midshift_start_window_local": str(
                rules_json.get("midshift_meal_start_window_local") or "13:00"
            ),
            "midshift_end_window_local": str(
                rules_json.get("midshift_meal_end_window_local") or "06:00"
            ),
            "midshift_min_break_minutes": _as_int(rules_json.get("midshift_meal_min_break_minutes")) or (60 if is_factory else 45),
            "midshift_midpoint_tolerance_minutes": _as_int(
                rules_json.get("midshift_meal_midpoint_tolerance_minutes")
            ) or 120,
        }

    if raw_ruleset in {"wa_v1", "washington_v1"}:
        return {
            "mode": "wa_windowed",
            "first_rule_code": str(rules_json.get("first_meal_rule_code") or "meal_break_first_window"),
            "additional_rule_code": str(
                rules_json.get("additional_meal_rule_code") or "meal_break_additional_window"
            ),
            "first_trigger_minutes": _as_int(rules_json.get("first_meal_trigger_minutes")) or 300,
            "first_window_start_minutes": _as_int(rules_json.get("first_meal_window_start_minutes")) or 120,
            "first_window_end_minutes": _as_int(rules_json.get("first_meal_window_end_minutes")) or 300,
            "first_min_break_minutes": _as_int(rules_json.get("first_meal_min_break_minutes")) or 30,
            "additional_trigger_beyond_normal_minutes": (
                _as_int(rules_json.get("additional_meal_trigger_beyond_normal_minutes")) or 180
            ),
            "additional_interval_minutes": _as_int(rules_json.get("additional_meal_interval_minutes")) or 300,
            "additional_min_break_minutes": _as_int(rules_json.get("additional_meal_min_break_minutes")) or 30,
        }

    return {
        "mode": "relative_windowed",
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
        "co_v1",
        "colorado_v1",
        "or_v1",
        "oregon_v1",
        "wa_v1",
        "washington_v1",
    }
    if not enabled:
        return None
    if raw_ruleset in {"co_v1", "colorado_v1"}:
        return {
            "mode": "co_timed",
            "rule_code": str(rules_json.get("rest_break_rule_code") or "paid_rest_break_quota"),
            "min_break_minutes": _as_int(rules_json.get("rest_break_min_minutes")) or 10,
            "max_continuous_work_minutes": _as_int(rules_json.get("rest_break_max_continuous_work_minutes")) or 240,
        }
    if raw_ruleset in {"or_v1", "oregon_v1"}:
        return {
            "mode": "or_timed",
            "rule_code": str(rules_json.get("rest_break_rule_code") or "paid_rest_break_quota"),
            "min_break_minutes": _as_int(rules_json.get("rest_break_min_minutes")) or 10,
            "max_continuous_work_minutes": _as_int(rules_json.get("rest_break_max_continuous_work_minutes")) or 240,
        }
    if raw_ruleset in {"wa_v1", "washington_v1"}:
        return {
            "mode": "wa_timed",
            "rule_code": str(rules_json.get("rest_break_rule_code") or "paid_rest_break_quota"),
            "min_break_minutes": _as_int(rules_json.get("rest_break_min_minutes")) or 10,
            "max_continuous_work_minutes": _as_int(rules_json.get("rest_break_max_continuous_work_minutes")) or 180,
        }
    return {
        "mode": "ca_count_only",
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
    if configured_premium_cents > 0:
        premium_rate_basis = "configured_fixed_cents"
        premium_rate_hourly_cents = None
        premium_cents = configured_premium_cents
    elif minimum_wage_cents > 0:
        premium_rate_basis = "minimum_wage_floor"
        premium_rate_hourly_cents = minimum_wage_cents
        premium_cents = minimum_wage_cents
    else:
        premium_rate_basis = "wage_basis_missing"
        premium_rate_hourly_cents = None
        premium_cents = 0
    return {
        "rule_code": str(rules_json.get("spread_of_hours_rule_code") or "spread_of_hours_premium"),
        "threshold_minutes": _as_int(rules_json.get("spread_of_hours_threshold_minutes")) or 600,
        "premium_cents": premium_cents,
        "premium_rate_basis": premium_rate_basis,
        "premium_rate_hourly_cents": premium_rate_hourly_cents,
    }


def _day_of_rest_rule(
    profile: labor_rules.LaborRuleProfileSnapshot,
) -> dict[str, object] | None:
    rules_json = profile.rules_json if isinstance(profile.rules_json, Mapping) else {}
    max_consecutive_work_days = labor_rules.max_consecutive_work_days(profile)
    if max_consecutive_work_days <= 0:
        return None
    raw_ruleset = str(rules_json.get("day_of_rest_ruleset") or "").strip().lower()
    default_rule_code = (
        "day_of_rest_in_seven"
        if _as_bool(rules_json.get("day_of_rest_required"))
        or raw_ruleset in {"ca_v1", "california_v1"}
        else "max_consecutive_work_days"
    )
    return {
        "rule_code": str(rules_json.get("day_of_rest_rule_code") or default_rule_code),
        "max_consecutive_work_days": max_consecutive_work_days,
    }


def _day_of_rest_workweek_rule(
    profile: labor_rules.LaborRuleProfileSnapshot,
) -> dict[str, object] | None:
    rules_json = profile.rules_json if isinstance(profile.rules_json, Mapping) else {}
    required_rest_days = labor_rules.required_rest_days_per_workweek(profile)
    if required_rest_days <= 0:
        return None
    return {
        "rule_code": str(rules_json.get("day_of_rest_workweek_rule_code") or "day_of_rest_workweek"),
        "required_rest_days_per_workweek": required_rest_days,
        "max_workdays_per_workweek": max(0, 7 - required_rest_days),
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
        "premium_rate_basis": (
            "configured_fixed_cents"
            if _as_int(rest_rule.get("premium_cents")) > 0
            else None
        ),
        "premium_rate_hourly_cents": None,
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
    profile: labor_rules.LaborRuleProfileSnapshot,
    meal_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
    employee_premium_hourly_rate_cents: int | None,
    employee_premium_rate_basis: str | None,
) -> list[dict[str, object]]:
    mode = str(meal_rule.get("mode") or "relative_windowed").strip().lower()
    if mode == "co_windowed":
        return _meal_break_rule_results_colorado(
            profile,
            meal_rule,
            candidate_shift=candidate_shift,
            counted_intervals=counted_intervals,
            shift_facts=shift_facts,
            break_facts=break_facts,
            employee_premium_hourly_rate_cents=employee_premium_hourly_rate_cents,
            employee_premium_rate_basis=employee_premium_rate_basis,
        )
    if mode == "ny_non_factory_windowed":
        return _meal_break_rule_results_new_york_non_factory(
            meal_rule,
            candidate_shift=candidate_shift,
            shift_facts=shift_facts,
            break_facts=break_facts,
        )
    if mode == "or_windowed":
        return _meal_break_rule_results_oregon(
            meal_rule,
            shift_facts=shift_facts,
            break_facts=break_facts,
        )
    if mode == "wa_windowed":
        return _meal_break_rule_results_washington(
            meal_rule,
            candidate_shift=candidate_shift,
            shift_facts=shift_facts,
            break_facts=break_facts,
        )
    return _meal_break_rule_results_relative_windowed(
        meal_rule,
        candidate_shift=candidate_shift,
        shift_facts=shift_facts,
        break_facts=break_facts,
        employee_premium_hourly_rate_cents=employee_premium_hourly_rate_cents,
        employee_premium_rate_basis=employee_premium_rate_basis,
    )


def _meal_break_rule_results_relative_windowed(
    meal_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
    employee_premium_hourly_rate_cents: int | None,
    employee_premium_rate_basis: str | None,
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
            premium_metadata = _resolved_premium_metadata(
                configured_premium_cents=_as_int(meal_rule.get("first_premium_cents")),
                employee_premium_hourly_rate_cents=employee_premium_hourly_rate_cents,
                employee_premium_rate_basis=employee_premium_rate_basis,
            )
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
                    **premium_metadata,
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
            premium_metadata = _resolved_premium_metadata(
                configured_premium_cents=_as_int(meal_rule.get("second_premium_cents")),
                employee_premium_hourly_rate_cents=employee_premium_hourly_rate_cents,
                employee_premium_rate_basis=employee_premium_rate_basis,
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
                    **premium_metadata,
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


def _meal_break_rule_results_washington(
    meal_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    scheduled_span_minutes = _as_int(shift_facts.get("scheduled_span_minutes"))
    has_structured_segments = _as_bool(shift_facts.get("has_structured_segments"))
    first_trigger_minutes = _as_int(meal_rule.get("first_trigger_minutes")) or 300
    if scheduled_span_minutes <= first_trigger_minutes:
        return []
    normal_workday_minutes = _washington_normal_workday_minutes(
        candidate_shift=candidate_shift,
        scheduled_span_minutes=scheduled_span_minutes,
    )
    required_meal_count = _required_washington_meal_break_count(
        scheduled_span_minutes=scheduled_span_minutes,
        normal_workday_minutes=normal_workday_minutes,
        additional_trigger_beyond_normal_minutes=(
            _as_int(meal_rule.get("additional_trigger_beyond_normal_minutes")) or 180
        ),
    )
    first_window_start_minutes = _as_int(meal_rule.get("first_window_start_minutes")) or 120
    first_window_end_minutes = _as_int(meal_rule.get("first_window_end_minutes")) or 300
    first_min_break_minutes = _as_int(meal_rule.get("first_min_break_minutes")) or 30
    qualifying_meal_breaks = sorted(
        [
            break_fact
            for break_fact in break_facts
            if str(break_fact.get("break_type") or "") == "meal"
            and not _as_bool(break_fact.get("is_paid"))
            and (_as_int(break_fact.get("duration_minutes")) or 0) >= first_min_break_minutes
        ],
        key=lambda break_fact: (
            _as_int(break_fact.get("start_offset_minutes")) or 0,
            _as_int(break_fact.get("end_offset_minutes")) or 0,
        ),
    )
    results: list[dict[str, object]] = []

    first_break_index, first_break = _next_qualifying_break_in_offset_window(
        qualifying_meal_breaks,
        minimum_index=0,
        window_start_minutes=first_window_start_minutes,
        window_end_minutes=first_window_end_minutes,
        min_break_minutes=first_min_break_minutes,
    )
    if first_break is None:
        return [
            {
                "rule_code": str(meal_rule.get("first_rule_code") or "meal_break_first_window"),
                "status": "warning" if not has_structured_segments else "block",
                "reason_codes": _meal_reason_codes(
                    base_code="first_meal_break_missing",
                    has_structured_segments=has_structured_segments,
                    waiver_possible=False,
                    waiver_allowed=True,
                ),
                "premium_required": False,
                "would_block": has_structured_segments,
                "required_break_minutes": first_min_break_minutes,
                "meal_break_window_start_minutes": first_window_start_minutes,
                "meal_break_window_end_minutes": first_window_end_minutes,
                "normal_workday_minutes": normal_workday_minutes,
                "required_meal_count": required_meal_count,
            }
        ]
    results.append(
        {
            "rule_code": str(meal_rule.get("first_rule_code") or "meal_break_first_window"),
            "status": "clear",
            "reason_codes": ["first_meal_break_scheduled"],
            "premium_required": False,
            "would_block": False,
            "required_break_minutes": first_min_break_minutes,
            "scheduled_break_minutes": _as_int(first_break.get("duration_minutes")),
            "break_start_offset_minutes": _as_int(first_break.get("start_offset_minutes")),
            "meal_break_window_start_minutes": first_window_start_minutes,
            "meal_break_window_end_minutes": first_window_end_minutes,
            "required_meal_index": 1,
            "normal_workday_minutes": normal_workday_minutes,
            "required_meal_count": required_meal_count,
        }
    )

    previous_break_end_minutes = _as_int(first_break.get("end_offset_minutes"))
    next_minimum_index = first_break_index + 1
    additional_rule_code = str(meal_rule.get("additional_rule_code") or "meal_break_additional_window")
    additional_interval_minutes = _as_int(meal_rule.get("additional_interval_minutes")) or 300
    additional_min_break_minutes = _as_int(meal_rule.get("additional_min_break_minutes")) or 30
    overtime_extension_required = scheduled_span_minutes >= (
        normal_workday_minutes + (_as_int(meal_rule.get("additional_trigger_beyond_normal_minutes")) or 180)
    )
    for required_meal_index in range(2, required_meal_count + 1):
        window_start_minutes = previous_break_end_minutes
        if required_meal_index == 2 and overtime_extension_required:
            window_start_minutes = max(window_start_minutes, normal_workday_minutes)
        window_end_minutes = min(
            scheduled_span_minutes,
            previous_break_end_minutes + additional_interval_minutes,
        )
        break_index, qualifying_break = _next_qualifying_break_in_offset_window(
            qualifying_meal_breaks,
            minimum_index=next_minimum_index,
            window_start_minutes=window_start_minutes,
            window_end_minutes=window_end_minutes,
            min_break_minutes=additional_min_break_minutes,
        )
        if qualifying_break is None:
            results.append(
                {
                    "rule_code": additional_rule_code,
                    "status": "warning" if not has_structured_segments else "block",
                    "reason_codes": _meal_reason_codes(
                        base_code="additional_meal_break_missing",
                        has_structured_segments=has_structured_segments,
                        waiver_possible=False,
                        waiver_allowed=True,
                    ),
                    "premium_required": False,
                    "would_block": has_structured_segments,
                    "required_break_minutes": additional_min_break_minutes,
                    "required_meal_index": required_meal_index,
                    "meal_break_window_start_minutes": window_start_minutes,
                    "meal_break_window_end_minutes": window_end_minutes,
                    "normal_workday_minutes": normal_workday_minutes,
                    "overtime_extension_required": required_meal_index == 2 and overtime_extension_required,
                }
            )
            break
        results.append(
            {
                "rule_code": additional_rule_code,
                "status": "clear",
                "reason_codes": ["additional_meal_break_scheduled"],
                "premium_required": False,
                "would_block": False,
                "required_break_minutes": additional_min_break_minutes,
                "scheduled_break_minutes": _as_int(qualifying_break.get("duration_minutes")),
                "break_start_offset_minutes": _as_int(qualifying_break.get("start_offset_minutes")),
                "required_meal_index": required_meal_index,
                "meal_break_window_start_minutes": window_start_minutes,
                "meal_break_window_end_minutes": window_end_minutes,
                "normal_workday_minutes": normal_workday_minutes,
                "overtime_extension_required": required_meal_index == 2 and overtime_extension_required,
            }
        )
        previous_break_end_minutes = _as_int(qualifying_break.get("end_offset_minutes"))
        next_minimum_index = break_index + 1
    return results


def _meal_break_rule_results_oregon(
    meal_rule: Mapping[str, object],
    *,
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    scheduled_span_minutes = _as_int(shift_facts.get("scheduled_span_minutes"))
    has_structured_segments = _as_bool(shift_facts.get("has_structured_segments"))
    required_meal_count = _required_oregon_meal_break_count(scheduled_span_minutes)
    if required_meal_count <= 0:
        return []

    first_min_break_minutes = _as_int(meal_rule.get("first_min_break_minutes")) or 30
    if scheduled_span_minutes <= (_as_int(meal_rule.get("first_short_shift_max_minutes")) or 420):
        first_window_start_minutes = _as_int(meal_rule.get("first_short_window_start_minutes")) or 120
        first_window_end_minutes = _as_int(meal_rule.get("first_short_window_end_minutes")) or 300
    else:
        first_window_start_minutes = _as_int(meal_rule.get("first_long_window_start_minutes")) or 180
        first_window_end_minutes = _as_int(meal_rule.get("first_long_window_end_minutes")) or 360

    qualifying_meal_breaks = sorted(
        [
            break_fact
            for break_fact in break_facts
            if str(break_fact.get("break_type") or "") == "meal"
            and not _as_bool(break_fact.get("is_paid"))
            and (_as_int(break_fact.get("duration_minutes")) or 0) >= first_min_break_minutes
        ],
        key=lambda break_fact: (
            _as_int(break_fact.get("start_offset_minutes")) or 0,
            _as_int(break_fact.get("end_offset_minutes")) or 0,
        ),
    )

    first_break_index = -1
    first_break: Mapping[str, object] | None = None
    for break_index, break_fact in enumerate(qualifying_meal_breaks):
        start_offset_minutes = _as_int(break_fact.get("start_offset_minutes")) or 0
        end_offset_minutes = _as_int(break_fact.get("end_offset_minutes")) or 0
        if start_offset_minutes < first_window_start_minutes or end_offset_minutes > first_window_end_minutes:
            continue
        first_break_index = break_index
        first_break = break_fact
        break
    if first_break is None:
        return [
            {
                "rule_code": str(meal_rule.get("first_rule_code") or "meal_break_first_window"),
                "status": "warning" if not has_structured_segments else "block",
                "reason_codes": _meal_reason_codes(
                    base_code="first_meal_break_missing",
                    has_structured_segments=has_structured_segments,
                    waiver_possible=False,
                    waiver_allowed=False,
                ),
                "premium_required": False,
                "would_block": has_structured_segments,
                "required_break_minutes": first_min_break_minutes,
                "meal_break_window_start_minutes": first_window_start_minutes,
                "meal_break_window_end_minutes": first_window_end_minutes,
                "required_meal_count": required_meal_count,
            }
        ]

    results: list[dict[str, object]] = [
        {
            "rule_code": str(meal_rule.get("first_rule_code") or "meal_break_first_window"),
            "status": "clear",
            "reason_codes": ["first_meal_break_scheduled"],
            "premium_required": False,
            "would_block": False,
            "required_break_minutes": first_min_break_minutes,
            "scheduled_break_minutes": _as_int(first_break.get("duration_minutes")),
            "break_start_offset_minutes": _as_int(first_break.get("start_offset_minutes")),
            "meal_break_window_start_minutes": first_window_start_minutes,
            "meal_break_window_end_minutes": first_window_end_minutes,
            "required_meal_count": required_meal_count,
        }
    ]
    if required_meal_count <= 1:
        return results

    additional_breaks = [
        break_fact
        for break_fact in qualifying_meal_breaks[first_break_index + 1 :]
        if (_as_int(break_fact.get("start_offset_minutes")) or 0)
        > (_as_int(first_break.get("end_offset_minutes")) or 0)
    ]
    if len(additional_breaks) < (required_meal_count - 1):
        results.append(
            {
                "rule_code": str(meal_rule.get("additional_rule_code") or "meal_break_additional_window"),
                "status": "warning" if not has_structured_segments else "block",
                "reason_codes": _meal_reason_codes(
                    base_code="additional_meal_break_missing",
                    has_structured_segments=has_structured_segments,
                    waiver_possible=False,
                    waiver_allowed=False,
                ),
                "premium_required": False,
                "would_block": has_structured_segments,
                "required_break_minutes": first_min_break_minutes,
                "required_meal_count": required_meal_count,
                "actual_meal_count": 1 + len(additional_breaks),
            }
        )
        return results

    results.append(
        {
            "rule_code": str(meal_rule.get("additional_rule_code") or "meal_break_additional_window"),
            "status": "clear",
            "reason_codes": ["additional_meal_break_scheduled"],
            "premium_required": False,
            "would_block": False,
            "required_break_minutes": first_min_break_minutes,
            "required_meal_count": required_meal_count,
            "actual_meal_count": 1 + len(additional_breaks),
        }
    )
    return results


def _meal_break_rule_results_colorado(
    profile: labor_rules.LaborRuleProfileSnapshot,
    meal_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
    employee_premium_hourly_rate_cents: int | None,
    employee_premium_rate_basis: str | None,
) -> list[dict[str, object]]:
    scheduled_span_minutes = _as_int(shift_facts.get("scheduled_span_minutes"))
    has_structured_segments = _as_bool(shift_facts.get("has_structured_segments"))
    first_trigger_minutes = _as_int(meal_rule.get("first_trigger_minutes")) or 300
    if scheduled_span_minutes <= first_trigger_minutes:
        return []

    first_window_start_minutes = _as_int(meal_rule.get("first_window_start_minutes")) or 60
    first_window_end_minutes = max(
        first_window_start_minutes,
        scheduled_span_minutes - (_as_int(meal_rule.get("first_window_end_offset_minutes")) or 60),
    )
    first_min_break_minutes = _as_int(meal_rule.get("first_min_break_minutes")) or 30
    allows_on_duty_paid_meal = _as_bool(meal_rule.get("allows_on_duty_paid_meal"))
    provided_meal_minutes = sum(
        max(0, _as_int(break_fact.get("duration_minutes")) or 0)
        for break_fact in break_facts
        if str(break_fact.get("break_type") or "") == "meal"
    )
    uncompensated_missing_meal_minutes = max(
        0,
        first_min_break_minutes - min(provided_meal_minutes, first_min_break_minutes),
    )

    qualifying_break = next(
        (
            break_fact
            for break_fact in sorted(
                break_facts,
                key=lambda current_break: (
                    _as_int(current_break.get("start_offset_minutes")) or 0,
                    _as_int(current_break.get("end_offset_minutes")) or 0,
                ),
            )
            if str(break_fact.get("break_type") or "") == "meal"
            and (
                allows_on_duty_paid_meal
                or not _as_bool(break_fact.get("is_paid"))
            )
            and (_as_int(break_fact.get("duration_minutes")) or 0) >= first_min_break_minutes
            and (_as_int(break_fact.get("start_offset_minutes")) or 0) >= first_window_start_minutes
            and (_as_int(break_fact.get("end_offset_minutes")) or 0) <= first_window_end_minutes
        ),
        None,
    )
    if qualifying_break is None:
        premium_required = False
        premium_type: str | None = None
        premium_cents = 0
        premium_regular_minutes = 0
        premium_ot_minutes = 0
        premium_dt_minutes = 0
        reason_codes = _meal_reason_codes(
            base_code="first_meal_break_missing",
            has_structured_segments=has_structured_segments,
            waiver_possible=False,
            waiver_allowed=False,
        )
        if has_structured_segments and uncompensated_missing_meal_minutes > 0:
            reason_codes.append("meal_break_wages_due")
            premium_required = True
            if (employee_premium_hourly_rate_cents or 0) > 0:
                incremental_wages = _incremental_wages_from_added_work_minutes(
                    profile,
                    candidate_shift=candidate_shift,
                    counted_intervals=counted_intervals,
                    added_work_minutes=uncompensated_missing_meal_minutes,
                    employee_base_hourly_rate_cents=employee_premium_hourly_rate_cents,
                )
                premium_type = "fixed_cents"
                premium_cents = incremental_wages["premium_cents"]
                premium_regular_minutes = incremental_wages["regular_minutes"]
                premium_ot_minutes = incremental_wages["ot_minutes"]
                premium_dt_minutes = incremental_wages["dt_minutes"]
                premium_rate_basis = employee_premium_rate_basis
                premium_rate_hourly_cents = employee_premium_hourly_rate_cents
                if premium_ot_minutes > 0 or premium_dt_minutes > 0:
                    reason_codes.append("meal_break_wages_include_overtime")
            else:
                premium_type = "wage_dependent_unresolved"
                premium_rate_basis = "wage_basis_missing"
                premium_rate_hourly_cents = None
                reason_codes.append("wage_dependent_premium_unresolved")
        else:
            premium_rate_basis = None
            premium_rate_hourly_cents = None
        return [
            {
                "rule_code": str(meal_rule.get("first_rule_code") or "meal_break_first_window"),
                "status": "warning" if not has_structured_segments else "block",
                "reason_codes": reason_codes,
                "premium_required": premium_required,
                "premium_type": premium_type,
                "premium_cents": premium_cents,
                "premium_rate_basis": premium_rate_basis,
                "premium_rate_hourly_cents": premium_rate_hourly_cents,
                "would_block": has_structured_segments,
                "required_break_minutes": first_min_break_minutes,
                "meal_break_window_start_minutes": first_window_start_minutes,
                "meal_break_window_end_minutes": first_window_end_minutes,
                "provided_meal_minutes": provided_meal_minutes,
                "uncompensated_missing_meal_minutes": uncompensated_missing_meal_minutes,
                "premium_regular_minutes": premium_regular_minutes,
                "premium_ot_minutes": premium_ot_minutes,
                "premium_dt_minutes": premium_dt_minutes,
            }
        ]
    return [
        {
            "rule_code": str(meal_rule.get("first_rule_code") or "meal_break_first_window"),
            "status": "clear",
            "reason_codes": ["first_meal_break_scheduled"],
            "premium_required": False,
            "would_block": False,
            "required_break_minutes": first_min_break_minutes,
            "scheduled_break_minutes": _as_int(qualifying_break.get("duration_minutes")),
            "break_start_offset_minutes": _as_int(qualifying_break.get("start_offset_minutes")),
            "meal_break_window_start_minutes": first_window_start_minutes,
            "meal_break_window_end_minutes": first_window_end_minutes,
            "meal_break_is_paid": _as_bool(qualifying_break.get("is_paid")),
            "provided_meal_minutes": provided_meal_minutes,
        }
    ]


def _meal_break_rule_results_new_york_non_factory(
    meal_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    scheduled_span_minutes = _as_int(shift_facts.get("scheduled_span_minutes"))
    has_structured_segments = _as_bool(shift_facts.get("has_structured_segments"))
    shift_timezone = _shift_timezone(candidate_shift)
    shift_local_start = candidate_shift.starts_at.astimezone(shift_timezone)
    shift_local_end = candidate_shift.ends_at.astimezone(shift_timezone)
    shift_local_date = shift_local_start.date()

    qualifying_meal_breaks = [
        break_fact
        for break_fact in break_facts
        if str(break_fact.get("break_type") or "") == "meal" and not _as_bool(break_fact.get("is_paid"))
    ]

    results: list[dict[str, object]] = []

    midday_trigger_minutes = _as_int(meal_rule.get("midday_trigger_minutes")) or 360
    midday_window_start = _parse_local_time(meal_rule.get("midday_window_start_local")) or time(11, 0)
    midday_window_end = _parse_local_time(meal_rule.get("midday_window_end_local")) or time(14, 0)
    midday_min_break_minutes = _as_int(meal_rule.get("midday_min_break_minutes")) or 30
    midday_rule_code = str(meal_rule.get("midday_rule_code") or "meal_break_midday_window")

    midday_window_start_at, midday_window_end_at = _local_window_bounds_for_date(
        shift_local_date,
        timezone=shift_timezone,
        window_start_local=midday_window_start,
        window_end_local=midday_window_end,
    )
    midday_required = (
        scheduled_span_minutes > midday_trigger_minutes
        and candidate_shift.starts_at < midday_window_end_at
        and candidate_shift.ends_at > midday_window_start_at
    )
    if midday_required:
        qualifying_midday = next(
            (
                break_fact
                for break_fact in qualifying_meal_breaks
                if _meal_break_within_local_window(
                    break_fact,
                    timezone=shift_timezone,
                    window_start_at=midday_window_start_at,
                    window_end_at=midday_window_end_at,
                    min_break_minutes=midday_min_break_minutes,
                )
            ),
            None,
        )
        results.append(
            _windowed_meal_rule_result(
                rule_code=midday_rule_code,
                has_structured_segments=has_structured_segments,
                qualifying_break=qualifying_midday,
                required_break_minutes=midday_min_break_minutes,
                window_start_at=midday_window_start_at,
                window_end_at=midday_window_end_at,
                missing_reason_code="midday_meal_break_missing",
                satisfied_reason_code="midday_meal_break_scheduled",
            )
        )

    evening_rule_code = str(meal_rule.get("evening_rule_code") or "meal_break_evening_window")
    evening_starts_before = _parse_local_time(
        meal_rule.get("evening_required_if_starts_before_local")
    ) or time(11, 0)
    evening_ends_after = _parse_local_time(
        meal_rule.get("evening_required_if_ends_after_local")
    ) or time(19, 0)
    evening_window_start = _parse_local_time(meal_rule.get("evening_window_start_local")) or time(17, 0)
    evening_window_end = _parse_local_time(meal_rule.get("evening_window_end_local")) or time(19, 0)
    evening_min_break_minutes = _as_int(meal_rule.get("evening_min_break_minutes")) or 20
    evening_window_start_at, evening_window_end_at = _local_window_bounds_for_date(
        shift_local_date,
        timezone=shift_timezone,
        window_start_local=evening_window_start,
        window_end_local=evening_window_end,
    )
    evening_required = (
        shift_local_start.timetz().replace(tzinfo=None) < evening_starts_before
        and candidate_shift.ends_at > evening_window_end_at.astimezone(candidate_shift.ends_at.tzinfo)
    )
    if evening_required:
        qualifying_evening = next(
            (
                break_fact
                for break_fact in qualifying_meal_breaks
                if _meal_break_within_local_window(
                    break_fact,
                    timezone=shift_timezone,
                    window_start_at=evening_window_start_at,
                    window_end_at=evening_window_end_at,
                    min_break_minutes=evening_min_break_minutes,
                )
            ),
            None,
        )
        results.append(
            _windowed_meal_rule_result(
                rule_code=evening_rule_code,
                has_structured_segments=has_structured_segments,
                qualifying_break=qualifying_evening,
                required_break_minutes=evening_min_break_minutes,
                window_start_at=evening_window_start_at,
                window_end_at=evening_window_end_at,
                missing_reason_code="evening_meal_break_missing",
                satisfied_reason_code="evening_meal_break_scheduled",
            )
        )

    midshift_rule_code = str(meal_rule.get("midshift_rule_code") or "meal_break_midshift_window")
    midshift_trigger_minutes = _as_int(meal_rule.get("midshift_trigger_minutes")) or 360
    midshift_start_window = _parse_local_time(meal_rule.get("midshift_start_window_local")) or time(13, 0)
    midshift_end_window = _parse_local_time(meal_rule.get("midshift_end_window_local")) or time(6, 0)
    midshift_min_break_minutes = _as_int(meal_rule.get("midshift_min_break_minutes")) or 45
    midshift_tolerance_minutes = _as_int(meal_rule.get("midshift_midpoint_tolerance_minutes")) or 120
    midshift_required = (
        scheduled_span_minutes > midshift_trigger_minutes
        and _local_time_in_wrapped_window(
            shift_local_start.timetz().replace(tzinfo=None),
            window_start=midshift_start_window,
            window_end=midshift_end_window,
        )
    )
    if midshift_required:
        qualifying_midshift = next(
            (
                break_fact
                for break_fact in qualifying_meal_breaks
                if _meal_break_near_shift_midpoint(
                    break_fact,
                    shift=candidate_shift,
                    min_break_minutes=midshift_min_break_minutes,
                    midpoint_tolerance_minutes=midshift_tolerance_minutes,
                )
            ),
            None,
        )
        midpoint_at = candidate_shift.starts_at + (
            candidate_shift.ends_at - candidate_shift.starts_at
        ) / 2
        results.append(
            _midshift_meal_rule_result(
                rule_code=midshift_rule_code,
                has_structured_segments=has_structured_segments,
                qualifying_break=qualifying_midshift,
                required_break_minutes=midshift_min_break_minutes,
                shift_midpoint_at=midpoint_at,
                midpoint_tolerance_minutes=midshift_tolerance_minutes,
            )
        )

    return results


def _paid_rest_break_rule_result(
    profile: labor_rules.LaborRuleProfileSnapshot,
    paid_rest_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
    employee_premium_hourly_rate_cents: int | None,
    employee_premium_rate_basis: str | None,
) -> dict[str, object]:
    mode = str(paid_rest_rule.get("mode") or "ca_count_only").strip().lower()
    if mode == "co_timed":
        return _paid_rest_break_rule_result_colorado(
            profile,
            paid_rest_rule,
            candidate_shift=candidate_shift,
            counted_intervals=counted_intervals,
            shift_facts=shift_facts,
            break_facts=break_facts,
            employee_premium_hourly_rate_cents=employee_premium_hourly_rate_cents,
            employee_premium_rate_basis=employee_premium_rate_basis,
        )
    if mode == "or_timed":
        return _paid_rest_break_rule_result_oregon(
            paid_rest_rule,
            shift_facts=shift_facts,
            break_facts=break_facts,
        )
    if mode == "wa_timed":
        return _paid_rest_break_rule_result_washington(
            paid_rest_rule,
            candidate_shift=candidate_shift,
            shift_facts=shift_facts,
            break_facts=break_facts,
        )
    return _paid_rest_break_rule_result_california(
        paid_rest_rule,
        shift_facts=shift_facts,
        break_facts=break_facts,
        employee_premium_hourly_rate_cents=employee_premium_hourly_rate_cents,
        employee_premium_rate_basis=employee_premium_rate_basis,
    )


def _paid_rest_break_rule_result_california(
    paid_rest_rule: Mapping[str, object],
    *,
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
    employee_premium_hourly_rate_cents: int | None,
    employee_premium_rate_basis: str | None,
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
    premium_metadata = _resolved_premium_metadata(
        configured_premium_cents=_as_int(paid_rest_rule.get("premium_cents")),
        employee_premium_hourly_rate_cents=employee_premium_hourly_rate_cents,
        employee_premium_rate_basis=employee_premium_rate_basis,
    )
    return {
        "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
        "status": "warning",
        "reason_codes": reason_codes,
        "premium_required": True,
        **premium_metadata,
        "would_block": False,
        "required_break_count": required_break_count,
        "actual_break_count": actual_break_count,
        "missing_break_count": max(0, required_break_count - actual_break_count),
        "required_break_minutes": min_break_minutes,
    }


def _paid_rest_break_rule_result_washington(
    paid_rest_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    net_active_work_minutes = _as_int(shift_facts.get("net_active_work_minutes"))
    has_structured_segments = _as_bool(shift_facts.get("has_structured_segments"))
    required_break_count = _required_washington_rest_break_count(net_active_work_minutes)
    min_break_minutes = _as_int(paid_rest_rule.get("min_break_minutes")) or 10
    max_continuous_work_minutes = _as_int(paid_rest_rule.get("max_continuous_work_minutes")) or 180
    qualifying_breaks = [
        break_fact
        for break_fact in break_facts
        if str(break_fact.get("break_type") or "") == "rest"
        and _as_bool(break_fact.get("is_paid"))
        and (_as_int(break_fact.get("duration_minutes")) or 0) >= min_break_minutes
    ]
    actual_break_count = len(qualifying_breaks)
    longest_gap_minutes = _as_int(shift_facts.get("longest_continuous_work_minutes")) or 0
    timing_gap_exceeded = longest_gap_minutes > max_continuous_work_minutes

    if required_break_count <= 0 and not timing_gap_exceeded:
        return {
            "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
            "status": "clear",
            "reason_codes": ["rest_break_not_required"],
            "premium_required": False,
            "would_block": False,
            "required_break_count": 0,
            "actual_break_count": actual_break_count,
            "max_continuous_work_minutes": max_continuous_work_minutes,
            "longest_work_gap_without_rest_break_minutes": longest_gap_minutes,
        }

    if actual_break_count >= required_break_count and not timing_gap_exceeded:
        return {
            "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
            "status": "clear",
            "reason_codes": ["rest_break_quota_satisfied"],
            "premium_required": False,
            "would_block": False,
            "required_break_count": required_break_count,
            "actual_break_count": actual_break_count,
            "required_break_minutes": min_break_minutes,
            "max_continuous_work_minutes": max_continuous_work_minutes,
            "longest_work_gap_without_rest_break_minutes": longest_gap_minutes,
        }

    reason_codes = ["rest_break_quota_missing"]
    if timing_gap_exceeded:
        reason_codes.append("rest_break_timing_gap_exceeded")
    if not has_structured_segments:
        reason_codes.append("structured_break_plan_missing")
    return {
        "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
        "status": "warning" if not has_structured_segments else "block",
        "reason_codes": reason_codes,
        "premium_required": False,
        "would_block": has_structured_segments,
        "required_break_count": required_break_count,
        "actual_break_count": actual_break_count,
        "missing_break_count": max(0, required_break_count - actual_break_count),
        "required_break_minutes": min_break_minutes,
        "max_continuous_work_minutes": max_continuous_work_minutes,
        "longest_work_gap_without_rest_break_minutes": longest_gap_minutes,
    }


def _paid_rest_break_rule_result_colorado(
    profile: labor_rules.LaborRuleProfileSnapshot,
    paid_rest_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
    employee_premium_hourly_rate_cents: int | None,
    employee_premium_rate_basis: str | None,
) -> dict[str, object]:
    scheduled_span_minutes = _as_int(shift_facts.get("scheduled_span_minutes"))
    has_structured_segments = _as_bool(shift_facts.get("has_structured_segments"))
    required_break_count = _required_colorado_rest_break_count(scheduled_span_minutes)
    min_break_minutes = _as_int(paid_rest_rule.get("min_break_minutes")) or 10
    max_continuous_work_minutes = _as_int(paid_rest_rule.get("max_continuous_work_minutes")) or 240
    qualifying_breaks = [
        break_fact
        for break_fact in break_facts
        if str(break_fact.get("break_type") or "") == "rest"
        and _as_bool(break_fact.get("is_paid"))
        and (_as_int(break_fact.get("duration_minutes")) or 0) >= min_break_minutes
    ]
    provided_paid_rest_minutes = sum(
        max(0, _as_int(break_fact.get("duration_minutes")) or 0)
        for break_fact in break_facts
        if str(break_fact.get("break_type") or "") == "rest"
        and _as_bool(break_fact.get("is_paid"))
    )
    actual_break_count = len(qualifying_breaks)
    longest_gap_minutes = _as_int(shift_facts.get("longest_continuous_work_minutes")) or 0
    timing_gap_exceeded = longest_gap_minutes > max_continuous_work_minutes
    required_total_paid_rest_minutes = required_break_count * min_break_minutes
    missing_paid_rest_minutes = max(
        0,
        required_total_paid_rest_minutes
        - min(provided_paid_rest_minutes, required_total_paid_rest_minutes),
    )
    if required_break_count <= 0 and not timing_gap_exceeded:
        return {
            "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
            "status": "clear",
            "reason_codes": ["rest_break_not_required"],
            "premium_required": False,
            "would_block": False,
            "required_break_count": 0,
            "actual_break_count": actual_break_count,
            "max_continuous_work_minutes": max_continuous_work_minutes,
            "longest_work_gap_without_rest_break_minutes": longest_gap_minutes,
            "provided_paid_rest_minutes": provided_paid_rest_minutes,
        }

    if (
        actual_break_count >= required_break_count
        and missing_paid_rest_minutes <= 0
        and not timing_gap_exceeded
    ):
        return {
            "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
            "status": "clear",
            "reason_codes": ["rest_break_quota_satisfied"],
            "premium_required": False,
            "would_block": False,
            "required_break_count": required_break_count,
            "actual_break_count": actual_break_count,
            "required_break_minutes": min_break_minutes,
            "max_continuous_work_minutes": max_continuous_work_minutes,
            "longest_work_gap_without_rest_break_minutes": longest_gap_minutes,
            "provided_paid_rest_minutes": provided_paid_rest_minutes,
        }

    reason_codes = ["rest_break_quota_missing"]
    if timing_gap_exceeded:
        reason_codes.append("rest_break_timing_gap_exceeded")
    if not has_structured_segments:
        reason_codes.append("structured_break_plan_missing")
    premium_required = False
    premium_type: str | None = None
    premium_cents = 0
    premium_regular_minutes = 0
    premium_ot_minutes = 0
    premium_dt_minutes = 0
    premium_rate_basis: str | None = None
    premium_rate_hourly_cents: int | None = None
    if has_structured_segments and missing_paid_rest_minutes > 0:
        reason_codes.append("rest_break_wages_due")
        premium_required = True
        if (employee_premium_hourly_rate_cents or 0) > 0:
            incremental_wages = _incremental_wages_from_added_work_minutes(
                profile,
                candidate_shift=candidate_shift,
                counted_intervals=counted_intervals,
                added_work_minutes=missing_paid_rest_minutes,
                employee_base_hourly_rate_cents=employee_premium_hourly_rate_cents,
            )
            premium_type = "fixed_cents"
            premium_cents = incremental_wages["premium_cents"]
            premium_regular_minutes = incremental_wages["regular_minutes"]
            premium_ot_minutes = incremental_wages["ot_minutes"]
            premium_dt_minutes = incremental_wages["dt_minutes"]
            premium_rate_basis = employee_premium_rate_basis
            premium_rate_hourly_cents = employee_premium_hourly_rate_cents
            if premium_ot_minutes > 0 or premium_dt_minutes > 0:
                reason_codes.append("rest_break_wages_include_overtime")
        else:
            premium_type = "wage_dependent_unresolved"
            premium_rate_basis = "wage_basis_missing"
            reason_codes.append("wage_dependent_premium_unresolved")
    return {
        "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
        "status": "warning" if not has_structured_segments else "block",
        "reason_codes": reason_codes,
        "premium_required": premium_required,
        "premium_type": premium_type,
        "premium_cents": premium_cents,
        "premium_rate_basis": premium_rate_basis,
        "premium_rate_hourly_cents": premium_rate_hourly_cents,
        "would_block": has_structured_segments,
        "required_break_count": required_break_count,
        "actual_break_count": actual_break_count,
        "missing_break_count": max(0, required_break_count - actual_break_count),
        "provided_paid_rest_minutes": provided_paid_rest_minutes,
        "missing_paid_rest_minutes": missing_paid_rest_minutes,
        "required_break_minutes": min_break_minutes,
        "max_continuous_work_minutes": max_continuous_work_minutes,
        "longest_work_gap_without_rest_break_minutes": longest_gap_minutes,
        "premium_regular_minutes": premium_regular_minutes,
        "premium_ot_minutes": premium_ot_minutes,
        "premium_dt_minutes": premium_dt_minutes,
    }


def _paid_rest_break_rule_result_oregon(
    paid_rest_rule: Mapping[str, object],
    *,
    shift_facts: Mapping[str, object],
    break_facts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    scheduled_span_minutes = _as_int(shift_facts.get("scheduled_span_minutes"))
    has_structured_segments = _as_bool(shift_facts.get("has_structured_segments"))
    required_break_count = _required_oregon_rest_break_count(scheduled_span_minutes)
    min_break_minutes = _as_int(paid_rest_rule.get("min_break_minutes")) or 10
    max_continuous_work_minutes = _as_int(paid_rest_rule.get("max_continuous_work_minutes")) or 240
    qualifying_breaks = [
        break_fact
        for break_fact in break_facts
        if str(break_fact.get("break_type") or "") == "rest"
        and _as_bool(break_fact.get("is_paid"))
        and (_as_int(break_fact.get("duration_minutes")) or 0) >= min_break_minutes
    ]
    actual_break_count = len(qualifying_breaks)
    longest_gap_minutes = _as_int(shift_facts.get("longest_continuous_work_minutes")) or 0
    timing_gap_exceeded = longest_gap_minutes > max_continuous_work_minutes
    if required_break_count <= 0 and not timing_gap_exceeded:
        return {
            "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
            "status": "clear",
            "reason_codes": ["rest_break_not_required"],
            "premium_required": False,
            "would_block": False,
            "required_break_count": 0,
            "actual_break_count": actual_break_count,
            "max_continuous_work_minutes": max_continuous_work_minutes,
            "longest_work_gap_without_rest_break_minutes": longest_gap_minutes,
        }

    if actual_break_count >= required_break_count and not timing_gap_exceeded:
        return {
            "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
            "status": "clear",
            "reason_codes": ["rest_break_quota_satisfied"],
            "premium_required": False,
            "would_block": False,
            "required_break_count": required_break_count,
            "actual_break_count": actual_break_count,
            "required_break_minutes": min_break_minutes,
            "max_continuous_work_minutes": max_continuous_work_minutes,
            "longest_work_gap_without_rest_break_minutes": longest_gap_minutes,
        }

    reason_codes = ["rest_break_quota_missing"]
    if timing_gap_exceeded:
        reason_codes.append("rest_break_timing_gap_exceeded")
    if not has_structured_segments:
        reason_codes.append("structured_break_plan_missing")
    return {
        "rule_code": str(paid_rest_rule.get("rule_code") or "paid_rest_break_quota"),
        "status": "warning" if not has_structured_segments else "block",
        "reason_codes": reason_codes,
        "premium_required": False,
        "would_block": has_structured_segments,
        "required_break_count": required_break_count,
        "actual_break_count": actual_break_count,
        "missing_break_count": max(0, required_break_count - actual_break_count),
        "required_break_minutes": min_break_minutes,
        "max_continuous_work_minutes": max_continuous_work_minutes,
        "longest_work_gap_without_rest_break_minutes": longest_gap_minutes,
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
        "premium_rate_basis": (
            "configured_fixed_cents" if premium_type == "fixed_cents" else "wage_basis_missing"
        ),
        "premium_rate_hourly_cents": None,
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
        "premium_rate_basis": _normalized_optional_string(
            spread_of_hours_rule.get("premium_rate_basis")
        ),
        "premium_rate_hourly_cents": _as_int(
            spread_of_hours_rule.get("premium_rate_hourly_cents")
        ),
        "would_block": False,
        "scheduled_span_minutes": scheduled_span_minutes,
        "threshold_minutes": threshold_minutes,
        "excess_minutes": max(0, scheduled_span_minutes - threshold_minutes),
    }


def _day_of_rest_rule_result(
    day_of_rest_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
) -> dict[str, object]:
    rule_code = str(day_of_rest_rule.get("rule_code") or "day_of_rest_in_seven")
    max_consecutive_work_days = _as_int(day_of_rest_rule.get("max_consecutive_work_days")) or 0
    projected_streak = _projected_consecutive_workday_streak(
        candidate_shift=candidate_shift,
        counted_intervals=counted_intervals,
    )
    if projected_streak["projected_consecutive_work_days"] <= max_consecutive_work_days:
        return {
            "rule_code": rule_code,
            "status": "clear",
            "reason_codes": ["consecutive_workday_limit_satisfied"],
            "premium_required": False,
            "would_block": False,
            "projected_consecutive_work_days": projected_streak["projected_consecutive_work_days"],
            "max_consecutive_work_days": max_consecutive_work_days,
            "streak_start_date": projected_streak["streak_start_date"],
            "streak_end_date": projected_streak["streak_end_date"],
            "candidate_worked_dates_local": projected_streak["candidate_worked_dates_local"],
        }

    reason_codes = ["consecutive_workday_limit_exceeded"]
    if max_consecutive_work_days == 6:
        reason_codes.append("seven_consecutive_workdays_projected")
    return {
        "rule_code": rule_code,
        "status": "block",
        "reason_codes": reason_codes,
        "premium_required": False,
        "would_block": True,
        "projected_consecutive_work_days": projected_streak["projected_consecutive_work_days"],
        "max_consecutive_work_days": max_consecutive_work_days,
        "excess_consecutive_work_days": max(
            0,
            projected_streak["projected_consecutive_work_days"] - max_consecutive_work_days,
        ),
        "streak_start_date": projected_streak["streak_start_date"],
        "streak_end_date": projected_streak["streak_end_date"],
        "candidate_worked_dates_local": projected_streak["candidate_worked_dates_local"],
    }


def _day_of_rest_workweek_rule_result(
    profile: labor_rules.LaborRuleProfileSnapshot,
    day_of_rest_workweek_rule: Mapping[str, object],
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
) -> dict[str, object]:
    rule_code = str(day_of_rest_workweek_rule.get("rule_code") or "day_of_rest_workweek")
    required_rest_days = _as_int(day_of_rest_workweek_rule.get("required_rest_days_per_workweek")) or 0
    max_workdays = _as_int(day_of_rest_workweek_rule.get("max_workdays_per_workweek")) or max(0, 7 - required_rest_days)
    projected_workweek = _projected_worked_days_in_workweek(
        profile,
        candidate_shift=candidate_shift,
        counted_intervals=counted_intervals,
    )
    projected_days = int(projected_workweek["projected_workdays_in_workweek"])
    if projected_days <= max_workdays:
        return {
            "rule_code": rule_code,
            "status": "clear",
            "reason_codes": ["workweek_rest_day_satisfied"],
            "premium_required": False,
            "would_block": False,
            "required_rest_days_per_workweek": required_rest_days,
            "max_workdays_per_workweek": max_workdays,
            "projected_workdays_in_workweek": projected_days,
            "workweek_start_date": projected_workweek["workweek_start_date"],
            "workweek_end_date": projected_workweek["workweek_end_date"],
            "candidate_worked_dates_local": projected_workweek["candidate_worked_dates_local"],
            "projected_worked_dates_local": projected_workweek["projected_worked_dates_local"],
        }

    reason_codes = ["workweek_rest_day_missing"]
    if max_workdays == 6:
        reason_codes.append("seven_workdays_in_workweek_projected")
    return {
        "rule_code": rule_code,
        "status": "block",
        "reason_codes": reason_codes,
        "premium_required": False,
        "would_block": True,
        "required_rest_days_per_workweek": required_rest_days,
        "max_workdays_per_workweek": max_workdays,
        "projected_workdays_in_workweek": projected_days,
        "excess_workdays_in_workweek": max(0, projected_days - max_workdays),
        "workweek_start_date": projected_workweek["workweek_start_date"],
        "workweek_end_date": projected_workweek["workweek_end_date"],
        "candidate_worked_dates_local": projected_workweek["candidate_worked_dates_local"],
        "projected_worked_dates_local": projected_workweek["projected_worked_dates_local"],
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


def _resolved_employee_premium_rate_context(
    *,
    employee_base_hourly_rate_cents: int | None,
    employee_premium_hourly_rate_cents: int | None,
) -> dict[str, object]:
    if (employee_premium_hourly_rate_cents or 0) > 0:
        return {
            "premium_rate_basis": "employee_compliance_regular_rate",
            "premium_rate_hourly_cents": max(0, int(employee_premium_hourly_rate_cents or 0)),
        }
    if (employee_base_hourly_rate_cents or 0) > 0:
        return {
            "premium_rate_basis": "employee_base_hourly_rate_fallback",
            "premium_rate_hourly_cents": max(0, int(employee_base_hourly_rate_cents or 0)),
        }
    return {
        "premium_rate_basis": "wage_basis_missing",
        "premium_rate_hourly_cents": None,
    }


def _incremental_wages_from_added_work_minutes(
    profile: labor_rules.LaborRuleProfileSnapshot,
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
    added_work_minutes: int,
    employee_base_hourly_rate_cents: int,
) -> dict[str, int]:
    baseline_buckets = labor_rules.overtime_projection_buckets(
        profile,
        candidate_shift=candidate_shift,
        counted_intervals=counted_intervals,
    )
    extended_shift = SimpleNamespace(
        id=candidate_shift.id,
        starts_at=candidate_shift.starts_at,
        ends_at=candidate_shift.ends_at + timedelta(minutes=added_work_minutes),
        timezone=candidate_shift.timezone,
    )
    extended_buckets = labor_rules.overtime_projection_buckets(
        profile,
        candidate_shift=extended_shift,
        counted_intervals=counted_intervals,
    )
    regular_hours_delta = max(
        0.0,
        (_as_float(extended_buckets.get("projected_regular_hours")) or 0.0)
        - (_as_float(baseline_buckets.get("projected_regular_hours")) or 0.0),
    )
    ot_hours_delta = max(
        0.0,
        (_as_float(extended_buckets.get("projected_ot_hours")) or 0.0)
        - (_as_float(baseline_buckets.get("projected_ot_hours")) or 0.0),
    )
    dt_hours_delta = max(
        0.0,
        (_as_float(extended_buckets.get("projected_dt_hours")) or 0.0)
        - (_as_float(baseline_buckets.get("projected_dt_hours")) or 0.0),
    )
    premium_cents = round(
        (employee_base_hourly_rate_cents * regular_hours_delta)
        + (employee_base_hourly_rate_cents * 1.5 * ot_hours_delta)
        + (employee_base_hourly_rate_cents * 2.0 * dt_hours_delta)
    )
    return {
        "premium_cents": max(0, premium_cents),
        "regular_minutes": max(0, round(regular_hours_delta * 60)),
        "ot_minutes": max(0, round(ot_hours_delta * 60)),
        "dt_minutes": max(0, round(dt_hours_delta * 60)),
    }


def _resolved_premium_metadata(
    *,
    configured_premium_cents: int,
    employee_premium_hourly_rate_cents: int | None,
    employee_premium_rate_basis: str | None,
) -> dict[str, object]:
    if configured_premium_cents > 0:
        return {
            "premium_type": "fixed_cents",
            "premium_cents": configured_premium_cents,
            "premium_rate_basis": "configured_fixed_cents",
            "premium_rate_hourly_cents": None,
        }
    if (employee_premium_hourly_rate_cents or 0) > 0:
        return {
            "premium_type": "fixed_cents",
            "premium_cents": max(0, int(employee_premium_hourly_rate_cents or 0)),
            "premium_rate_basis": employee_premium_rate_basis or "employee_base_hourly_rate_fallback",
            "premium_rate_hourly_cents": max(0, int(employee_premium_hourly_rate_cents or 0)),
        }
    return {
        "premium_type": "wage_dependent_unresolved",
        "premium_cents": 0,
        "premium_rate_basis": "wage_basis_missing",
        "premium_rate_hourly_cents": None,
    }


def _customer_policy_rule_results(
    *,
    profile: labor_rules.LaborRuleProfileSnapshot,
    compliance_settings: Mapping[str, object],
    shift_facts: Mapping[str, object],
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
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

    max_consecutive_workdays_result = _maximum_consecutive_workdays_policy_rule_result(
        configured_days=_as_int(compliance_settings.get("max_consecutive_work_days")),
        candidate_shift=candidate_shift,
        counted_intervals=counted_intervals,
    )
    if max_consecutive_workdays_result is not None:
        rule_results.append(max_consecutive_workdays_result)

    required_rest_days_per_workweek_result = _required_rest_days_per_workweek_policy_rule_result(
        profile,
        configured_days=_as_int(compliance_settings.get("required_rest_days_per_workweek")),
        candidate_shift=candidate_shift,
        counted_intervals=counted_intervals,
    )
    if required_rest_days_per_workweek_result is not None:
        rule_results.append(required_rest_days_per_workweek_result)

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


def _maximum_consecutive_workdays_policy_rule_result(
    *,
    configured_days: int,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
) -> dict[str, object] | None:
    if configured_days <= 0:
        return None
    projected_streak = _projected_consecutive_workday_streak(
        candidate_shift=candidate_shift,
        counted_intervals=counted_intervals,
    )
    projected_days = int(projected_streak["projected_consecutive_work_days"])
    if projected_days <= configured_days:
        return {
            "rule_code": "customer_policy_max_consecutive_work_days",
            "status": "clear",
            "reason_codes": ["max_consecutive_work_days_satisfied_by_policy"],
            "premium_required": False,
            "would_block": False,
            "configured_days": configured_days,
            "projected_consecutive_work_days": projected_days,
            "streak_start_date": projected_streak["streak_start_date"],
            "streak_end_date": projected_streak["streak_end_date"],
            "candidate_worked_dates_local": projected_streak["candidate_worked_dates_local"],
        }
    reason_codes = ["max_consecutive_work_days_exceeded_by_policy"]
    if configured_days == 6:
        reason_codes.append("seven_consecutive_workdays_projected")
    return {
        "rule_code": "customer_policy_max_consecutive_work_days",
        "status": "block",
        "reason_codes": reason_codes,
        "premium_required": False,
        "would_block": True,
        "configured_days": configured_days,
        "projected_consecutive_work_days": projected_days,
        "excess_consecutive_work_days": max(0, projected_days - configured_days),
        "streak_start_date": projected_streak["streak_start_date"],
        "streak_end_date": projected_streak["streak_end_date"],
        "candidate_worked_dates_local": projected_streak["candidate_worked_dates_local"],
    }


def _required_rest_days_per_workweek_policy_rule_result(
    profile: labor_rules.LaborRuleProfileSnapshot,
    *,
    configured_days: int,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
) -> dict[str, object] | None:
    if configured_days <= 0:
        return None
    projected_workweek = _projected_worked_days_in_workweek(
        profile,
        candidate_shift=candidate_shift,
        counted_intervals=counted_intervals,
    )
    max_workdays = max(0, 7 - configured_days)
    projected_days = int(projected_workweek["projected_workdays_in_workweek"])
    if projected_days <= max_workdays:
        return {
            "rule_code": "customer_policy_required_rest_days_per_workweek",
            "status": "clear",
            "reason_codes": ["workweek_rest_day_satisfied_by_policy"],
            "premium_required": False,
            "would_block": False,
            "required_rest_days_per_workweek": configured_days,
            "max_workdays_per_workweek": max_workdays,
            "projected_workdays_in_workweek": projected_days,
            "workweek_start_date": projected_workweek["workweek_start_date"],
            "workweek_end_date": projected_workweek["workweek_end_date"],
            "candidate_worked_dates_local": projected_workweek["candidate_worked_dates_local"],
            "projected_worked_dates_local": projected_workweek["projected_worked_dates_local"],
        }
    reason_codes = ["workweek_rest_day_missing_by_policy"]
    if max_workdays == 6:
        reason_codes.append("seven_workdays_in_workweek_projected")
    return {
        "rule_code": "customer_policy_required_rest_days_per_workweek",
        "status": "block",
        "reason_codes": reason_codes,
        "premium_required": False,
        "would_block": True,
        "required_rest_days_per_workweek": configured_days,
        "max_workdays_per_workweek": max_workdays,
        "projected_workdays_in_workweek": projected_days,
        "excess_workdays_in_workweek": max(0, projected_days - max_workdays),
        "workweek_start_date": projected_workweek["workweek_start_date"],
        "workweek_end_date": projected_workweek["workweek_end_date"],
        "candidate_worked_dates_local": projected_workweek["candidate_worked_dates_local"],
        "projected_worked_dates_local": projected_workweek["projected_worked_dates_local"],
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


def _projected_consecutive_workday_streak(
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
) -> dict[str, object]:
    timezone_name = candidate_shift.timezone or "UTC"
    worked_day_dates = _worked_local_day_dates(
        timezone_name=timezone_name,
        intervals=counted_intervals,
    )
    candidate_day_dates = _local_dates_for_interval(
        timezone_name=timezone_name,
        start_at=candidate_shift.starts_at,
        end_at=candidate_shift.ends_at,
    )
    worked_day_dates.update(candidate_day_dates)

    if not worked_day_dates:
        return {
            "projected_consecutive_work_days": 0,
            "streak_start_date": None,
            "streak_end_date": None,
            "candidate_worked_dates_local": [],
        }

    streak_length = 0
    streak_start: date | None = None
    streak_end: date | None = None
    ordered_dates = sorted(worked_day_dates)
    current_start = ordered_dates[0]
    current_end = ordered_dates[0]

    def _streak_intersects_candidate_days(start_day: date, end_day: date) -> bool:
        for candidate_day in candidate_day_dates:
            if start_day <= candidate_day <= end_day:
                return True
        return False

    def _consider_streak(start_day: date, end_day: date) -> tuple[int, date | None, date | None]:
        length = (end_day - start_day).days + 1
        if not _streak_intersects_candidate_days(start_day, end_day):
            return streak_length, streak_start, streak_end
        if length > streak_length:
            return length, start_day, end_day
        return streak_length, streak_start, streak_end

    for worked_day in ordered_dates[1:]:
        if worked_day == current_end + timedelta(days=1):
            current_end = worked_day
            continue
        streak_length, streak_start, streak_end = _consider_streak(current_start, current_end)
        current_start = worked_day
        current_end = worked_day

    streak_length, streak_start, streak_end = _consider_streak(current_start, current_end)
    return {
        "projected_consecutive_work_days": streak_length,
        "streak_start_date": streak_start.isoformat() if streak_start is not None else None,
        "streak_end_date": streak_end.isoformat() if streak_end is not None else None,
        "candidate_worked_dates_local": [
            worked_day.isoformat() for worked_day in sorted(candidate_day_dates)
        ],
    }


def _projected_worked_days_in_workweek(
    profile: labor_rules.LaborRuleProfileSnapshot,
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[labor_rules.CountedInterval],
) -> dict[str, object]:
    timezone_name = candidate_shift.timezone or "UTC"
    workweek_start, workweek_end = labor_rules.workweek_window_for_shift(profile, shift=candidate_shift)
    worked_day_dates = _worked_local_day_dates_within_window(
        timezone_name=timezone_name,
        intervals=counted_intervals,
        start_at=workweek_start,
        end_at=workweek_end,
    )
    candidate_day_dates = _local_dates_for_interval_with_window(
        timezone_name=timezone_name,
        start_at=candidate_shift.starts_at,
        end_at=candidate_shift.ends_at,
        window_start=workweek_start,
        window_end=workweek_end,
    )
    worked_day_dates.update(candidate_day_dates)
    shift_timezone = ZoneInfo(timezone_name)
    return {
        "projected_workdays_in_workweek": len(worked_day_dates),
        "workweek_start_date": workweek_start.astimezone(shift_timezone).date().isoformat(),
        "workweek_end_date": (workweek_end - timedelta(minutes=1)).astimezone(shift_timezone).date().isoformat(),
        "candidate_worked_dates_local": [
            worked_day.isoformat() for worked_day in sorted(candidate_day_dates)
        ],
        "projected_worked_dates_local": [
            worked_day.isoformat() for worked_day in sorted(worked_day_dates)
        ],
    }


def _worked_local_day_dates(
    *,
    timezone_name: str,
    intervals: Sequence[labor_rules.CountedInterval],
) -> set[date]:
    worked_dates: set[date] = set()
    for interval in intervals:
        worked_dates.update(
            _local_dates_for_interval(
                timezone_name=timezone_name,
                start_at=interval.start_at,
                end_at=interval.end_at,
            )
        )
    return worked_dates


def _worked_local_day_dates_within_window(
    *,
    timezone_name: str,
    intervals: Sequence[labor_rules.CountedInterval],
    start_at: datetime,
    end_at: datetime,
) -> set[date]:
    worked_dates: set[date] = set()
    for interval in intervals:
        worked_dates.update(
            _local_dates_for_interval_with_window(
                timezone_name=timezone_name,
                start_at=interval.start_at,
                end_at=interval.end_at,
                window_start=start_at,
                window_end=end_at,
            )
        )
    return worked_dates


def _local_dates_for_interval(
    *,
    timezone_name: str,
    start_at: datetime,
    end_at: datetime,
) -> set[date]:
    if end_at <= start_at:
        return set()
    tz = ZoneInfo(timezone_name)
    current_local = start_at.astimezone(tz)
    end_local = end_at.astimezone(tz)
    local_dates: set[date] = set()
    while current_local < end_local:
        local_dates.add(current_local.date())
        next_midnight = datetime.combine(
            current_local.date() + timedelta(days=1),
            time.min,
            tzinfo=tz,
        )
        current_local = min(next_midnight, end_local)
    return local_dates


def _local_dates_for_interval_with_window(
    *,
    timezone_name: str,
    start_at: datetime,
    end_at: datetime,
    window_start: datetime,
    window_end: datetime,
) -> set[date]:
    clipped_start = max(start_at, window_start)
    clipped_end = min(end_at, window_end)
    if clipped_end <= clipped_start:
        return set()
    return _local_dates_for_interval(
        timezone_name=timezone_name,
        start_at=clipped_start,
        end_at=clipped_end,
    )


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


def _windowed_meal_rule_result(
    *,
    rule_code: str,
    has_structured_segments: bool,
    qualifying_break: Mapping[str, object] | None,
    required_break_minutes: int,
    window_start_at: datetime,
    window_end_at: datetime,
    missing_reason_code: str,
    satisfied_reason_code: str,
) -> dict[str, object]:
    if qualifying_break is not None:
        return {
            "rule_code": rule_code,
            "status": "clear",
            "reason_codes": [satisfied_reason_code],
            "premium_required": False,
            "would_block": False,
            "required_break_minutes": required_break_minutes,
            "scheduled_break_minutes": _as_int(qualifying_break.get("duration_minutes")),
            "break_start_at": _iso_or_none(qualifying_break.get("starts_at")),
            "break_end_at": _iso_or_none(qualifying_break.get("ends_at")),
            "window_start_at": window_start_at.isoformat(),
            "window_end_at": window_end_at.isoformat(),
        }
    return {
        "rule_code": rule_code,
        "status": "warning" if not has_structured_segments else "block",
        "reason_codes": _meal_reason_codes(
            base_code=missing_reason_code,
            has_structured_segments=has_structured_segments,
            waiver_possible=False,
            waiver_allowed=True,
        ),
        "premium_required": False,
        "would_block": has_structured_segments,
        "required_break_minutes": required_break_minutes,
        "window_start_at": window_start_at.isoformat(),
        "window_end_at": window_end_at.isoformat(),
    }


def _midshift_meal_rule_result(
    *,
    rule_code: str,
    has_structured_segments: bool,
    qualifying_break: Mapping[str, object] | None,
    required_break_minutes: int,
    shift_midpoint_at: datetime,
    midpoint_tolerance_minutes: int,
) -> dict[str, object]:
    if qualifying_break is not None:
        return {
            "rule_code": rule_code,
            "status": "clear",
            "reason_codes": ["midshift_meal_break_scheduled"],
            "premium_required": False,
            "would_block": False,
            "required_break_minutes": required_break_minutes,
            "scheduled_break_minutes": _as_int(qualifying_break.get("duration_minutes")),
            "break_start_at": _iso_or_none(qualifying_break.get("starts_at")),
            "break_end_at": _iso_or_none(qualifying_break.get("ends_at")),
            "shift_midpoint_at": shift_midpoint_at.isoformat(),
            "midpoint_tolerance_minutes": midpoint_tolerance_minutes,
        }
    return {
        "rule_code": rule_code,
        "status": "warning" if not has_structured_segments else "block",
        "reason_codes": _meal_reason_codes(
            base_code="midshift_meal_break_missing",
            has_structured_segments=has_structured_segments,
            waiver_possible=False,
            waiver_allowed=True,
        ),
        "premium_required": False,
        "would_block": has_structured_segments,
        "required_break_minutes": required_break_minutes,
        "shift_midpoint_at": shift_midpoint_at.isoformat(),
        "midpoint_tolerance_minutes": midpoint_tolerance_minutes,
    }


def _meal_break_within_local_window(
    break_fact: Mapping[str, object],
    *,
    timezone: ZoneInfo,
    window_start_at: datetime,
    window_end_at: datetime,
    min_break_minutes: int,
) -> bool:
    break_start_at = _as_datetime(break_fact.get("starts_at"))
    break_end_at = _as_datetime(break_fact.get("ends_at"))
    break_minutes = _as_int(break_fact.get("duration_minutes")) or 0
    if break_start_at is None or break_end_at is None or break_minutes < min_break_minutes:
        return False
    localized_start = break_start_at.astimezone(timezone)
    localized_end = break_end_at.astimezone(timezone)
    return localized_start >= window_start_at and localized_end <= window_end_at


def _meal_break_near_shift_midpoint(
    break_fact: Mapping[str, object],
    *,
    shift: Shift,
    min_break_minutes: int,
    midpoint_tolerance_minutes: int,
) -> bool:
    break_start_at = _as_datetime(break_fact.get("starts_at"))
    break_end_at = _as_datetime(break_fact.get("ends_at"))
    break_minutes = _as_int(break_fact.get("duration_minutes")) or 0
    if break_start_at is None or break_end_at is None or break_minutes < min_break_minutes:
        return False
    break_midpoint_at = break_start_at + (break_end_at - break_start_at) / 2
    shift_midpoint_at = shift.starts_at + (shift.ends_at - shift.starts_at) / 2
    return abs((break_midpoint_at - shift_midpoint_at).total_seconds()) <= midpoint_tolerance_minutes * 60


def _local_window_bounds_for_date(
    shift_local_date: date,
    *,
    timezone: ZoneInfo,
    window_start_local: time,
    window_end_local: time,
) -> tuple[datetime, datetime]:
    start_at = datetime.combine(shift_local_date, window_start_local, tzinfo=timezone)
    end_at = datetime.combine(shift_local_date, window_end_local, tzinfo=timezone)
    if end_at <= start_at:
        end_at += timedelta(days=1)
    return start_at, end_at


def _local_time_in_wrapped_window(
    value: time,
    *,
    window_start: time,
    window_end: time,
) -> bool:
    if window_start <= window_end:
        return window_start <= value <= window_end
    return value >= window_start or value <= window_end


def _as_datetime(value: object | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _iso_or_none(value: object | None) -> str | None:
    resolved = _as_datetime(value)
    return resolved.isoformat() if resolved is not None else None


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
            "premium_rate_basis": _normalized_optional_string(result.get("premium_rate_basis")),
            "premium_rate_hourly_cents": (
                _as_int(result.get("premium_rate_hourly_cents"))
                if result.get("premium_rate_hourly_cents") is not None
                else None
            ),
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


def _required_oregon_meal_break_count(scheduled_span_minutes: int) -> int:
    if scheduled_span_minutes < 360:
        return 0
    if scheduled_span_minutes < 840:
        return 1
    if scheduled_span_minutes < 1320:
        return 2
    return 3


def _required_oregon_rest_break_count(scheduled_span_minutes: int) -> int:
    if scheduled_span_minutes <= 120:
        return 0
    full_blocks = scheduled_span_minutes // 240
    remainder = scheduled_span_minutes % 240
    return full_blocks + (1 if remainder > 120 else 0)


def _required_colorado_rest_break_count(scheduled_span_minutes: int) -> int:
    if scheduled_span_minutes <= 120:
        return 0
    full_blocks = scheduled_span_minutes // 240
    remainder = scheduled_span_minutes % 240
    return full_blocks + (1 if remainder > 120 else 0)


def _required_washington_rest_break_count(net_active_work_minutes: int) -> int:
    if net_active_work_minutes <= 180:
        return 0
    full_blocks = net_active_work_minutes // 240
    remainder = net_active_work_minutes % 240
    return full_blocks + (1 if remainder > 180 else 0)


def _required_washington_meal_break_count(
    *,
    scheduled_span_minutes: int,
    normal_workday_minutes: int,
    additional_trigger_beyond_normal_minutes: int,
) -> int:
    if scheduled_span_minutes <= 300:
        return 0
    required_by_consecutive_hours = max(1, (scheduled_span_minutes - 300 + 329) // 330)
    if scheduled_span_minutes >= normal_workday_minutes + additional_trigger_beyond_normal_minutes:
        return max(required_by_consecutive_hours, 2)
    return required_by_consecutive_hours


def _washington_normal_workday_minutes(
    *,
    candidate_shift: Shift,
    scheduled_span_minutes: int,
) -> int:
    shift_metadata = candidate_shift.shift_metadata if isinstance(candidate_shift.shift_metadata, Mapping) else {}
    raw_minutes = _as_int(shift_metadata.get("compliance_normal_workday_minutes"))
    if raw_minutes > 0:
        return raw_minutes
    raw_start = shift_metadata.get("compliance_normal_shift_starts_at")
    raw_end = shift_metadata.get("compliance_normal_shift_ends_at")
    if isinstance(raw_start, str) and isinstance(raw_end, str):
        try:
            starts_at = datetime.fromisoformat(raw_start)
            ends_at = datetime.fromisoformat(raw_end)
        except ValueError:
            return scheduled_span_minutes
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=timezone.utc)
        if ends_at > starts_at:
            return max(0, int(round((ends_at - starts_at).total_seconds() / 60.0)))
    return scheduled_span_minutes


def _next_qualifying_break_in_offset_window(
    break_facts: Sequence[Mapping[str, object]],
    *,
    minimum_index: int,
    window_start_minutes: int,
    window_end_minutes: int,
    min_break_minutes: int,
) -> tuple[int, Mapping[str, object] | None]:
    for break_index in range(max(0, minimum_index), len(break_facts)):
        break_fact = break_facts[break_index]
        start_offset_minutes = _as_int(break_fact.get("start_offset_minutes")) or 0
        if start_offset_minutes < window_start_minutes or start_offset_minutes > window_end_minutes:
            continue
        if (_as_int(break_fact.get("duration_minutes")) or 0) < min_break_minutes:
            continue
        return break_index, break_fact
    return -1, None


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
