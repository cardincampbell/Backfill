from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business, Location

DERIVATION_VERSION = "business_identity_places_v1"
_GENERIC_BASE_NAMES = {"location", "store", "shop", "office", "branch"}
_PROTECTED_BASE_NAMES = {
    "boston market",
    "kansas city bbq",
    "new york pizza",
    "california pizza kitchen",
}
_ADDRESS_COMPONENT_TYPES = (
    "locality",
    "postal_town",
    "neighborhood",
    "sublocality",
    "sublocality_level_1",
    "sublocality_level_2",
    "administrative_area_level_3",
)
_SEPARATOR_PATTERN = r"[-\u2013\u2014|:@\u00b7]"


@dataclass(frozen=True)
class LocationIdentity:
    location_id: UUID
    raw_place_name: str | None
    canonical_business_name: str
    location_label: str | None
    confidence: float
    derivation_method: str
    reason_codes: list[str]
    evidence: dict[str, object]
    suggested_location_name: str


@dataclass(frozen=True)
class BusinessIdentityResult:
    canonical_business_name: str
    confidence: float
    derivation_method: str
    reason_codes: list[str]
    support_location_count: int
    evidence: dict[str, object]
    locations: list[LocationIdentity]


@dataclass(frozen=True)
class _CandidateSuffix:
    base_name: str
    suffix: str
    method: str
    reason_codes: list[str]


def _as_text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _normalize_match_text(value: str | None) -> str:
    if value is None:
        return ""
    lowered = value.strip().lower()
    normalized = re.sub(r"[^\w\s]", " ", lowered)
    return " ".join(normalized.split())


def _candidate_location_tokens(location: Location) -> list[str]:
    metadata = location.google_place_metadata or {}
    address_components = metadata.get("address_components") if isinstance(metadata.get("address_components"), list) else []

    ordered: list[str | None] = [
        _as_text(metadata.get("location_label")),
        _as_text(metadata.get("neighborhood")),
        _as_text(metadata.get("sublocality")),
        _as_text(metadata.get("city")),
        _as_text(location.locality),
    ]
    for component in address_components:
        if not isinstance(component, dict):
            continue
        component_types = component.get("types") if isinstance(component.get("types"), list) else []
        if not any(component_type in _ADDRESS_COMPONENT_TYPES for component_type in component_types):
            continue
        ordered.append(_as_text(component.get("longText")))
        ordered.append(_as_text(component.get("shortText")))

    seen: set[str] = set()
    tokens: list[str] = []
    for token in ordered:
        normalized = _normalize_match_text(token)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(token.strip())  # type: ignore[union-attr]
    tokens.sort(key=lambda value: (-len(_normalize_match_text(value)), value.lower()))
    return tokens


def _meaningful_base_name(base_name: str) -> bool:
    normalized = _normalize_match_text(base_name)
    if len(normalized) < 3:
        return False
    words = normalized.split()
    if len(words) < 2:
        return False
    if normalized in _GENERIC_BASE_NAMES:
        return False
    return True


def _protected_base_name(base_name: str) -> bool:
    return _normalize_match_text(base_name) in _PROTECTED_BASE_NAMES


def _strip_trailing_locality(raw_place_name: str | None, location_tokens: Sequence[str]) -> _CandidateSuffix | None:
    raw_name = _as_text(raw_place_name)
    if raw_name is None:
        return None

    for token in location_tokens:
        token_text = _as_text(token)
        if token_text is None:
            continue
        escaped_token = re.escape(token_text)
        patterns = (
            (
                re.compile(rf"^(?P<base>.+?)\s*[\(\[]\s*{escaped_token}\s*[\)\]]\s*$", re.IGNORECASE),
                "single_location_parenthetical_suffix_match",
                ["suffix.parenthetical", "suffix.exact_locality_match"],
            ),
            (
                re.compile(rf"^(?P<base>.+?)\s*(?:{_SEPARATOR_PATTERN})\s*{escaped_token}\s*$", re.IGNORECASE),
                "single_location_separator_suffix_match",
                ["suffix.separator", "suffix.exact_locality_match"],
            ),
            (
                re.compile(rf"^(?P<base>.+?)\s+{escaped_token}\s*$", re.IGNORECASE),
                "single_location_terminal_suffix_match",
                ["suffix.trailing_token", "suffix.exact_locality_match"],
            ),
        )
        for pattern, method, reason_codes in patterns:
            match = pattern.match(raw_name)
            if match is None:
                continue
            base_name = (match.group("base") or "").strip(" -–—|:·@()[]")
            if not base_name:
                continue
            return _CandidateSuffix(
                base_name=base_name,
                suffix=token_text,
                method=method,
                reason_codes=list(reason_codes),
            )
    return None


