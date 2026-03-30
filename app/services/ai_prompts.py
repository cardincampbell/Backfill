from __future__ import annotations

from typing import Any

from app.services.ai_runtime import AiStructuredRequest


def build_intent_classification_request(*, text: str, channel: str) -> AiStructuredRequest:
    return AiStructuredRequest(
        task_name="intent_classification",
        system_prompt=(
            "Classify Backfill natural-language scheduling intent. "
            "Choose the most likely supported Backfill action for the manager or operator request."
        ),
        user_prompt=text,
        json_schema={
            "type": "object",
            "properties": {
                "intent_type": {"type": "string"},
                "domain": {"type": "string"},
                "action_candidates": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "confidence_score": {"type": "number"},
                "channel": {"type": "string"},
            },
            "required": [
                "intent_type",
                "domain",
                "action_candidates",
                "confidence_score",
                "channel",
            ],
            "additionalProperties": False,
        },
        schema_name="backfill_intent_classification",
        schema_description="Structured Backfill intent classification result.",
        metadata={"text": text, "channel": channel},
    )


def build_open_shift_creation_request(
    *,
    text: str,
    channel: str,
    context: dict[str, Any] | None = None,
) -> AiStructuredRequest:
    return AiStructuredRequest(
        task_name="open_shift_creation_extraction",
        system_prompt=(
            "Extract the required fields for creating a Backfill open shift. "
            "Return only what the manager explicitly requested or what is safely inferable. "
            "If a field is missing or unclear, return null for that field. "
            "Normalize dates to YYYY-MM-DD and times to HH:MM:SS when possible."
        ),
        user_prompt=text,
        json_schema={
            "type": "object",
            "properties": {
                "role": {"type": ["string", "null"]},
                "date": {"type": ["string", "null"]},
                "start_time": {"type": ["string", "null"]},
                "end_time": {"type": ["string", "null"]},
                "spans_midnight": {"type": ["boolean", "null"]},
                "start_open_shift_offer": {"type": "boolean"},
                "shift_label": {"type": ["string", "null"]},
                "notes": {"type": ["string", "null"]},
                "pay_rate": {"type": ["number", "null"]},
                "requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "role",
                "date",
                "start_time",
                "end_time",
                "spans_midnight",
                "start_open_shift_offer",
                "shift_label",
                "notes",
                "pay_rate",
                "requirements",
            ],
            "additionalProperties": False,
        },
        schema_name="backfill_open_shift_creation",
        schema_description="Structured Backfill open-shift creation payload.",
        metadata={"text": text, "channel": channel, "context": dict(context or {})},
    )


def build_shift_edit_request(
    *,
    text: str,
    channel: str,
    context: dict[str, Any] | None = None,
) -> AiStructuredRequest:
    return AiStructuredRequest(
        task_name="shift_edit_extraction",
        system_prompt=(
            "Extract the requested Backfill shift edits. "
            "Return only fields the manager explicitly wants to change or that are safely inferable. "
            "If a field is not requested, return null for it. "
            "Normalize dates to YYYY-MM-DD and times to HH:MM:SS when possible."
        ),
        user_prompt=text,
        json_schema={
            "type": "object",
            "properties": {
                "role": {"type": ["string", "null"]},
                "date": {"type": ["string", "null"]},
                "start_time": {"type": ["string", "null"]},
                "end_time": {"type": ["string", "null"]},
                "spans_midnight": {"type": ["boolean", "null"]},
                "shift_label": {"type": ["string", "null"]},
                "notes": {"type": ["string", "null"]},
                "pay_rate": {"type": ["number", "null"]},
                "requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "role",
                "date",
                "start_time",
                "end_time",
                "spans_midnight",
                "shift_label",
                "notes",
                "pay_rate",
                "requirements",
            ],
            "additionalProperties": False,
        },
        schema_name="backfill_shift_edit",
        schema_description="Structured Backfill shift edit payload.",
        metadata={"text": text, "channel": channel, "context": dict(context or {})},
    )
