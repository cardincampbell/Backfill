from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business, Location
from app.models.common import ShiftLifecycleStatus
from app.models.scheduling import Shift
from app.schemas.auto_scheduler import GeneratedDemandPayload, ProposedShiftPayload

_PATTERN_LOOKBACK_DAYS = 28
_PATTERN_GENERATION_VERSION = "historical_pattern_v1"


async def generate_pattern_based_demand(
    session: AsyncSession,
    *,
    business: Business,
    location: Location,
    planning_window_start: datetime,
    planning_window_end: datetime,
    current_shifts: Sequence[Shift],
) -> GeneratedDemandPayload:
    timezone_name = location.timezone or business.timezone or "UTC"
    tz = ZoneInfo(timezone_name)
    historical_shifts = await _load_historical_pattern_shifts(
        session,
        business_id=business.id,
        location_id=location.id,
        planning_window_start=planning_window_start,
    )
    if not historical_shifts:
        return GeneratedDemandPayload(
            proposed_shifts=[],
            metadata={
                "strategy": _PATTERN_GENERATION_VERSION,
                "status": "no_historical_pattern_data",
                "historical_shift_count": 0,
                "generated_shift_count": 0,
                "lookback_days": _PATTERN_LOOKBACK_DAYS,
            },
        )

    authored_envelope_counts = _current_draft_envelope_counts(
        business_id=business.id,
        location_id=location.id,
        timezone=tz,
        shifts=current_shifts,
    )
    historical_patterns = _historical_patterns_by_weekday(
        shifts=historical_shifts,
        timezone=tz,
    )

    proposed_shifts: list[ProposedShiftPayload] = []
    target_dates = _planning_service_dates(
        planning_window_start=planning_window_start,
        planning_window_end=planning_window_end,
        timezone=tz,
    )
    for target_date in target_dates:
        weekday_patterns = historical_patterns.get(target_date.weekday(), {})
        for pattern_key, pattern in sorted(
            weekday_patterns.items(),
            key=lambda item: (
                item[1]["start_minutes"],
                str(item[1]["role_id"]),
                item[1]["end_minutes"],
            ),
        ):
            normalized_key = _normalized_demand_key(
                business_id=business.id,
                location_id=location.id,
                role_id=pattern["role_id"],
                service_date=target_date,
                start_minutes=pattern["start_minutes"],
                end_minutes=pattern["end_minutes"],
            )
            authored_headcount = authored_envelope_counts.get(normalized_key, 0)
            target_headcount = max(1, int(round(mean(pattern["daily_counts"]))))
            remaining_headcount = max(0, target_headcount - authored_headcount)
            if remaining_headcount <= 0:
                continue

            starts_at, ends_at = _window_datetimes_for_service_date(
                service_date=target_date,
                start_minutes=pattern["start_minutes"],
                end_minutes=pattern["end_minutes"],
                tz=tz,
            )
            source_dates = [value.isoformat() for value in sorted(pattern["source_dates"])]
            for seat_offset in range(remaining_headcount):
                seat_number = authored_headcount + seat_offset + 1
                proposed_shifts.append(
                    ProposedShiftPayload(
                        demand_key=f"{normalized_key}:seat:{seat_number}",
                        source_type="historical_pattern",
                        generation_version=_PATTERN_GENERATION_VERSION,
                        location_id=location.id,
                        role_id=pattern["role_id"],
                        timezone=timezone_name,
                        starts_at=starts_at,
                        ends_at=ends_at,
                        headcount=1,
                        premium_cents=pattern["premium_cents"],
                        requires_manager_approval=pattern["requires_manager_approval"],
                        generation_payload={
                            "normalized_demand_key": normalized_key,
                            "target_headcount": target_headcount,
                            "existing_draft_headcount": authored_headcount,
                            "remaining_generated_headcount": remaining_headcount,
                            "seat_number": seat_number,
                            "source_dates": source_dates,
                            "source_observation_count": len(source_dates),
                            "pattern_key": pattern_key,
                        },
                    )
                )

    return GeneratedDemandPayload(
        proposed_shifts=proposed_shifts,
        metadata={
            "strategy": _PATTERN_GENERATION_VERSION,
            "status": "generated",
            "historical_shift_count": len(historical_shifts),
            "generated_shift_count": len(proposed_shifts),
            "historical_week_count": _historical_week_count(historical_shifts, tz),
            "lookback_days": _PATTERN_LOOKBACK_DAYS,
            "netting_mode": "exact_normalized_demand_envelope_v1",
            "preserved_draft_headcount": sum(authored_envelope_counts.values()),
            "generated_envelope_count": len(
                {
                    str(item.generation_payload.get("normalized_demand_key") or item.demand_key)
                    for item in proposed_shifts
                }
            ),
        },
    )


