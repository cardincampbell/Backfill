from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Sequence
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.ai import LlmGeneration
from app.models.business import Business, Location, Role
from app.models.business_classification import (
    BusinessDerivationGapSuggestion,
    BusinessDerivationRun,
)
from app.models.role_taxonomy import BusinessSubvertical, BusinessVertical
from app.services import llm_gateway, role_derivation
from app.services.utils import role_code_from_name

DERIVATION_VERSION = "business_classification_v1"
_CLASSIFICATION_TOOL_NAME = "submit_business_classification"
_CLASSIFICATION_CONFIDENCE_FLOOR = 0.68


@dataclass(frozen=True)
class GapSuggestion:
    suggestion_type: str
    confidence: float | None = None
    reason: str | None = None
    vertical_code: str | None = None
    subvertical_code: str | None = None
    proposed_code: str | None = None
    proposed_display_name: str | None = None


@dataclass(frozen=True)
class LlmClassificationCandidate:
    decision: str
    confidence: float | None
    reason: str | None
    reason_codes: tuple[str, ...]
    vertical_code: str | None = None
    subvertical_code: str | None = None
    selected_role_codes: tuple[str, ...] = ()
    gap_suggestions: tuple[GapSuggestion, ...] = ()
    provider: str | None = None
    model: str | None = None
    llm_generation_id: UUID | None = None


@dataclass(frozen=True)
class BusinessClassificationOutcome:
    derivation: role_derivation.DerivationResult
    source: str
    mode: str
    fallback_reason: str | None
    baseline_role_codes: tuple[str, ...]
    selected_role_codes: tuple[str, ...]
    llm_candidate: LlmClassificationCandidate | None


def _classification_mode() -> str:
    mode = settings.business_classification_mode.strip().lower()
    return mode if mode in {"shadow", "primary"} else "shadow"


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _serializable_place_metadata(metadata: dict | None) -> dict[str, Any]:
    payload = dict(metadata or {})
    return {
        "display_name": role_derivation._as_text(payload.get("display_name")),
        "name": role_derivation._as_text(payload.get("name")),
        "primary_type": role_derivation._as_text(payload.get("primary_type")),
        "types": [value for value in payload.get("types", []) if isinstance(value, str)][:20],
        "website_uri": role_derivation._as_text(payload.get("website_uri")),
        "regular_opening_hours": payload.get("regular_opening_hours")
        if isinstance(payload.get("regular_opening_hours"), dict)
        else {},
    }


def _serializable_location(location: Location) -> dict[str, Any]:
    return {
        "location_id": str(location.id),
        "name": location.name,
        "display_name": location.display_name,
        "locality": location.locality,
        "region": location.region,
        "google_place_metadata": _serializable_place_metadata(location.google_place_metadata),
    }


async def _load_subvertical_catalog(
    session: AsyncSession,
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    rows = (
        await session.execute(
            select(BusinessSubvertical).where(BusinessSubvertical.is_active.is_(True))
        )
    ).scalars().all()
    display_names = {row.code: row.display_name for row in rows}
    by_vertical: dict[str, list[str]] = {}
    for row in rows:
        by_vertical.setdefault(row.business_vertical_code, []).append(row.code)
    return (
        display_names,
        {key: tuple(sorted(values)) for key, values in by_vertical.items()},
    )


async def _load_vertical_display_names(session: AsyncSession) -> dict[str, str]:
    rows = (
        await session.execute(select(BusinessVertical).where(BusinessVertical.is_active.is_(True)))
    ).scalars().all()
    return {row.code: row.display_name for row in rows}


def _classification_tool_definition(
    taxonomy: role_derivation.RoleDerivationTaxonomy,
) -> llm_gateway.LlmToolDefinition:
    role_codes = sorted(taxonomy.business_role_archetypes)
    vertical_codes = sorted(taxonomy.active_vertical_codes)
    subvertical_codes = sorted(
        {
            code
            for values in taxonomy.subverticals_by_vertical.values()
            for code in values
        }
    )
    return llm_gateway.LlmToolDefinition(
        name=_CLASSIFICATION_TOOL_NAME,
        description=(
            "Return the best business classification from the allowed taxonomy, or abstain when evidence is weak."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["classify", "abstain"]},
                "vertical_code": {"type": "string", "enum": vertical_codes},
                "subvertical_code": {"type": "string", "enum": subvertical_codes},
                "selected_role_codes": {
                    "type": "array",
                    "items": {"type": "string", "enum": role_codes},
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"},
                "reason_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "gap_suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "suggestion_type": {
                                "type": "string",
                                "enum": ["missing_role_archetype", "missing_subvertical"],
                            },
                            "vertical_code": {"type": "string", "enum": vertical_codes},
                            "subvertical_code": {"type": "string", "enum": subvertical_codes},
                            "proposed_code": {"type": "string"},
                            "proposed_display_name": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "reason": {"type": "string"},
                        },
                        "required": ["suggestion_type", "confidence", "reason"],
                    },
                },
            },
            "required": [
                "decision",
                "selected_role_codes",
                "confidence",
                "reason",
                "reason_codes",
                "gap_suggestions",
            ],
        },
    )


