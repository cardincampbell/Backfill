from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business, Location, LocationRole, Role
from app.models.common import ShiftLifecycleStatus
from app.models.role_taxonomy import BusinessPlaceType
from app.models.scheduling import Shift
from app.schemas.business import (
    BusinessCreate,
    BusinessProfileUpdate,
    LocationCreate,
    LocationRoleAttach,
    LocationRoleCreateAndAssign,
    LocationRoleReplace,
    RoleCreate,
)
from app.services import (
    business_classification,
    business_identity_derivation,
    labor_rule_resolution,
    role_derivation,
    role_normalization,
    shift_defaults,
)
from app.services.utils import role_code_from_name, slugify


@dataclass(frozen=True)
class RoleCreateResult:
    role: Role
    decision: str
    normalized_name: str
    confidence: float | None = None
    reason: str | None = None

async def _next_unique_business_slug(session: AsyncSession, requested: str) -> str:
    base = slugify(requested)
    slug = base
    suffix = 2
    while await session.scalar(select(Business.id).where(Business.slug == slug)) is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


async def _next_unique_location_slug(session: AsyncSession, business_id: UUID, requested: str) -> str:
    base = slugify(requested)
    slug = base
    suffix = 2
    while (
        await session.scalar(
            select(Location.id).where(Location.business_id == business_id, Location.slug == slug)
        )
        is not None
    ):
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


async def _next_unique_role_code(session: AsyncSession, business_id: UUID, requested: str) -> str:
    base = role_code_from_name(requested)
    code = base
    suffix = 2
    while (
        await session.scalar(select(Role.id).where(Role.business_id == business_id, Role.code == code))
        is not None
    ):
        code = f"{base}_{suffix}"
        suffix += 1
    return code


def _normalize_location_identity_value(value: str | None) -> str | None:
    normalized = _normalize_optional(value)
    return normalized.lower() if normalized else None


def _location_identity_key_from_payload(payload: LocationCreate) -> tuple[str, str] | None:
    place_id = _normalize_optional(payload.google_place_id)
    if place_id:
        return ("google_place_id", place_id)

    address_parts = [
        _normalize_location_identity_value(payload.address_line_1),
        _normalize_location_identity_value(payload.locality),
        _normalize_location_identity_value(payload.region),
        _normalize_location_identity_value(payload.postal_code),
        _normalize_location_identity_value(payload.country_code or "US"),
    ]
    if address_parts[0] and address_parts[1] and address_parts[2]:
        return ("normalized_address", "|".join(part or "" for part in address_parts))
    return None


def _location_identity_key_from_record(location: Location) -> tuple[str, str] | None:
    place_id = _normalize_optional(location.google_place_id)
    if place_id:
        return ("google_place_id", place_id)

    address_parts = [
        _normalize_location_identity_value(location.address_line_1),
        _normalize_location_identity_value(location.locality),
        _normalize_location_identity_value(location.region),
        _normalize_location_identity_value(location.postal_code),
        _normalize_location_identity_value(location.country_code or "US"),
    ]
    if address_parts[0] and address_parts[1] and address_parts[2]:
        return ("normalized_address", "|".join(part or "" for part in address_parts))
    return None


async def _find_duplicate_location(
    session: AsyncSession,
    business_id: UUID,
    payload: LocationCreate,
) -> Location | None:
    requested_key = _location_identity_key_from_payload(payload)
    if requested_key is None:
        return None

    result = await session.execute(
        select(Location).where(Location.business_id == business_id)
    )
    for location in result.scalars().all():
        if _location_identity_key_from_record(location) == requested_key:
            return location
    return None


async def _find_existing_business_role(
    session: AsyncSession,
    business_id: UUID,
    *,
    name: str,
    code: str | None = None,
) -> Role | None:
    normalized_name = name.strip()
    normalized_code = role_code_from_name(code or normalized_name)

    existing_by_code = await session.scalar(
        select(Role).where(Role.business_id == business_id, Role.code == normalized_code)
    )
    if existing_by_code is not None:
        return existing_by_code

    return await session.scalar(
        select(Role).where(
            Role.business_id == business_id,
            func.lower(Role.name) == normalized_name.lower(),
        )
    )


