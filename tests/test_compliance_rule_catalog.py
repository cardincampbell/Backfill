from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.business import Location
from app.services import compliance_rule_catalog, labor_rules


@pytest.mark.asyncio
async def test_location_compliance_rule_catalog_includes_active_profiles_and_permit_templates(monkeypatch):
    location = Location(
        id=uuid4(),
        business_id=uuid4(),
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        region="CA",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
    )
    reference_time = datetime(2026, 4, 28, 18, 0, tzinfo=timezone.utc)

    async def fake_active_profiles(_session, jurisdiction_code, *, as_of):
        assert jurisdiction_code == "US-CA"
        assert as_of == reference_time
        return [
            labor_rules.LaborRuleProfileSnapshot(
                profile_id=uuid4(),
                code="ca_restaurant_v1",
                jurisdiction_code="US-CA",
                display_name="California restaurant baseline",
                overtime_mode="daily_8_plus_weekly_plus_7th_day",
                daily_ot_threshold_hours=8.0,
                weekly_ot_threshold_hours=40.0,
                double_time_threshold_hours=12.0,
                consecutive_hours_threshold_hours=None,
                industry_profile_code="restaurant",
                rules_json={
                    "meal_break_ruleset": "ca_v1",
                    "rest_break_ruleset": "ca_v1",
                    "day_of_rest_ruleset": "ca_v1",
                    "day_of_rest_workweek_required": True,
                    "rest_window_required": True,
                },
                effective_start_date=None,
                effective_end_date=None,
                source_urls=("https://example.com/ca-rule-pack",),
                source_version="ca_rule_pack_v3",
                source_hash="sha256:ca-pack",
                version_id=uuid4(),
                version_no=3,
                payload_hash="sha256:profile-payload",
                payload_json={"code": "ca_restaurant_v1"},
            )
        ]

    monkeypatch.setattr(
        labor_rules,
        "active_profiles_for_jurisdiction",
        fake_active_profiles,
    )

    catalog = await compliance_rule_catalog.location_compliance_rule_catalog(
        None,  # type: ignore[arg-type]
        location=location,
        as_of=reference_time,
    )

    assert catalog["jurisdiction_code"] == "US-CA"
    assert len(catalog["labor_rule_profiles"]) == 1
    labor_entry = catalog["labor_rule_profiles"][0]
    assert labor_entry["code"] == "ca_restaurant_v1"
    assert labor_entry["source_version"] == "ca_rule_pack_v3"
    assert labor_entry["rule_families"] == [
        "day_of_rest",
        "meal_break",
        "overtime",
        "rest_break",
        "rest_window",
    ]

    assert len(catalog["work_permit_templates"]) >= 1
    permit_entry = catalog["work_permit_templates"][0]
    assert permit_entry["catalog_kind"] == "work_permit_template"
    assert permit_entry["jurisdiction_code"] == "US-CA"
    assert permit_entry["source_version"] == "dir_minors_summary_charts_v1"
    assert "minor_labor" in permit_entry["rule_families"]
    assert permit_entry["payload_hash"].startswith("sha256:")


@pytest.mark.asyncio
async def test_location_compliance_rule_catalog_classifies_new_york_hospitality_rules(monkeypatch):
    location = Location(
        id=uuid4(),
        business_id=uuid4(),
        name="Hotel",
        display_name="Hotel",
        slug="hotel",
        region="NY",
        country_code="US",
        timezone="America/New_York",
        settings={"labor_industry_profile_code": "hospitality"},
    )
    reference_time = datetime(2026, 5, 1, 18, 0, tzinfo=timezone.utc)

    async def fake_active_profiles(_session, jurisdiction_code, *, as_of):
        assert jurisdiction_code == "US-NY"
        assert as_of == reference_time
        return [
            labor_rules.LaborRuleProfileSnapshot(
                profile_id=uuid4(),
                code="us_ny_hospitality_nonexempt",
                jurisdiction_code="US-NY",
                display_name="New York Hospitality Nonexempt",
                overtime_mode="weekly_only",
                daily_ot_threshold_hours=None,
                weekly_ot_threshold_hours=40.0,
                double_time_threshold_hours=None,
                consecutive_hours_threshold_hours=None,
                industry_profile_code="hospitality",
                rules_json={
                    "workweek_start_day_local": "sunday",
                    "workweek_start_time_local": "00:00",
                    "meal_break_ruleset": "ny_non_factory_v1",
                    "spread_of_hours_ruleset": "ny_v1",
                    "day_of_rest_workweek_required": True,
                },
                effective_start_date=None,
                effective_end_date=None,
                source_urls=("https://dol.ny.gov/hospitality-industry-wage-order-cr146",),
                source_version="seed_v1_ny_hospitality_compliance_pack",
                source_hash="sha256:ny-hospitality-pack",
                version_id=uuid4(),
                version_no=1,
                payload_hash="sha256:ny-hospitality-profile",
                payload_json={"code": "us_ny_hospitality_nonexempt"},
            )
        ]

    monkeypatch.setattr(
        labor_rules,
        "active_profiles_for_jurisdiction",
        fake_active_profiles,
    )

    catalog = await compliance_rule_catalog.location_compliance_rule_catalog(
        None,  # type: ignore[arg-type]
        location=location,
        as_of=reference_time,
    )

    labor_entry = catalog["labor_rule_profiles"][0]
    assert labor_entry["code"] == "us_ny_hospitality_nonexempt"
    assert labor_entry["rule_families"] == ["day_of_rest", "meal_break", "overtime", "spread_of_hours"]