def _build_llm_prompt(
    *,
    business: Business,
    locations: Sequence[Location],
    taxonomy: role_derivation.RoleDerivationTaxonomy,
    rules_derivation: role_derivation.DerivationResult,
    vertical_display_names: dict[str, str],
    subvertical_display_names: dict[str, str],
) -> str:
    payload = {
        "business": {
            "id": str(business.id),
            "name": business.name,
            "display_name": business.display_name,
            "current_vertical": business.vertical,
            "place_metadata": _serializable_place_metadata(business.place_metadata),
        },
        "locations": [_serializable_location(location) for location in locations[:8]],
        "rules_fallback": {
            "vertical": rules_derivation.classification.vertical,
            "subvertical": rules_derivation.classification.subvertical,
            "confidence": rules_derivation.classification.confidence,
            "reason_codes": rules_derivation.classification.reason_codes,
            "role_codes": [role.role_key for role in rules_derivation.roles],
        },
        "allowed_taxonomy": {
            "verticals": [
                {
                    "code": code,
                    "display_name": vertical_display_names.get(code, code.replace("_", " ").title()),
                    "baseline_role_codes": list(taxonomy.business_vertical_role_archetypes.get(code, ())),
                    "subvertical_codes": list(taxonomy.subverticals_by_vertical.get(code, ())),
                }
                for code in taxonomy.active_vertical_codes
            ],
            "subverticals": [
                {
                    "code": code,
                    "display_name": subvertical_display_names.get(code, code.replace("_", " ").title()),
                }
                for code in sorted(subvertical_display_names)
            ],
            "role_archetypes": [
                {
                    "code": role_code,
                    "display_name": definition.display_name,
                    "role_family": definition.role_family,
                }
                for role_code, definition in sorted(taxonomy.business_role_archetypes.items())
            ],
        },
        "instructions": [
            "Classify the business into the allowed taxonomy only.",
            "Use abstain when the evidence is weak, contradictory, or insufficient.",
            "selected_role_codes should only include extra role archetypes beyond the seeded baseline pack for the chosen vertical.",
            "You may add gap_suggestions when the bounded taxonomy appears incomplete, but never invent live taxonomy rows.",
            "Prefer precision over coverage. Forced guesses are worse than abstaining.",
        ],
    }
    return json.dumps(payload, ensure_ascii=True)


async def _lookup_llm_generation_id(
    session: AsyncSession,
    *,
    business_id: UUID,
    trace_id: str,
) -> UUID | None:
    rows = await llm_gateway.list_generations(
        session,
        business_id=business_id,
        purpose="business_classification",
        trace_id=trace_id,
        limit=1,
    )
    return rows[0].id if rows else None


def _normalize_gap_suggestions(
    raw_items: Any,
    *,
    taxonomy: role_derivation.RoleDerivationTaxonomy,
) -> tuple[GapSuggestion, ...]:
    suggestions: list[GapSuggestion] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    allowed_verticals = set(taxonomy.active_vertical_codes)
    allowed_subverticals = {
        code
        for values in taxonomy.subverticals_by_vertical.values()
        for code in values
    }
    for item in raw_items or []:
        if not isinstance(item, dict):
            continue
        suggestion_type = role_derivation._as_text(item.get("suggestion_type"))
        if suggestion_type not in {"missing_role_archetype", "missing_subvertical"}:
            continue
        vertical_code = role_derivation._as_text(item.get("vertical_code"))
        if vertical_code and vertical_code not in allowed_verticals:
            vertical_code = None
        subvertical_code = role_derivation._as_text(item.get("subvertical_code"))
        if subvertical_code and subvertical_code not in allowed_subverticals:
            subvertical_code = None
        proposed_code = role_derivation._as_text(item.get("proposed_code"))
        proposed_display_name = role_derivation._as_text(item.get("proposed_display_name"))
        reason = role_derivation._as_text(item.get("reason"))
        try:
            confidence_value = float(item.get("confidence"))
        except (TypeError, ValueError):
            confidence_value = None
        confidence = None if confidence_value is None else max(0.0, min(confidence_value, 1.0))
        dedupe_key = (suggestion_type, proposed_code, proposed_display_name)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        suggestions.append(
            GapSuggestion(
                suggestion_type=suggestion_type,
                vertical_code=vertical_code,
                subvertical_code=subvertical_code,
                proposed_code=proposed_code,
                proposed_display_name=proposed_display_name,
                confidence=confidence,
                reason=reason,
            )
        )
    return tuple(suggestions)


