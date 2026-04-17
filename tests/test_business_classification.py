from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.business import Business, Location, Role
from app.models.business_classification import (
    BusinessDerivationGapSuggestion,
    BusinessDerivationRun,
)
from app.models.role_taxonomy import (
    BusinessRoleArchetype,
    BusinessSubvertical,
    BusinessVertical,
    BusinessVerticalRoleArchetype,
    BusinessVerticalTypeMapping,
)
from app.services import business_classification, llm_gateway


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarResult(self._values)


class FakeSession:
    def __init__(self):
        self.added: list[object] = []
        self.execute_queue: list[list[object]] = []

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

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)


def _make_business() -> Business:
    now = datetime.now(timezone.utc)
    return Business(
        id=uuid4(),
        name="Sample Business LLC",
        display_name="Sample Business",
        slug="sample-business",
        vertical=None,
        primary_email="ops@example.com",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={"name": "Sample Business", "primary_type": "cafe", "types": ["cafe", "coffee_shop"]},
        created_at=now,
        updated_at=now,
    )


def _make_location(*, business_id, primary_type: str, types: list[str]) -> Location:
    now = datetime.now(timezone.utc)
    return Location(
        id=uuid4(),
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        address_line_1="123 Main St",
        locality="Los Angeles",
        region="CA",
        postal_code="90001",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_id="place_123",
        google_place_metadata={
            "primary_type": primary_type,
            "types": types,
            "website_uri": "https://example.com",
        },
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _taxonomy_execute_queue() -> list[list[object]]:
    verticals = [
        BusinessVertical(code="cafe", display_name="Cafe", is_active=True, metadata_json={}),
        BusinessVertical(code="bar", display_name="Bar", is_active=True, metadata_json={}),
        BusinessVertical(code="mixed_unknown", display_name="Mixed / Unknown", is_active=True, metadata_json={}),
    ]
    mappings = [
        BusinessVerticalTypeMapping(place_type="cafe", business_vertical_code="cafe", subvertical_code="cafe", is_active=True, metadata_json={}),
        BusinessVerticalTypeMapping(place_type="coffee_shop", business_vertical_code="cafe", subvertical_code="coffee_shop", is_active=True, metadata_json={}),
        BusinessVerticalTypeMapping(place_type="bar", business_vertical_code="bar", subvertical_code="bar", is_active=True, metadata_json={}),
    ]
    subverticals = [
        BusinessSubvertical(code="cafe", business_vertical_code="cafe", display_name="Cafe", is_active=True, metadata_json={}),
        BusinessSubvertical(code="coffee_shop", business_vertical_code="cafe", display_name="Coffee Shop", is_active=True, metadata_json={}),
        BusinessSubvertical(code="bar", business_vertical_code="bar", display_name="Bar", is_active=True, metadata_json={}),
    ]
    role_archetypes = [
        BusinessRoleArchetype(code="general_manager", display_name="General Manager", role_family="management", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="shift_lead", display_name="Shift Lead", role_family="operations", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="barista", display_name="Barista", role_family="front_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="cashier", display_name="Cashier", role_family="front_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="assistant_manager", display_name="Assistant Manager", role_family="management", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="bartender", display_name="Bartender", role_family="front_of_house", is_active=True, metadata_json={}),
    ]
    vertical_roles = [
        BusinessVerticalRoleArchetype(business_vertical_code="cafe", business_role_code="general_manager", sort_order=10, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="cafe", business_role_code="shift_lead", sort_order=20, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="cafe", business_role_code="barista", sort_order=30, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="cafe", business_role_code="cashier", sort_order=40, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bar", business_role_code="general_manager", sort_order=10, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bar", business_role_code="bartender", sort_order=20, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="mixed_unknown", business_role_code="general_manager", sort_order=10, is_active=True, metadata_json={}),
    ]
    return [verticals, mappings, subverticals, role_archetypes, vertical_roles, verticals, subverticals]


@pytest.mark.asyncio
async def test_sync_business_classification_primary_uses_llm_and_persists_gap_suggestions(monkeypatch):
    session = FakeSession()
    session.execute_queue = [*_taxonomy_execute_queue(), []]
    business = _make_business()
    location = _make_location(business_id=business.id, primary_type="cafe", types=["cafe", "coffee_shop"])

    monkeypatch.setattr(
        business_classification,
        "settings",
        SimpleNamespace(
            business_classification_model="gpt-test",
            business_classification_mode="primary",
        ),
    )
    monkeypatch.setattr(business_classification.llm_gateway, "provider_is_configured", lambda _provider: True)
    async def fake_lookup(*args, **kwargs):
        return uuid4()

    monkeypatch.setattr(business_classification, "_lookup_llm_generation_id", fake_lookup)

    async def fake_generate(_session, request):
        assert request.purpose == "business_classification"
        return llm_gateway.LlmGenerationResult(
            provider=llm_gateway.LlmProvider.OPENAI,
            model="gpt-test",
            tool_calls=[
                llm_gateway.LlmToolCall(
                    tool_call_id="call_1",
                    name="submit_business_classification",
                    arguments={
                        "decision": "classify",
                        "vertical_code": "cafe",
                        "subvertical_code": "coffee_shop",
                        "selected_role_codes": ["assistant_manager"],
                        "confidence": 0.92,
                        "reason": "Coffee-shop signals are consistent.",
                        "reason_codes": ["llm.vertical.cafe"],
                        "gap_suggestions": [
                            {
                                "suggestion_type": "missing_role_archetype",
                                "vertical_code": "cafe",
                                "proposed_code": "drive_thru_specialist",
                                "proposed_display_name": "Drive Thru Specialist",
                                "confidence": 0.81,
                                "reason": "Likely missing cafe role.",
                            }
                        ],
                    },
                )
            ],
        )

    monkeypatch.setattr(business_classification.llm_gateway, "generate", fake_generate)

    derivation = await business_classification.sync_business_classification(
        session,
        business,
        locations=[location],
    )

    assert derivation.classification.vertical == "cafe"
    assert derivation.classification.subvertical == "coffee_shop"
    assert {role.role_key for role in derivation.roles} >= {
        "general_manager",
        "shift_lead",
        "barista",
        "cashier",
        "assistant_manager",
    }
    assert business.settings["derived_classification"]["source"] == "llm"
    assert business.settings["derived_classification"]["mode"] == "primary"
    assert any(isinstance(item, BusinessDerivationRun) and item.source == "llm" for item in session.added)
    assert any(
        isinstance(item, BusinessDerivationGapSuggestion)
        and item.proposed_code == "drive_thru_specialist"
        for item in session.added
    )


@pytest.mark.asyncio
async def test_sync_business_classification_primary_falls_back_when_llm_abstains(monkeypatch):
    session = FakeSession()
    session.execute_queue = [*_taxonomy_execute_queue(), []]
    business = _make_business()
    location = _make_location(business_id=business.id, primary_type="cafe", types=["cafe"])

    monkeypatch.setattr(
        business_classification,
        "settings",
        SimpleNamespace(
            business_classification_model="gpt-test",
            business_classification_mode="primary",
        ),
    )
    monkeypatch.setattr(business_classification.llm_gateway, "provider_is_configured", lambda _provider: True)
    async def fake_lookup(*args, **kwargs):
        return uuid4()

    monkeypatch.setattr(business_classification, "_lookup_llm_generation_id", fake_lookup)

    async def fake_generate(_session, request):
        return llm_gateway.LlmGenerationResult(
            provider=llm_gateway.LlmProvider.OPENAI,
            model="gpt-test",
            tool_calls=[
                llm_gateway.LlmToolCall(
                    tool_call_id="call_1",
                    name="submit_business_classification",
                    arguments={
                        "decision": "abstain",
                        "selected_role_codes": [],
                        "confidence": 0.24,
                        "reason": "Insufficient evidence",
                        "reason_codes": ["llm.abstain.insufficient_evidence"],
                        "gap_suggestions": [],
                    },
                )
            ],
        )

    monkeypatch.setattr(business_classification.llm_gateway, "generate", fake_generate)

    derivation = await business_classification.sync_business_classification(
        session,
        business,
        locations=[location],
    )

    assert derivation.classification.vertical == "cafe"
    assert business.settings["derived_classification"]["source"] == "rules"
    assert business.settings["derived_classification"]["fallback_reason"] == "Insufficient evidence"
    run = next(item for item in session.added if isinstance(item, BusinessDerivationRun))
    assert run.source == "rules"
    assert run.fallback_reason == "Insufficient evidence"


@pytest.mark.asyncio
async def test_sync_business_classification_shadow_does_not_apply_llm_result(monkeypatch):
    session = FakeSession()
    session.execute_queue = [*_taxonomy_execute_queue(), []]
    business = _make_business()
    location = _make_location(business_id=business.id, primary_type="cafe", types=["cafe"])

    monkeypatch.setattr(
        business_classification,
        "settings",
        SimpleNamespace(
            business_classification_model="gpt-test",
            business_classification_mode="shadow",
        ),
    )
    monkeypatch.setattr(business_classification.llm_gateway, "provider_is_configured", lambda _provider: True)
    async def fake_lookup(*args, **kwargs):
        return uuid4()

    monkeypatch.setattr(business_classification, "_lookup_llm_generation_id", fake_lookup)

    async def fake_generate(_session, request):
        return llm_gateway.LlmGenerationResult(
            provider=llm_gateway.LlmProvider.OPENAI,
            model="gpt-test",
            tool_calls=[
                llm_gateway.LlmToolCall(
                    tool_call_id="call_1",
                    name="submit_business_classification",
                    arguments={
                        "decision": "classify",
                        "vertical_code": "bar",
                        "subvertical_code": "bar",
                        "selected_role_codes": ["bartender"],
                        "confidence": 0.91,
                        "reason": "Nightlife leaning.",
                        "reason_codes": ["llm.vertical.bar"],
                        "gap_suggestions": [],
                    },
                )
            ],
        )

    monkeypatch.setattr(business_classification.llm_gateway, "generate", fake_generate)

    derivation = await business_classification.sync_business_classification(
        session,
        business,
        locations=[location],
    )

    assert derivation.classification.vertical == "cafe"
    assert business.settings["derived_classification"]["source"] == "rules"
    assert business.settings["derived_classification"]["mode"] == "shadow"
    assert business.settings["derived_classification"]["fallback_reason"] == "shadow_mode"
    assert business.settings["derived_classification"]["llm_candidate"]["vertical"] == "bar"
