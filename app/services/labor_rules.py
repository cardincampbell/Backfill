from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace
from typing import Iterable, Mapping, Sequence
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.business import Business, Location
from app.models.common import AssignmentStatus, ShiftLifecycleStatus
from app.models.labor_rules import (
    LaborRuleProfile,
    LaborRuleProfileVersion,
    LocationLaborRuleResolution,
)
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee

OVERTIME_MODES = {
    "weekly_only",
    "daily_8_plus_weekly",
    "daily_12_or_consecutive_plus_weekly",
    "daily_8_plus_weekly_plus_7th_day",
    "conditional_daily_plus_weekly",
    "industry_specific",
}

_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True)
class LaborRuleProfileSnapshot:
    profile_id: UUID
    code: str
    jurisdiction_code: str
    display_name: str
    overtime_mode: str
    daily_ot_threshold_hours: float | None
    weekly_ot_threshold_hours: float | None
    double_time_threshold_hours: float | None
    consecutive_hours_threshold_hours: float | None
    industry_profile_code: str | None
    rules_json: dict[str, object]
    effective_start_date: date | None
    effective_end_date: date | None
    source_urls: tuple[str, ...]
    source_version: str | None
    source_hash: str | None
    version_id: UUID
    version_no: int
    payload_hash: str
    payload_json: dict[str, object]


@dataclass(frozen=True)
class CountedInterval:
    start_at: datetime
    end_at: datetime
    shift_id: UUID
    assignment_status: str


@dataclass(frozen=True)
class HoursSnapshot:
    employee_id: UUID
    profile_version_id: UUID | None
    workday_window: dict[str, str]
    workweek_window: dict[str, str]
    counted_intervals: tuple[CountedInterval, ...]
    gross_hours_by_window: dict[str, float]


def labor_rules_mode() -> str:
    mode = settings.labor_rules_mode.strip().lower()
    return mode if mode in {"shadow", "primary"} else "shadow"


def labor_rules_primary_enabled() -> bool:
    return labor_rules_mode() == "primary"