async def _llm_classification_candidate(
    session: AsyncSession,
    *,
    business: Business,
    locations: Sequence[Location],
    taxonomy: role_derivation.RoleDerivationTaxonomy,
    rules_derivation: role_derivation.DerivationResult,
    vertical_display_names: dict[str, str],
    subvertical_display_names: dict[str, str],
) -> LlmClassificationCandidate | None:
    if not settings.business_classification_model or not llm_gateway.provider_is_configured(
        llm_gateway.LlmProvider.OPENAI
    ):
        return None

    trace_id = str(uuid4())
    result = await llm_gateway.generate(
        session,
        request=llm_gateway.LlmGenerationRequest(
            purpose="business_classification",
            business_id=business.id,
            provider=llm_gateway.LlmProvider.OPENAI,
            model=settings.business_classification_model,
            prompt_version=DERIVATION_VERSION,
            messages=[
                llm_gateway.LlmMessage(
                    role="system",
                    content=(
                        "You classify businesses into a bounded internal taxonomy. "
                        "Use the tool exactly once. Abstain when the evidence is weak."
                    ),
                ),
                llm_gateway.LlmMessage(
                    role="user",
                    content=_build_llm_prompt(
                        business=business,
                        locations=locations,
                        taxonomy=taxonomy,
                        rules_derivation=rules_derivation,
                        vertical_display_names=vertical_display_names,
                        subvertical_display_names=subvertical_display_names,
                    ),
                ),
            ],
            tools=[_classification_tool_definition(taxonomy)],
            tool_choice=_CLASSIFICATION_TOOL_NAME,
            temperature=0,
            max_output_tokens=600,
            metadata={
                "feature": "business_classification",
                "trace_id": trace_id,
                "rules_vertical": rules_derivation.classification.vertical,
            },
        ),
    )

    call = next(
        (tool_call for tool_call in result.tool_calls if tool_call.name == _CLASSIFICATION_TOOL_NAME),
        None,
    )
    payload = call.arguments if call is not None else _json_object(result.output_text)
    if not isinstance(payload, dict) or not payload:
        return LlmClassificationCandidate(
            decision="abstain",
            confidence=None,
            reason="invalid_structured_output",
            reason_codes=("llm.invalid_structured_output",),
            provider=result.provider,
            model=result.model,
            llm_generation_id=await _lookup_llm_generation_id(session, business_id=business.id, trace_id=trace_id),
        )

    decision = role_derivation._as_text(payload.get("decision")) or "abstain"
    if decision not in {"classify", "abstain"}:
        decision = "abstain"

    allowed_verticals = set(taxonomy.active_vertical_codes)
    raw_vertical = role_derivation._as_text(payload.get("vertical_code"))
    vertical_code = raw_vertical if raw_vertical in allowed_verticals else None

    raw_subvertical = role_derivation._as_text(payload.get("subvertical_code"))
    subvertical_code = None
    if (
        raw_subvertical
        and vertical_code
        and raw_subvertical in set(taxonomy.subverticals_by_vertical.get(vertical_code, ()))
    ):
        subvertical_code = raw_subvertical

    selected_role_codes: list[str] = []
    allowed_role_codes = set(taxonomy.business_role_archetypes)
    for value in payload.get("selected_role_codes") or []:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
        if normalized and normalized in allowed_role_codes and normalized not in selected_role_codes:
            selected_role_codes.append(normalized)

    try:
        confidence_value = float(payload.get("confidence"))
    except (TypeError, ValueError):
        confidence_value = None
    confidence = None if confidence_value is None else max(0.0, min(confidence_value, 1.0))

    reason = role_derivation._as_text(payload.get("reason"))
    reason_codes = tuple(
        dict.fromkeys(
            code.strip()
            for code in payload.get("reason_codes", [])
            if isinstance(code, str) and code.strip()
        )
    )
    if not reason_codes:
        default_code = "llm.abstain" if decision == "abstain" else "llm.classify"
        reason_codes = (default_code,)

    if decision == "classify" and (vertical_code is None or confidence is None):
        decision = "abstain"
        reason = reason or "missing_required_fields"
        reason_codes = tuple(sorted(set(reason_codes) | {"llm.invalid_missing_fields"}))

    return LlmClassificationCandidate(
        decision=decision,
        vertical_code=vertical_code,
        subvertical_code=subvertical_code,
        selected_role_codes=tuple(selected_role_codes),
        confidence=confidence,
        reason=reason,
        reason_codes=reason_codes,
        gap_suggestions=_normalize_gap_suggestions(payload.get("gap_suggestions"), taxonomy=taxonomy),
        provider=result.provider,
        model=result.model,
        llm_generation_id=await _lookup_llm_generation_id(session, business_id=business.id, trace_id=trace_id),
    )


