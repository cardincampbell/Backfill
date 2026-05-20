from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Location
from app.services import labor_rules, work_permit_rules


def _country_code_from_jurisdiction(jurisdiction_code: str) -> str | None:
    parts = str(jurisdiction_code or "").strip().upper().split("-", 1)
    return parts[0] if parts and parts[0] else None


def _template_applies_to_jurisdiction(
    template_jurisdiction_code: str | None,
    jurisdiction_code: str,
) -> bool:
    template_code = str(template_jurisdiction_code or "").strip().upper()
    current_code = str(jurisdiction_code or "").strip().upper()
    if not template_code or not current_code:
        return True
    if template_code == current_code:
        return True
    return _country_code_from_jurisdiction(template_code) == _country_code_from_jurisdiction(current_code)


def _labor_profile_rule_families(profile: labor_rules.LaborRuleProfileSnapshot) -> list[str]:
    rules = dict(profile.rules_json or {})
    families: set[str] = set()
    if profile.overtime_mode:
        families.add("overtime")
    if rules.get("rest_window_required") or rules.get("minimum_rest_hours"):
        families.add("rest_window")
    if rules.get("meal_break_ruleset") or rules.get("meal_break_required"):
        families.add("meal_break")
    if rules.get("rest_break_ruleset") or rules.get("paid_rest_break_required"):
        families.add("rest_break")
    if rules.get("split_shift_required") or rules.get("split_shift_ruleset"):
        families.add("split_shift")
    if rules.get("spread_of_hours_required") or rules.get("spread_of_hours_ruleset"):
        families.add("spread_of_hours")
    if (
        rules.get("day_of_rest_required")
        or rules.get("day_of_rest_ruleset")
        or rules.get("day_of_rest_workweek_required")
        or rules.get("required_rest_days_per_workweek")
    ):
        families.add("day_of_rest")
    if rules.get("minor_labor_ruleset") or rules.get("work_permit_required"):
        families.add("minor_labor")
        families.add("work_permit")
    return sorted(families or {"general_labor"})


def _labor_profile_entry(profile: labor_rules.LaborRuleProfileSnapshot) -> dict[str, Any]:
    return {
        "catalog_kind": "labor_rule_profile",
        "code": profile.code,
        "label": profile.display_name,
        "description": None,
        "jurisdiction_code": profile.jurisdiction_code,
        "source_document_title": None,
        "source_urls": list(profile.source_urls),
        "source_version": profile.source_version,
        "source_hash": profile.source_hash,
        "effective_start_date": profile.effective_start_date,
        "effective_end_date": profile.effective_end_date,
        "payload_hash": profile.payload_hash,
        "rule_families": _labor_profile_rule_families(profile),
        "version_id": profile.version_id,
        "version_no": profile.version_no,
        "rule_payload": dict(profile.payload_json or {}),
    }


def _work_permit_template_entry(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "catalog_kind": "work_permit_template",
        "code": str(template.get("code") or ""),
        "label": str(template.get("label") or template.get("code") or ""),
        "description": template.get("description"),
        "jurisdiction_code": template.get("jurisdiction_code"),
        "source_document_title": template.get("source_document_title"),
        "source_urls": [template["source_url"]] if template.get("source_url") else [],
        "source_version": template.get("source_version"),
        "source_hash": template.get("source_hash"),
        "effective_start_date": template.get("effective_start_date"),
        "effective_end_date": template.get("effective_end_date"),
        "payload_hash": template.get("payload_hash"),
        "rule_families": list(template.get("rule_families") or []),
        "version_id": None,
        "version_no": None,
        "rule_payload": dict(template.get("rule_profile") or {}),
    }


async def location_compliance_rule_catalog(
    session: AsyncSession,
    *,
    location: Location,
    as_of: datetime | None = None,
) -> dict[str, object]:
    reference_time = as_of or datetime.now(timezone.utc)
    jurisdiction_code = labor_rules.resolve_jurisdiction_code(location)
    labor_profiles = await labor_rules.active_profiles_for_jurisdiction(
        session,
        jurisdiction_code,
        as_of=reference_time,
    )
    permit_templates = [
        _work_permit_template_entry(template)
        for template in work_permit_rules.list_work_permit_templates()
        if _template_applies_to_jurisdiction(
            str(template.get("jurisdiction_code") or "").strip() or None,
            jurisdiction_code,
        )
    ]
    return {
        "location_id": location.id,
        "jurisdiction_code": jurisdiction_code,
        "as_of": reference_time,
        "labor_rule_profiles": [
            _labor_profile_entry(profile)
            for profile in labor_profiles
        ],
        "work_permit_templates": permit_templates,
    }
