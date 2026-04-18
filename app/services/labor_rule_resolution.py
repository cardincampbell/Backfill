from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Sequence
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.business import Business, Location
from app.models.labor_rules import LaborRuleResolutionRun, LocationLaborRuleResolution
from app.services import labor_rules, llm_gateway

RESOLUTION_VERSION = "labor_rule_resolution_v1"
_PROFILE_SELECTION_TOOL = "submit_labor_rule_profile_selection"
_CONFIDENCE_FLOOR = 0.72


@dataclass(frozen=True)
class LlmResolutionCandidate:
    decision: str
    selected_profile_code: str | None
    confidence: float | None
    reason: str | None
    reason_codes: tuple[str, ...]
    llm_generation_id: UUID | None
    provider: str | None
    model: str | None


@dataclass(frozen=True)
class ResolutionOutcome:
    profile: labor_rules.LaborRuleProfileSnapshot | None
    resolution_source: str
    confidence: float | None
    reason_codes: tuple[str, ...]
    fallback_reason: str | None
    llm_generation_id: UUID | None
    applied: bool
    mode: str


def _resolution_mode() -> str:
    mode = settings.labor_rules_mode.strip().lower()
    return mode if mode in {"shadow", "primary"} else "shadow"


def _selection_tool_definition(
    profiles: Sequence[labor_rules.LaborRuleProfileSnapshot],
) -> llm_gateway.LlmToolDefinition:
    profile_codes = sorted({profile.code for profile in profiles})
    return llm_gateway.LlmToolDefinition(
        name=_PROFILE_SELECTION_TOOL,
        description="Choose one approved labor-rule profile code from the provided candidates, or abstain.",
        input_schema={
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["select", "abstain"]},
                "selected_profile_code": {"type": "string", "enum": profile_codes},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"},
                "reason_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["decision", "confidence", "reason", "reason_codes"],
        },
    )


def _build_prompt(
    *,
    business: Business,
    location: Location,
    profiles: Sequence[labor_rules.LaborRuleProfileSnapshot],
) -> str:
    derived_classification = business.settings.get("derived_classification") if isinstance(business.settings, dict) else {}
    payload = {
        "business": {
            "business_id": str(business.id),
            "name": business.name,
            "display_name": business.display_name,
            "vertical": business.vertical,
            "derived_classification": derived_classification if isinstance(derived_classification, dict) else {},
        },
        "location": {
            "location_id": str(location.id),
            "name": location.name,
            "display_name": location.display_name,
            "region": location.region,
            "country_code": location.country_code,
            "timezone": location.timezone,
            "settings": dict(location.settings or {}),
            "google_place_metadata": dict(location.google_place_metadata or {}),
        },
        "jurisdiction_code": labor_rules.resolve_jurisdiction_code(location),
        "candidate_profiles": [
            {
                "code": profile.code,
                "display_name": profile.display_name,
                "overtime_mode": profile.overtime_mode,
                "industry_profile_code": profile.industry_profile_code,
                "rules_json": profile.rules_json,
            }
            for profile in profiles
        ],
        "instructions": [
            "Pick one existing profile code only when the evidence is strong.",
            "Abstain when the available metadata does not clearly support one candidate over another.",
            "Never invent new profile codes or new labor-rule concepts.",
        ],
    }
    return json.dumps(payload, ensure_ascii=True)


async def _lookup_llm_generation_id(
    session: AsyncSession,
    *,
    business_id: UUID,
    trace_id: str,
) -> UUID | None:
    generations = await llm_gateway.list_generations(
        session,
        business_id=business_id,
        purpose="labor_rule_profile_selection",
        provider=llm_gateway.LlmProvider.OPENAI,
        trace_id=trace_id,
        limit=1,
    )
    if not generations:
        return None
    return generations[0].id