def _as_float(value: object | None) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _as_int(value: object | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: object | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _json_dict(value: object | None) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _json_list(value: object | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def resolve_jurisdiction_code(location: Location) -> str:
    country = (location.country_code or "").strip().upper()
    region = (location.region or "").strip().upper()
    if country and region:
        return f"{country}-{region}"
    if country:
        return country
    return "US"


def profile_payload_hash(payload: dict[str, object]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def build_profile_payload(profile: LaborRuleProfile) -> dict[str, object]:
    return {
        "profile_id": str(profile.id),
        "code": profile.code,
        "jurisdiction_code": profile.jurisdiction_code,
        "display_name": profile.display_name,
        "overtime_mode": profile.overtime_mode,
        "daily_ot_threshold_hours": _as_float(profile.daily_ot_threshold_hours),
        "weekly_ot_threshold_hours": _as_float(profile.weekly_ot_threshold_hours),
        "double_time_threshold_hours": _as_float(profile.double_time_threshold_hours),
        "consecutive_hours_threshold_hours": _as_float(profile.consecutive_hours_threshold_hours),
        "industry_profile_code": profile.industry_profile_code,
        "rules_json": _json_dict(profile.rules_json),
        "effective_start_date": profile.effective_start_date.isoformat() if profile.effective_start_date else None,
        "effective_end_date": profile.effective_end_date.isoformat() if profile.effective_end_date else None,
        "source_urls": list(_json_list(profile.source_urls)),
        "source_version": profile.source_version,
        "source_hash": profile.source_hash,
    }


def snapshot_from_rows(
    profile: LaborRuleProfile,
    version: LaborRuleProfileVersion,
) -> LaborRuleProfileSnapshot:
    payload_json = _json_dict(version.payload_json) or build_profile_payload(profile)
    return LaborRuleProfileSnapshot(
        profile_id=profile.id,
        code=profile.code,
        jurisdiction_code=profile.jurisdiction_code,
        display_name=profile.display_name,
        overtime_mode=profile.overtime_mode,
        daily_ot_threshold_hours=_as_float(profile.daily_ot_threshold_hours),
        weekly_ot_threshold_hours=_as_float(profile.weekly_ot_threshold_hours),
        double_time_threshold_hours=_as_float(profile.double_time_threshold_hours),
        consecutive_hours_threshold_hours=_as_float(profile.consecutive_hours_threshold_hours),
        industry_profile_code=profile.industry_profile_code,
        rules_json=_json_dict(profile.rules_json),
        effective_start_date=profile.effective_start_date,
        effective_end_date=profile.effective_end_date,
        source_urls=_json_list(profile.source_urls),
        source_version=profile.source_version,
        source_hash=profile.source_hash,
        version_id=version.id,
        version_no=version.version_no,
        payload_hash=version.payload_hash,
        payload_json=payload_json,
    )


def _country_jurisdiction_code(jurisdiction_code: str) -> str | None:
    parts = jurisdiction_code.split("-", 1)
    return parts[0] if parts and parts[0] else None


def _is_profile_effective(
    profile: LaborRuleProfileSnapshot,
    *,
    as_of_date: date,
) -> bool:
    if profile.effective_start_date and as_of_date < profile.effective_start_date:
        return False
    if profile.effective_end_date and as_of_date > profile.effective_end_date:
        return False
    return True


async def _latest_versions_for_profiles(
    session: AsyncSession,
    profiles: Sequence[LaborRuleProfile],
) -> dict[UUID, LaborRuleProfileVersion]:
    if not profiles:
        return {}
    profile_ids = [profile.id for profile in profiles]
    rows = (
        await session.execute(
            select(LaborRuleProfileVersion)
            .where(LaborRuleProfileVersion.labor_rule_profile_id.in_(profile_ids))
            .order_by(
                LaborRuleProfileVersion.labor_rule_profile_id.asc(),
                LaborRuleProfileVersion.version_no.desc(),
            )
        )
    ).scalars().all()
    latest: dict[UUID, LaborRuleProfileVersion] = {}
    for row in rows:
        latest.setdefault(row.labor_rule_profile_id, row)
    return latest


async def active_profiles_for_jurisdiction(
    session: AsyncSession,
    jurisdiction_code: str,
    *,
    as_of: datetime | None = None,
) -> list[LaborRuleProfileSnapshot]:
    as_of_date = (as_of or datetime.now(timezone.utc)).date()
    candidate_jurisdictions = [jurisdiction_code]
    country_code = _country_jurisdiction_code(jurisdiction_code)
    if country_code and country_code not in candidate_jurisdictions:
        candidate_jurisdictions.append(country_code)

    profiles = (
        await session.execute(
            select(LaborRuleProfile)
            .where(
                LaborRuleProfile.is_active.is_(True),
                LaborRuleProfile.jurisdiction_code.in_(candidate_jurisdictions),
            )
            .order_by(LaborRuleProfile.jurisdiction_code.desc(), LaborRuleProfile.code.asc())
        )
    ).scalars().all()
    versions = await _latest_versions_for_profiles(session, profiles)
    snapshots = [
        snapshot_from_rows(profile, versions[profile.id])
        for profile in profiles
        if profile.id in versions
    ]
    return [
        snapshot
        for snapshot in snapshots
        if _is_profile_effective(snapshot, as_of_date=as_of_date)
    ]


async def load_profile_snapshot_by_version_id(
    session: AsyncSession,
    version_id: UUID,
) -> LaborRuleProfileSnapshot | None:
    version = await session.get(LaborRuleProfileVersion, version_id)
    if version is None:
        return None
    profile = await session.get(LaborRuleProfile, version.labor_rule_profile_id)
    if profile is None:
        return None
    return snapshot_from_rows(profile, version)


async def load_authoritative_location_resolution(
    session: AsyncSession,
    *,
    location_id: UUID,
) -> LocationLaborRuleResolution | None:
    result = await session.execute(
        select(LocationLaborRuleResolution).where(LocationLaborRuleResolution.location_id == location_id)
    )
    return result.scalars().first()


async def runtime_resolved_profile(
    session: AsyncSession,
    *,
    location: Location,
    business: Business | None = None,
    as_of: datetime | None = None,
) -> LaborRuleProfileSnapshot | None:
    resolution = await load_authoritative_location_resolution(session, location_id=location.id)
    if resolution is not None:
        snapshot = await load_profile_snapshot_by_version_id(session, resolution.resolved_profile_version_id)
        if snapshot is not None and _is_profile_effective(snapshot, as_of_date=(as_of or datetime.now(timezone.utc)).date()):
            return snapshot

    profiles = await active_profiles_for_jurisdiction(session, resolve_jurisdiction_code(location), as_of=as_of)
    if not profiles:
        return None

    industry_code = None
    if isinstance(location.settings, dict):
        raw_industry = location.settings.get("labor_industry_profile_code")
        if isinstance(raw_industry, str) and raw_industry.strip():
            industry_code = raw_industry.strip()

    if industry_code:
        matching = [profile for profile in profiles if profile.industry_profile_code == industry_code]
        if len(matching) == 1:
            return matching[0]

    generic_profiles = [profile for profile in profiles if not profile.industry_profile_code]
    if len(generic_profiles) == 1:
        return generic_profiles[0]
    if len(profiles) == 1:
        return profiles[0]
    return None


def _workweek_boundary_config(profile: LaborRuleProfileSnapshot) -> tuple[int, time]:
    rules = profile.rules_json
    raw_day = str(rules.get("workweek_start_day_local") or "monday").strip().lower()
    weekday = _WEEKDAY_INDEX.get(raw_day, 0)
    raw_time = str(rules.get("workweek_start_time_local") or "00:00").strip()
    try:
        hour, minute = [int(part) for part in raw_time.split(":", 1)]
        local_time = time(hour=max(0, min(hour, 23)), minute=max(0, min(minute, 59)))
    except Exception:
        local_time = time(0, 0)
    return weekday, local_time


def max_consecutive_work_days(profile: LaborRuleProfileSnapshot) -> int:
    rules = profile.rules_json if isinstance(profile.rules_json, dict) else {}
    configured = _as_int(rules.get("max_consecutive_work_days")) or 0
    if configured > 0:
        return configured
    raw_ruleset = str(rules.get("day_of_rest_ruleset") or "").strip().lower()
    if _as_bool(rules.get("day_of_rest_required")) or raw_ruleset in {
        "ca_v1",
        "california_v1",
    }:
        return 6
    return 0


def required_rest_days_per_workweek(profile: LaborRuleProfileSnapshot) -> int:
    rules = profile.rules_json if isinstance(profile.rules_json, dict) else {}
    configured = _as_int(rules.get("required_rest_days_per_workweek")) or 0
    if configured > 0:
        return min(configured, 7)
    if _as_bool(rules.get("day_of_rest_workweek_required")):
        return 1
    return 0


def effective_max_consecutive_work_days(
    profile: LaborRuleProfileSnapshot,
    *,
    compliance_settings: Mapping[str, object] | None = None,
) -> int:
    policy_days = (
        _as_int(compliance_settings.get("max_consecutive_work_days"))
        if isinstance(compliance_settings, Mapping)
        else 0
    ) or 0
    return max(max_consecutive_work_days(profile), policy_days)


def workweek_window_for_shift(
    profile: LaborRuleProfileSnapshot,
    *,
    shift: Shift,
) -> tuple[datetime, datetime]:
    tz = ZoneInfo(shift.timezone)
    local_start = shift.starts_at.astimezone(tz)
    weekday, start_time_local = _workweek_boundary_config(profile)
    days_since_boundary = (local_start.weekday() - weekday) % 7
    boundary_date = local_start.date() - timedelta(days=days_since_boundary)
    boundary_local = datetime.combine(boundary_date, start_time_local, tzinfo=tz)
    if local_start < boundary_local:
        boundary_local -= timedelta(days=7)
    return boundary_local.astimezone(timezone.utc), (boundary_local + timedelta(days=7)).astimezone(timezone.utc)


def workday_window_for_shift(shift: Shift) -> tuple[datetime, datetime]:
    tz = ZoneInfo(shift.timezone)
    local_start = shift.starts_at.astimezone(tz)
    day_start_local = datetime.combine(local_start.date(), time.min, tzinfo=tz)
    return day_start_local.astimezone(timezone.utc), (day_start_local + timedelta(days=1)).astimezone(timezone.utc)


def _shift_interval_for_counting(
    *,
    starts_at: datetime,
    ends_at: datetime,
    status: AssignmentStatus | str,
    reference_time: datetime,
) -> tuple[datetime, datetime] | None:
    if starts_at >= ends_at:
        return None
    status_text = str(status.value if hasattr(status, "value") else status)
    if status_text in {AssignmentStatus.assigned.value, AssignmentStatus.accepted.value} and starts_at <= reference_time < ends_at:
        clipped_end = reference_time
    else:
        clipped_end = ends_at
    if clipped_end <= starts_at:
        return None
    return starts_at, clipped_end


def _merge_intervals(intervals: Sequence[CountedInterval]) -> list[CountedInterval]:
    ordered = sorted(intervals, key=lambda item: (item.start_at, item.end_at))
    if not ordered:
        return []
    merged: list[CountedInterval] = [ordered[0]]
    for interval in ordered[1:]:
        current = merged[-1]
        if interval.start_at <= current.end_at:
            merged[-1] = CountedInterval(
                start_at=current.start_at,
                end_at=max(current.end_at, interval.end_at),
                shift_id=current.shift_id,
                assignment_status=current.assignment_status,
            )
            continue
        merged.append(interval)
    return merged


def _clip_intervals(
    intervals: Sequence[CountedInterval],
    *,
    start_at: datetime,
    end_at: datetime,
) -> list[CountedInterval]:
    clipped: list[CountedInterval] = []
    for interval in intervals:
        clipped_start = max(interval.start_at, start_at)
        clipped_end = min(interval.end_at, end_at)
        if clipped_start >= clipped_end:
            continue
        clipped.append(
            CountedInterval(
                start_at=clipped_start,
                end_at=clipped_end,
                shift_id=interval.shift_id,
                assignment_status=interval.assignment_status,
            )
        )
    return _merge_intervals(clipped)


def _interval_duration_hours(intervals: Sequence[CountedInterval]) -> float:
    return round(sum((interval.end_at - interval.start_at).total_seconds() for interval in intervals) / 3600, 4)


def _candidate_interval(shift: Shift) -> CountedInterval:
    return CountedInterval(
        start_at=shift.starts_at,
        end_at=shift.ends_at,
        shift_id=shift.id,
        assignment_status="candidate_shift",
    )


async def build_hours_snapshots(
    session: AsyncSession,
    *,
    employees: Sequence[Employee],
    shift: Shift,
    profile: LaborRuleProfileSnapshot,
    compliance_settings: Mapping[str, object] | None = None,
    now: datetime | None = None,
) -> dict[UUID, HoursSnapshot]:
    reference_time = now or datetime.now(timezone.utc)
    employee_ids = [employee.id for employee in employees]
    if not employee_ids:
        return {}

    workweek_start, workweek_end = workweek_window_for_shift(profile, shift=shift)
    workday_start, workday_end = workday_window_for_shift(shift)
    consecutive_threshold = max(12.0, float(profile.consecutive_hours_threshold_hours or 0.0))
    consecutive_workday_lookaround_days = max(
        0,
        effective_max_consecutive_work_days(
            profile,
            compliance_settings=compliance_settings,
        ),
    )
    query_start = min(
        workweek_start,
        workday_start,
        shift.starts_at - timedelta(hours=consecutive_threshold),
        shift.starts_at - timedelta(days=consecutive_workday_lookaround_days),
    )
    query_end = max(
        workweek_end,
        shift.ends_at + timedelta(days=consecutive_workday_lookaround_days),
        reference_time,
    )

    rows = await session.execute(
        select(
            ShiftAssignment.employee_id,
            ShiftAssignment.shift_id,
            ShiftAssignment.status,
            Shift.starts_at,
            Shift.ends_at,
            Shift.lifecycle_status,
        )
        .join(Shift, ShiftAssignment.shift_id == Shift.id)
        .where(
            ShiftAssignment.employee_id.in_(employee_ids),
            ShiftAssignment.status.in_(
                [AssignmentStatus.assigned, AssignmentStatus.accepted, AssignmentStatus.completed]
            ),
            Shift.lifecycle_status != ShiftLifecycleStatus.cancelled,
            Shift.ends_at > query_start,
            Shift.starts_at < query_end,
        )
    )

    intervals_by_employee: dict[UUID, list[CountedInterval]] = {employee_id: [] for employee_id in employee_ids}
    for employee_id, shift_id, status, starts_at, ends_at, _lifecycle_status in rows.all():
        if employee_id is None or shift_id is None or starts_at is None or ends_at is None:
            continue
        counted = _shift_interval_for_counting(
            starts_at=starts_at,
            ends_at=ends_at,
            status=status,
            reference_time=reference_time,
        )
        if counted is None:
            continue
        intervals_by_employee.setdefault(employee_id, []).append(
            CountedInterval(
                start_at=counted[0],
                end_at=counted[1],
                shift_id=shift_id,
                assignment_status=str(status.value if hasattr(status, "value") else status),
            )
        )

    snapshots: dict[UUID, HoursSnapshot] = {}
    for employee in employees:
        merged = tuple(_merge_intervals(intervals_by_employee.get(employee.id, [])))
        snapshots[employee.id] = HoursSnapshot(
            employee_id=employee.id,
            profile_version_id=profile.version_id,
            workday_window={"start": workday_start.isoformat(), "end": workday_end.isoformat()},
            workweek_window={"start": workweek_start.isoformat(), "end": workweek_end.isoformat()},
            counted_intervals=merged,
            gross_hours_by_window={
                "workday": _interval_duration_hours(
                    _clip_intervals(merged, start_at=workday_start, end_at=workday_end)
                ),
                "workweek": _interval_duration_hours(
                    _clip_intervals(merged, start_at=workweek_start, end_at=workweek_end)
                ),
                "projected_with_candidate_shift": _interval_duration_hours(
                    _merge_intervals(
                        [
                            *_clip_intervals(merged, start_at=workweek_start, end_at=workweek_end),
                            _candidate_interval(shift),
                        ]
                    )
                ),
            },
        )
    return snapshots


def _hours_by_local_day(
    intervals: Sequence[CountedInterval],
    *,
    shift_timezone: str,
    window_start: datetime,
    window_end: datetime,
) -> dict[date, float]:
    tz = ZoneInfo(shift_timezone)
    clipped = _clip_intervals(intervals, start_at=window_start, end_at=window_end)
    hours_by_day: dict[date, float] = {}
    for interval in clipped:
        current_local = interval.start_at.astimezone(tz)
        end_local = interval.end_at.astimezone(tz)
        while current_local.date() < end_local.date():
            next_midnight = datetime.combine(current_local.date() + timedelta(days=1), time.min, tzinfo=tz)
            hours_by_day[current_local.date()] = hours_by_day.get(current_local.date(), 0.0) + (
                next_midnight - current_local
            ).total_seconds() / 3600
            current_local = next_midnight
        hours_by_day[current_local.date()] = hours_by_day.get(current_local.date(), 0.0) + (
            end_local - current_local
        ).total_seconds() / 3600
    return {key: round(value, 4) for key, value in hours_by_day.items()}


def _longest_contiguous_run_hours(intervals: Sequence[CountedInterval]) -> float:
    merged = _merge_intervals(intervals)
    if not merged:
        return 0.0
    return max((interval.end_at - interval.start_at).total_seconds() / 3600 for interval in merged)


def _classify_day_hours(
    *,
    profile: LaborRuleProfileSnapshot,
    day_date: date,
    day_hours: float,
    week_start_date: date,
    worked_day_dates: set[date],
) -> tuple[float, float, float, set[str]]:
    reason_codes: set[str] = set()
    if day_hours <= 0:
        return 0.0, 0.0, 0.0, reason_codes

    mode = profile.overtime_mode
    daily_threshold = float(profile.daily_ot_threshold_hours or 0.0)
    double_time_threshold = float(profile.double_time_threshold_hours or 0.0)

    if mode == "industry_specific":
        mode = str(profile.rules_json.get("base_mode") or "weekly_only").strip()

    if mode == "conditional_daily_plus_weekly" and not bool(profile.rules_json.get("daily_threshold_active")):
        mode = "weekly_only"

    seventh_day = (
        mode == "daily_8_plus_weekly_plus_7th_day"
        and day_date == week_start_date + timedelta(days=6)
        and all(week_start_date + timedelta(days=offset) in worked_day_dates for offset in range(7))
    )
    if seventh_day:
        ot_hours = min(day_hours, 8.0)
        dt_hours = max(day_hours - 8.0, 0.0)
        reason_codes.add("seventh_day_triggered")
        if dt_hours > 0:
            reason_codes.add("double_time_triggered")
        return max(day_hours - ot_hours - dt_hours, 0.0), round(ot_hours, 4), round(dt_hours, 4), reason_codes

    if mode in {"weekly_only"}:
        return round(day_hours, 4), 0.0, 0.0, reason_codes

    ot_hours = 0.0
    dt_hours = 0.0
    regular_hours = day_hours
    if daily_threshold > 0 and day_hours > daily_threshold:
        if double_time_threshold > 0 and day_hours > double_time_threshold:
            dt_hours = day_hours - double_time_threshold
            ot_hours = max(double_time_threshold - daily_threshold, 0.0)
            reason_codes.add("double_time_triggered")
        else:
            ot_hours = day_hours - daily_threshold
        regular_hours = max(day_hours - ot_hours - dt_hours, 0.0)
        reason_codes.add("daily_ot_triggered")

    return round(regular_hours, 4), round(ot_hours, 4), round(dt_hours, 4), reason_codes


def evaluate_overtime_projection(
    profile: LaborRuleProfileSnapshot | None,
    *,
    candidate_shift: Shift,
    counted_intervals: Sequence[CountedInterval],
    reference_time: datetime,
) -> dict[str, object]:
    if profile is None:
        return {
            "profile_code": None,
            "profile_version_id": None,
            "profile_payload_hash": None,
            "jurisdiction_code": None,
            "status": "unresolved",
            "projected_regular_hours": 0.0,
            "projected_ot_hours": 0.0,
            "projected_dt_hours": 0.0,
            "projected_total_hours": 0.0,
            "projected_max_day_hours": 0.0,
            "projected_cost_multiplier": 1.0,
            "reason_codes": ["no_matching_labor_rule_profile"],
            "evaluation_source": "no_profile_fallback",
            "evaluation_reference_time": reference_time.isoformat(),
        }

    workweek_start, workweek_end = workweek_window_for_shift(profile, shift=candidate_shift)
    projected_intervals = _merge_intervals([*counted_intervals, _candidate_interval(candidate_shift)])
    week_hours_total = _interval_duration_hours(
        _clip_intervals(projected_intervals, start_at=workweek_start, end_at=workweek_end)
    )
    hours_by_day = _hours_by_local_day(
        projected_intervals,
        shift_timezone=candidate_shift.timezone,
        window_start=workweek_start,
        window_end=workweek_end,
    )
    worked_day_dates = {day for day, hours in hours_by_day.items() if hours > 0}
    week_start_date = workweek_start.astimezone(ZoneInfo(candidate_shift.timezone)).date()

    total_regular = 0.0
    total_ot = 0.0
    total_dt = 0.0
    reason_codes: set[str] = set()
    for day_date, day_hours in sorted(hours_by_day.items()):
        regular_hours, ot_hours, dt_hours, day_reasons = _classify_day_hours(
            profile=profile,
            day_date=day_date,
            day_hours=day_hours,
            week_start_date=week_start_date,
            worked_day_dates=worked_day_dates,
        )
        total_regular += regular_hours
        total_ot += ot_hours
        total_dt += dt_hours
        reason_codes.update(day_reasons)

    weekly_threshold = float(profile.weekly_ot_threshold_hours or 0.0)
    if weekly_threshold > 0 and total_regular > weekly_threshold:
        weekly_extra = total_regular - weekly_threshold
        total_regular -= weekly_extra
        total_ot += weekly_extra
        reason_codes.add("weekly_ot_triggered")

    consecutive_threshold = float(profile.consecutive_hours_threshold_hours or 0.0)
    if consecutive_threshold > 0:
        longest_run = _longest_contiguous_run_hours(projected_intervals)
        if longest_run > consecutive_threshold:
            consecutive_extra = max(0.0, longest_run - consecutive_threshold)
            already_classified = total_ot + total_dt
            additional_ot = max(0.0, consecutive_extra - already_classified)
            if additional_ot > 0:
                total_regular = max(0.0, total_regular - additional_ot)
                total_ot += additional_ot
            reason_codes.add("consecutive_hours_triggered")

    weighted_cost = total_regular + (1.5 * total_ot) + (2.0 * total_dt)
    total_hours = total_regular + total_ot + total_dt
    projected_cost_multiplier = round(weighted_cost / total_hours, 4) if total_hours > 0 else 1.0

    status = "clear"
    if total_dt > 0:
        status = "high"
    elif total_ot > 0:
        status = "elevated"
    else:
        weekly_threshold = float(profile.weekly_ot_threshold_hours or 0.0)
        daily_threshold = float(profile.daily_ot_threshold_hours or 0.0)
        candidate_day_hours = hours_by_day.get(candidate_shift.starts_at.astimezone(ZoneInfo(candidate_shift.timezone)).date(), 0.0)
        if (
            (weekly_threshold > 0 and weekly_threshold - week_hours_total <= 4.0)
            or (daily_threshold > 0 and daily_threshold - candidate_day_hours <= 2.0)
        ):
            status = "watch"

    reason_codes_list = sorted(reason_codes) or ["no_overtime_triggered"]
    return {
        "profile_code": profile.code,
        "profile_version_id": str(profile.version_id),
        "profile_payload_hash": profile.payload_hash,
        "jurisdiction_code": profile.jurisdiction_code,
        "status": status,
        "projected_regular_hours": round(total_regular, 2),
        "projected_ot_hours": round(total_ot, 2),
        "projected_dt_hours": round(total_dt, 2),
        "projected_total_hours": round(total_hours, 2),
        "projected_max_day_hours": round(max(hours_by_day.values(), default=0.0), 2),
        "projected_cost_multiplier": round(projected_cost_multiplier, 4),
        "reason_codes": reason_codes_list,
        "evaluation_source": "deterministic_profile_engine",
        "evaluation_reference_time": reference_time.isoformat(),
    }


def overtime_multiplier_for_projection(
    projection: dict[str, object],
    *,
    apply_to_ranking: bool,
) -> float:
    if not apply_to_ranking:
        return 1.0
    cost_multiplier = _as_float(projection.get("projected_cost_multiplier")) or 1.0
    return round(max(0.4, min(1.0, 1.0 / cost_multiplier)), 4)


def legacy_overtime_risk_snapshot(projection: dict[str, object]) -> dict[str, object]:
    total_hours = (
        (_as_float(projection.get("projected_regular_hours")) or 0.0)
        + (_as_float(projection.get("projected_ot_hours")) or 0.0)
        + (_as_float(projection.get("projected_dt_hours")) or 0.0)
    )
    return {
        "status": projection.get("status") or "clear",
        "multiplier": overtime_multiplier_for_projection(
            projection,
            apply_to_ranking=labor_rules_primary_enabled(),
        ),
        "projected_hours": round(total_hours, 2),
    }


async def evaluate_employee_overtime_projection(
    session: AsyncSession,
    *,
    employee: Employee,
    shift: Shift,
    now: datetime | None = None,
) -> dict[str, object]:
    location = getattr(shift, "location", None)
    if location is None:
        location = SimpleNamespace(
            id=shift.location_id,
            region=None,
            country_code="US",
            timezone=shift.timezone,
            settings={},
        )
    business = getattr(location, "business", None)
    profile = await runtime_resolved_profile(
        session,
        location=location,
        business=business,
        as_of=now,
    )
    if profile is None:
        return evaluate_overtime_projection(None, candidate_shift=shift, counted_intervals=(), reference_time=now or datetime.now(timezone.utc))

    snapshots = await build_hours_snapshots(session, employees=[employee], shift=shift, profile=profile, now=now)
    snapshot = snapshots.get(employee.id)
    return evaluate_overtime_projection(
        profile,
        candidate_shift=shift,
        counted_intervals=snapshot.counted_intervals if snapshot is not None else (),
        reference_time=now or datetime.now(timezone.utc),
    )
