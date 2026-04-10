from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.ai import LlmGeneration


class LlmProvider:
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LlmGenerationStatus:
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LlmGatewayError(RuntimeError):
    """Base error for provider-agnostic LLM gateway failures."""


class LlmGatewayConfigurationError(LlmGatewayError):
    """Raised when a request cannot be resolved to a configured provider/model."""


class LlmProviderNotRegisteredError(LlmGatewayError):
    """Raised when a provider has no adapter registered in the gateway."""


@dataclass(frozen=True)
class LlmMessage:
    role: str
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True)
class LlmToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class LlmToolCall:
    tool_call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LlmUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_micros: int | None = None


@dataclass(frozen=True)
class LlmGenerationRequest:
    purpose: str
    messages: list[LlmMessage]
    business_id: UUID | None = None
    location_id: UUID | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    tools: list[LlmToolDefinition] = field(default_factory=list)
    tool_choice: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class LlmGenerationResult:
    provider: str
    model: str
    output_text: str | None = None
    finish_reason: str | None = None
    provider_generation_id: str | None = None
    tool_calls: list[LlmToolCall] = field(default_factory=list)
    usage: LlmUsage = field(default_factory=LlmUsage)
    response_payload: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] | None = None


class LlmProviderAdapter(Protocol):
    async def generate(self, request: LlmGenerationRequest) -> LlmGenerationResult:
        ...


_REGISTERED_ADAPTERS: dict[str, LlmProviderAdapter] = {}


def register_adapter(provider: str, adapter: LlmProviderAdapter) -> None:
    _REGISTERED_ADAPTERS[provider.strip().lower()] = adapter


def unregister_adapter(provider: str) -> None:
    _REGISTERED_ADAPTERS.pop(provider.strip().lower(), None)


def clear_adapters() -> None:
    _REGISTERED_ADAPTERS.clear()


def configured_provider_api_key(provider: str) -> str:
    normalized_provider = provider.strip().lower()
    if normalized_provider == LlmProvider.OPENAI:
        return settings.openai_api_key
    if normalized_provider == LlmProvider.ANTHROPIC:
        return settings.anthropic_api_key
    return ""


def provider_is_configured(provider: str) -> bool:
    return bool(configured_provider_api_key(provider))


def _normalize_value(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize_value(asdict(value))
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    return value


def _resolve_provider(request: LlmGenerationRequest) -> str:
    provider = (request.provider or settings.llm_default_provider).strip().lower()
    if not provider:
        raise LlmGatewayConfigurationError("No LLM provider configured for request")
    return provider


def _resolve_model(request: LlmGenerationRequest) -> str:
    model = (request.model or settings.llm_default_model).strip()
    if not model:
        raise LlmGatewayConfigurationError("No LLM model configured for request")
    return model


def _trace_id(metadata: Mapping[str, Any] | None) -> str:
    raw_trace_id = (metadata or {}).get("trace_id")
    if isinstance(raw_trace_id, UUID):
        return str(raw_trace_id)
    if isinstance(raw_trace_id, str) and raw_trace_id.strip():
        return raw_trace_id.strip()
    return str(uuid4())


def _request_payload(
    request: LlmGenerationRequest,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    return {
        "provider": provider or request.provider,
        "model": model or request.model,
        "purpose": request.purpose,
        "prompt_version": request.prompt_version,
        "messages": _normalize_value(request.messages),
        "tools": _normalize_value(request.tools),
        "tool_choice": request.tool_choice,
        "temperature": request.temperature,
        "max_output_tokens": request.max_output_tokens,
    }


def _response_payload(result: LlmGenerationResult) -> dict[str, Any]:
    return dict(_normalize_value(result.response_payload) or {})


async def generate(
    session: AsyncSession,
    *,
    request: LlmGenerationRequest,
) -> LlmGenerationResult:
    started_at = datetime.now(timezone.utc)
    trace_id = _trace_id(request.metadata)
    provider = ""
    model = ""

    try:
        provider = _resolve_provider(request)
        model = _resolve_model(request)
        adapter = _REGISTERED_ADAPTERS.get(provider)
        if adapter is None:
            raise LlmProviderNotRegisteredError(f"No LLM adapter registered for provider {provider!r}")

        effective_request = replace(request, provider=provider, model=model)
        result = await adapter.generate(effective_request)
    except Exception as exc:
        session.add(
            LlmGeneration(
                business_id=request.business_id,
                location_id=request.location_id,
                provider=provider or "unresolved",
                model=model or "unresolved",
                purpose=request.purpose,
                status=LlmGenerationStatus.FAILED,
                prompt_version=request.prompt_version,
                trace_id=trace_id,
                request_payload=_request_payload(request, provider=provider or None, model=model or None),
                response_payload={},
                tool_calls=[],
                generation_metadata={
                    "trace_id": trace_id,
                    **dict(_normalize_value(request.metadata) or {}),
                },
                error_message=str(exc),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
        )
        raise

    completed_at = datetime.now(timezone.utc)
    latency_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))
    session.add(
        LlmGeneration(
            business_id=request.business_id,
            location_id=request.location_id,
            provider=result.provider,
            model=result.model,
            purpose=request.purpose,
            status=LlmGenerationStatus.SUCCEEDED,
            prompt_version=request.prompt_version,
            trace_id=trace_id,
            provider_generation_id=result.provider_generation_id,
            finish_reason=result.finish_reason,
            output_text=result.output_text,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            total_tokens=result.usage.total_tokens,
            estimated_cost_micros=result.usage.estimated_cost_micros,
            latency_ms=latency_ms,
            request_payload=_request_payload(request, provider=result.provider, model=result.model),
            response_payload=_response_payload(result),
            tool_calls=_normalize_value(result.tool_calls),
            generation_metadata={
                "trace_id": trace_id,
                **dict(_normalize_value(request.metadata) or {}),
                **dict(_normalize_value(result.metadata) or {}),
            },
            started_at=started_at,
            completed_at=completed_at,
        )
    )
    return result
