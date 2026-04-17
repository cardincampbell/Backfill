from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.business import Role
from app.services import llm_gateway

_PLACEHOLDER_ROLE_NAMES = {
    "asdf",
    "employee",
    "n/a",
    "na",
    "none",
    "qwerty",
    "role",
    "temp",
    "test",
    "tmp",
    "unknown",
    "worker",
}


class RoleNameRejectedError(ValueError):
    pass


@dataclass(frozen=True)
class RoleNormalizationResult:
    decision: str
    normalized_name: str
    confidence: float | None = None
    reason: str | None = None
    matched_role: Role | None = None


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _title_case_segment(value: str) -> str:
    if not value:
        return value
    if value.isupper() and 1 < len(value) <= 4:
        return value
    return value[0].upper() + value[1:].lower()


def format_role_name(value: str) -> str:
    return " ".join(
        "-".join(_title_case_segment(segment) for segment in word.split("-"))
        for word in _collapse_whitespace(value).split(" ")
        if word
    )


def _normalized_lookup_key(value: str) -> str:
    return _collapse_whitespace(value).casefold()


def _match_existing_role(existing_roles: Sequence[Role], candidate_name: str) -> Role | None:
    candidate_key = _normalized_lookup_key(candidate_name)
    for role in existing_roles:
        if _normalized_lookup_key(role.name or "") == candidate_key:
            return role
    return None


def _reject_reason_for_name(candidate_name: str) -> str | None:
    normalized = _collapse_whitespace(candidate_name)
    lowered = normalized.casefold()
    if not normalized:
        return "Enter a role name."
    if len(normalized) < 2:
        return "Enter a clearer role name."
    if not re.search(r"[A-Za-z]", normalized):
        return "Role names need at least one letter."
    if lowered in _PLACEHOLDER_ROLE_NAMES:
        return "Enter a real role name instead of a placeholder."
    if re.fullmatch(r"(.)\1{3,}", lowered):
        return "Enter a clearer role name."
    return None


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    if not raw_text.strip():
        return {}
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


async def _llm_normalize_role_name(
    session: AsyncSession,
    *,
    business_id: UUID,
    raw_name: str,
    existing_roles: Sequence[Role],
) -> dict[str, Any]:
    existing_role_names = [role.name for role in existing_roles if role.name][:200]
    prompt_payload = {
        "raw_role_name": raw_name,
        "existing_role_names": existing_role_names,
        "instructions": {
            "allowed_decisions": ["reuse_existing", "create_new", "reject"],
            "reuse_existing_when": "the input is clearly the same role as an existing role, including spelling corrections",
            "reject_when": "the input is gibberish, a placeholder, or too ambiguous to trust",
            "normalized_name_style": "short professional role title in title case",
        },
        "output_schema": {
            "decision": "reuse_existing | create_new | reject",
            "normalized_name": "string",
            "matched_existing_name": "string | null",
            "confidence": "number between 0 and 1",
            "reason": "short string",
        },
    }
    result = await llm_gateway.generate(
        session,
        request=llm_gateway.LlmGenerationRequest(
            purpose="role_normalization",
            business_id=business_id,
            provider=llm_gateway.LlmProvider.OPENAI,
            model=settings.role_normalization_model,
            messages=[
                llm_gateway.LlmMessage(
                    role="system",
                    content=(
                        "You normalize employee role titles for a workforce scheduling app. "
                        "Return exactly one JSON object and no other text."
                    ),
                ),
                llm_gateway.LlmMessage(
                    role="user",
                    content=json.dumps(prompt_payload, ensure_ascii=True),
                ),
            ],
            temperature=0,
            max_output_tokens=300,
            metadata={
                "feature": "role_normalization",
                "raw_name": raw_name,
                "existing_role_count": len(existing_role_names),
            },
        ),
    )
    return _extract_json_object(result.output_text or "")


async def normalize_role_name(
    session: AsyncSession,
    *,
    business_id: UUID,
    raw_name: str,
    existing_roles: Sequence[Role],
) -> RoleNormalizationResult:
    formatted_name = format_role_name(raw_name)
    reject_reason = _reject_reason_for_name(formatted_name)
    if reject_reason is not None:
        return RoleNormalizationResult(
            decision="reject",
            normalized_name=formatted_name,
            reason=reject_reason,
        )

    existing_role = _match_existing_role(existing_roles, formatted_name)
    if existing_role is not None:
        return RoleNormalizationResult(
            decision="reuse_existing",
            normalized_name=existing_role.name,
            confidence=1.0,
            reason="Exact match to an existing role.",
            matched_role=existing_role,
        )

    if not settings.role_normalization_model or not settings.openai_api_key:
        return RoleNormalizationResult(
            decision="create_new",
            normalized_name=formatted_name,
            confidence=1.0,
            reason="Role normalization model is not configured.",
        )

    try:
        normalized_payload = await _llm_normalize_role_name(
            session,
            business_id=business_id,
            raw_name=formatted_name,
            existing_roles=existing_roles,
        )
    except Exception as exc:  # pragma: no cover - exercised via gateway tests elsewhere
        raise RoleNameRejectedError("Could not validate this role name right now.") from exc

    decision = str(normalized_payload.get("decision") or "").strip().lower()
    candidate_name = format_role_name(str(normalized_payload.get("normalized_name") or formatted_name))
    matched_existing_name = format_role_name(str(normalized_payload.get("matched_existing_name") or ""))
    reason = str(normalized_payload.get("reason") or "").strip() or None
    try:
        confidence = float(normalized_payload.get("confidence"))
    except (TypeError, ValueError):
        confidence = None
    if confidence is not None:
        confidence = max(0.0, min(confidence, 1.0))

    reject_reason = _reject_reason_for_name(candidate_name)
    if reject_reason is not None:
        return RoleNormalizationResult(
            decision="reject",
            normalized_name=candidate_name,
            confidence=confidence,
            reason=reject_reason,
        )

    matched_role = _match_existing_role(existing_roles, matched_existing_name) or _match_existing_role(
        existing_roles,
        candidate_name,
    )
    if matched_role is not None:
        return RoleNormalizationResult(
            decision="reuse_existing",
            normalized_name=matched_role.name,
            confidence=confidence,
            reason=reason or "Matched an existing role.",
            matched_role=matched_role,
        )

    if decision == "reject":
        return RoleNormalizationResult(
            decision="reject",
            normalized_name=candidate_name,
            confidence=confidence,
            reason=reason or "Enter a clearer role name.",
        )

    if confidence is not None and confidence < 0.6:
        return RoleNormalizationResult(
            decision="reject",
            normalized_name=candidate_name,
            confidence=confidence,
            reason=reason or "Enter a clearer role name.",
        )

    return RoleNormalizationResult(
        decision="create_new",
        normalized_name=candidate_name,
        confidence=confidence,
        reason=reason,
    )
