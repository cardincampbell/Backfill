from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.business import Business, Location, Role
from app.models.role_taxonomy import (
    BusinessRoleArchetype,
    BusinessSubvertical,
    BusinessVertical,
    BusinessVerticalRoleArchetype,
    BusinessVerticalTypeMapping,
)
from app.services import llm_gateway
from app.services.utils import role_code_from_name

DERIVATION_VERSION = "places_rules_v2_db_taxonomy"


@dataclass(frozen=True)
class DerivedClassification:
    vertical: str
    subvertical: str | None
    confidence: float
    reason_codes: list[str]


@dataclass(frozen=True)
class DerivedRole:
    role_key: str
    display_name: str
    role_family: str
    confidence: float
    derivation_type: str
    reason_codes: list[str]
    support_location_ids: list[UUID]


@dataclass(frozen=True)
class DerivationResult:
    classification: DerivedClassification
    roles: list[DerivedRole]


@dataclass(frozen=True)
class _SourceContext:
    location_id: UUID | None
    primary_type: str | None
    types: tuple[str, ...]
    website_uri: str | None
    regular_opening_hours: dict


@dataclass(frozen=True)
class BusinessRoleArchetypeDefinition:
    display_name: str
    role_family: str


@dataclass(frozen=True)
class RoleDerivationTaxonomy:
    business_vertical_type_mappings: dict[str, tuple[str, str | None]]
    business_vertical_role_archetypes: dict[str, tuple[str, ...]]
    business_role_archetypes: dict[str, BusinessRoleArchetypeDefinition]
    active_vertical_codes: tuple[str, ...]
    subverticals_by_vertical: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class LlmDerivationSuggestion:
    vertical: str | None = None
    subvertical: str | None = None
    role_keys: tuple[str, ...] = ()
    confidence: float | None = None
    reason: str | None = None


async def load_role_derivation_taxonomy(session: AsyncSession) -> RoleDerivationTaxonomy:
    vertical_rows = (
        await session.execute(
            select(BusinessVertical).where(BusinessVertical.is_active.is_(True))
        )
    ).scalars().all()
    active_vertical_codes = {row.code for row in vertical_rows}

    mapping_rows = (
        await session.execute(
            select(BusinessVerticalTypeMapping).where(
                BusinessVerticalTypeMapping.is_active.is_(True)
            )
        )
    ).scalars().all()
    subvertical_rows = (
        await session.execute(
            select(BusinessSubvertical).where(BusinessSubvertical.is_active.is_(True))
        )
    ).scalars().all()

    archetype_rows = (
        await session.execute(
            select(BusinessRoleArchetype).where(BusinessRoleArchetype.is_active.is_(True))
        )
    ).scalars().all()
    active_role_codes = {row.code for row in archetype_rows}

    vertical_role_rows = (
        await session.execute(
            select(BusinessVerticalRoleArchetype)
            .where(BusinessVerticalRoleArchetype.is_active.is_(True))
            .order_by(
                BusinessVerticalRoleArchetype.business_vertical_code,
                BusinessVerticalRoleArchetype.sort_order,
                BusinessVerticalRoleArchetype.business_role_code,
            )
        )
    ).scalars().all()

    business_vertical_type_mappings = {
        row.place_type.strip().lower(): (row.business_vertical_code, row.subvertical_code)
        for row in mapping_rows
        if row.business_vertical_code in active_vertical_codes and row.place_type.strip()
    }
    subverticals_by_vertical: dict[str, set[str]] = {code: set() for code in active_vertical_codes}
    for row in subvertical_rows:
        if row.business_vertical_code not in active_vertical_codes:
            continue
        subverticals_by_vertical.setdefault(row.business_vertical_code, set()).add(row.code)
    business_vertical_role_archetypes: dict[str, list[str]] = {
        code: [] for code in active_vertical_codes
    }
    for row in vertical_role_rows:
        if (
            row.business_vertical_code not in active_vertical_codes
            or row.business_role_code not in active_role_codes
        ):
            continue
        business_vertical_role_archetypes.setdefault(
            row.business_vertical_code,
            [],
        ).append(row.business_role_code)

    business_role_archetypes = {
        row.code: BusinessRoleArchetypeDefinition(
            display_name=row.display_name,
            role_family=row.role_family,
        )
        for row in archetype_rows
    }

    if not business_vertical_type_mappings or not business_role_archetypes:
        raise ValueError("role_derivation_taxonomy_missing")

    return RoleDerivationTaxonomy(
        business_vertical_type_mappings=business_vertical_type_mappings,
        business_vertical_role_archetypes={
            key: tuple(value) for key, value in business_vertical_role_archetypes.items()
        },
        business_role_archetypes=business_role_archetypes,
        active_vertical_codes=tuple(sorted(active_vertical_codes)),
        subverticals_by_vertical={
            key: tuple(sorted(value))
            for key, value in subverticals_by_vertical.items()
        },
    )


