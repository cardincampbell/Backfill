from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services import ai_policy, ai_prompts
from app.services.ai_runtime import run_structured


@dataclass
class IntentClassification:
    intent: dict[str, Any]
    runtime: dict[str, Any]


async def classify_intent(*, text: str, channel: str) -> IntentClassification:
    response = await run_structured(
        ai_prompts.build_intent_classification_request(
            text=text,
            channel=channel,
        ),
        provider_override=ai_policy.select_intent_provider(channel=channel),
    )
    return IntentClassification(
        intent=dict(response.parsed_output),
        runtime={
            "policy_provider": ai_policy.select_intent_provider(channel=channel),
            "requested_provider": response.requested_provider,
            "provider": response.provider,
            "model": response.model,
            "request_id": response.request_id,
            "latency_ms": response.latency_ms,
            "usage": dict(response.usage or {}),
            "fallback_used": bool(response.fallback_used),
            "fallback_provider": response.fallback_provider,
            "fallback_reason": response.fallback_reason,
            "primary_error": response.primary_error,
        },
    )
