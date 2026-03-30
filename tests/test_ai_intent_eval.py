from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import settings
from app.services.ai_intent import classify_intent


def _load_cases() -> list[dict]:
    path = Path(__file__).parent / "fixtures" / "ai_intent_eval_cases.json"
    return json.loads(path.read_text())


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _load_cases())
async def test_intent_eval_cases_are_stable_under_rules_provider(monkeypatch, case):
    monkeypatch.setattr(settings, "backfill_ai_provider", "rules")
    classification = await classify_intent(
        text=case["text"],
        channel=case["channel"],
    )

    assert classification.runtime["provider"] == "rules"
    assert classification.intent["intent_type"] == case["intent_type"]
    assert classification.intent["domain"] == case["domain"]
    assert classification.intent["action_candidates"] == case["action_candidates"]
    assert classification.intent["channel"] == case["channel"]
