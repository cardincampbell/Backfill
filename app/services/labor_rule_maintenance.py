from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Sequence
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.labor_rules import (
    LaborRuleProfile,
    LaborRuleSourceDocument,
    LaborRuleUpdateProposal,
)
from app.services import labor_rules, llm_gateway

MAINTENANCE_VERSION = "labor_rule_maintenance_v1"
_PROPOSAL_TOOL = "submit_labor_rule_update_proposal"


@dataclass(frozen=True)
class ValidatedProfileCandidate:
    payload: dict[str, Any]
    validation_errors: tuple[str, ...]


def _proposal_status() -> str:
    return "needs_review" if settings.labor_rule_proposal_autoqueue else "draft"


async def fetch_active_source_documents(
    session: AsyncSession,
    jurisdiction_code: str,
) -> list[LaborRuleSourceDocument]:
    rows = await session.execute(
        select(LaborRuleSourceDocument).where(
            LaborRuleSourceDocument.jurisdiction_code == jurisdiction_code,
            LaborRuleSourceDocument.is_active.is_(True),
        )
    )
    return list(rows.scalars().all())


def detect_source_changes(
    source_documents: Sequence[LaborRuleSourceDocument],
    *,
    previous_hashes: Sequence[str] | None = None,
) -> bool:
    current_hashes = sorted(
        str(document.content_hash).strip()
        for document in source_documents
        if document.content_hash
    )
    return current_hashes != sorted(str(item).strip() for item in (previous_hashes or []) if str(item).strip())


def validate_profile_candidate(candidate: dict[str, Any]) -> ValidatedProfileCandidate:
    payload = dict(candidate)
    errors: list[str] = []
    overtime_mode = str(payload.get("overtime_mode") or "").strip()
    if overtime_mode not in labor_rules.OVERTIME_MODES:
        errors.append("unsupported_overtime_mode")

    jurisdiction_code = str(payload.get("jurisdiction_code") or "").strip()
    if not jurisdiction_code:
        errors.append("jurisdiction_code_required")

    display_name = str(payload.get("display_name") or "").strip()
    if not display_name:
        errors.append("display_name_required")

    weekly_threshold = labor_rules._as_float(payload.get("weekly_ot_threshold_hours"))
    daily_threshold = labor_rules._as_float(payload.get("daily_ot_threshold_hours"))
    double_threshold = labor_rules._as_float(payload.get("double_time_threshold_hours"))
    consecutive_threshold = labor_rules._as_float(payload.get("consecutive_hours_threshold_hours"))
    if weekly_threshold is not None and weekly_threshold < 0:
        errors.append("invalid_weekly_threshold")
    if daily_threshold is not None and daily_threshold < 0:
        errors.append("invalid_daily_threshold")
    if double_threshold is not None and double_threshold < 0:
        errors.append("invalid_double_time_threshold")
    if consecutive_threshold is not None and consecutive_threshold < 0:
        errors.append("invalid_consecutive_threshold")
    if (
        daily_threshold is not None
        and double_threshold is not None
        and double_threshold < daily_threshold
    ):
        errors.append("double_time_before_daily_threshold")

    return ValidatedProfileCandidate(payload=payload, validation_errors=tuple(errors))


def _proposal_tool_definition() -> llm_gateway.LlmToolDefinition:
    return llm_gateway.LlmToolDefinition(
        name=_PROPOSAL_TOOL,
        description="Return proposed labor-rule profile updates using the bounded labor-rule schema.",
        input_schema={
            "type": "object",
            "properties": {
                "proposal_type": {"type": "string"},
                "reason_summary": {"type": "string"},
                "citations_json": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "proposed_profiles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "jurisdiction_code": {"type": "string"},
                            "display_name": {"type": "string"},
                            "overtime_mode": {"type": "string", "enum": sorted(labor_rules.OVERTIME_MODES)},
                            "daily_ot_threshold_hours": {"type": "number"},
                            "weekly_ot_threshold_hours": {"type": "number"},
                            "double_time_threshold_hours": {"type": "number"},
                            "consecutive_hours_threshold_hours": {"type": "number"},
                            "industry_profile_code": {"type": "string"},
                            "rules_json": {"type": "object"},
                            "effective_start_date": {"type": "string"},
                            "effective_end_date": {"type": "string"},
                            "source_urls": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "source_version": {"type": "string"},
                            "source_hash": {"type": "string"},
                        },
                        "required": [
                            "code",
                            "jurisdiction_code",
                            "display_name",
                            "overtime_mode",
                            "rules_json",
                        ],
                    },
                },
            },
            "required": ["proposal_type", "reason_summary", "citations_json", "proposed_profiles"],
        },
    )