def _initial_business_display_name(payload: BusinessCreate) -> str:
    return (
        _normalize_optional(payload.display_name)
        or _normalize_optional((payload.place_metadata or {}).get("brand_name"))
        or payload.name.strip()
    )


def _initial_location_display_name(payload: LocationCreate) -> str:
    return (
        _normalize_optional(payload.display_name)
        or _normalize_optional((payload.google_place_metadata or {}).get("location_label"))
        or payload.name.strip()
    )


def _extract_business_place_types(metadata: dict | None) -> list[tuple[str, bool]]:
    payload = metadata or {}
    primary_type = _normalize_optional(str(payload.get("primary_type") or "").lower() or None)
    ordered: list[tuple[str, bool]] = []
    seen: set[str] = set()

    if primary_type:
        ordered.append((primary_type, True))
        seen.add(primary_type)

    for value in payload.get("types") or []:
        if not isinstance(value, str):
            continue
        normalized = _normalize_optional(value.lower())
        if not normalized or normalized in seen:
            continue
        ordered.append((normalized, False))
        seen.add(normalized)

    return ordered


def _add_business_place_type_rows(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    metadata: dict | None,
) -> None:
    for place_type, is_primary in _extract_business_place_types(metadata):
        session.add(
            BusinessPlaceType(
                business_id=business_id,
                location_id=location_id,
                source_provider="google_places",
                place_type=place_type,
                is_primary=is_primary,
                metadata_json={},
            )
        )


def _merge_role_metadata(
    existing: dict | None,
    *,
    source: str,
    source_metadata: dict | None = None,
) -> dict:
    metadata = dict(existing or {})
    sources = [item for item in metadata.get("sources", []) if isinstance(item, str) and item.strip()]
    if source not in sources:
        sources.append(source)
    metadata["sources"] = sorted(set(sources))
    metadata["last_source"] = source

    source_details = dict(metadata.get("source_details") or {})
    current_source_payload = dict(source_details.get(source) or {})
    if source_metadata:
        current_source_payload.update(source_metadata)
    source_details[source] = current_source_payload
    metadata["source_details"] = source_details
    return metadata


async def list_businesses(session: AsyncSession, business_ids: Optional[Sequence[UUID]] = None) -> list[Business]:
    stmt = select(Business).order_by(Business.created_at.desc())
    if business_ids is not None:
        if not business_ids:
            return []
        stmt = stmt.where(Business.id.in_(business_ids))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_business(session: AsyncSession, business_id: UUID) -> Optional[Business]:
    return await session.get(Business, business_id)


async def create_business_record(
    session: AsyncSession,
    payload: BusinessCreate,
    *,
    derive_identity: bool = True,
    derive_roles: bool = True,
) -> Business:
    business_name = payload.name.strip()
    business_display_name = _initial_business_display_name(payload)
    requested_name = business_display_name or business_name
    slug = await _next_unique_business_slug(session, payload.slug or requested_name)
    settings = dict(payload.settings or {})
    if not settings.get("display_name_source") and not payload.place_metadata:
        settings["display_name_source"] = "manual"
    business = Business(
        name=business_name,
        display_name=business_display_name,
        slug=slug,
        vertical=payload.vertical,
        primary_phone_e164=payload.primary_phone_e164,
        primary_email=payload.primary_email,
        timezone=payload.timezone,
        settings=settings,
        place_metadata=payload.place_metadata,
    )
    session.add(business)
    await session.flush()
    _add_business_place_type_rows(
        session,
        business_id=business.id,
        location_id=None,
        metadata=payload.place_metadata,
    )
    if derive_identity:
        await business_identity_derivation.sync_business_identity(session, business, locations=[])
    if derive_roles:
        await business_classification.sync_business_classification(session, business, locations=[])
    return business


async def create_business(session: AsyncSession, payload: BusinessCreate) -> Business:
    business = await create_business_record(session, payload)
    await session.refresh(business)
    return business


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