async def _load_historical_pattern_shifts(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    planning_window_start: datetime,
) -> list[Shift]:
    lookback_start = planning_window_start - timedelta(days=_PATTERN_LOOKBACK_DAYS)
    stmt = (
        select(Shift)
        .where(
            Shift.business_id == business_id,
            Shift.location_id == location_id,
            Shift.lifecycle_status != ShiftLifecycleStatus.draft,
            Shift.starts_at >= lookback_start,
            Shift.starts_at < planning_window_start,
        )
        .order_by(Shift.starts_at.asc(), Shift.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _planning_service_dates(
    *,
    planning_window_start: datetime,
    planning_window_end: datetime,
    timezone: ZoneInfo,
) -> list[date]:
    start_local = planning_window_start.astimezone(timezone).date()
    end_local = planning_window_end.astimezone(timezone).date()
    current = start_local
    days: list[date] = []
    while current < end_local:
        days.append(current)
        current += timedelta(days=1)
    return days


def _historical_patterns_by_weekday(
    *,
    shifts: Sequence[Shift],
    timezone: ZoneInfo,
) -> dict[int, dict[str, dict[str, object]]]:
    grouped_counts: dict[int, dict[str, dict[date, int]]] = defaultdict(lambda: defaultdict(dict))
    grouped_metadata: dict[int, dict[str, dict[str, object]]] = defaultdict(dict)
    for shift in shifts:
        service_date, start_minutes, end_minutes = _localized_shift_window(shift, timezone)
        weekday = service_date.weekday()
        pattern_key = _pattern_group_key(
            role_id=shift.role_id,
            start_minutes=start_minutes,
            end_minutes=end_minutes,
            premium_cents=int(shift.premium_cents or 0),
            requires_manager_approval=bool(shift.requires_manager_approval),
        )
        counts = grouped_counts[weekday].setdefault(pattern_key, {})
        counts[service_date] = counts.get(service_date, 0) + int(shift.seats_requested or 1)
        grouped_metadata[weekday][pattern_key] = {
            "role_id": shift.role_id,
            "start_minutes": start_minutes,
            "end_minutes": end_minutes,
            "premium_cents": int(shift.premium_cents or 0),
            "requires_manager_approval": bool(shift.requires_manager_approval),
        }

    normalized: dict[int, dict[str, dict[str, object]]] = {}
    for weekday, pattern_counts in grouped_counts.items():
        normalized[weekday] = {}
        for pattern_key, daily_counts in pattern_counts.items():
            metadata = grouped_metadata[weekday][pattern_key]
            normalized[weekday][pattern_key] = {
                **metadata,
                "daily_counts": list(daily_counts.values()),
                "source_dates": list(daily_counts.keys()),
            }
    return normalized


def _current_draft_envelope_counts(
    *,
    business_id: UUID,
    location_id: UUID,
    timezone: ZoneInfo,
    shifts: Sequence[Shift],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for shift in shifts:
        if shift.lifecycle_status != ShiftLifecycleStatus.draft:
            continue
        service_date, start_minutes, end_minutes = _localized_shift_window(shift, timezone)
        demand_key = _normalized_demand_key(
            business_id=business_id,
            location_id=location_id,
            role_id=shift.role_id,
            service_date=service_date,
            start_minutes=start_minutes,
            end_minutes=end_minutes,
        )
        counts[demand_key] += int(shift.seats_requested or 1)
    return counts


def _localized_shift_window(
    shift: Shift,
    timezone: ZoneInfo,
) -> tuple[date, int, int]:
    starts_local = shift.starts_at.astimezone(timezone)
    ends_local = shift.ends_at.astimezone(timezone)
    service_date = starts_local.date()
    start_minutes = (starts_local.hour * 60) + starts_local.minute
    end_minutes = (ends_local.hour * 60) + ends_local.minute
    if ends_local.date() > service_date or end_minutes <= start_minutes:
        end_minutes += 24 * 60
    return service_date, start_minutes, end_minutes


def _window_datetimes_for_service_date(
    *,
    service_date: date,
    start_minutes: int,
    end_minutes: int,
    tz: ZoneInfo,
) -> tuple[datetime, datetime]:
    local_start = datetime.combine(service_date, time.min, tzinfo=tz) + timedelta(minutes=start_minutes)
    local_end = datetime.combine(service_date, time.min, tzinfo=tz) + timedelta(minutes=end_minutes)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _normalized_demand_key(
    *,
    business_id: UUID,
    location_id: UUID,
    role_id: UUID,
    service_date: date,
    start_minutes: int,
    end_minutes: int,
) -> str:
    return (
        f"{business_id}:{location_id}:{role_id}:{service_date.isoformat()}:"
        f"{start_minutes:04d}:{end_minutes:04d}"
    )


def _pattern_group_key(
    *,
    role_id: UUID,
    start_minutes: int,
    end_minutes: int,
    premium_cents: int,
    requires_manager_approval: bool,
) -> str:
    return f"{role_id}:{start_minutes:04d}:{end_minutes:04d}:{premium_cents}:{int(requires_manager_approval)}"


def _historical_week_count(
    shifts: Sequence[Shift],
    timezone: ZoneInfo,
) -> int:
    weeks = {
        shift.starts_at.astimezone(timezone).date().isocalendar()[:2]
        for shift in shifts
    }
    return len(weeks)
