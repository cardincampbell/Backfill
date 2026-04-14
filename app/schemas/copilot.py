from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class CopilotToolRead(BaseSchema):
    name: str
    title: str
    description: str
    intent_family: str
    mutates_state: bool = False
    availability: Literal["available", "planned"] = "available"


class CopilotSessionCreate(BaseSchema):
    location_id: Optional[UUID] = None
    normalized_channel: str = "dashboard"
    reuse_active: bool = True


class CopilotValidationResultRead(BaseSchema):
    ok: bool
    code: str
    message: str


class CopilotIntentRead(BaseSchema):
    family: str
    tool_name: str
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class CopilotSessionRead(BaseSchema):
    id: UUID
    business_id: UUID
    location_id: Optional[UUID] = None
    operator_user_id: UUID
    channel_last_seen: str = "dashboard"
    intent_family: Optional[str] = None
    state: Literal[
        "active",
        "awaiting_confirmation",
        "awaiting_clarification",
        "completed",
        "expired",
    ] = "active"
    context_profile: dict = Field(default_factory=dict)
    working_memory: dict = Field(default_factory=dict)
    expires_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime


class CopilotMessageRead(BaseSchema):
    id: UUID
    copilot_session_id: UUID
    direction: Literal["inbound", "outbound"]
    normalized_channel: str = "dashboard"
    raw_text: str
    normalized_text: str
    message_metadata: dict = Field(default_factory=dict)
    created_at: datetime


class CopilotActionRunRead(BaseSchema):
    id: UUID
    copilot_session_id: UUID
    tool_name: str
    status: Literal["planned", "validated", "executed", "failed", "cancelled"]
    input_payload: dict = Field(default_factory=dict)
    validation_result: CopilotValidationResultRead
    result_payload: dict = Field(default_factory=dict)
    error_payload: dict = Field(default_factory=dict)
    started_at: datetime
    finished_at: Optional[datetime] = None


class CopilotSessionDetailRead(BaseSchema):
    session: CopilotSessionRead
    tools: list[CopilotToolRead] = Field(default_factory=list)
    messages: list[CopilotMessageRead] = Field(default_factory=list)
    action_runs: list[CopilotActionRunRead] = Field(default_factory=list)


class CopilotMessageCreate(BaseSchema):
    text: str
    location_id: Optional[UUID] = None
    normalized_channel: str = "dashboard"


class CopilotTurnRead(BaseSchema):
    session: CopilotSessionRead
    resolved_intent: CopilotIntentRead
    inbound_message: CopilotMessageRead
    outbound_message: CopilotMessageRead
    action_run: CopilotActionRunRead
    tools: list[CopilotToolRead] = Field(default_factory=list)


class CopilotSessionEventRead(BaseSchema):
    event_id: UUID
    event_type: Literal[
        "session.ready",
        "user.message.accepted",
        "assistant.turn.started",
        "assistant.progress",
        "tool.started",
        "tool.finished",
        "assistant.message.completed",
        "assistant.turn.failed",
        "session.error",
    ]
    trace_id: str
    session_id: UUID
    occurred_at: datetime
    payload: dict = Field(default_factory=dict)