async def update_business_profile(
    session: AsyncSession,
    business: Business,
    payload: BusinessProfileUpdate,
    *,
    actor_user_id: UUID | None = None,
) -> dict[str, object]:
    display_name = payload.display_name.strip()
    timezone_name = payload.timezone.strip()
    if not display_name:
        raise ValueError("business_name_required")
    if not timezone_name:
        raise ValueError("timezone_required")

    vertical = _normalize_optional(payload.vertical)
    primary_email = _normalize_optional(payload.primary_email)
    if primary_email is not None:
        primary_email = primary_email.lower()
    company_address = _normalize_optional(payload.company_address)
    week_start_day = payload.week_start_day
    coverage_field_map = {
        "same_day_second_shift_allowed": payload.same_day_second_shift_allowed,
        "same_location_overlap_minutes": payload.same_location_overlap_minutes,
        "cross_location_shift_coverage_allowed": payload.cross_location_shift_coverage_allowed,
        "cross_location_min_gap_minutes": payload.cross_location_min_gap_minutes,
        "cross_location_max_radius_miles": payload.cross_location_max_radius_miles,
    }
    auto_scheduler_field_map = {
        "labor_rule_mode": payload.auto_scheduler_labor_rule_mode,
        "fairness_mode": payload.auto_scheduler_fairness_mode,
    }
    reliability_coaching_field_map = {
        "style": payload.reliability_coaching_style,
    }

    changes: dict[str, object] = {}
    if business.display_name != display_name:
        business.display_name = display_name
        changes["display_name"] = display_name
    current_settings = dict(business.settings or {})
    settings = dict(current_settings)
    settings["display_name_source"] = "manual"
    settings.pop("brand_name_source", None)

    if business.vertical != vertical:
        business.vertical = vertical
        changes["vertical"] = vertical
        if vertical is None:
            settings.pop("vertical_source", None)
        else:
            settings["vertical_source"] = "manual"
    if business.primary_email != primary_email:
        business.primary_email = primary_email
        changes["primary_email"] = primary_email
    if business.timezone != timezone_name:
        business.timezone = timezone_name
        changes["timezone"] = timezone_name

    current_company_address = _normalize_optional(settings.get("company_profile_address"))
    if current_company_address != company_address:
        if company_address is None:
            settings.pop("company_profile_address", None)
        else:
            settings["company_profile_address"] = company_address
        changes["company_address"] = company_address

    current_week_start_day = _normalize_optional(settings.get("week_start_day"))
    if current_week_start_day != week_start_day:
        if week_start_day is None:
            settings.pop("week_start_day", None)
        else:
            settings["week_start_day"] = week_start_day
        changes["week_start_day"] = week_start_day

    current_coverage_settings = settings.get("coverage")
    coverage_settings = (
        dict(current_coverage_settings)
        if isinstance(current_coverage_settings, dict)
        else {}
    )
    coverage_changed = False
    for key, value in coverage_field_map.items():
        if key not in payload.model_fields_set:
            continue
        current_value = coverage_settings.get(key)
        if value is None:
            if key in coverage_settings:
                coverage_settings.pop(key, None)
                coverage_changed = True
                changes[key] = None
            continue
        if current_value != value:
            coverage_settings[key] = value
            coverage_changed = True
            changes[key] = value

    if coverage_changed:
        if coverage_settings:
            settings["coverage"] = coverage_settings
        else:
            settings.pop("coverage", None)

    current_auto_scheduler_settings = settings.get("auto_scheduler")
    auto_scheduler_settings = (
        dict(current_auto_scheduler_settings)
        if isinstance(current_auto_scheduler_settings, dict)
        else {}
    )
    auto_scheduler_changed = False
    for key, value in auto_scheduler_field_map.items():
        field_name = f"auto_scheduler_{key}"
        if field_name not in payload.model_fields_set:
            continue
        current_value = auto_scheduler_settings.get(key)
        if value is None:
            if key in auto_scheduler_settings:
                auto_scheduler_settings.pop(key, None)
                auto_scheduler_changed = True
                changes[field_name] = None
            continue
        if current_value != value:
            auto_scheduler_settings[key] = value
            auto_scheduler_changed = True
            changes[field_name] = value

    if auto_scheduler_changed:
        if auto_scheduler_settings:
            settings["auto_scheduler"] = auto_scheduler_settings
        else:
            settings.pop("auto_scheduler", None)

    current_reliability_coaching_settings = settings.get("reliability_coaching")
    reliability_coaching_settings = (
        dict(current_reliability_coaching_settings)
        if isinstance(current_reliability_coaching_settings, dict)
        else {}
    )
    reliability_coaching_changed = False
    for key, value in reliability_coaching_field_map.items():
        field_name = f"reliability_coaching_{key}"
        if field_name not in payload.model_fields_set:
            continue
        current_value = reliability_coaching_settings.get(key)
        if value is None:
            if key in reliability_coaching_settings:
                reliability_coaching_settings.pop(key, None)
                reliability_coaching_changed = True
                changes[field_name] = None
            continue
        if current_value != value:
            reliability_coaching_settings[key] = value
            reliability_coaching_changed = True
            changes[field_name] = value

    if reliability_coaching_changed:
        if reliability_coaching_settings:
            settings["reliability_coaching"] = reliability_coaching_settings
        else:
            settings.pop("reliability_coaching", None)

    if "compliance" in payload.model_fields_set:
        from app.services import settings as settings_service

        reference_time = datetime.now(timezone.utc)
        current_context = await settings_service.resolve_business_compliance_policy_context(
            session,
            business=business,
            as_of=reference_time,
        )
        expected_hash = payload.expected_compliance_policy_hash
        if expected_hash is not None:
            current_hash = (
                current_context.policy_hash
                if current_context is not None
                else settings_service.compliance_policy_hash({})
            )
            if current_hash != expected_hash:
                raise settings_service.CompliancePolicyPreviewStaleError(
                    current_compliance_policy_hash=current_hash,
                    current_compliance_settings=(
                        current_context.settings
                        if current_context is not None
                        else settings_service.read_compliance_settings({})
                    ),
                )
        next_compliance_settings = (
            settings_service.read_compliance_settings({}).model_dump()
            if payload.compliance is None
            else settings_service.merge_compliance_policy_update(
                current_context.settings.model_dump()
                if current_context is not None
                else {},
                payload.compliance,
            )
        )
        effective_at = payload.compliance_effective_at or reference_time
        current_settings_payload = (
            current_context.settings.model_dump()
            if current_context is not None
            else settings_service.read_compliance_settings({}).model_dump()
        )
        effective_context = current_context
        if (
            next_compliance_settings != current_settings_payload
            or payload.compliance_effective_at is not None
        ):
            created_version = await settings_service.create_compliance_policy_version(
                session,
                business=business,
                policy_scope="business",
                settings_payload=next_compliance_settings,
                effective_at=effective_at,
                created_by_user_id=actor_user_id,
            )
            if effective_at <= reference_time:
                effective_context = settings_service._context_from_version(created_version)
        settings = settings_service.apply_compliance_policy_context_to_settings(
            settings,
            context=effective_context,
        )
        changes["compliance"] = next_compliance_settings
        changes["compliance_effective_at"] = effective_at.isoformat()

    if "compliance_payroll_export" in payload.model_fields_set:
        from app.services import settings as settings_service

        if payload.compliance_payroll_export is None:
            if "compliance_payroll_export" in settings:
                settings.pop("compliance_payroll_export", None)
                changes["compliance_payroll_export"] = None
        else:
            next_payroll_export_settings = (
                settings_service.merge_compliance_payroll_export_update(
                    settings.get("compliance_payroll_export"),
                    payload.compliance_payroll_export,
                )
            )
            if settings.get("compliance_payroll_export") != next_payroll_export_settings:
                settings["compliance_payroll_export"] = next_payroll_export_settings
                changes["compliance_payroll_export"] = next_payroll_export_settings

    if settings != current_settings:
        business.settings = settings

    await session.flush()
    await session.refresh(business)
    return changes