def _llm_candidate_can_apply(candidate: LlmClassificationCandidate | None) -> tuple[bool, str | None]:
    if candidate is None:
        return False, "llm_unconfigured"
    if candidate.decision == "abstain":
        return False, candidate.reason or "llm_abstained"
    if candidate.confidence is None:
        return False, "llm_missing_confidence"
    if candidate.confidence < _CLASSIFICATION_CONFIDENCE_FLOOR:
        return False, "llm_low_confidence"
    if candidate.vertical_code is None:
        return False, "llm_missing_vertical"
    return True, None


def _roles_from_keys(
    *,
    role_keys: Sequence[str],
    taxonomy: role_derivation.RoleDerivationTaxonomy,
    confidence: float,
    derivation_type: str,
    reason_codes: Sequence[str],
) -> list[role_derivation.DerivedRole]:
    roles: list[role_derivation.DerivedRole] = []
    for role_key in role_keys:
        definition = taxonomy.business_role_archetypes.get(role_key)
        if definition is None:
            continue
        roles.append(
            role_derivation.DerivedRole(
                role_key=role_key,
                display_name=definition.display_name,
                role_family=definition.role_family,
                confidence=round(confidence, 3),
                derivation_type=derivation_type,
                reason_codes=list(reason_codes),
                support_location_ids=[],
            )
        )
    return roles


def _merge_role_sets(
    *,
    baseline_roles: Sequence[str],
    selected_roles: Sequence[str],
    taxonomy: role_derivation.RoleDerivationTaxonomy,
    confidence: float,
    reason_codes: Sequence[str],
) -> list[role_derivation.DerivedRole]:
    merged: dict[str, role_derivation.DerivedRole] = {}
    for role in _roles_from_keys(
        role_keys=baseline_roles,
        taxonomy=taxonomy,
        confidence=max(0.66, confidence),
        derivation_type="baseline",
        reason_codes=reason_codes,
    ):
        merged[role.role_key] = role
    for role in _roles_from_keys(
        role_keys=selected_roles,
        taxonomy=taxonomy,
        confidence=max(0.72, confidence),
        derivation_type="llm_selected",
        reason_codes=[*reason_codes, "llm.additional_role"],
    ):
        existing = merged.get(role.role_key)
        if existing is None or role.confidence > existing.confidence:
            merged[role.role_key] = role
    return sorted(merged.values(), key=lambda item: (-item.confidence, item.display_name))


def _primary_outcome_from_llm(
    *,
    candidate: LlmClassificationCandidate,
    taxonomy: role_derivation.RoleDerivationTaxonomy,
) -> BusinessClassificationOutcome:
    assert candidate.vertical_code is not None
    baseline_roles = taxonomy.business_vertical_role_archetypes.get(
        candidate.vertical_code,
        taxonomy.business_vertical_role_archetypes.get("mixed_unknown", ()),
    )
    applied_roles = _merge_role_sets(
        baseline_roles=baseline_roles,
        selected_roles=candidate.selected_role_codes,
        taxonomy=taxonomy,
        confidence=candidate.confidence or 0.72,
        reason_codes=candidate.reason_codes,
    )
    derivation = role_derivation.DerivationResult(
        classification=role_derivation.DerivedClassification(
            vertical=candidate.vertical_code,
            subvertical=candidate.subvertical_code,
            confidence=round(candidate.confidence or 0.72, 3),
            reason_codes=list(candidate.reason_codes),
        ),
        roles=applied_roles,
    )
    return BusinessClassificationOutcome(
        derivation=derivation,
        source="llm",
        mode="primary",
        fallback_reason=None,
        baseline_role_codes=tuple(baseline_roles),
        selected_role_codes=tuple(candidate.selected_role_codes),
        llm_candidate=candidate,
    )