async def _lookup_llm_generation_id(
    session: AsyncSession,
    *,
    business_id: UUID,
    trace_id: str,
) -> UUID | None:
    generations = await llm_gateway.list_generations(
        session,
        business_id=business_id,
        purpose="labor_rule_update_proposal",
        provider=llm_gateway.LlmProvider.OPENAI,
        trace_id=trace_id,
        limit=1,
    )
    if not generations:
        return None
    return generations[0].id


def _build_prompt(
    *,
    jurisdiction_code: str,
    source_documents: Sequence[LaborRuleSourceDocument],
    current_profiles: Sequence[LaborRuleProfile],
) -> str:
    payload = {
        "jurisdiction_code": jurisdiction_code,
        "source_documents": [
            {
                "source_url": document.source_url,
                "source_type": document.source_type,
                "normalized_text": document.normalized_text,
                "content_hash": document.content_hash,
            }
            for document in source_documents
        ],
        "current_profiles": [
            labor_rules.build_profile_payload(profile)
            for profile in current_profiles
        ],
        "instructions": [
            "Propose updates only within the bounded labor-rule profile schema.",
            "Do not invent new schema concepts.",
            "Prefer updating existing profile definitions over adding unnecessary profile families.",
        ],
    }
    return json.dumps(payload, ensure_ascii=True)


async def generate_rule_update_proposal(
    session: AsyncSession,
    *,
    jurisdiction_code: str,
    source_documents: Sequence[LaborRuleSourceDocument],
    current_profiles: Sequence[LaborRuleProfile],
    business_id: UUID | None = None,
) -> LaborRuleUpdateProposal | None:
    if not settings.labor_rule_update_model or not llm_gateway.provider_is_configured(llm_gateway.LlmProvider.OPENAI):
        return None

    trace_id = str(uuid4())
    result = await llm_gateway.generate(
        session,
        request=llm_gateway.LlmGenerationRequest(
            purpose="labor_rule_update_proposal",
            business_id=business_id,
            provider=llm_gateway.LlmProvider.OPENAI,
            model=settings.labor_rule_update_model,
            prompt_version=MAINTENANCE_VERSION,
            messages=[
                llm_gateway.LlmMessage(
                    role="system",
                    content=(
                        "You summarize labor rule source changes into bounded structured proposals. "
                        "Use the tool exactly once."
                    ),
                ),
                llm_gateway.LlmMessage(
                    role="user",
                    content=_build_prompt(
                        jurisdiction_code=jurisdiction_code,
                        source_documents=source_documents,
                        current_profiles=current_profiles,
                    ),
                ),
            ],
            tools=[_proposal_tool_definition()],
            tool_choice=_PROPOSAL_TOOL,
            temperature=0,
            max_output_tokens=1200,
            metadata={
                "feature": "labor_rule_update_proposal",
                "trace_id": trace_id,
                "jurisdiction_code": jurisdiction_code,
            },
        ),
    )
    llm_generation_id = None
    if business_id is not None:
        llm_generation_id = await _lookup_llm_generation_id(
            session,
            business_id=business_id,
            trace_id=trace_id,
        )

    tool_call = next((call for call in result.tool_calls if call.name == _PROPOSAL_TOOL), None)
    if tool_call is None:
        return None
    arguments = dict(tool_call.arguments or {})
    proposed_profiles = arguments.get("proposed_profiles", [])
    validated = [validate_profile_candidate(profile) for profile in proposed_profiles if isinstance(profile, dict)]
    if any(item.validation_errors for item in validated):
        return None

    proposal = LaborRuleUpdateProposal(
        jurisdiction_code=jurisdiction_code,
        proposal_status=_proposal_status(),
        proposal_type=str(arguments.get("proposal_type") or "profile_update").strip() or "profile_update",
        current_profile_codes=[profile.code for profile in current_profiles],
        proposed_profiles_json={"profiles": [item.payload for item in validated]},
        reason_summary=str(arguments.get("reason_summary") or "").strip() or None,
        citations_json=[
            str(item).strip()
            for item in arguments.get("citations_json", [])
            if str(item).strip()
        ],
        llm_provider=result.provider,
        llm_model=result.model,
        llm_generation_id=llm_generation_id,
    )
    session.add(proposal)
    await session.flush()
    return proposal
