from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.business import Business, Location
from app.models.labor_rules import LaborRuleResolutionRun, LocationLaborRuleResolution
from app.services import labor_rule_resolution, labor_rules, llm_gateway


class FakeSession:
    def __init__(self):
        self.added: list[object] = []

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        self.added.append(obj)

    async def flush(self):
        return None


def _business() -> Business:
    now = datetime.now(timezone.utc)
    return Business(
        id=uuid4(),
        name="Cafe Co",
        display_name="Cafe Co",
        slug="cafe-co",
        timezone="America/Los_Angeles",
        settings={"derived_classification": {"vertical": "cafe"}},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )


def _location(*, business_id, settings=None) -> Location:
    now = datetime.now(timezone.utc)
    return Location(
        id=uuid4(),
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        region="CA",
        country_code="US",
        timezone="America/Los_Angeles",
        settings=settings or {},
        google_place_metadata={},
        created_at=now,
        updated_at=now,
    )


def _profile(code: str, *, industry_code: str | None = None) -> labor_rules.LaborRuleProfileSnapshot:
    return labor_rules.LaborRuleProfileSnapshot(
        profile_id=uuid4(),
        code=code,
        jurisdiction_code="US-CA",
        display_name=code,
        overtime_mode="daily_8_plus_weekly_plus_7th_day",
        daily_ot_threshold_hours=8.0,
        weekly_ot_threshold_hours=40.0,
        double_time_threshold_hours=12.0,
        consecutive_hours_threshold_hours=None,
        industry_profile_code=industry_code,
        rules_json={"workweek_start_day_local": "monday", "workweek_start_time_local": "00:00"},
        effective_start_date=None,
        effective_end_date=None,
        source_urls=(),
        source_version="seed",
        source_hash="seed",
        version_id=uuid4(),
        version_no=1,
        payload_hash=f"sha256:{code}",
        payload_json={},
    )


@pytest.mark.asyncio
async def test_sync_location_labor_rule_resolution_primary_persists_authoritative_row(monkeypatch):
    session = FakeSession()
    business = _business()
    location = _location(business_id=business.id)

    monkeypatch.setattr(
        labor_rule_resolution,
        "settings",
        SimpleNamespace(
            labor_rules_mode="primary",
            labor_rule_profile_selection_model="",
        ),
    )
    async def fake_profiles(*args, **kwargs):
        return [_profile("us_ca_general_nonexempt")]

    async def fake_existing(*args, **kwargs):
        return None

    monkeypatch.setattr(labor_rule_resolution.labor_rules, "active_profiles_for_jurisdiction", fake_profiles)
    monkeypatch.setattr(labor_rule_resolution.labor_rules, "load_authoritative_location_resolution", fake_existing)

    outcome = await labor_rule_resolution.sync_location_labor_rule_resolution(
        session,
        business=business,
        location=location,
    )

    assert outcome.applied is True
    assert any(isinstance(item, LaborRuleResolutionRun) for item in session.added)
    assert any(isinstance(item, LocationLaborRuleResolution) for item in session.added)


@pytest.mark.asyncio
async def test_sync_location_labor_rule_resolution_shadow_only_persists_run(monkeypatch):
    session = FakeSession()
    business = _business()
    location = _location(business_id=business.id)

    monkeypatch.setattr(
        labor_rule_resolution,
        "settings",
        SimpleNamespace(
            labor_rules_mode="shadow",
            labor_rule_profile_selection_model="",
        ),
    )
    async def fake_profiles(*args, **kwargs):
        return [_profile("us_ca_general_nonexempt")]

    monkeypatch.setattr(labor_rule_resolution.labor_rules, "active_profiles_for_jurisdiction", fake_profiles)

    outcome = await labor_rule_resolution.sync_location_labor_rule_resolution(
        session,
        business=business,
        location=location,
    )

    assert outcome.applied is False
    assert any(isinstance(item, LaborRuleResolutionRun) for item in session.added)
    assert not any(isinstance(item, LocationLaborRuleResolution) for item in session.added)


@pytest.mark.asyncio
async def test_sync_location_labor_rule_resolution_uses_llm_for_multiple_profiles(monkeypatch):
    session = FakeSession()
    business = _business()
    location = _location(business_id=business.id)
    manufacturing = _profile("us_ca_manufacturing", industry_code="manufacturing")
    hospitality = _profile("us_ca_hospitality", industry_code="hospitality")

    monkeypatch.setattr(
        labor_rule_resolution,
        "settings",
        SimpleNamespace(
            labor_rules_mode="primary",
            labor_rule_profile_selection_model="gpt-test",
        ),
    )
    async def fake_profiles(*args, **kwargs):
        return [manufacturing, hospitality]

    async def fake_existing(*args, **kwargs):
        return None

    monkeypatch.setattr(labor_rule_resolution.labor_rules, "active_profiles_for_jurisdiction", fake_profiles)
    monkeypatch.setattr(labor_rule_resolution.labor_rules, "load_authoritative_location_resolution", fake_existing)
    monkeypatch.setattr(labor_rule_resolution.llm_gateway, "provider_is_configured", lambda _provider: True)

    async def fake_lookup(*args, **kwargs):
        return uuid4()

    async def fake_generate(_session, request):
        return llm_gateway.LlmGenerationResult(
            provider=llm_gateway.LlmProvider.OPENAI,
            model="gpt-test",
            tool_calls=[
                llm_gateway.LlmToolCall(
                    tool_call_id="call_1",
                    name="submit_labor_rule_profile_selection",
                    arguments={
                        "decision": "select",
                        "selected_profile_code": "us_ca_hospitality",
                        "confidence": 0.91,
                        "reason": "Hospitality setting matches the approved profile family.",
                        "reason_codes": ["llm.profile_selection.hospitality"],
                    },
                )
            ],
        )

    monkeypatch.setattr(labor_rule_resolution, "_lookup_llm_generation_id", fake_lookup)
    monkeypatch.setattr(labor_rule_resolution.llm_gateway, "generate", fake_generate)

    outcome = await labor_rule_resolution.sync_location_labor_rule_resolution(
        session,
        business=business,
        location=location,
    )

    assert outcome.profile is not None
    assert outcome.profile.code == "us_ca_hospitality"
    assert outcome.resolution_source == "llm"