def _as_text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _extract_json_object(raw_text: str | None) -> dict:
    if not raw_text:
        return {}
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            parsed = json.loads(raw_text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _unique_strings(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in values:
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def _source_context(location_id: UUID | None, metadata: dict | None) -> _SourceContext | None:
    payload = metadata or {}
    primary_type = _as_text(payload.get("primary_type"))
    types = _unique_strings(value for value in (payload.get("types") or []) if isinstance(value, str))
    website_uri = _as_text(payload.get("website_uri"))
    regular_opening_hours = payload.get("regular_opening_hours") if isinstance(payload.get("regular_opening_hours"), dict) else {}
    if primary_type is None and not types and website_uri is None:
        return None
    return _SourceContext(
        location_id=location_id,
        primary_type=primary_type.lower() if primary_type is not None else None,
        types=types,
        website_uri=website_uri,
        regular_opening_hours=regular_opening_hours,
    )


def _opening_hours_flags(regular_opening_hours: dict) -> set[str]:
    flags: set[str] = set()
    periods = regular_opening_hours.get("periods")
    if not isinstance(periods, list):
        return flags
    for period in periods:
        if not isinstance(period, dict):
            continue
        open_info = period.get("open")
        if not isinstance(open_info, dict):
            continue
        time_value = _as_text(open_info.get("time"))
        if time_value is None or len(time_value) != 4 or not time_value.isdigit():
            continue
        hour = int(time_value[:2])
        if hour < 11:
            flags.add("morning_operation")
        if hour >= 17:
            flags.add("evening_operation")
        if hour >= 22 or hour <= 3:
            flags.add("late_night_operation")
    return flags


def _classify_source(
    source: _SourceContext,
    *,
    taxonomy: RoleDerivationTaxonomy,
) -> DerivedClassification:
    scores: dict[str, float] = {}
    subvertical_scores: dict[str, float] = {}
    reason_codes: dict[str, set[str]] = {}

    def apply_token(token: str, *, weight: float, origin: str) -> None:
        match = taxonomy.business_vertical_type_mappings.get(token)
        if match is None:
            return
        vertical, subvertical = match
        scores[vertical] = scores.get(vertical, 0.0) + weight
        if subvertical:
            subvertical_scores[subvertical] = subvertical_scores.get(subvertical, 0.0) + weight
        reason_codes.setdefault(vertical, set()).add(f"{origin}.{token}")

    if source.primary_type is not None:
        apply_token(source.primary_type, weight=5.0, origin="places.primary_type")
    for token in source.types:
        apply_token(token, weight=2.0, origin="places.type")

    if not scores:
        return DerivedClassification(
            vertical="mixed_unknown",
            subvertical=None,
            confidence=0.35,
            reason_codes=["places.metadata_sparse"],
        )

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    vertical, top_score = ordered[0]
    runner_up = ordered[1][1] if len(ordered) > 1 else 0.0
    confidence = min(0.96, 0.45 + (top_score * 0.05) + max(0.0, top_score - runner_up) * 0.02)
    subvertical = None
    if subvertical_scores:
        subvertical = sorted(subvertical_scores.items(), key=lambda item: item[1], reverse=True)[0][0]
    return DerivedClassification(
        vertical=vertical,
        subvertical=subvertical,
        confidence=round(confidence, 3),
        reason_codes=sorted(reason_codes.get(vertical, {f"vertical.{vertical}"})),
    )


def _derive_source_roles(
    source: _SourceContext,
    *,
    taxonomy: RoleDerivationTaxonomy,
) -> tuple[DerivedClassification, list[tuple[str, str, list[str]]]]:
    classification = _classify_source(source, taxonomy=taxonomy)
    tokens = set(source.types)
    if source.primary_type is not None:
        tokens.add(source.primary_type)
    flags = _opening_hours_flags(source.regular_opening_hours)
    fallback_roles = taxonomy.business_vertical_role_archetypes.get("mixed_unknown", ())
    base_roles = list(
        taxonomy.business_vertical_role_archetypes.get(
            classification.vertical,
            fallback_roles,
        )
    )
    derived: list[tuple[str, str, list[str]]] = [
        (role_key, "base", [f"vertical.{classification.vertical}", *classification.reason_codes])
        for role_key in base_roles
    ]

    def add_role(role_key: str, reason_codes: Sequence[str]) -> None:
        if role_key in {entry[0] for entry in derived}:
            return
        derived.append((role_key, "modifier", list(reason_codes)))

    if classification.vertical == "restaurant":
        if tokens.intersection({"bar", "wine_bar", "pub", "night_club"}):
            add_role("bartender", ["vertical.restaurant", "modifier.bar_service"])
            add_role("barback", ["vertical.restaurant", "modifier.bar_service"])
        if "meal_delivery" in tokens:
            add_role("delivery_coordinator", ["vertical.restaurant", "places.type.meal_delivery"])
        if "meal_takeaway" in tokens:
            add_role("expeditor", ["vertical.restaurant", "places.type.meal_takeaway"])
        if tokens.intersection({"bakery", "cafe", "coffee_shop"}):
            add_role("prep_kitchen", ["vertical.restaurant", "modifier.food_prep"])

    if classification.vertical == "cafe":
        if "bakery" in tokens:
            add_role("baker", ["vertical.cafe", "places.type.bakery"])
        if flags.intersection({"morning_operation", "evening_operation"}):
            add_role("assistant_manager", ["vertical.cafe", *sorted(flags)])

    if classification.vertical == "retail":
        if tokens.intersection({"grocery_store", "supermarket", "convenience_store"}):
            add_role("pickup_associate", ["vertical.retail", "modifier.pickup_operations"])
        if "late_night_operation" in flags:
            add_role("inventory_lead", ["vertical.retail", "operating_model.late_night_operation"])

    if classification.vertical == "beauty":
        if "spa" in tokens:
            add_role("esthetician", ["vertical.beauty", "places.type.spa"])
        if "nail_salon" in tokens:
            add_role("nail_technician", ["vertical.beauty", "places.type.nail_salon"])

    if classification.vertical == "home_services":
        if tokens.intersection({"general_contractor", "roofing_contractor", "hvac_contractor"}):
            add_role("installer", ["vertical.home_services", "modifier.installation"])

    if classification.vertical == "warehouse" and tokens.intersection({"warehouse", "storage"}):
        add_role("forklift_operator", ["vertical.warehouse", "modifier.equipment"])

    return classification, derived


def derive_business_catalog(
    *,
    taxonomy: RoleDerivationTaxonomy,
    business_place_metadata: dict | None,
    locations: Sequence[Location],
) -> DerivationResult:
    contexts: list[_SourceContext] = []
    business_context = _source_context(None, business_place_metadata)
    if business_context is not None:
        contexts.append(business_context)
    for location in locations:
        source = _source_context(location.id, location.google_place_metadata)
        if source is not None:
            contexts.append(source)

    if not contexts:
        return DerivationResult(
            classification=DerivedClassification(
                vertical="mixed_unknown",
                subvertical=None,
                confidence=0.2,
                reason_codes=["places.metadata_missing"],
            ),
            roles=[],
        )

    vertical_scores: dict[str, float] = {}
    vertical_reason_codes: dict[str, set[str]] = {}
    subvertical_scores: dict[str, float] = {}
    role_support: dict[str, dict] = {}

    for source in contexts:
        classification, role_entries = _derive_source_roles(source, taxonomy=taxonomy)
        vertical_scores[classification.vertical] = vertical_scores.get(classification.vertical, 0.0) + classification.confidence
        vertical_reason_codes.setdefault(classification.vertical, set()).update(classification.reason_codes)
        if classification.subvertical:
            subvertical_scores[classification.subvertical] = subvertical_scores.get(classification.subvertical, 0.0) + classification.confidence

        for role_key, derivation_type, reason_codes in role_entries:
            entry = role_support.setdefault(
                role_key,
                {
                    "confidence_total": 0.0,
                    "samples": 0,
                    "derivation_types": set(),
                    "reason_codes": set(),
                    "location_ids": set(),
                },
            )
            entry["confidence_total"] += classification.confidence
            entry["samples"] += 1
            entry["derivation_types"].add(derivation_type)
            entry["reason_codes"].update(reason_codes)
            if source.location_id is not None:
                entry["location_ids"].add(source.location_id)

    ordered_verticals = sorted(vertical_scores.items(), key=lambda item: item[1], reverse=True)
    top_vertical, top_score = ordered_verticals[0]
    runner_up = ordered_verticals[1][1] if len(ordered_verticals) > 1 else 0.0
    business_confidence = min(0.97, 0.5 + top_score * 0.12 + max(0.0, top_score - runner_up) * 0.05)
    subvertical = None
    if subvertical_scores:
        subvertical = sorted(subvertical_scores.items(), key=lambda item: item[1], reverse=True)[0][0]

    roles: list[DerivedRole] = []
    for role_key, support in role_support.items():
        definition = taxonomy.business_role_archetypes.get(role_key)
        if definition is None:
            display_name = role_key.replace("_", " ").title()
            role_family = "operations"
        else:
            display_name = definition.display_name
            role_family = definition.role_family
        average_confidence = support["confidence_total"] / max(1, support["samples"])
        cross_location_bonus = min(0.1, max(0, len(support["location_ids"]) - 1) * 0.03)
        confidence = round(min(0.97, average_confidence + cross_location_bonus), 3)
        derivation_type = "modifier" if "modifier" in support["derivation_types"] and "base" not in support["derivation_types"] else "base"
        roles.append(
            DerivedRole(
                role_key=role_key,
                display_name=display_name,
                role_family=role_family,
                confidence=confidence,
                derivation_type=derivation_type,
                reason_codes=sorted(support["reason_codes"]),
                support_location_ids=sorted(support["location_ids"], key=str),
            )
        )

    roles.sort(key=lambda item: (-item.confidence, item.display_name))
    return DerivationResult(
        classification=DerivedClassification(
            vertical=top_vertical,
            subvertical=subvertical,
            confidence=round(business_confidence, 3),
            reason_codes=sorted(vertical_reason_codes.get(top_vertical, {f"vertical.{top_vertical}"})),
        ),
        roles=roles,
    )


def _serializable_location_metadata(location: Location) -> dict:
    metadata = dict(location.google_place_metadata or {})
    return {
        "location_id": str(location.id),
        "name": location.name,
        "primary_type": _as_text(metadata.get("primary_type")),
        "types": [value for value in metadata.get("types", []) if isinstance(value, str)][:20],
        "website_uri": _as_text(metadata.get("website_uri")),
        "regular_opening_hours": metadata.get("regular_opening_hours") if isinstance(metadata.get("regular_opening_hours"), dict) else {},
    }


def _build_llm_derivation_prompt(
    *,
    business: Business,
    taxonomy: RoleDerivationTaxonomy,
    business_place_metadata: dict | None,
    locations: Sequence[Location],
    deterministic: DerivationResult,
) -> str:
    payload = {
        "business": {
            "name": business.display_name or business.name,
            "current_vertical": business.vertical,
            "place_metadata": dict(business_place_metadata or {}),
        },
        "locations": [_serializable_location_metadata(location) for location in locations[:8]],
        "deterministic_derivation": {
            "vertical": deterministic.classification.vertical,
            "subvertical": deterministic.classification.subvertical,
            "confidence": deterministic.classification.confidence,
            "reason_codes": deterministic.classification.reason_codes,
            "role_keys": [role.role_key for role in deterministic.roles],
        },
        "allowed_verticals": list(taxonomy.active_vertical_codes),
        "allowed_subverticals_by_vertical": {
            key: list(value) for key, value in taxonomy.subverticals_by_vertical.items()
        },
        "allowed_role_catalog": [
            {
                "role_key": role_key,
                "display_name": definition.display_name,
                "role_family": definition.role_family,
            }
            for role_key, definition in sorted(taxonomy.business_role_archetypes.items())
        ],
        "instructions": {
            "goal": "Refine the business vertical/subvertical and suggest extra role archetypes that are likely useful for this business.",
            "constraints": [
                "Do not invent new verticals, subverticals, or role keys.",
                "Only return values from the allowed lists.",
                "Prefer the deterministic derivation unless there is strong evidence to refine it.",
                "Only suggest extra role keys that are missing from deterministic_role_keys.",
            ],
            "output_schema": {
                "vertical": "string | null",
                "subvertical": "string | null",
                "additional_role_keys": "string[]",
                "confidence": "number between 0 and 1",
                "reason": "short string",
            },
        },
    }
    return json.dumps(payload, ensure_ascii=True)


async def _llm_refine_business_catalog(
    session: AsyncSession,
    *,
    business: Business,
    taxonomy: RoleDerivationTaxonomy,
    business_place_metadata: dict | None,
    locations: Sequence[Location],
    deterministic: DerivationResult,
) -> LlmDerivationSuggestion | None:
    if not settings.role_derivation_model or not settings.openai_api_key:
        return None

    result = await llm_gateway.generate(
        session,
        request=llm_gateway.LlmGenerationRequest(
            purpose="role_derivation_refinement",
            business_id=business.id,
            provider=llm_gateway.LlmProvider.OPENAI,
            model=settings.role_derivation_model,
            messages=[
                llm_gateway.LlmMessage(
                    role="system",
                    content=(
                        "You refine business vertical classification and suggest extra role archetypes. "
                        "Return exactly one JSON object and no other text."
                    ),
                ),
                llm_gateway.LlmMessage(
                    role="user",
                    content=_build_llm_derivation_prompt(
                        business=business,
                        taxonomy=taxonomy,
                        business_place_metadata=business_place_metadata,
                        locations=locations,
                        deterministic=deterministic,
                    ),
                ),
            ],
            temperature=0,
            max_output_tokens=400,
            metadata={
                "feature": "role_derivation_refinement",
                "deterministic_vertical": deterministic.classification.vertical,
                "deterministic_role_count": len(deterministic.roles),
            },
        ),
    )
    payload = _extract_json_object(result.output_text)
    if not payload:
        return None

    raw_vertical = _as_text(payload.get("vertical"))
    vertical = raw_vertical.lower() if raw_vertical and raw_vertical.lower() in taxonomy.active_vertical_codes else None

    raw_subvertical = _as_text(payload.get("subvertical"))
    subvertical = None
    if vertical and raw_subvertical:
        allowed_subverticals = set(taxonomy.subverticals_by_vertical.get(vertical, ()))
        lowered_subvertical = raw_subvertical.lower()
        if lowered_subvertical in allowed_subverticals:
            subvertical = lowered_subvertical

    allowed_role_keys = set(taxonomy.business_role_archetypes)
    deterministic_role_keys = {role.role_key for role in deterministic.roles}
    additional_role_keys: list[str] = []
    for value in payload.get("additional_role_keys") or []:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
        if not normalized or normalized not in allowed_role_keys or normalized in deterministic_role_keys:
            continue
        if normalized not in additional_role_keys:
            additional_role_keys.append(normalized)

    try:
        confidence_value = float(payload.get("confidence"))
    except (TypeError, ValueError):
        confidence_value = None
    confidence = None if confidence_value is None else max(0.0, min(confidence_value, 1.0))
    reason = _as_text(payload.get("reason"))
    return LlmDerivationSuggestion(
        vertical=vertical,
        subvertical=subvertical,
        role_keys=tuple(additional_role_keys),
        confidence=confidence,
        reason=reason,
    )


async def _apply_llm_refinement(
    session: AsyncSession,
    *,
    business: Business,
    taxonomy: RoleDerivationTaxonomy,
    business_place_metadata: dict | None,
    locations: Sequence[Location],
    derivation: DerivationResult,
) -> tuple[DerivationResult, LlmDerivationSuggestion | None]:
    suggestion = await _llm_refine_business_catalog(
        session,
        business=business,
        taxonomy=taxonomy,
        business_place_metadata=business_place_metadata,
        locations=locations,
        deterministic=derivation,
    )
    if suggestion is None:
        return derivation, None

    if suggestion.confidence is not None and suggestion.confidence < 0.7:
        return derivation, suggestion

    classification = derivation.classification
    if suggestion.vertical is not None:
        classification = DerivedClassification(
            vertical=suggestion.vertical,
            subvertical=suggestion.subvertical,
            confidence=round(max(classification.confidence, suggestion.confidence or classification.confidence), 3),
            reason_codes=sorted(
                set(classification.reason_codes)
                | {"llm.vertical_refinement"}
                | ({f"llm.vertical.{suggestion.vertical}"} if suggestion.vertical else set())
            ),
        )

    roles = list(derivation.roles)
    for role_key in suggestion.role_keys:
        definition = taxonomy.business_role_archetypes.get(role_key)
        if definition is None:
            continue
        roles.append(
            DerivedRole(
                role_key=role_key,
                display_name=definition.display_name,
                role_family=definition.role_family,
                confidence=round(max(0.72, suggestion.confidence or 0.72), 3),
                derivation_type="llm_modifier",
                reason_codes=["llm.additional_role", *(["llm.vertical_refinement"] if suggestion.vertical else [])],
                support_location_ids=[],
            )
        )

    deduped_roles: dict[str, DerivedRole] = {}
    for role in roles:
        existing = deduped_roles.get(role.role_key)
        if existing is None or role.confidence > existing.confidence:
            deduped_roles[role.role_key] = role

    refined = DerivationResult(
        classification=classification,
        roles=sorted(deduped_roles.values(), key=lambda item: (-item.confidence, item.display_name)),
    )
    return refined, suggestion


async def sync_business_role_catalog(
    session: AsyncSession,
    business: Business,
    *,
    locations: Sequence[Location] | None = None,
) -> DerivationResult:
    from app.services import business_classification

    return await business_classification.sync_business_classification(
        session,
        business,
        locations=locations,
    )
