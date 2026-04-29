from __future__ import annotations

from typing import Any

from app.schemas.workforce import EmployeeWorkPermitRuleProfile

WORK_PERMIT_WEEKDAY_ORDER = {
    "sunday": 0,
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
}

CALIFORNIA_MINOR_TEMPLATE_SOURCE_URL = "https://www.dir.ca.gov/dlse/MinorsSummaryCharts.pdf"

WORK_PERMIT_RULE_TEMPLATES: dict[str, dict[str, Any]] = {
    "ca_14_15_school_enrolled_v1": {
        "template_code": "ca_14_15_school_enrolled_v1",
        "label": "California ages 14-15 while school enrolled",
        "description": "3 hours on schooldays, 8 hours on non-schooldays, 18 hours on school weeks, and later summer limits.",
        "jurisdiction_code": "US-CA",
        "source_url": CALIFORNIA_MINOR_TEMPLATE_SOURCE_URL,
        "daily_max_minutes_school_day": 180,
        "daily_max_minutes_non_school_day": 480,
        "daily_max_minutes_summer_break": 480,
        "weekly_max_minutes_school_week": 1080,
        "weekly_max_minutes_non_school_week": 2400,
        "weekly_max_minutes_summer_break": 2400,
        "earliest_start_local_time": "07:00",
        "latest_end_local_time": "19:00",
        "latest_end_local_time_summer_break": "21:00",
    },
    "ca_16_17_school_required_v1": {
        "template_code": "ca_16_17_school_required_v1",
        "label": "California ages 16-17 while school required",
        "description": "4 hours on schooldays, 8 hours on non-schooldays, up to 48 hours weekly, with later end time before non-schooldays.",
        "jurisdiction_code": "US-CA",
        "source_url": CALIFORNIA_MINOR_TEMPLATE_SOURCE_URL,
        "daily_max_minutes_school_day": 240,
        "daily_max_minutes_non_school_day": 480,
        "daily_max_minutes_preceding_non_school_day": 480,
        "daily_max_minutes_summer_break": 480,
        "weekly_max_minutes": 2880,
        "weekly_max_minutes_summer_break": 2880,
        "earliest_start_local_time": "05:00",
        "latest_end_local_time": "22:00",
        "latest_end_local_time_preceding_non_school_day": "00:30",
    },
}


def resolve_work_permit_rule_profile_payload(
    value: object | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    try:
        profile = (
            value
            if isinstance(value, EmployeeWorkPermitRuleProfile)
            else EmployeeWorkPermitRuleProfile.model_validate(value)
        )
    except Exception:
        return None
    raw = profile.model_dump(
        mode="json",
        exclude_none=True,
        exclude_defaults=True,
    )
    template_code = str(raw.get("template_code") or "").strip().lower() or None
    template_payload = dict(WORK_PERMIT_RULE_TEMPLATES.get(template_code or "", {}))
    if template_code:
        raw["template_code"] = template_code
    merged = {
        **template_payload,
        **raw,
    }
    weekdays = merged.get("allowed_weekdays")
    if isinstance(weekdays, list):
        merged["allowed_weekdays"] = sorted(
            {
                str(item or "").strip().lower()
                for item in weekdays
                if str(item or "").strip().lower() in WORK_PERMIT_WEEKDAY_ORDER
            },
            key=lambda item: WORK_PERMIT_WEEKDAY_ORDER[item],
        )
        if not merged["allowed_weekdays"]:
            merged.pop("allowed_weekdays", None)
    if not merged:
        return None
    return merged


def list_work_permit_templates() -> list[dict[str, object]]:
    templates: list[dict[str, object]] = []
    for code, payload in sorted(WORK_PERMIT_RULE_TEMPLATES.items()):
        resolved_rule_profile = resolve_work_permit_rule_profile_payload(payload)
        if resolved_rule_profile is None:
            continue
        templates.append(
            {
                "code": code,
                "label": str(payload.get("label") or code),
                "description": str(payload.get("description") or "").strip() or None,
                "jurisdiction_code": str(payload.get("jurisdiction_code") or "").strip() or None,
                "source_url": str(payload.get("source_url") or "").strip() or None,
                "rule_profile": resolved_rule_profile,
            }
        )
    return templates
