from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.services import ai_prompts
from app.services.ai_intent import classify_intent
from app.services.ai_runtime import (
    AiRuntimeError,
    AiStructuredOutputError,
    run_structured,
)


@pytest.mark.asyncio
async def test_run_structured_uses_rules_provider_by_default(monkeypatch):
    monkeypatch.setattr(settings, "backfill_ai_provider", "rules")
    monkeypatch.setattr(settings, "backfill_ai_model", "rules-v1")

    response = await run_structured(
        ai_prompts.build_intent_classification_request(
            text="publish next week",
            channel="web",
        )
    )

    assert response.provider == "rules"
    assert response.model == "rules-v1"
    assert response.parsed_output["action_candidates"] == ["publish_schedule"]
    assert response.parsed_output["channel"] == "web"


@pytest.mark.asyncio
async def test_run_structured_uses_openai_responses_api(monkeypatch):
    captured = {}

    class _FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "resp_123",
                "model": "gpt-4.1-mini",
                "usage": {"input_tokens": 12, "output_tokens": 8},
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"intent_type":"query","domain":"schedule",'
                                    '"action_candidates":["get_schedule_summary"],'
                                    '"confidence_score":0.91,"channel":"voice"}'
                                ),
                            }
                        ],
                    }
                ],
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(settings, "backfill_ai_provider", "openai")
    monkeypatch.setattr(settings, "backfill_ai_model", "gpt-4.1-mini")
    monkeypatch.setattr(settings, "openai_api_key", "test-openai-key")
    monkeypatch.setattr(settings, "openai_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "backfill_ai_timeout_seconds", 12.5)
    monkeypatch.setattr("app.services.ai_runtime.httpx.AsyncClient", _FakeClient)

    response = await run_structured(
        ai_prompts.build_intent_classification_request(
            text="what's the schedule status?",
            channel="voice",
        )
    )

    assert response.provider == "openai"
    assert response.request_id == "resp_123"
    assert response.parsed_output["action_candidates"] == ["get_schedule_summary"]
    assert response.parsed_output["channel"] == "voice"
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer test-openai-key"
    assert captured["timeout"] == 12.5
    assert captured["json"]["text"]["format"]["type"] == "json_schema"
    assert captured["json"]["text"]["format"]["name"] == "backfill_intent_classification"
    assert captured["json"]["model"] == "gpt-4.1-mini"
    assert response.requested_provider == "openai"
    assert response.fallback_used is False


@pytest.mark.asyncio
async def test_run_structured_openai_provider_rejects_refusals(monkeypatch):
    class _FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "resp_456",
                "model": "gpt-4.1-mini",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "refusal",
                                "refusal": "I can’t help with that request.",
                            }
                        ],
                    }
                ],
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            return _FakeResponse()

    monkeypatch.setattr(settings, "backfill_ai_provider", "openai")
    monkeypatch.setattr(settings, "backfill_ai_model", "gpt-4.1-mini")
    monkeypatch.setattr(settings, "openai_api_key", "test-openai-key")
    monkeypatch.setattr(settings, "backfill_ai_fallback_enabled", False)
    monkeypatch.setattr("app.services.ai_runtime.httpx.AsyncClient", _FakeClient)

    with pytest.raises(AiStructuredOutputError):
        await run_structured(
            ai_prompts.build_intent_classification_request(
                text="publish next week",
                channel="web",
            )
        )


@pytest.mark.asyncio
async def test_run_structured_openai_provider_falls_back_to_rules_on_transport_error(monkeypatch):
    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            raise httpx.ConnectError("upstream unavailable")

    monkeypatch.setattr(settings, "backfill_ai_provider", "openai")
    monkeypatch.setattr(settings, "backfill_ai_model", "gpt-4.1-mini")
    monkeypatch.setattr(settings, "openai_api_key", "test-openai-key")
    monkeypatch.setattr(settings, "backfill_ai_fallback_enabled", True)
    monkeypatch.setattr(settings, "backfill_ai_fallback_provider", "rules")
    monkeypatch.setattr("app.services.ai_runtime.httpx.AsyncClient", _FakeClient)

    response = await run_structured(
        ai_prompts.build_intent_classification_request(
            text="publish next week",
            channel="web",
        )
    )

    assert response.requested_provider == "openai"
    assert response.provider == "rules"
    assert response.fallback_used is True
    assert response.fallback_provider == "rules"
    assert response.fallback_reason == "ConnectError"
    assert "upstream unavailable" in str(response.primary_error)
    assert response.parsed_output["action_candidates"] == ["publish_schedule"]


@pytest.mark.asyncio
async def test_run_structured_openai_provider_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "backfill_ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "backfill_ai_fallback_enabled", False)

    with pytest.raises(AiRuntimeError):
        await run_structured(
            ai_prompts.build_intent_classification_request(
                text="publish next week",
                channel="web",
            )
        )


@pytest.mark.asyncio
async def test_classify_intent_uses_rules_for_channels_not_enabled_for_openai(monkeypatch):
    monkeypatch.setattr(settings, "backfill_ai_provider", "openai")
    monkeypatch.setattr(settings, "backfill_ai_openai_channels", ["web"])

    classification = await classify_intent(
        text="what is the coverage status right now?",
        channel="sms",
    )

    assert classification.runtime["policy_provider"] == "rules"
    assert classification.runtime["provider"] == "rules"
    assert classification.intent["action_candidates"] == ["get_coverage_status"]


@pytest.mark.asyncio
async def test_run_structured_can_extract_open_shift_creation_fields_under_rules_provider(monkeypatch):
    monkeypatch.setattr(settings, "backfill_ai_provider", "rules")

    response = await run_structured(
        ai_prompts.build_open_shift_creation_request(
            text="Create an open dishwasher shift on 2026-04-15 from 11 to 7 and offer it now",
            channel="web",
            context={"week_start_date": "2026-04-13"},
        )
    )

    assert response.provider == "rules"
    assert response.parsed_output["role"] == "dishwasher"
    assert response.parsed_output["date"] == "2026-04-15"
    assert response.parsed_output["start_time"] == "11:00:00"
    assert response.parsed_output["end_time"] == "19:00:00"
    assert response.parsed_output["start_open_shift_offer"] is True


@pytest.mark.asyncio
async def test_run_structured_can_extract_shift_edit_fields_under_rules_provider(monkeypatch):
    monkeypatch.setattr(settings, "backfill_ai_provider", "rules")

    response = await run_structured(
        ai_prompts.build_shift_edit_request(
            text="Move the dishwasher shift to 12 to 8 on 2026-04-16",
            channel="web",
            context={"week_start_date": "2026-04-13"},
        )
    )

    assert response.provider == "rules"
    assert response.parsed_output["date"] == "2026-04-16"
    assert response.parsed_output["start_time"] == "12:00:00"
    assert response.parsed_output["end_time"] == "20:00:00"
