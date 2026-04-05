from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business, Location, Role
from app.services.utils import role_code_from_name

DERIVATION_VERSION = "places_rules_v1"


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
class _RoleDefinition:
    display_name: str
    role_family: str


_VERTICAL_TOKEN_RULES: dict[str, tuple[str, str | None]] = {
    "restaurant": ("restaurant", "full_service_restaurant"),
    "meal_takeaway": ("restaurant", "takeout_restaurant"),
    "meal_delivery": ("restaurant", "delivery_restaurant"),
    "cafe": ("cafe", "cafe"),
    "coffee_shop": ("cafe", "coffee_shop"),
    "bakery": ("bakery", "bakery"),
    "bar": ("bar", "bar"),
    "pub": ("bar", "pub"),
    "wine_bar": ("bar", "wine_bar"),
    "night_club": ("bar", "nightlife"),
    "grocery_store": ("retail", "grocery"),
    "supermarket": ("retail", "grocery"),
    "convenience_store": ("retail", "convenience"),
    "store": ("retail", None),
    "department_store": ("retail", "department_store"),
    "shopping_mall": ("retail", "shopping_center"),
    "clothing_store": ("retail", "apparel"),
    "shoe_store": ("retail", "apparel"),
    "book_store": ("retail", "specialty_retail"),
    "hair_salon": ("beauty", "hair_salon"),
    "beauty_salon": ("beauty", "beauty_salon"),
    "barber_shop": ("beauty", "barber_shop"),
    "nail_salon": ("beauty", "nail_salon"),
    "spa": ("beauty", "spa"),
    "gym": ("fitness", "gym"),
    "fitness_center": ("fitness", "fitness_center"),
    "yoga_studio": ("fitness", "yoga_studio"),
    "pilates_studio": ("fitness", "pilates_studio"),
    "dentist": ("dental_clinic", "dentistry"),
    "orthodontist": ("dental_clinic", "orthodontics"),
    "doctor": ("medical_clinic", "doctor_office"),
    "hospital": ("medical_clinic", "hospital"),
    "medical_lab": ("medical_clinic", "medical_lab"),
    "urgent_care_center": ("medical_clinic", "urgent_care"),
    "pharmacy": ("medical_clinic", "pharmacy"),
    "electrician": ("home_services", "electrical"),
    "plumber": ("home_services", "plumbing"),
    "roofing_contractor": ("home_services", "roofing"),
    "hvac_contractor": ("home_services", "hvac"),
    "general_contractor": ("home_services", "contracting"),
    "locksmith": ("home_services", "locksmith"),
    "moving_company": ("home_services", "moving"),
    "painter": ("home_services", "painting"),
    "warehouse": ("warehouse", "warehouse"),
    "storage": ("warehouse", "storage"),
    "self_storage": ("warehouse", "storage"),
    "lodging": ("hotel", "lodging"),
    "hotel": ("hotel", "hotel"),
    "motel": ("hotel", "motel"),
    "resort_hotel": ("hotel", "resort"),
    "lawyer": ("professional_office", "legal"),
    "accounting": ("professional_office", "accounting"),
    "insurance_agency": ("professional_office", "insurance"),
    "real_estate_agency": ("professional_office", "real_estate"),
    "bank": ("professional_office", "finance"),
    "corporate_office": ("professional_office", "office"),
}

