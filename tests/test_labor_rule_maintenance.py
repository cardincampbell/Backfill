from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.business import Business
from app.models.labor_rules import LaborRuleProfile, LaborRuleSourceDocument, LaborRuleUpdateProposal
from app.services import labor_rule_maintenance, llm_gateway


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


def test_validate_profile_candidate_rejects_invalid_threshold_order():
    candidate = labor_rule_maintenance.validate_profile_candidate(
        {
            "code": "us_ca_general_nonexempt",
            "jurisdiction_code": "US-CA",
            "display_name": "California General Nonexempt",
            "overtime_mode": "daily_8_plus_weekly_plus_7th_day",
            "daily_ot_threshold_hours": 8,
            "double_time_threshold_hours": 6,
            "rules_json": {},
        }
    )

    assert "double_time_before_daily_threshold" in candidate.validation_errors


@pytest.mark.asyncio
async def test_generate_rule_update_proposal_persists_structured_proposal(monkeypatch):
    session = FakeSession()
    business = Business(
        id=uuid4(),
        name="Ops",
        display_name="Ops",
        slug="ops",
        timezone="America/Los_Angeles",
        settings={},
        place_metadata={},
    )
    source_document = LaborRuleSourceDocument(
        id=uuid4(),
        jurisdiction_code="US-CA",
        source_url="https://example.com/ca",
        source_type="official",
        normalized_text="California overtime source",
        content_hash="hash1",
        is_active=True,
    )
    current_profile = LaborRuleProfile(
        id=uuid4(),
        code="us_ca_general_nonexempt",
        jurisdiction_code="US-CA",
        display_name="California General Nonexempt",
        overtime_mode="daily_8_plus_weekly_plus_7th_day",
        daily_ot_threshold_hours=8,
        weekly_ot_threshold_hours=40,
        double_time_threshold_hours=12,
        rules_json={"workweek_start_day_local": "monday"},
        source_urls=[],
        is_active=True,
    )

    monkeypatch.setattr(
        labor_rule_maintenance,
        "settings",
        SimpleNamespace(
            labor_rule_update_model="gpt-test",
            labor_rule_proposal_autoqueue=True,
        ),
    )
    monkeypatch.setattr(labor_rule_maintenance.llm_gateway, "provider_is_configured", lambda _provider: True)

    async def fake_lookup(*args, **kwargs):
        return uuid4()

    async def fake_generate(_session, request):
        return llm_gateway.LlmGenerationResult(
            provider=llm_gateway.LlmProvider.OPENAI,
            model="gpt-test",
            tool_calls=[
                llm_gateway.LlmToolCall(
                    tool_call_id="call_1",
                    name="submit_labor_rule_update_proposal",
                    arguments={
                        "proposal_type": "profile_update",
                        "reason_summary": "Clarify California source metadata.",
                        "citations_json": ["https://example.com/ca"],
                        "proposed_profiles": [
                            {
                                "code": "us_ca_general_nonexempt",
                                "jurisdiction_code": "US-CA",
                                "display_name": "California General Nonexempt",
                                "overtime_mode": "daily_8_plus_weekly_plus_7th_day",
                                "daily_ot_threshold_hours": 8,
                                "weekly_ot_threshold_hours": 40,
                                "double_time_threshold_hours": 12,
                                "rules_json": {"workweek_start_day_local": "monday"},
                            }
                        ],
                    },
                )
            ],
        )

    monkeypatch.setattr(labor_rule_maintenance, "_lookup_llm_generation_id", fake_lookup)
    monkeypatch.setattr(labor_rule_maintenance.llm_gateway, "generate", fake_generate)

    proposal = await labor_rule_maintenance.generate_rule_update_proposal(
        session,
        jurisdiction_code="US-CA",
        source_documents=[source_document],
        current_profiles=[current_profile],
        business_id=business.id,
    )

    assert proposal is not None
    assert proposal.proposal_status == "needs_review"
    assert proposal.proposal_type == "profile_update"
    assert any(isinstance(item, LaborRuleUpdateProposal) for item in session.added)