def _fallback_outcome(
    *,
    rules_derivation: role_derivation.DerivationResult,
    candidate: LlmClassificationCandidate | None,
    fallback_reason: str,
    mode: str,
    taxonomy: role_derivation.RoleDerivationTaxonomy,
) -> BusinessClassificationOutcome:
    baseline_roles = taxonomy.business_vertical_role_archetypes.get(
        rules_derivation.classification.vertical,
        taxonomy.business_vertical_role_archetypes.get("mixed_unknown", ()),
    )
    selected_role_codes = tuple(
        role.role_key for role in rules_derivation.roles if role.role_key not in set(baseline_roles)
    )
    return BusinessClassificationOutcome(
        derivation=rules_derivation,
        source="rules",
        mode=mode,
        fallback_reason=fallback_reason,
        baseline_role_codes=tuple(baseline_roles),
        selected_role_codes=selected_role_codes,
        llm_candidate=candidate,
    )


def _snapshot_payload(
    *,
    outcome: BusinessClassificationOutcome,
    location_count: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "vertical": outcome.derivation.classification.vertical,
        "subvertical": outcome.derivation.classification.subvertical,
        "confidence": outcome.derivation.classification.confidence,
        "reason_codes": outcome.derivation.classification.reason_codes,
        "location_count": location_count,
        "derivation_version": DERIVATION_VERSION,
        "source": outcome.source,
        "mode": outcome.mode,
        "baseline_role_codes": list(outcome.baseline_role_codes),
        "selected_role_codes": list(outcome.selected_role_codes),
        "applied_role_codes": [role.role_key for role in outcome.derivation.roles],
    }
    if outcome.fallback_reason is not None:
        payload["fallback_reason"] = outcome.fallback_reason
    if outcome.llm_candidate is not None:
        payload["llm_candidate"] = {
            "decision": outcome.llm_candidate.decision,
            "vertical": outcome.llm_candidate.vertical_code,
            "subvertical": outcome.llm_candidate.subvertical_code,
            "selected_role_codes": list(outcome.llm_candidate.selected_role_codes),
            "confidence": outcome.llm_candidate.confidence,
            "reason": outcome.llm_candidate.reason,
            "reason_codes": list(outcome.llm_candidate.reason_codes),
            "provider": outcome.llm_candidate.provider,
            "model": outcome.llm_candidate.model,
            "applied": outcome.source == "llm" and outcome.mode == "primary",
        }
    return payload


def _role_metadata_payload(
    *,
    role: role_derivation.DerivedRole,
) -> dict[str, Any]:
    return {
        "source": "business_classification",
        "version": DERIVATION_VERSION,
        "confidence": role.confidence,
        "role_family": role.role_family,
        "derivation_type": role.derivation_type,
        "reason_codes": role.reason_codes,
        "support_location_ids": [str(location_id) for location_id in role.support_location_ids],
        "support_location_count": len(role.support_location_ids),
    }


async def _persist_gap_suggestions(
    session: AsyncSession,
    *,
    business_id: UUID,
    derivation_run_id: UUID,
    gap_suggestions: Sequence[GapSuggestion],
) -> None:
    for suggestion in gap_suggestions:
        session.add(
            BusinessDerivationGapSuggestion(
                business_id=business_id,
                derivation_run_id=derivation_run_id,
                suggestion_type=suggestion.suggestion_type,
                vertical_code=suggestion.vertical_code,
                subvertical_code=suggestion.subvertical_code,
                proposed_code=suggestion.proposed_code,
                proposed_display_name=suggestion.proposed_display_name,
                confidence=suggestion.confidence,
                reason=suggestion.reason,
                suggestion_metadata={},
            )
        )


