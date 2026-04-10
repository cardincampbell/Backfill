from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.schemas.common import BaseSchema


class LlmGenerationSummaryRead(BaseSchema):
    id: UUID
    business_id: UUID | None = None
    location_id: UUID | None = None
    provider: str
    model: str
    purpose: str
    status: str
    prompt_version: str | None = None
    trace_id: str | None = None
    provider_generation_id: str | None = None
    finish_reason: str | None = None
    output_text: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_micros: int | None = None
    latency_ms: int | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class LlmGenerationDetailRead(LlmGenerationSummaryRead):
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    generation_metadata: dict[str, Any]