async def list_locations(session: AsyncSession, business_id: UUID) -> list[Location]:
    result = await session.execute(
        select(Location).where(Location.business_id == business_id).order_by(Location.created_at.desc())
    )
    return list(result.scalars().all())


async def get_location(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
) -> Optional[Location]:
    location = await session.get(Location, location_id)
    if location is None or location.business_id != business_id:
        return None
    return location


async def create_location_record(
    session: AsyncSession,
    business_id: UUID,
    payload: LocationCreate,
    *,
    derive_identity: bool = True,
    derive_roles: bool = True,
) -> Location:
    business = await get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")
    duplicate_location = await _find_duplicate_location(session, business_id, payload)
    if duplicate_location is not None:
        raise ValueError("location_already_exists")

    location_name = payload.name.strip()
    location_display_name = _initial_location_display_name(payload)
    slug = await _next_unique_location_slug(session, business_id, payload.slug or location_display_name)
    location = Location(
        business_id=business_id,
        name=location_name,
        display_name=location_display_name,
        slug=slug,
        address_line_1=payload.address_line_1,
        address_line_2=payload.address_line_2,
        locality=payload.locality,
        region=payload.region,
        postal_code=payload.postal_code,
        country_code=payload.country_code,
        timezone=payload.timezone,
        latitude=payload.latitude,
        longitude=payload.longitude,
        google_place_id=payload.google_place_id,
        google_place_metadata=payload.google_place_metadata,
        settings=payload.settings,
    )
    session.add(location)
    await session.flush()
    await shift_defaults.seed_business_shift_defaults_from_location(
        session,
        business=business,
        location=location,
    )
    _add_business_place_type_rows(
        session,
        business_id=business_id,
        location_id=location.id,
        metadata=payload.google_place_metadata,
    )
    if derive_identity or derive_roles:
        existing_locations = await list_locations(session, business_id)
        if derive_identity:
            await business_identity_derivation.sync_business_identity(
                session,
                business,
                locations=existing_locations,
            )
    if derive_roles:
        await business_classification.sync_business_classification(session, business, locations=existing_locations)
        await labor_rule_resolution.sync_location_labor_rule_resolution(
            session,
            business=business,
            location=location,
        )
    return location