async def run_llm_profile_selection(
    session: AsyncSession,
    *,
    business: Business,
    location: Location,
    profiles: Sequence[labor_rules.LaborRuleProfileSnapshot],
) -> LlmResolutionCandidate | None:
    if not settings.labor_rule_profile_selection_model or not llm_gateway.provider_is_configured(
        llm_gateway.LlmProvider.OPENAI
    ):
        return None

    trace_id = str(uuid4())
    result = await llm_gateway.generate(
        session,
        request=llm_gateway.LlmGenerationRequest(
            purpose="labor_rule_profile_selection",
            business_id=business.id,
            location_id=location.id,
            provider=llm_gateway.LlmProvider.OPENAI,
            model=settings.labor_rule_profile_selection_model,
            prompt_version=RESOLUTION_VERSION,
            messages=[
                llm_gateway.LlmMessage(
                    role="system",
                    content=(
                        "You choose among approved labor rule profiles for a location. "
                        "Use the tool exactly once and abstain when evidence is weak."
                    ),
                ),
                llm_gateway.LlmMessage(
                    role="user",
                    content=_build_prompt(
                        business=business,
                        location=location,
                        profiles=profiles,
                    ),
                ),
            ],
            tools=[_selection_tool_definition(profiles)],
            tool_choice=_PROFILE_SELECTION_TOOL,
            temperature=0,
            max_output_tokens=300,
            metadata={
                "feature": "labor_rule_profile_selection",
                "trace_id": trace_id,
                "jurisdiction_code": labor_rules.resolve_jurisdiction_code(location),
            },
        ),
    )
    llm_generation_id = await _lookup_llm_generation_id(session, business_id=business.id, trace_id=trace_id)
    tool_call = next((call for call in result.tool_calls if call.name == _PROFILE_SELECTION_TOOL), None)
    if tool_call is None:
        return None
    arguments = dict(tool_call.arguments or {})
    decision = str(arguments.get("decision") or "abstain").strip().lower()
    selected_profile_code = str(arguments.get("selected_profile_code") or "").strip() or None
    confidence = labor_rules._as_float(arguments.get("confidence"))
    reason = str(arguments.get("reason") or "").strip() or None
    reason_codes = tuple(
        str(item).strip()
        for item in arguments.get("reason_codes", [])
        if str(item).strip()
    )
    if decision == "select" and selected_profile_code not in {profile.code for profile in profiles}:
        return None
    return LlmResolutionCandidate(
        decision=decision,
        selected_profile_code=selected_profile_code,
        confidence=confidence,
        reason=reason,
        reason_codes=reason_codes,
        llm_generation_id=llm_generation_id,
        provider=result.provider,
        model=result.model,
    )


def _manual_override_code(location: Location) -> str | None:
    if not isinstance(location.settings, dict):
        return None
    raw_value = location.settings.get("labor_rule_manual_override_profile_code")
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized or None


def _deterministic_selection(
    *,
    business: Business,
    location: Location,
    profiles: Sequence[labor_rules.LaborRuleProfileSnapshot],
) -> tuple[labor_rules.LaborRuleProfileSnapshot | None, str, tuple[str, ...]]:
    manual_override_code = _manual_override_code(location)
    if manual_override_code:
        matching_override = [profile for profile in profiles if profile.code == manual_override_code]
        if len(matching_override) == 1:
            return matching_override[0], "manual_override", ("manual_override_profile",)

    if len(profiles) == 1:
        return profiles[0], "deterministic", ("single_active_profile",)

    industry_code = None
    if isinstance(location.settings, dict):
        raw_industry = location.settings.get("labor_industry_profile_code")
        if isinstance(raw_industry, str) and raw_industry.strip():
            industry_code = raw_industry.strip()
    if industry_code:
        exact = [profile for profile in profiles if profile.industry_profile_code == industry_code]
        if len(exact) == 1:
            return exact[0], "deterministic", ("industry_profile_match",)

    generic = [profile for profile in profiles if not profile.industry_profile_code]
    if len(generic) == 1:
        return generic[0], "fallback", ("generic_jurisdiction_profile",)

    return None, "fallback", ("multiple_plausible_profiles",)


async def persist_resolution_run(
    session: AsyncSession,
    *,
    location: Location,
    jurisdiction_code: str,
    candidate_profiles: Sequence[labor_rules.LaborRuleProfileSnapshot],
    outcome: ResolutionOutcome,
    input_snapshot: dict[str, object],
) -> LaborRuleResolutionRun:
    run = LaborRuleResolutionRun(
        location_id=location.id,
        jurisdiction_code=jurisdiction_code,
        candidate_profile_codes=[profile.code for profile in candidate_profiles],
        selected_profile_code=outcome.profile.code if outcome.profile else None,
        selected_profile_version_id=outcome.profile.version_id if outcome.profile else None,
        selected_profile_payload_hash=outcome.profile.payload_hash if outcome.profile else None,
        decision="selected" if outcome.profile is not None else "abstained",
        confidence=outcome.confidence,
        reason_codes=list(outcome.reason_codes),
        input_snapshot_json=input_snapshot,
        llm_generation_id=outcome.llm_generation_id,
    )
    session.add(run)
    await session.flush()
    return run


