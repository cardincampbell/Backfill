from __future__ import annotations

import pytest

from app.services import llm_adapters, llm_gateway


class FakeOpenAIResponsesClient:
    class _Responses:
        async def create(self, **_kwargs):
            return {
                "id": "resp_123",
                "status": "completed",
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 32,
                    "total_tokens": 152,
                },
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Publish the schedule."}],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "schedule.publish",
                        "arguments": "{\"location_id\":\"loc_1\"}",
                    },
                ],
            }

    def __init__(self):
        self.responses = self._Responses()


class FakeAnthropicMessagesClient:
    class _Messages:
        async def create(self, **_kwargs):
            return {
                "id": "msg_123",
                "stop_reason": "tool_use",
                "usage": {
                    "input_tokens": 90,
                    "output_tokens": 18,
                },
                "content": [
                    {"type": "text", "text": "I can do that."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "coverage.start_campaign",
                        "input": {"shift_id": "shift_1"},
                    },
                ],
            }

    def __init__(self):
        self.messages = self._Messages()


class FakeSettings:
    openai_api_key = "openai-key"
    anthropic_api_key = "anthropic-key"


@pytest.fixture(autouse=True)
def reset_registry(monkeypatch):
    llm_gateway.clear_adapters()
    monkeypatch.setattr(llm_adapters, "settings", FakeSettings())
    yield
    llm_gateway.clear_adapters()


@pytest.mark.asyncio
async def test_openai_adapter_normalizes_responses_output_and_tool_calls():
    adapter = llm_adapters.OpenAIResponsesAdapter(
        api_key="test-key",
        client=FakeOpenAIResponsesClient(),
    )

    result = await adapter.generate(
        llm_gateway.LlmGenerationRequest(
            purpose="intent_resolution",
            provider=llm_gateway.LlmProvider.OPENAI,
            model="gpt-test",
            messages=[llm_gateway.LlmMessage(role="user", content="Publish next week.")],
            tools=[
                llm_gateway.LlmToolDefinition(
                    name="schedule.publish",
                    description="Publish a schedule.",
                    input_schema={"type": "object"},
                )
            ],
        )
    )

    assert result.provider == llm_gateway.LlmProvider.OPENAI
    assert result.provider_generation_id == "resp_123"
    assert result.finish_reason == "completed"
    assert result.output_text == "Publish the schedule."
    assert result.usage.total_tokens == 152
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "schedule.publish"
    assert result.tool_calls[0].arguments["location_id"] == "loc_1"
    assert result.metadata["sdk"] == "openai.responses"


@pytest.mark.asyncio
async def test_anthropic_adapter_normalizes_content_blocks_and_tool_calls():
    adapter = llm_adapters.AnthropicMessagesAdapter(
        api_key="test-key",
        client=FakeAnthropicMessagesClient(),
    )

    result = await adapter.generate(
        llm_gateway.LlmGenerationRequest(
            purpose="tool_selection",
            provider=llm_gateway.LlmProvider.ANTHROPIC,
            model="claude-test",
            messages=[
                llm_gateway.LlmMessage(role="system", content="You are Backfill."),
                llm_gateway.LlmMessage(role="user", content="Start coverage."),
            ],
            tools=[
                llm_gateway.LlmToolDefinition(
                    name="coverage.start_campaign",
                    description="Start a campaign.",
                    input_schema={"type": "object"},
                )
            ],
        )
    )

    assert result.provider == llm_gateway.LlmProvider.ANTHROPIC
    assert result.provider_generation_id == "msg_123"
    assert result.finish_reason == "tool_use"
    assert result.output_text == "I can do that."
    assert result.usage.input_tokens == 90
    assert result.usage.output_tokens == 18
    assert result.usage.total_tokens == 108
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "coverage.start_campaign"
    assert result.tool_calls[0].arguments["shift_id"] == "shift_1"
    assert result.metadata["sdk"] == "anthropic.messages"


def test_register_configured_adapters_registers_available_providers():
    llm_adapters.register_configured_adapters()

    assert llm_gateway._REGISTERED_ADAPTERS[llm_gateway.LlmProvider.OPENAI].__class__.__name__ == "OpenAIResponsesAdapter"
    assert llm_gateway._REGISTERED_ADAPTERS[llm_gateway.LlmProvider.ANTHROPIC].__class__.__name__ == "AnthropicMessagesAdapter"