async def create_location(session: AsyncSession, business_id: UUID, payload: LocationCreate) -> Location:
    location = await create_location_record(session, business_id, payload)
    await session.refresh(location)
    return location


async def delete_location(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
) -> Location:
    location = await get_location(session, business_id, location_id)
    if location is None:
        raise LookupError("location_not_found")

    blocking_shift_count = await session.scalar(
        select(func.count(Shift.id)).where(
            Shift.location_id == location_id,
            (Shift.starts_at < func.now())
            | Shift.lifecycle_status.in_(
                (
                    ShiftLifecycleStatus.in_progress,
                    ShiftLifecycleStatus.completed,
                )
            ),
        )
    )
    if int(blocking_shift_count or 0) > 0:
        raise ValueError("location_has_operational_data")

    await session.delete(location)
    await session.flush()
    return location


async def get_location_delete_readiness(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
) -> dict[str, object]:
    location = await get_location(session, business_id, location_id)
    if location is None:
        raise LookupError("location_not_found")

    shift_count = await session.scalar(
        select(func.count(Shift.id)).where(
            Shift.location_id == location_id,
            (Shift.starts_at < func.now())
            | Shift.lifecycle_status.in_(
                (
                    ShiftLifecycleStatus.in_progress,
                    ShiftLifecycleStatus.completed,
                )
            ),
        )
    )
    blocking_shift_count = int(shift_count or 0)
    if blocking_shift_count > 0:
        reason = (
            "This location has historical shifts and cannot be removed until those shifts are "
            "deleted or moved."
        )
    else:
        reason = None

    return {
        "business_id": business_id,
        "location_id": location_id,
        "can_delete": blocking_shift_count == 0,
        "reason": reason,
    }