def _raw_place_name(location: Location) -> str | None:
    metadata = location.google_place_metadata or {}
    return (
        _as_text(metadata.get("display_name"))
        or _as_text(metadata.get("name"))
        or _as_text(location.name)
    )


def _fallback_business_name(business: Business, locations: Sequence[Location]) -> str:
    for candidate in (
        _as_text(business.brand_name),
        _as_text((business.place_metadata or {}).get("name")),
        _as_text((business.place_metadata or {}).get("brand_name")),
    ):
        if candidate is not None:
            return candidate
    for location in locations:
        candidate = _raw_place_name(location)
        if candidate is not None:
            return candidate
    return business.legal_name.strip()


def _suggested_location_name(canonical_business_name: str, raw_place_name: str | None, location_label: str | None) -> str:
    if location_label:
        raw_normalized = _normalize_match_text(raw_place_name)
        canonical_normalized = _normalize_match_text(canonical_business_name)
        if raw_normalized and raw_normalized == canonical_normalized:
            return raw_place_name or f"{canonical_business_name} · {location_label}"
        return f"{canonical_business_name} · {location_label}"
    return raw_place_name or canonical_business_name


def derive_business_identity(business: Business, *, locations: Sequence[Location]) -> BusinessIdentityResult:
    fallback_business_name = _fallback_business_name(business, locations)
    candidate_rows: list[dict[str, object]] = []

    for location in locations:
        raw_place_name = _raw_place_name(location)
        location_tokens = _candidate_location_tokens(location)
        candidate = _strip_trailing_locality(raw_place_name, location_tokens)
        candidate_rows.append(
            {
                "location": location,
                "raw_place_name": raw_place_name,
                "tokens": location_tokens,
                "candidate": candidate,
            }
        )

    grouped_candidates: dict[str, list[dict[str, object]]] = {}
    for row in candidate_rows:
        candidate = row["candidate"]
        if not isinstance(candidate, _CandidateSuffix):
            continue
        if not _meaningful_base_name(candidate.base_name):
            continue
        if _protected_base_name(candidate.base_name):
            continue
        grouped_candidates.setdefault(_normalize_match_text(candidate.base_name), []).append(row)

    sibling_choice: tuple[str, list[dict[str, object]]] | None = None
    for normalized_base, rows in grouped_candidates.items():
        distinct_labels = {
            _normalize_match_text(row["candidate"].suffix)  # type: ignore[union-attr]
            for row in rows
            if isinstance(row["candidate"], _CandidateSuffix)
        }
        if len(rows) < 2 or len(distinct_labels) < 2:
            continue
        if sibling_choice is None or len(rows) > len(sibling_choice[1]):
            sibling_choice = (normalized_base, rows)

    if sibling_choice is not None:
        _, supported_rows = sibling_choice
        chosen_candidate = supported_rows[0]["candidate"]
        assert isinstance(chosen_candidate, _CandidateSuffix)
        canonical_business_name = chosen_candidate.base_name
        support_location_count = len(supported_rows)
        business_method = "multi_location_locality_suffix_match"
        business_reason_codes = [
            "sibling_confirmation",
            "suffix.exact_locality_match",
            "suffix.trailing_match",
        ]
        confidence = round(min(0.98, 0.9 + max(0, support_location_count - 2) * 0.02), 3)
        evidence = {
            "matched_location_ids": [str(row["location"].id) for row in supported_rows],
            "matched_suffixes": sorted(
                {
                    row["candidate"].suffix  # type: ignore[union-attr]
                    for row in supported_rows
                    if isinstance(row["candidate"], _CandidateSuffix)
                }
            ),
            "candidate_bases": sorted(
                {
                    row["candidate"].base_name  # type: ignore[union-attr]
                    for row in supported_rows
                    if isinstance(row["candidate"], _CandidateSuffix)
                }
            ),
        }
    else:
        single_candidate: _CandidateSuffix | None = None
        for row in candidate_rows:
            candidate = row["candidate"]
            if not isinstance(candidate, _CandidateSuffix):
                continue
            if not _meaningful_base_name(candidate.base_name):
                continue
            if _protected_base_name(candidate.base_name):
                continue
            single_candidate = candidate
            break

        if single_candidate is not None:
            canonical_business_name = single_candidate.base_name
            support_location_count = 1
            business_method = single_candidate.method
            business_reason_codes = list(single_candidate.reason_codes)
            business_reason_codes.append("single_location_fallback")
            confidence = 0.76
            evidence = {
                "matched_location_ids": [
                    str(row["location"].id)
                    for row in candidate_rows
                    if row["candidate"] is single_candidate
                ],
                "matched_suffixes": [single_candidate.suffix],
                "candidate_bases": [single_candidate.base_name],
            }
        else:
            canonical_business_name = fallback_business_name
            support_location_count = 0
            business_method = "raw_place_name_fallback"
            business_reason_codes = ["confidence_below_threshold", "raw_place_name_fallback"]
            confidence = 0.2
            evidence = {
                "matched_location_ids": [],
                "matched_suffixes": [],
                "candidate_bases": [],
            }

    business_locations: list[LocationIdentity] = []
    for row in candidate_rows:
        location = row["location"]
        assert isinstance(location, Location)
        raw_place_name = row["raw_place_name"] if isinstance(row["raw_place_name"], str) else _raw_place_name(location)
        candidate = row["candidate"]
        location_tokens = row["tokens"] if isinstance(row["tokens"], list) else []

        location_label: str | None = None
        derivation_method = business_method
        reason_codes = list(business_reason_codes)
        confidence_score = confidence

        if isinstance(candidate, _CandidateSuffix) and _normalize_match_text(candidate.base_name) == _normalize_match_text(canonical_business_name):
            location_label = candidate.suffix
            derivation_method = (
                "multi_location_locality_suffix_match"
                if support_location_count >= 2
                else candidate.method
            )
            reason_codes = sorted(set(reason_codes + candidate.reason_codes))
        elif location_tokens:
            location_label = location_tokens[0]
            reason_codes = sorted(set(reason_codes + ["location.context_label"]))
            confidence_score = round(min(confidence_score, 0.65), 3)

        suggested_location_name = _suggested_location_name(canonical_business_name, raw_place_name, location_label)
        business_locations.append(
            LocationIdentity(
                location_id=location.id,
                raw_place_name=raw_place_name,
                canonical_business_name=canonical_business_name,
                location_label=location_label,
                confidence=round(confidence_score, 3),
                derivation_method=derivation_method,
                reason_codes=reason_codes,
                evidence={
                    "candidate_suffix": candidate.suffix if isinstance(candidate, _CandidateSuffix) else None,
                    "address_tokens": list(location_tokens),
                },
                suggested_location_name=suggested_location_name,
            )
        )

    return BusinessIdentityResult(
        canonical_business_name=canonical_business_name,
        confidence=round(confidence, 3),
        derivation_method=business_method,
        reason_codes=business_reason_codes,
        support_location_count=support_location_count,
        evidence=evidence,
        locations=business_locations,
    )