async def _apply_authoritative_resolution(
    session: AsyncSession,
    *,
    location: Location,
    jurisdiction_code: str,
    outcome: ResolutionOutcome,
) -> None:
    if outcome.profile is None:
        return
    existing = await labor_rules.load_authoritative_location_resolution(session, location_id=location.id)
    payload = {
        "mode": outcome.mode,
        "reason_codes": list(outcome.reason_codes),
        "fallback_reason": outcome.fallback_reason,
    }
    if existing is None:
        session.add(
            LocationLaborRuleResolution(
                location_id=location.id,
                jurisdiction_code=jurisdiction_code,
                resolved_profile_code=outcome.profile.code,
                resolved_profile_version_id=outcome.profile.version_id,
                resolved_profile_payload_hash=outcome.profile.payload_hash,
                resolution_source=outcome.resolution_source,
                resolution_confidence=outcome.confidence,
                manual_override_profile_code=_manual_override_code(location),
                resolution_context_json=payload,
                llm_generation_id=outcome.llm_generation_id,
                resolved_at=datetime.now(timezone.utc),
            )
        )
        await session.flush()
        return

    existing.jurisdiction_code = jurisdiction_code
    existing.resolved_profile_code = outcome.profile.code
    existing.resolved_profile_version_id = outcome.profile.version_id
    existing.resolved_profile_payload_hash = outcome.profile.payload_hash
    existing.resolution_source = outcome.resolution_source
    existing.resolution_confidence = outcome.confidence
    existing.manual_override_profile_code = _manual_override_code(location)
    existing.resolution_context_json = payload
    existing.llm_generation_id = outcome.llm_generation_id
    existing.resolved_at = datetime.now(timezone.utc)
    await session.flush()


async def sync_location_labor_rule_resolution(
    session: AsyncSession,
    *,
    business: Business,
    location: Location,
) -> ResolutionOutcome:
    mode = _resolution_mode()
    jurisdiction_code = labor_rules.resolve_jurisdiction_code(location)
    candidate_profiles = await labor_rules.active_profiles_for_jurisdiction(
        session,
        jurisdiction_code,
    )
    selected_profile, source, deterministic_reason_codes = _deterministic_selection(
        business=business,
        location=location,
        profiles=candidate_profiles,
    )

    fallback_reason = None
    llm_generation_id = None
    confidence = 1.0 if selected_profile is not None else None
    resolution_source = source
    reason_codes = deterministic_reason_codes

    if selected_profile is None and candidate_profiles:
        llm_candidate = await run_llm_profile_selection(
            session,
            business=business,
            location=location,
            profiles=candidate_profiles,
        )
        if (
            llm_candidate is not None
            and llm_candidate.decision == "select"
            and llm_candidate.selected_profile_code
            and (llm_candidate.confidence or 0.0) >= _CONFIDENCE_FLOOR
        ):
            selected_profile = next(
                (profile for profile in candidate_profiles if profile.code == llm_candidate.selected_profile_code),
                None,
            )
            resolution_source = "llm" if selected_profile is not None else "fallback"
            confidence = llm_candidate.confidence
            llm_generation_id = llm_candidate.llm_generation_id
            reason_codes = llm_candidate.reason_codes or ("llm_profile_selection",)
        else:
            fallback_reason = (
                llm_candidate.reason if llm_candidate is not None and llm_candidate.reason else "llm_abstained_or_low_confidence"
            )
            reason_codes = tuple(
                list(reason_codes) + ([fallback_reason] if fallback_reason else [])
            ) or ("llm_abstained_or_low_confidence",)
            llm_generation_id = llm_candidate.llm_generation_id if llm_candidate is not None else None
    elif selected_profile is None and not candidate_profiles:
        fallback_reason = "no_matching_labor_rule_profile"
        reason_codes = ("no_matching_labor_rule_profile",)

    outcome = ResolutionOutcome(
        profile=selected_profile,
        resolution_source=resolution_source,
        confidence=confidence,
        reason_codes=reason_codes,
        fallback_reason=fallback_reason,
        llm_generation_id=llm_generation_id,
        applied=bool(selected_profile is not None and mode == "primary"),
        mode=mode,
    )

    await persist_resolution_run(
        session,
        location=location,
        jurisdiction_code=jurisdiction_code,
        candidate_profiles=candidate_profiles,
        outcome=outcome,
        input_snapshot={
            "business_id": str(business.id),
            "location_id": str(location.id),
            "jurisdiction_code": jurisdiction_code,
            "candidate_profiles": [profile.code for profile in candidate_profiles],
            "location_settings": dict(location.settings or {}),
            "business_vertical": business.vertical,
        },
    )

    if outcome.applied:
        await _apply_authoritative_resolution(
            session,
            location=location,
            jurisdiction_code=jurisdiction_code,
            outcome=outcome,
        )

    return outcome
