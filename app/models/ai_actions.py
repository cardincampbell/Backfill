from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AiWebActionRequest(BaseModel):
    location_id: int = Field(gt=0)
    text: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class AiActionClarifyRequest(BaseModel):
    selection: dict[str, Any]


class AiActionFeedbackRequest(BaseModel):
    helpful: Optional[bool] = None
    correct: Optional[bool] = None
    notes: Optional[str] = None


class AiActionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    action_request_id: int
    status: str
    mode: str
    summary: str
    risk_class: Optional[str] = None
    requires_confirmation: Optional[bool] = None
    clarification: Optional[dict[str, Any]] = None
    confirmation: Optional[dict[str, Any]] = None
    redirect: Optional[dict[str, Any]] = None
    ui_payload: Optional[dict[str, Any]] = None
    runtime: Optional[dict[str, Any]] = None
    next_actions: list[dict[str, Any]] = Field(default_factory=list)


class AiActionHistoryItem(BaseModel):
    action_request_id: int
    channel: str
    status: str
    text: str
    summary: str
    risk_class: Optional[str] = None
    action_type: Optional[str] = None
    runtime: Optional[dict[str, Any]] = None
    created_at: str
    updated_at: Optional[str] = None


class AiActionHistoryResponse(BaseModel):
    location_id: int
    items: list[AiActionHistoryItem]


class AiActionDebugResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    action_request_id: int
    request: dict[str, Any]
    entities: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    session: Optional[dict[str, Any]] = None


class AiRuntimeStatsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    location_id: int
    days: int
    summary: dict[str, Any]
    status_counts: dict[str, int] = Field(default_factory=dict)
    channel_counts: dict[str, int] = Field(default_factory=dict)
    action_counts: dict[str, int] = Field(default_factory=dict)
    provider_counts: dict[str, int] = Field(default_factory=dict)
    recent_fallbacks: list[dict[str, Any]] = Field(default_factory=list)


class AiCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    location_id: int
    provider_policy: dict[str, Any]
    actions: list[dict[str, Any]] = Field(default_factory=list)


class AiActionFeedbackResponse(BaseModel):
    action_request_id: int
    feedback_recorded: bool
    feedback: dict[str, Any]


class AiActiveSessionItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: int
    action_request_id: int
    location_id: int
    channel: str
    status: str
    pending_prompt_type: Optional[str] = None
    action_type: Optional[str] = None
    text: str
    summary: str
    expires_at: Optional[str] = None
    is_expired: bool = False
    created_at: str
    updated_at: Optional[str] = None


class AiActiveSessionsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    location_id: int
    items: list[AiActiveSessionItem] = Field(default_factory=list)


class InternalAiActionRecentResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    items: list[dict[str, Any]] = Field(default_factory=list)


class InternalAiActionSessionsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    items: list[dict[str, Any]] = Field(default_factory=list)