async def sync_business_identity(
    session: AsyncSession,
    business: Business,
    *,
    locations: Sequence[Location] | None = None,
) -> BusinessIdentityResult:
    if locations is None:
        result = await session.execute(select(Location).where(Location.business_id == business.id))
        locations = list(result.scalars().all())

    derivation = derive_business_identity(business, locations=locations)

    business_settings = dict(business.settings or {})
    manual_override_active = business_settings.get("brand_name_source") == "manual"
    business_settings["derived_identity"] = {
        "raw_place_name": _as_text((business.place_metadata or {}).get("name")),
        "canonical_business_name": derivation.canonical_business_name,
        "name_derivation_confidence": derivation.confidence,
        "name_derivation_method": derivation.derivation_method,
        "derivation_version": DERIVATION_VERSION,
        "reason_codes": derivation.reason_codes,
        "support_location_count": derivation.support_location_count,
        "manual_override_active": manual_override_active,
        "evidence": derivation.evidence,
    }
    if not manual_override_active:
        business.brand_name = derivation.canonical_business_name
        business_settings["brand_name_source"] = "derived"
    business.settings = business_settings

    locations_by_id = {identity.location_id: identity for identity in derivation.locations}
    for location in locations:
        identity = locations_by_id.get(location.id)
        if identity is None:
            continue
        location_settings = dict(location.settings or {})
        location_settings["derived_identity"] = {
            "raw_place_name": identity.raw_place_name,
            "canonical_business_name": identity.canonical_business_name,
            "location_label": identity.location_label,
            "name_derivation_confidence": identity.confidence,
            "name_derivation_method": identity.derivation_method,
            "derivation_version": DERIVATION_VERSION,
            "reason_codes": identity.reason_codes,
            "suggested_location_name": identity.suggested_location_name,
            "evidence": identity.evidence,
        }
        location.settings = location_settings

    await session.flush()
    return derivation