async def list_roles(session: AsyncSession, business_id: UUID) -> list[Role]:
    result = await session.execute(
        select(Role).where(Role.business_id == business_id).order_by(Role.name.asc(), Role.created_at.asc())
    )
    return list(result.scalars().all())


async def ensure_business_role(
    session: AsyncSession,
    *,
    business_id: UUID,
    role_name: str,
    source: str,
    role_code: str | None = None,
    category: str | None = None,
    description: str | None = None,
    min_notice_minutes: int | None = None,
    default_shift_length_minutes: int | None = None,
    coverage_priority: int | None = None,
    metadata_json: dict | None = None,
    source_metadata: dict | None = None,
) -> Role:
    normalized_name = role_name.strip()
    if not normalized_name:
        raise ValueError("role_name_required")

    code = role_code_from_name(role_code or normalized_name)
    existing = await session.scalar(
        select(Role).where(Role.business_id == business_id, Role.code == code)
    )
    if existing is None:
        role = Role(
            business_id=business_id,
            code=code,
            name=normalized_name,
            category=category,
            description=description,
            min_notice_minutes=max(0, int(min_notice_minutes or 0)),
            default_shift_length_minutes=default_shift_length_minutes,
            coverage_priority=max(0, int(coverage_priority if coverage_priority is not None else 100)),
            metadata_json=_merge_role_metadata(
                metadata_json,
                source=source,
                source_metadata=source_metadata,
            ),
        )
        session.add(role)
        await session.flush()
        return role

    if not existing.name:
        existing.name = normalized_name
    if category and not existing.category:
        existing.category = category
    if description and not existing.description:
        existing.description = description
    if default_shift_length_minutes is not None and existing.default_shift_length_minutes is None:
        existing.default_shift_length_minutes = default_shift_length_minutes
    if min_notice_minutes is not None and existing.min_notice_minutes == 0 and min_notice_minutes > 0:
        existing.min_notice_minutes = min_notice_minutes
    if coverage_priority is not None and existing.coverage_priority == 100 and coverage_priority != 100:
        existing.coverage_priority = max(0, int(coverage_priority))

    existing.metadata_json = _merge_role_metadata(
        {**dict(existing.metadata_json or {}), **dict(metadata_json or {})},
        source=source,
        source_metadata=source_metadata,
    )
    await session.flush()
    return existing


async def create_role(session: AsyncSession, business_id: UUID, payload: RoleCreate) -> RoleCreateResult:
    business = await get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")

    existing_roles = await list_roles(session, business_id)
    normalization = await role_normalization.normalize_role_name(
        session,
        business_id=business_id,
        raw_name=payload.name,
        existing_roles=existing_roles,
    )
    if normalization.decision == "reject":
        raise role_normalization.RoleNameRejectedError(
            normalization.reason or "Enter a clearer role name."
        )
    if payload.code is None and normalization.matched_role is not None:
        return RoleCreateResult(
            role=normalization.matched_role,
            decision="reused_existing",
            normalized_name=normalization.normalized_name,
            confidence=normalization.confidence,
            reason=normalization.reason,
        )

    existing_role = await _find_existing_business_role(
        session,
        business_id,
        name=normalization.normalized_name,
        code=payload.code,
    )
    if existing_role is not None:
        if payload.code is not None:
            raise ValueError("role_already_exists")
        return RoleCreateResult(
            role=existing_role,
            decision="reused_existing",
            normalized_name=normalization.normalized_name,
            confidence=normalization.confidence,
            reason=normalization.reason,
        )

    code = await _next_unique_role_code(
        session,
        business_id,
        payload.code or normalization.normalized_name,
    )
    role = Role(
        business_id=business_id,
        code=code,
        name=normalization.normalized_name,
        category=payload.category,
        description=payload.description,
        min_notice_minutes=payload.min_notice_minutes,
        default_shift_length_minutes=payload.default_shift_length_minutes,
        coverage_priority=payload.coverage_priority,
        metadata_json=payload.metadata_json,
    )
    session.add(role)
    await session.flush()
    await session.refresh(role)
    return RoleCreateResult(
        role=role,
        decision="created_new",
        normalized_name=normalization.normalized_name,
        confidence=normalization.confidence,
        reason=normalization.reason,
    )