async def sync_business_classification(
    session: AsyncSession,
    business: Business,
    *,
    locations: Sequence[Location] | None = None,
) -> role_derivation.DerivationResult:
    if locations is None:
        result = await session.execute(select(Location).where(Location.business_id == business.id))
        locations = list(result.scalars().all())

    taxonomy = await role_derivation.load_role_derivation_taxonomy(session)
    vertical_display_names = await _load_vertical_display_names(session)
    subvertical_display_names, _ = await _load_subvertical_catalog(session)
    rules_derivation = role_derivation.derive_business_catalog(
        taxonomy=taxonomy,
        business_place_metadata=business.place_metadata,
        locations=locations,
    )
    llm_candidate = await _llm_classification_candidate(
        session,
        business=business,
        locations=locations,
        taxonomy=taxonomy,
        rules_derivation=rules_derivation,
        vertical_display_names=vertical_display_names,
        subvertical_display_names=subvertical_display_names,
    )
    mode = _classification_mode()
    can_apply_llm, llm_fallback_reason = _llm_candidate_can_apply(llm_candidate)

    if mode == "primary" and can_apply_llm and llm_candidate is not None:
        outcome = _primary_outcome_from_llm(candidate=llm_candidate, taxonomy=taxonomy)
    elif mode == "shadow":
        outcome = _fallback_outcome(
            rules_derivation=rules_derivation,
            candidate=llm_candidate,
            fallback_reason="shadow_mode",
            mode=mode,
            taxonomy=taxonomy,
        )
    else:
        outcome = _fallback_outcome(
            rules_derivation=rules_derivation,
            candidate=llm_candidate,
            fallback_reason=llm_fallback_reason or "rules_fallback",
            mode=mode,
            taxonomy=taxonomy,
        )

    settings_payload = dict(business.settings or {})
    settings_payload["derived_classification"] = _snapshot_payload(
        outcome=outcome,
        location_count=len([location for location in locations if location.google_place_metadata]),
    )
    if settings_payload.get("vertical_source") != "manual":
        business.vertical = outcome.derivation.classification.vertical
        settings_payload["vertical_source"] = "derived"
    business.settings = settings_payload

    derivation_run = BusinessDerivationRun(
        business_id=business.id,
        llm_generation_id=outcome.llm_candidate.llm_generation_id if outcome.llm_candidate is not None else None,
        mode=outcome.mode,
        source=outcome.source,
        decision=outcome.llm_candidate.decision if outcome.llm_candidate is not None else "rules_fallback",
        provider=outcome.llm_candidate.provider if outcome.llm_candidate is not None else None,
        model=outcome.llm_candidate.model if outcome.llm_candidate is not None else None,
        vertical_code=outcome.derivation.classification.vertical,
        subvertical_code=outcome.derivation.classification.subvertical,
        confidence=outcome.derivation.classification.confidence,
        applied=True,
        fallback_reason=outcome.fallback_reason,
        evidence_payload={
            "business_place_metadata": _serializable_place_metadata(business.place_metadata),
            "locations": [_serializable_location(location) for location in locations[:8]],
        },
        reason_codes=outcome.derivation.classification.reason_codes,
        baseline_role_codes=list(outcome.baseline_role_codes),
        selected_role_codes=list(outcome.selected_role_codes),
        applied_role_codes=[role.role_key for role in outcome.derivation.roles],
        run_metadata={
            "llm_candidate": _snapshot_payload(
                outcome=BusinessClassificationOutcome(
                    derivation=outcome.derivation,
                    source=outcome.source,
                    mode=outcome.mode,
                    fallback_reason=outcome.fallback_reason,
                    baseline_role_codes=outcome.baseline_role_codes,
                    selected_role_codes=outcome.selected_role_codes,
                    llm_candidate=outcome.llm_candidate,
                ),
                location_count=len(locations),
            ).get("llm_candidate"),
        },
    )
    session.add(derivation_run)
    await session.flush()
    if outcome.llm_candidate is not None:
        await _persist_gap_suggestions(
            session,
            business_id=business.id,
            derivation_run_id=derivation_run.id,
            gap_suggestions=outcome.llm_candidate.gap_suggestions,
        )

    existing_rows = await session.execute(select(Role).where(Role.business_id == business.id))
    existing_roles = {role.code: role for role in existing_rows.scalars().all()}
    for derived_role in outcome.derivation.roles:
        metadata_payload = _role_metadata_payload(role=derived_role)
        existing = existing_roles.get(role_code_from_name(derived_role.role_key))
        if existing is None:
            session.add(
                Role(
                    business_id=business.id,
                    code=role_code_from_name(derived_role.role_key),
                    name=derived_role.display_name,
                    category=derived_role.role_family,
                    min_notice_minutes=0,
                    coverage_priority=100,
                    metadata_json={"derivation": metadata_payload},
                )
            )
            continue

        metadata_json = dict(existing.metadata_json or {})
        metadata_json["derivation"] = metadata_payload
        existing.metadata_json = metadata_json
        if not existing.category:
            existing.category = derived_role.role_family

    await session.flush()
    return outcome.derivation