_BASE_ROLE_PACKS: dict[str, tuple[str, ...]] = {
    "restaurant": (
        "general_manager",
        "assistant_manager",
        "shift_lead",
        "server",
        "host",
        "line_cook",
        "dishwasher",
    ),
    "cafe": (
        "general_manager",
        "shift_lead",
        "barista",
        "cashier",
        "prep_kitchen",
    ),
    "bakery": (
        "general_manager",
        "shift_lead",
        "baker",
        "cashier",
        "prep_kitchen",
    ),
    "bar": (
        "general_manager",
        "assistant_manager",
        "shift_lead",
        "bartender",
        "barback",
        "host",
    ),
    "retail": (
        "store_manager",
        "assistant_manager",
        "shift_lead",
        "sales_associate",
        "cashier",
        "stock_associate",
    ),
    "beauty": (
        "location_manager",
        "receptionist",
        "stylist",
        "assistant",
    ),
    "fitness": (
        "general_manager",
        "shift_lead",
        "front_desk_associate",
        "coach_trainer",
    ),
    "medical_clinic": (
        "practice_manager",
        "receptionist",
        "medical_assistant",
    ),
    "dental_clinic": (
        "practice_manager",
        "receptionist",
        "dental_assistant",
        "dental_hygienist",
    ),
    "home_services": (
        "operations_manager",
        "dispatcher",
        "field_technician",
        "estimator",
        "customer_support",
    ),
    "warehouse": (
        "site_manager",
        "shift_supervisor",
        "picker_packer",
        "inventory_associate",
        "receiving_clerk",
    ),
    "hotel": (
        "general_manager",
        "front_desk_associate",
        "housekeeper",
        "maintenance_technician",
        "night_auditor",
    ),
    "professional_office": (
        "office_manager",
        "receptionist",
        "coordinator",
    ),
    "mixed_unknown": ("general_manager",),
}

_ROLE_DEFINITIONS: dict[str, _RoleDefinition] = {
    "general_manager": _RoleDefinition("General Manager", "management"),
    "assistant_manager": _RoleDefinition("Assistant Manager", "management"),
    "shift_lead": _RoleDefinition("Shift Lead", "operations"),
    "server": _RoleDefinition("Server", "front_of_house"),
    "host": _RoleDefinition("Host", "front_of_house"),
    "line_cook": _RoleDefinition("Line Cook", "back_of_house"),
    "dishwasher": _RoleDefinition("Dishwasher", "back_of_house"),
    "bartender": _RoleDefinition("Bartender", "front_of_house"),
    "barback": _RoleDefinition("Barback", "front_of_house"),
    "barista": _RoleDefinition("Barista", "front_of_house"),
    "cashier": _RoleDefinition("Cashier", "front_of_house"),
    "prep_kitchen": _RoleDefinition("Prep Kitchen", "back_of_house"),
    "baker": _RoleDefinition("Baker", "back_of_house"),
    "store_manager": _RoleDefinition("Store Manager", "management"),
    "sales_associate": _RoleDefinition("Sales Associate", "sales"),
    "stock_associate": _RoleDefinition("Stock Associate", "inventory"),
    "pickup_associate": _RoleDefinition("Pickup Associate", "front_of_house"),
    "inventory_lead": _RoleDefinition("Inventory Lead", "inventory"),
    "location_manager": _RoleDefinition("Location Manager", "management"),
    "receptionist": _RoleDefinition("Receptionist", "front_desk"),
    "stylist": _RoleDefinition("Stylist", "service"),
    "assistant": _RoleDefinition("Assistant", "service"),
    "esthetician": _RoleDefinition("Esthetician", "service"),
    "nail_technician": _RoleDefinition("Nail Technician", "service"),
    "coach_trainer": _RoleDefinition("Coach / Trainer", "service"),
    "front_desk_associate": _RoleDefinition("Front Desk Associate", "front_desk"),
    "practice_manager": _RoleDefinition("Practice Manager", "management"),
    "medical_assistant": _RoleDefinition("Medical Assistant", "clinical"),
    "dental_assistant": _RoleDefinition("Dental Assistant", "clinical"),
    "dental_hygienist": _RoleDefinition("Dental Hygienist", "clinical"),
    "operations_manager": _RoleDefinition("Operations Manager", "management"),
    "dispatcher": _RoleDefinition("Dispatcher", "operations"),
    "field_technician": _RoleDefinition("Field Technician", "field"),
    "installer": _RoleDefinition("Installer", "field"),
    "estimator": _RoleDefinition("Estimator", "operations"),
    "customer_support": _RoleDefinition("Customer Support", "support"),
    "site_manager": _RoleDefinition("Site Manager", "management"),
    "shift_supervisor": _RoleDefinition("Shift Supervisor", "operations"),
    "picker_packer": _RoleDefinition("Picker / Packer", "warehouse"),
    "inventory_associate": _RoleDefinition("Inventory Associate", "warehouse"),
    "receiving_clerk": _RoleDefinition("Receiving Clerk", "warehouse"),
    "forklift_operator": _RoleDefinition("Forklift Operator", "warehouse"),
    "housekeeper": _RoleDefinition("Housekeeper", "operations"),
    "maintenance_technician": _RoleDefinition("Maintenance Technician", "operations"),
    "night_auditor": _RoleDefinition("Night Auditor", "operations"),
    "office_manager": _RoleDefinition("Office Manager", "management"),
    "coordinator": _RoleDefinition("Coordinator", "operations"),
    "delivery_coordinator": _RoleDefinition("Delivery Coordinator", "operations"),
    "expeditor": _RoleDefinition("Expeditor", "operations"),
    "food_runner": _RoleDefinition("Food Runner", "front_of_house"),
    "expo": _RoleDefinition("Expo", "back_of_house"),
}