async def rerun_role_derivation(session: AsyncSession, business_id: UUID) -> tuple[Business, list[Role]]:
    business = await get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")

    locations = await list_locations(session, business_id)
    await business_classification.sync_business_classification(session, business, locations=locations)
    await session.flush()
    await session.refresh(business)
    roles = await list_roles(session, business_id)
    return business, roles


async def rerun_business_identity_derivation(session: AsyncSession, business_id: UUID) -> Business:
    business = await get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")

    locations = await list_locations(session, business_id)
    await business_identity_derivation.sync_business_identity(session, business, locations=locations)
    await session.flush()
    await session.refresh(business)
    return business


async def attach_role_to_location(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
    role_id: UUID,
    payload: LocationRoleAttach,
) -> LocationRole:
    location = await session.get(Location, location_id)
    role = await session.get(Role, role_id)
    if location is None or role is None or location.business_id != business_id or role.business_id != business_id:
        raise LookupError("location_or_role_not_found")

    existing = await session.scalar(
        select(LocationRole).where(LocationRole.location_id == location_id, LocationRole.role_id == role_id)
    )
    if existing is None:
        existing = LocationRole(
            location_id=location_id,
            role_id=role_id,
            min_headcount=payload.min_headcount,
            max_headcount=payload.max_headcount,
            premium_rules=payload.premium_rules,
            coverage_settings=payload.coverage_settings,
        )
        session.add(existing)
    else:
        existing.is_active = True
        existing.min_headcount = payload.min_headcount
        existing.max_headcount = payload.max_headcount
        existing.premium_rules = payload.premium_rules
        existing.coverage_settings = payload.coverage_settings

    await session.flush()
    await session.refresh(existing)
    return existing


async def list_location_roles(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
) -> list[LocationRole]:
    location = await session.get(Location, location_id)
    if location is None or location.business_id != business_id:
        raise LookupError("location_not_found")

    result = await session.execute(
        select(LocationRole)
        .where(
            LocationRole.location_id == location_id,
            LocationRole.is_active.is_(True),
        )
        .order_by(LocationRole.created_at.asc())
    )
    rows = list(result.scalars().all())
    shift_counts = await _locked_shift_counts_by_role_id(session, location_id)
    for row in rows:
        count = shift_counts.get(row.role_id, 0)
        setattr(row, "assigned_shift_count", count)
        setattr(row, "is_locked", count > 0)
    return rows


async def replace_location_roles(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
    payload: LocationRoleReplace,
) -> list[LocationRole]:
    location = await session.get(Location, location_id)
    if location is None or location.business_id != business_id:
        raise LookupError("location_not_found")

    requested_roles = payload.roles
    requested_role_ids = [item.role_id for item in requested_roles]
    if len(requested_role_ids) != len(set(requested_role_ids)):
        raise ValueError("duplicate_role_ids")

    roles_by_id: dict[UUID, Role] = {}
    if requested_role_ids:
        role_result = await session.execute(
            select(Role).where(Role.business_id == business_id, Role.id.in_(requested_role_ids))
        )
        roles_by_id = {role.id: role for role in role_result.scalars().all()}
        if len(roles_by_id) != len(requested_role_ids):
            raise LookupError("role_not_found")

    existing_result = await session.execute(
        select(LocationRole).where(LocationRole.location_id == location_id)
    )
    existing_rows = list(existing_result.scalars().all())
    existing_by_role_id = {row.role_id: row for row in existing_rows}
    desired_role_ids = set(requested_role_ids)
    locked_shift_counts = await _locked_shift_counts_by_role_id(session, location_id)

    for existing in existing_rows:
        if existing.role_id not in desired_role_ids:
            if locked_shift_counts.get(existing.role_id, 0) > 0:
                raise ValueError(
                    "Cannot remove a role that still has active shifts at this location."
                )
            existing.is_active = False

    for item in requested_roles:
        existing = existing_by_role_id.get(item.role_id)
        if existing is None:
            existing = LocationRole(
                location_id=location_id,
                role_id=item.role_id,
                is_active=True,
                min_headcount=item.min_headcount,
                max_headcount=item.max_headcount,
                premium_rules=item.premium_rules or {},
                coverage_settings=item.coverage_settings or {},
            )
            session.add(existing)
            existing_by_role_id[item.role_id] = existing
            continue

        existing.is_active = True
        if "min_headcount" in item.model_fields_set:
            existing.min_headcount = item.min_headcount
        if "max_headcount" in item.model_fields_set:
            existing.max_headcount = item.max_headcount
        if "premium_rules" in item.model_fields_set:
            existing.premium_rules = item.premium_rules or {}
        if "coverage_settings" in item.model_fields_set:
            existing.coverage_settings = item.coverage_settings or {}

    await session.flush()
    active_rows = [
        existing_by_role_id[role_id]
        for role_id in requested_role_ids
        if existing_by_role_id[role_id].is_active
    ]
    refreshed_shift_counts = await _locked_shift_counts_by_role_id(session, location_id)
    for row in active_rows:
        count = refreshed_shift_counts.get(row.role_id, 0)
        setattr(row, "assigned_shift_count", count)
        setattr(row, "is_locked", count > 0)
    return active_rows


