from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.config import settings
from app.services import llm_gateway

_OPENAI_DEFAULT_MAX_OUTPUT_TOKENS = 1024
_ANTHROPIC_DEFAULT_MAX_OUTPUT_TOKENS = 1024


def _normalize_payload(payload: Any) -> Any:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    if isinstance(payload, Mapping):
        return {
            str(key): _normalize_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, (list, tuple, set)):
        return [_normalize_payload(item) for item in payload]
    return payload


def _safe_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _openai_tool_choice(tool_choice: str | None) -> Any:
    if not tool_choice:
        return None
    if tool_choice in {"auto", "none", "required"}:
        return tool_choice
    return {"type": "function", "name": tool_choice}


def _anthropic_tool_choice(tool_choice: str | None) -> Any:
    if not tool_choice or tool_choice == "auto":
        return None
    if tool_choice == "required":
        return {"type": "any"}
    if tool_choice == "none":
        return {"type": "auto"}
    return {"type": "tool", "name": tool_choice}


def _openai_input_messages(messages: list[llm_gateway.LlmMessage]) -> list[dict[str, Any]]:
    return [
        {
            "role": message.role,
            "content": [{"type": "input_text", "text": message.content}],
        }
        for message in messages
    ]


def _openai_tools(tools: list[llm_gateway.LlmToolDefinition]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        }
        for tool in tools
    ]


def _anthropic_payload(request: llm_gateway.LlmGenerationRequest) -> dict[str, Any]:
    system_chunks = [message.content for message in request.messages if message.role == "system"]
    payload: dict[str, Any] = {
        "model": request.model,
        "messages": [
            {"role": message.role, "content": message.content}
            for message in request.messages
            if message.role != "system"
        ],
        "max_tokens": request.max_output_tokens or _ANTHROPIC_DEFAULT_MAX_OUTPUT_TOKENS,
    }
    if system_chunks:
        payload["system"] = "\n\n".join(system_chunks)
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.tools:
        payload["tools"] = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in request.tools
        ]
    tool_choice = _anthropic_tool_choice(request.tool_choice)
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    return payload


def _build_openai_client(api_key: str):
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is not installed") from exc
    return AsyncOpenAI(api_key=api_key)


def _build_anthropic_client(api_key: str):
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        raise RuntimeError("anthropic package is not installed") from exc
    return AsyncAnthropic(api_key=api_key)


class OpenAIResponsesAdapter:
    def __init__(self, *, api_key: str, client: Any | None = None):
        self._api_key = api_key
        self._client = client

    def _client_instance(self):
        if self._client is None:
            self._client = _build_openai_client(self._api_key)
        return self._client

    async def generate(self, request: llm_gateway.LlmGenerationRequest) -> llm_gateway.LlmGenerationResult:
        payload: dict[str, Any] = {
            "model": request.model,
            "input": _openai_input_messages(request.messages),
            "max_output_tokens": request.max_output_tokens or _OPENAI_DEFAULT_MAX_OUTPUT_TOKENS,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools:
            payload["tools"] = _openai_tools(request.tools)
        tool_choice = _openai_tool_choice(request.tool_choice)
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        response = await self._client_instance().responses.create(**payload)
        normalized = _normalize_payload(response)
        output = normalized.get("output", []) if isinstance(normalized, Mapping) else []

        output_text = getattr(response, "output_text", None)
        if not output_text:
            chunks: list[str] = []
            for item in output:
                if item.get("type") != "message":
                    continue
                for block in item.get("content", []):
                    if block.get("type") in {"output_text", "text"} and block.get("text"):
                        chunks.append(block["text"])
            output_text = "\n".join(chunks) if chunks else None

        tool_calls: list[llm_gateway.LlmToolCall] = []
        for item in output:
            if item.get("type") != "function_call":
                continue
            tool_calls.append(
                llm_gateway.LlmToolCall(
                    tool_call_id=str(item.get("call_id") or item.get("id") or ""),
                    name=str(item.get("name") or ""),
                    arguments=_safe_json_object(item.get("arguments")),
                )
            )

        usage_payload = normalized.get("usage", {}) if isinstance(normalized, Mapping) else {}
        usage = llm_gateway.LlmUsage(
            input_tokens=usage_payload.get("input_tokens"),
            output_tokens=usage_payload.get("output_tokens"),
            total_tokens=usage_payload.get("total_tokens"),
        )
        return llm_gateway.LlmGenerationResult(
            provider=llm_gateway.LlmProvider.OPENAI,
            model=request.model or "",
            output_text=output_text,
            finish_reason=str(normalized.get("status") or "") or None,
            provider_generation_id=normalized.get("id"),
            tool_calls=tool_calls,
            usage=usage,
            response_payload=normalized if isinstance(normalized, Mapping) else {},
            metadata={"sdk": "openai.responses"},
        )


class AnthropicMessagesAdapter:
    def __init__(self, *, api_key: str, client: Any | None = None):
        self._api_key = api_key
        self._client = client

    def _client_instance(self):
        if self._client is None:
            self._client = _build_anthropic_client(self._api_key)
        return self._client

    async def generate(self, request: llm_gateway.LlmGenerationRequest) -> llm_gateway.LlmGenerationResult:
        payload = _anthropic_payload(request)
        response = await self._client_instance().messages.create(**payload)
        normalized = _normalize_payload(response)
        content = normalized.get("content", []) if isinstance(normalized, Mapping) else []

        text_chunks: list[str] = []
        tool_calls: list[llm_gateway.LlmToolCall] = []
        for block in content:
            block_type = block.get("type")
            if block_type == "text" and block.get("text"):
                text_chunks.append(block["text"])
            elif block_type == "tool_use":
                tool_calls.append(
                    llm_gateway.LlmToolCall(
                        tool_call_id=str(block.get("id") or ""),
                        name=str(block.get("name") or ""),
                        arguments=_safe_json_object(block.get("input")),
                    )
                )

        usage_payload = normalized.get("usage", {}) if isinstance(normalized, Mapping) else {}
        usage = llm_gateway.LlmUsage(
            input_tokens=usage_payload.get("input_tokens"),
            output_tokens=usage_payload.get("output_tokens"),
        )
        if usage.total_tokens is None and usage.input_tokens is not None and usage.output_tokens is not None:
            usage = llm_gateway.LlmUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.input_tokens + usage.output_tokens,
            )

        return llm_gateway.LlmGenerationResult(
            provider=llm_gateway.LlmProvider.ANTHROPIC,
            model=request.model or "",
            output_text="\n".join(text_chunks) if text_chunks else None,
            finish_reason=normalized.get("stop_reason"),
            provider_generation_id=normalized.get("id"),
            tool_calls=tool_calls,
            usage=usage,
            response_payload=normalized if isinstance(normalized, Mapping) else {},
            metadata={"sdk": "anthropic.messages"},
        )


def build_configured_adapter(provider: str):
    normalized_provider = provider.strip().lower()
    if normalized_provider == llm_gateway.LlmProvider.OPENAI and settings.openai_api_key:
        return OpenAIResponsesAdapter(api_key=settings.openai_api_key)
    if normalized_provider == llm_gateway.LlmProvider.ANTHROPIC and settings.anthropic_api_key:
        return AnthropicMessagesAdapter(api_key=settings.anthropic_api_key)
    return None


def register_configured_adapters() -> None:
    for provider in (llm_gateway.LlmProvider.OPENAI, llm_gateway.LlmProvider.ANTHROPIC):
        adapter = build_configured_adapter(provider)
        if adapter is not None:
            llm_gateway.register_adapter(provider, adapter)