def _as_text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


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


def _classify_source(source: _SourceContext) -> DerivedClassification:
    scores: dict[str, float] = {}
    subvertical_scores: dict[str, float] = {}
    reason_codes: dict[str, set[str]] = {}

    def apply_token(token: str, *, weight: float, origin: str) -> None:
        match = _VERTICAL_TOKEN_RULES.get(token)
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


def _derive_source_roles(source: _SourceContext) -> tuple[DerivedClassification, list[tuple[str, str, list[str]]]]:
    classification = _classify_source(source)
    tokens = set(source.types)
    if source.primary_type is not None:
        tokens.add(source.primary_type)
    flags = _opening_hours_flags(source.regular_opening_hours)
    base_roles = list(_BASE_ROLE_PACKS.get(classification.vertical, _BASE_ROLE_PACKS["mixed_unknown"]))
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


def derive_business_catalog(*, business_place_metadata: dict | None, locations: Sequence[Location]) -> DerivationResult:
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
        classification, role_entries = _derive_source_roles(source)
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
        definition = _ROLE_DEFINITIONS.get(role_key)
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


async def sync_business_role_catalog(
    session: AsyncSession,
    business: Business,
    *,
    locations: Sequence[Location] | None = None,
) -> DerivationResult:
    if locations is None:
        result = await session.execute(select(Location).where(Location.business_id == business.id))
        locations = list(result.scalars().all())

    derivation = derive_business_catalog(
        business_place_metadata=business.place_metadata,
        locations=locations,
    )

    settings = dict(business.settings or {})
    settings["derived_classification"] = {
        "vertical": derivation.classification.vertical,
        "subvertical": derivation.classification.subvertical,
        "confidence": derivation.classification.confidence,
        "reason_codes": derivation.classification.reason_codes,
        "location_count": len([location for location in locations if location.google_place_metadata]),
        "derivation_version": DERIVATION_VERSION,
    }
    vertical_source = settings.get("vertical_source")
    if vertical_source != "manual":
        business.vertical = derivation.classification.vertical
        settings["vertical_source"] = "derived"
    business.settings = settings

    existing_rows = await session.execute(select(Role).where(Role.business_id == business.id))
    existing_roles = {role.code: role for role in existing_rows.scalars().all()}

    for derived_role in derivation.roles:
        metadata_payload = {
            "source": "places_role_derivation",
            "version": DERIVATION_VERSION,
            "confidence": derived_role.confidence,
            "role_family": derived_role.role_family,
            "derivation_type": derived_role.derivation_type,
            "reason_codes": derived_role.reason_codes,
            "support_location_ids": [str(location_id) for location_id in derived_role.support_location_ids],
            "support_location_count": len(derived_role.support_location_ids),
        }
        existing = existing_roles.get(derived_role.role_key)
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
    return derivation