async def create_and_assign_location_role(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
    payload: LocationRoleCreateAndAssign,
) -> tuple[Role, LocationRole]:
    location = await session.get(Location, location_id)
    if location is None or location.business_id != business_id:
        raise LookupError("location_not_found")

    existing_roles = await list_roles(session, business_id)
    normalization = await role_normalization.normalize_role_name(
        session,
        business_id=business_id,
        raw_name=payload.name,
        existing_roles=existing_roles,
    )
    if normalization.decision == "reject":
        raise role_normalization.RoleNameRejectedError(
            normalization.reason or "Enter a clearer role name."
        )

    role = await ensure_business_role(
        session,
        business_id=business_id,
        role_name=normalization.matched_role.name if normalization.matched_role else normalization.normalized_name,
        role_code=payload.code,
        category=payload.category,
        description=payload.description,
        min_notice_minutes=payload.min_notice_minutes,
        default_shift_length_minutes=payload.default_shift_length_minutes,
        coverage_priority=payload.coverage_priority,
        metadata_json=payload.metadata_json,
        source="location_role_editor",
        source_metadata={"location_id": str(location_id)},
    )

    location_role = await attach_role_to_location(
        session,
        business_id,
        location_id,
        role.id,
        LocationRoleAttach(
            min_headcount=payload.min_headcount,
            max_headcount=payload.max_headcount,
            premium_rules=payload.premium_rules,
            coverage_settings=payload.coverage_settings,
        ),
    )
    return role, location_role


async def ensure_location_role(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    role_id: UUID,
    source: str,
) -> LocationRole:
    location = await session.get(Location, location_id)
    role = await session.get(Role, role_id)
    if location is None or role is None or location.business_id != business_id or role.business_id != business_id:
        raise LookupError("location_or_role_not_found")

    existing = await session.scalar(
        select(LocationRole).where(LocationRole.location_id == location_id, LocationRole.role_id == role_id)
    )
    if existing is None:
        existing = LocationRole(
            location_id=location_id,
            role_id=role_id,
            coverage_settings={"source": source},
        )
        session.add(existing)
    else:
        existing.is_active = True
        coverage_settings = dict(existing.coverage_settings or {})
        coverage_settings.setdefault("source", source)
        coverage_settings["last_source"] = source
        existing.coverage_settings = coverage_settings

    await session.flush()
    return existing


async def _locked_shift_counts_by_role_id(
    session: AsyncSession,
    location_id: UUID,
) -> dict[UUID, int]:
    result = await session.execute(
        select(Shift.role_id, func.count(Shift.id))
        .where(
            Shift.location_id == location_id,
            Shift.lifecycle_status != ShiftLifecycleStatus.draft,
        )
        .group_by(Shift.role_id)
    )
    return {role_id: int(count) for role_id, count in result.all()}
