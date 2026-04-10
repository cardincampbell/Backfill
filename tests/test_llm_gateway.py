from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.ai import LlmGeneration
from app.models.finance import CostLedgerEntry
from app.services import llm_gateway


class FakeGatewaySession:
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


class SuccessAdapter:
    async def generate(self, request: llm_gateway.LlmGenerationRequest) -> llm_gateway.LlmGenerationResult:
        assert request.provider == llm_gateway.LlmProvider.OPENAI
        assert request.model == "gpt-test"
        return llm_gateway.LlmGenerationResult(
            provider=request.provider,
            model=request.model,
            output_text="Ready to publish.",
            finish_reason="stop",
            provider_generation_id="resp_123",
            tool_calls=[
                llm_gateway.LlmToolCall(
                    tool_call_id="tool_1",
                    name="schedule.publish",
                    arguments={"location_id": "loc_1"},
                )
            ],
            usage=llm_gateway.LlmUsage(
                input_tokens=120,
                output_tokens=32,
                total_tokens=152,
                estimated_cost_micros=4100,
            ),
            response_payload={"id": "resp_123", "type": "response"},
            metadata={"provider_latency_bucket": "fast"},
        )


class FailureAdapter:
    async def generate(self, request: llm_gateway.LlmGenerationRequest) -> llm_gateway.LlmGenerationResult:
        raise RuntimeError(f"provider_failed:{request.provider}")


class FakeSettings:
    openai_api_key = "openai-key"
    anthropic_api_key = "anthropic-key"
    llm_default_provider = llm_gateway.LlmProvider.OPENAI
    llm_default_model = "gpt-test"


@pytest.fixture(autouse=True)
def reset_gateway_registry(monkeypatch):
    llm_gateway.clear_adapters()
    monkeypatch.setattr(llm_gateway, "settings", FakeSettings())
    yield
    llm_gateway.clear_adapters()


@pytest.mark.asyncio
async def test_generate_persists_normalized_success_row_with_defaults():
    llm_gateway.register_adapter(llm_gateway.LlmProvider.OPENAI, SuccessAdapter())
    session = FakeGatewaySession()
    business_id = uuid4()
    location_id = uuid4()
    trace_id = uuid4()

    result = await llm_gateway.generate(
        session,
        request=llm_gateway.LlmGenerationRequest(
            purpose="intent_resolution",
            business_id=business_id,
            location_id=location_id,
            messages=[
                llm_gateway.LlmMessage(role="system", content="You are Backfill."),
                llm_gateway.LlmMessage(role="user", content="Publish next week."),
            ],
            tools=[
                llm_gateway.LlmToolDefinition(
                    name="schedule.publish",
                    description="Publish a draft schedule.",
                    input_schema={"type": "object"},
                )
            ],
            metadata={"trace_id": trace_id, "channel": "dashboard"},
        ),
    )

    assert result.output_text == "Ready to publish."
    rows = [entry for entry in session.added if isinstance(entry, LlmGeneration)]
    assert len(rows) == 1
    row = rows[0]
    assert row.business_id == business_id
    assert row.location_id == location_id
    assert row.provider == llm_gateway.LlmProvider.OPENAI
    assert row.model == "gpt-test"
    assert row.purpose == "intent_resolution"
    assert row.status == llm_gateway.LlmGenerationStatus.SUCCEEDED
    assert row.trace_id == str(trace_id)
    assert row.provider_generation_id == "resp_123"
    assert row.finish_reason == "stop"
    assert row.output_text == "Ready to publish."
    assert row.input_tokens == 120
    assert row.output_tokens == 32
    assert row.total_tokens == 152
    assert row.estimated_cost_micros == 4100
    assert row.request_payload["provider"] == llm_gateway.LlmProvider.OPENAI
    assert row.request_payload["model"] == "gpt-test"
    assert row.request_payload["messages"][1]["content"] == "Publish next week."
    assert row.response_payload["id"] == "resp_123"
    assert row.tool_calls[0]["name"] == "schedule.publish"
    assert row.generation_metadata["trace_id"] == str(trace_id)
    assert row.generation_metadata["channel"] == "dashboard"
    assert row.generation_metadata["provider_latency_bucket"] == "fast"
    assert row.latency_ms is not None
    assert row.latency_ms >= 0
    cost_rows = [entry for entry in session.added if isinstance(entry, CostLedgerEntry)]
    assert len(cost_rows) == 1
    cost_row = cost_rows[0]
    assert cost_row.provider == llm_gateway.LlmProvider.OPENAI
    assert cost_row.product == "llm_generation"
    assert cost_row.reference_type == "llm_generation"
    assert cost_row.total_cost_micros == 4100
    assert cost_row.cost_metadata["trace_id"] == str(trace_id)
    assert cost_row.cost_metadata["total_tokens"] == 152


@pytest.mark.asyncio
async def test_generate_persists_failure_row_before_reraising():
    llm_gateway.register_adapter(llm_gateway.LlmProvider.ANTHROPIC, FailureAdapter())
    session = FakeGatewaySession()

    with pytest.raises(RuntimeError, match="provider_failed:anthropic"):
        await llm_gateway.generate(
            session,
            request=llm_gateway.LlmGenerationRequest(
                purpose="tool_selection",
                provider=llm_gateway.LlmProvider.ANTHROPIC,
                model="claude-test",
                messages=[llm_gateway.LlmMessage(role="user", content="Find coverage.")],
                metadata={"trace_id": "trace_123"},
            ),
        )

    rows = [entry for entry in session.added if isinstance(entry, LlmGeneration)]
    assert len(rows) == 1
    row = rows[0]
    assert row.provider == llm_gateway.LlmProvider.ANTHROPIC
    assert row.model == "claude-test"
    assert row.status == llm_gateway.LlmGenerationStatus.FAILED
    assert row.trace_id == "trace_123"
    assert row.error_message == "provider_failed:anthropic"
    assert row.request_payload["provider"] == llm_gateway.LlmProvider.ANTHROPIC
    assert row.request_payload["model"] == "claude-test"
    assert row.request_payload["messages"][0]["content"] == "Find coverage."
    assert row.response_payload == {}
    assert row.tool_calls == []
    assert row.generation_metadata["trace_id"] == "trace_123"
    cost_rows = [entry for entry in session.added if isinstance(entry, CostLedgerEntry)]
    assert cost_rows == []


@pytest.mark.asyncio
async def test_generate_raises_when_no_adapter_is_registered_but_still_records_failure():
    session = FakeGatewaySession()

    with pytest.raises(llm_gateway.LlmProviderNotRegisteredError, match="openai"):
        await llm_gateway.generate(
            session,
            request=llm_gateway.LlmGenerationRequest(
                purpose="general",
                provider=llm_gateway.LlmProvider.OPENAI,
                model="gpt-test",
                messages=[llm_gateway.LlmMessage(role="user", content="Hello")],
            ),
        )

    rows = [entry for entry in session.added if isinstance(entry, LlmGeneration)]
    assert len(rows) == 1
    assert rows[0].status == llm_gateway.LlmGenerationStatus.FAILED
    assert "No LLM adapter registered" in (rows[0].error_message or "")


def test_provider_is_configured_checks_per_provider_keys():
    assert llm_gateway.provider_is_configured(llm_gateway.LlmProvider.OPENAI) is True
    assert llm_gateway.provider_is_configured(llm_gateway.LlmProvider.ANTHROPIC) is True
    assert llm_gateway.provider_is_configured("unknown") is False
