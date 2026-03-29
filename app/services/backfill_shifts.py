from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time, timedelta
from typing import Optional

import aiosqlite

from app.db import queries
from app.models.audit import AuditAction
from app.services import audit as audit_svc
from app.services import cascade as cascade_svc
from app.services import notifications as notifications_svc
from app.services import outreach as outreach_svc
from app.services import shift_manager

MAX_CSV_BYTES = 10 * 1024 * 1024
_PREVIEW_ROW_LIMIT = 5
_TIME_FORMATS = ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p")


def _trim_text(value: object | None) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_phone(value: object | None) -> Optional[str]:
    text = _trim_text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if text.startswith("+") and 10 <= len(digits) <= 15:
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def _parse_date(value: object | None) -> Optional[date]:
    text = _trim_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_time(value: object | None) -> Optional[time]:
    text = _trim_text(value)
    if not text:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text.upper(), fmt).time().replace(microsecond=0)
        except ValueError:
            continue
    return None


def _week_start_for(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _week_end_for(week_start: date) -> date:
    return week_start + timedelta(days=6)


def _serialize_schedule_template_shift(slot: dict) -> dict:
    return {
        "id": int(slot["id"]),
        "day_of_week": int(slot["day_of_week"]),
        "role": slot["role"],
        "start_time": slot["start_time"],
        "end_time": slot["end_time"],
        "spans_midnight": bool(slot.get("spans_midnight")),
        "pay_rate": float(slot.get("pay_rate") or 0.0),
        "requirements": list(slot.get("requirements") or []),
        "shift_label": slot.get("shift_label"),
        "notes": slot.get("notes"),
        "worker_id": slot.get("worker_id"),
        "worker_name": slot.get("worker_name"),
        "assignment_status": slot.get("assignment_status") or "open",
        "available_actions": ["edit", "duplicate", "delete"],
    }


def _time_to_minutes(value: str | time) -> int:
    parsed = _parse_time(value if isinstance(value, str) else value.strftime("%H:%M:%S"))
    assert parsed is not None
    return parsed.hour * 60 + parsed.minute


def _slot_duration_hours(slot: dict) -> float:
    start_minutes = _time_to_minutes(str(slot["start_time"]))
    end_minutes = _time_to_minutes(str(slot["end_time"]))
    if bool(slot.get("spans_midnight")) or end_minutes <= start_minutes:
        end_minutes += 24 * 60
    return round((end_minutes - start_minutes) / 60.0, 2)


def _slot_interval(slot: dict) -> tuple[int, int]:
    start_minutes = _time_to_minutes(str(slot["start_time"]))
    end_minutes = _time_to_minutes(str(slot["end_time"]))
    base = int(slot["day_of_week"]) * 24 * 60
    start_total = base + start_minutes
    end_total = base + end_minutes
    if bool(slot.get("spans_midnight")) or end_minutes <= start_minutes:
        end_total += 24 * 60
    return start_total, end_total


def _slot_worker_is_assigned(slot: dict) -> bool:
    return bool(
        slot.get("worker_id") is not None
        and slot.get("assignment_status") in {"assigned", "claimed", "confirmed"}
    )


def _normalize_day_of_week_filter(day_of_week_filter: list[int] | None) -> list[int]:
    if not day_of_week_filter:
        return []
    normalized = sorted({int(day) for day in day_of_week_filter})
    for day in normalized:
        if day < 0 or day > 6:
            raise ValueError("Day of week filter must be between 0 and 6")
    return normalized


def _normalize_assignment_strategy(assignment_strategy: str | None) -> str:
    strategy = (_trim_text(assignment_strategy) or "priority_first").lower().replace("-", "_")
    if strategy not in {"priority_first", "balance_hours", "minimize_overtime"}:
        raise ValueError(
            "Assignment strategy must be one of priority_first, balance_hours, minimize_overtime"
        )
    return strategy


def _template_worker_priority_rank(worker: dict) -> int:
    return int(
        worker.get("active_assignment", {}).get("priority_rank")
        or worker.get("priority_rank")
        or 9999
    )


def _template_suggestion_score(
    *,
    strategy: str,
    priority_rank: int,
    current_hours: float,
    remaining_after_assignment: float | None,
    would_exceed_max_hours: bool,
) -> tuple[float, dict]:
    priority_component = max(0.0, 100.0 - float(min(priority_rank, 100)))
    balance_component = max(0.0, 80.0 - float(current_hours))
    if remaining_after_assignment is None:
        capacity_component = 20.0
        no_cap_penalty = -25.0 if strategy == "minimize_overtime" else 0.0
    else:
        capacity_component = max(-40.0, float(remaining_after_assignment))
        no_cap_penalty = 0.0
    overtime_penalty = -1000.0 if would_exceed_max_hours else 0.0

    if strategy == "priority_first":
        total = priority_component * 100.0 + balance_component * 5.0 + capacity_component + overtime_penalty
    elif strategy == "balance_hours":
        total = balance_component * 100.0 + priority_component * 5.0 + capacity_component + overtime_penalty
    else:
        total = capacity_component * 100.0 + priority_component * 2.0 + balance_component + overtime_penalty + no_cap_penalty

    return round(total, 2), {
        "priority_component": round(priority_component, 2),
        "balance_component": round(balance_component, 2),
        "capacity_component": round(capacity_component, 2),
        "overtime_penalty": round(overtime_penalty + no_cap_penalty, 2),
        "total": round(total, 2),
    }


def _template_suggestion_confidence(
    *,
    rank: int,
    would_exceed_max_hours: bool,
    remaining_after_assignment: float | None,
) -> str:
    if would_exceed_max_hours:
        return "low"
    if rank == 1 and (remaining_after_assignment is None or remaining_after_assignment >= 4.0):
        return "high"
    if rank <= 3:
        return "medium"
    return "low"


def _build_template_worker_suggestions(
    *,
    slot: dict,
    candidates: list[dict],
    worker_assignments: dict[int, list[dict]],
    worker_hours: dict[int, float],
    worker_shift_counts: dict[int, int],
    assignment_strategy: str,
    limit: int = 5,
) -> list[dict]:
    strategy = _normalize_assignment_strategy(assignment_strategy)
    duration_hours = _slot_duration_hours(slot)
    suggestions: list[dict] = []

    for worker in candidates:
        if str(slot["role"]) not in (worker.get("eligible_roles") or []):
            continue
        worker_id = int(worker["id"])
        overlaps_existing = any(
            _template_slots_overlap(slot, assigned_slot)
            for assigned_slot in worker_assignments.get(worker_id, [])
        )
        if overlaps_existing:
            continue

        current_hours = round(float(worker_hours.get(worker_id, 0.0)), 2)
        projected_hours = round(current_hours + duration_hours, 2)
        max_hours = worker.get("max_hours_per_week")
        remaining_hours = (
            round(float(max_hours) - current_hours, 2)
            if max_hours is not None
            else None
        )
        remaining_after_assignment = (
            round(float(max_hours) - projected_hours, 2)
            if max_hours is not None
            else None
        )
        would_exceed_max_hours = bool(
            max_hours is not None and projected_hours > float(max_hours)
        )
        priority_rank = _template_worker_priority_rank(worker)
        score, score_breakdown = _template_suggestion_score(
            strategy=strategy,
            priority_rank=priority_rank,
            current_hours=current_hours,
            remaining_after_assignment=remaining_after_assignment,
            would_exceed_max_hours=would_exceed_max_hours,
        )
        suggestions.append(
            {
                "worker_id": worker_id,
                "worker_name": worker.get("name"),
                "priority_rank": priority_rank,
                "eligible_roles": list(worker.get("eligible_roles") or []),
                "max_hours_per_week": max_hours,
                "assigned_template_hours": current_hours,
                "assigned_shift_count": int(worker_shift_counts.get(worker_id, 0)),
                "projected_template_hours": projected_hours,
                "remaining_hours": remaining_hours,
                "remaining_hours_after_assignment": remaining_after_assignment,
                "would_exceed_max_hours": would_exceed_max_hours,
                "score": score,
                "score_breakdown": score_breakdown,
            }
        )

    if not suggestions:
        return []

    min_priority_rank = min(int(item["priority_rank"]) for item in suggestions)
    min_current_hours = min(float(item["assigned_template_hours"]) for item in suggestions)
    remaining_after_values = [
        float(item["remaining_hours_after_assignment"])
        for item in suggestions
        if item.get("remaining_hours_after_assignment") is not None
    ]
    max_remaining_after = max(remaining_after_values) if remaining_after_values else None
    strategy_reason = {
        "priority_first": "priority_preferred",
        "balance_hours": "hours_balance_preferred",
        "minimize_overtime": "overtime_risk_minimized",
    }[strategy]

    suggestions.sort(
        key=lambda item: (
            -float(item["score"]),
            int(item["priority_rank"]),
            float(item["assigned_template_hours"]),
            (item.get("worker_name") or "").lower(),
            int(item["worker_id"]),
        )
    )

    for index, item in enumerate(suggestions, start=1):
        reason_codes: list[str] = [strategy_reason]
        if index == 1:
            reason_codes.insert(0, "recommended")
        if int(item["priority_rank"]) == min_priority_rank:
            reason_codes.append("top_priority_rank")
        if float(item["assigned_template_hours"]) == min_current_hours:
            reason_codes.append("lightest_current_load")
        if (
            max_remaining_after is not None
            and item.get("remaining_hours_after_assignment") is not None
            and float(item["remaining_hours_after_assignment"]) == max_remaining_after
        ):
            reason_codes.append("most_remaining_capacity")
        if item["would_exceed_max_hours"]:
            reason_codes.append("would_exceed_max_hours")
        else:
            reason_codes.append("within_max_hours")
        if item.get("max_hours_per_week") is None:
            reason_codes.append("no_hour_cap_configured")

        item["rank"] = index
        item["reason_codes"] = reason_codes
        item["confidence"] = _template_suggestion_confidence(
            rank=index,
            would_exceed_max_hours=bool(item["would_exceed_max_hours"]),
            remaining_after_assignment=(
                float(item["remaining_hours_after_assignment"])
                if item.get("remaining_hours_after_assignment") is not None
                else None
            ),
        )

    return suggestions[:limit]


async def _build_template_warning_map(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    slots: list[dict],
) -> dict[int, list[dict]]:
    overlap_warnings_by_slot, _ = _collect_template_overlap_warnings(slots)
    warnings_by_slot: dict[int, list[dict]] = {}
    for slot in slots:
        warnings = await _build_template_slot_warnings(
            db,
            location_id=location_id,
            slot=slot,
        )
        warnings.extend(overlap_warnings_by_slot.get(int(slot["id"]), []))
        warnings_by_slot[int(slot["id"])] = warnings
    return warnings_by_slot


def _build_template_assignment_maps(
    *,
    slots: list[dict],
    warnings_by_slot: dict[int, list[dict]],
    exclude_shift_id: int | None = None,
) -> tuple[dict[int, list[dict]], dict[int, float], dict[int, int]]:
    worker_assignments: dict[int, list[dict]] = {}
    worker_hours: dict[int, float] = {}
    worker_shift_counts: dict[int, int] = {}
    for slot in slots:
        shift_id = int(slot["id"])
        if exclude_shift_id is not None and shift_id == exclude_shift_id:
            continue
        if not _slot_worker_is_assigned(slot) or warnings_by_slot.get(shift_id):
            continue
        worker_id = int(slot["worker_id"])
        worker_assignments.setdefault(worker_id, []).append(slot)
        worker_hours[worker_id] = round(
            worker_hours.get(worker_id, 0.0) + _slot_duration_hours(slot),
            2,
        )
        worker_shift_counts[worker_id] = worker_shift_counts.get(worker_id, 0) + 1
    return worker_assignments, worker_hours, worker_shift_counts


def _serialize_schedule_template(template: dict, slots: list[dict]) -> dict:
    serialized_slots = [_serialize_schedule_template_shift(slot) for slot in slots]
    assigned_shift_count = sum(
        1
        for slot in serialized_slots
        if slot.get("worker_id") is not None
        and slot.get("assignment_status") in {"assigned", "claimed", "confirmed"}
    )
    return {
        "id": int(template["id"]),
        "location_id": int(template["location_id"]),
        "name": template["name"],
        "description": template.get("description"),
        "source_schedule_id": template.get("source_schedule_id"),
        "created_by": template.get("created_by"),
        "created_at": template.get("created_at"),
        "updated_at": template.get("updated_at"),
        "shift_count": len(serialized_slots),
        "assigned_shift_count": assigned_shift_count,
        "shifts": serialized_slots,
    }


def _template_available_actions(*, template: dict, shift_count: int) -> list[str]:
    actions = ["edit", "clone", "delete", "add_shift"]
    if shift_count > 0:
        actions.extend(["preview", "apply", "apply_range"])
    if template.get("source_schedule_id"):
        actions.append("refresh")
    return actions


async def _build_template_slot_warnings(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    slot: dict,
) -> list[dict]:
    warnings: list[dict] = []
    worker_id = slot.get("worker_id")
    assignment_status = slot.get("assignment_status") or "open"
    if worker_id is None or assignment_status not in {"assigned", "claimed", "confirmed"}:
        return warnings

    worker = await queries.get_worker(db, int(worker_id))
    if worker is None:
        warnings.append(
            {
                "code": "worker_missing",
                "message": "Assigned worker no longer exists",
            }
        )
        return warnings

    if (worker.get("employment_status") or "active") != "active":
        warnings.append(
            {
                "code": "worker_inactive",
                "message": "Assigned worker is not active",
            }
        )
    if worker.get("location_id") != location_id:
        warnings.append(
            {
                "code": "worker_wrong_location",
                "message": "Assigned worker is not currently assigned to this location",
            }
        )
    if slot.get("role") not in (worker.get("roles") or []):
        warnings.append(
            {
                "code": "worker_role_mismatch",
                "message": "Assigned worker is not eligible for this role",
            }
        )
    return warnings


def _collect_template_overlap_warnings(slots: list[dict]) -> tuple[dict[int, list[dict]], list[dict]]:
    warnings_by_slot: dict[int, list[dict]] = {int(slot["id"]): [] for slot in slots}
    template_warnings: list[dict] = []
    for index, left in enumerate(slots):
        left_id = int(left["id"])
        left_start, left_end = _slot_interval(left)
        for right in slots[index + 1 :]:
            right_id = int(right["id"])
            right_start, right_end = _slot_interval(right)
            if max(left_start, right_start) >= min(left_end, right_end):
                continue
            warning = {
                "code": "template_overlap",
                "message": "Template shifts overlap in time",
                "conflicts_with_shift_id": right_id,
            }
            warnings_by_slot[left_id].append(warning)
            warnings_by_slot[right_id].append(
                {
                    "code": "template_overlap",
                    "message": "Template shifts overlap in time",
                    "conflicts_with_shift_id": left_id,
                }
            )
            template_warnings.append(
                {
                    "code": "template_overlap",
                    "message": "Template shifts overlap in time",
                    "shift_ids": sorted([left_id, right_id]),
                }
            )
    return warnings_by_slot, template_warnings


def _build_template_summaries(slots: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    daily: dict[int, dict] = {}
    roles: dict[str, dict] = {}
    workers: dict[int, dict] = {}

    for slot in slots:
        duration_hours = _slot_duration_hours(slot)
        assigned = _slot_worker_is_assigned(slot)
        day = int(slot["day_of_week"])
        role = str(slot["role"])

        daily_entry = daily.setdefault(
            day,
            {"day_of_week": day, "shift_count": 0, "assigned_shift_count": 0, "total_hours": 0.0},
        )
        daily_entry["shift_count"] += 1
        daily_entry["assigned_shift_count"] += 1 if assigned else 0
        daily_entry["total_hours"] = round(daily_entry["total_hours"] + duration_hours, 2)

        role_entry = roles.setdefault(
            role,
            {"role": role, "shift_count": 0, "assigned_shift_count": 0, "total_hours": 0.0},
        )
        role_entry["shift_count"] += 1
        role_entry["assigned_shift_count"] += 1 if assigned else 0
        role_entry["total_hours"] = round(role_entry["total_hours"] + duration_hours, 2)

        if assigned and slot.get("worker_id") is not None:
            worker_id = int(slot["worker_id"])
            worker_entry = workers.setdefault(
                worker_id,
                {
                    "worker_id": worker_id,
                    "worker_name": slot.get("worker_name"),
                    "shift_count": 0,
                    "total_hours": 0.0,
                },
            )
            worker_entry["shift_count"] += 1
            worker_entry["total_hours"] = round(worker_entry["total_hours"] + duration_hours, 2)

    return (
        [daily[key] for key in sorted(daily)],
        sorted(roles.values(), key=lambda item: (item["role"],)),
        sorted(workers.values(), key=lambda item: (item["worker_name"] or "", item["worker_id"])),
    )


async def _serialize_schedule_template_detail(
    db: aiosqlite.Connection,
    *,
    template: dict,
    slots: list[dict] | None = None,
) -> dict:
    template_slots = slots if slots is not None else await queries.list_schedule_template_shifts(db, int(template["id"]))
    overlap_warnings_by_slot, template_warnings = _collect_template_overlap_warnings(template_slots)
    daily_summary, role_summary, worker_summary = _build_template_summaries(template_slots)
    serialized_slots: list[dict] = []
    assigned_shift_count = 0
    unassigned_shift_count = 0
    invalid_assignment_count = 0
    warning_count = 0
    for slot in template_slots:
        slot_payload = _serialize_schedule_template_shift(slot)
        warnings = await _build_template_slot_warnings(
            db,
            location_id=int(template["location_id"]),
            slot=slot,
        )
        warnings.extend(overlap_warnings_by_slot.get(int(slot["id"]), []))
        slot_payload["warnings"] = warnings
        if _slot_worker_is_assigned(slot_payload):
            assigned_shift_count += 1
            if warnings:
                invalid_assignment_count += 1
        else:
            unassigned_shift_count += 1
        warning_count += len(warnings)
        serialized_slots.append(slot_payload)

    valid_assignment_count = max(assigned_shift_count - invalid_assignment_count, 0)
    return {
        "id": int(template["id"]),
        "location_id": int(template["location_id"]),
        "name": template["name"],
        "description": template.get("description"),
        "source_schedule_id": template.get("source_schedule_id"),
        "created_by": template.get("created_by"),
        "created_at": template.get("created_at"),
        "updated_at": template.get("updated_at"),
        "shift_count": len(serialized_slots),
        "assigned_shift_count": assigned_shift_count,
        "unassigned_shift_count": unassigned_shift_count,
        "available_actions": _template_available_actions(
            template=template,
            shift_count=len(serialized_slots),
        ),
        "validation_summary": {
            "warning_count": warning_count,
            "overlap_count": len(template_warnings),
            "invalid_assignment_count": invalid_assignment_count,
            "valid_assignment_count": valid_assignment_count,
            "unassigned_shift_count": unassigned_shift_count,
            "is_ready_to_apply": len(serialized_slots) > 0,
        },
        "template_warnings": template_warnings,
        "daily_summary": daily_summary,
        "role_summary": role_summary,
        "worker_summary": worker_summary,
        "shifts": serialized_slots,
    }


def _shift_start_datetime(shift: dict) -> Optional[datetime]:
    shift_date = shift.get("date")
    start_time = shift.get("start_time")
    if not shift_date or not start_time:
        return None
    try:
        return datetime.fromisoformat(f"{shift_date}T{start_time}")
    except ValueError:
        return None


def _normalize_target_field(value: object | None) -> Optional[str]:
    text = (_trim_text(value) or "").lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    aliases = {
        "name": "worker_name",
        "employee_name": "worker_name",
        "employee": "worker_name",
        "assigned_employee": "worker_name",
        "assigned_worker": "worker_name",
        "assigned_worker_name": "worker_name",
        "mobile": "phone",
        "mobile_number": "phone",
        "phone_number": "phone",
        "cell": "phone",
        "email_address": "email",
        "employee_id": "employee_id",
        "start": "start_time",
        "end": "end_time",
        "shift_notes": "notes",
        "label": "shift_label",
    }
    return aliases.get(text, text)


def _read_csv_text(csv_text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    columns = [col.strip() for col in (reader.fieldnames or []) if col and col.strip()]
    rows: list[dict[str, str]] = []
    for raw_row in reader:
        row: dict[str, str] = {}
        for key, value in raw_row.items():
            if key is None:
                continue
            row[key.strip()] = (value or "").strip()
        rows.append(row)
    return columns, rows


def _normalize_row_payload(row: dict[str, str], mapping: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for source_column, target_field in mapping.items():
        canonical = _normalize_target_field(target_field)
        if canonical is None:
            continue
        value = _trim_text(row.get(source_column))
        if value is not None:
            normalized[canonical] = value
    if "worker_name" not in normalized:
        first = normalized.get("first_name")
        last = normalized.get("last_name")
        full_name = " ".join(part for part in [first, last] if part)
        if full_name:
            normalized["worker_name"] = full_name
    return normalized


def _summarize_import_rows(total_rows: int, results: list[dict]) -> dict:
    return {
        "total_rows": total_rows,
        "worker_rows": sum(1 for row in results if row["entity_type"] == "worker"),
        "shift_rows": sum(1 for row in results if row["entity_type"] == "shift"),
        "success_rows": sum(1 for row in results if row["outcome"] == "success"),
        "warning_rows": sum(1 for row in results if row["outcome"] == "warning"),
        "failed_rows": sum(1 for row in results if row["outcome"] == "failed"),
        "skipped_rows": sum(1 for row in results if row["outcome"] == "skipped"),
        "committed_rows": sum(1 for row in results if row.get("committed_at")),
        "pending_rows": sum(1 for row in results if not row.get("committed_at")),
    }


def _validate_entity_payload(
    *,
    row_number: int,
    raw_row: dict[str, str],
    entity_type: str,
    payload: dict[str, str],
) -> dict:
    if entity_type == "shift":
        return _validate_shift_payload(row_number, raw_row, payload)
    return _validate_worker_payload(row_number, raw_row, payload)


def _normalize_override_payload(overrides: dict[str, str]) -> dict[str, Optional[str]]:
    normalized: dict[str, Optional[str]] = {}
    for key, value in overrides.items():
        canonical = _normalize_target_field(key) or key
        text = _trim_text(value)
        normalized[canonical] = text
    return normalized


def _derive_job_status(rows: list[dict]) -> str:
    pending_rows = [row for row in rows if not row.get("committed_at")]
    has_committed_rows = any(row.get("committed_at") for row in rows)
    if has_committed_rows:
        if any(row["outcome"] == "success" for row in pending_rows):
            return "validating"
        if any(row["outcome"] in {"warning", "failed", "skipped"} for row in pending_rows):
            return "partially_completed"
        return "completed"
    if any(row["outcome"] in {"warning", "failed"} for row in pending_rows):
        return "action_needed"
    if any(row["outcome"] in {"success", "skipped"} for row in pending_rows):
        return "validating"
    return "validating"


def _validate_worker_payload(row_number: int, raw_row: dict[str, str], payload: dict[str, str]) -> dict:
    worker_name = _trim_text(payload.get("worker_name"))
    role = _trim_text(payload.get("role"))
    phone = _normalize_phone(payload.get("phone"))
    if not worker_name:
        return {
            "row_number": row_number,
            "entity_type": "worker",
            "outcome": "failed",
            "error_code": "worker_name_missing",
            "error_message": "Worker name is required",
            "raw_payload": raw_row,
            "normalized_payload": None,
        }
    if not phone:
        return {
            "row_number": row_number,
            "entity_type": "worker",
            "outcome": "failed",
            "error_code": "phone_malformed",
            "error_message": "Phone number could not be normalized",
            "raw_payload": raw_row,
            "normalized_payload": None,
        }
    if not role:
        return {
            "row_number": row_number,
            "entity_type": "worker",
            "outcome": "failed",
            "error_code": "role_missing",
            "error_message": "Role is required",
            "raw_payload": raw_row,
            "normalized_payload": None,
        }
    first_name, _, last_name = worker_name.partition(" ")
    normalized_payload = {
        "name": worker_name,
        "first_name": payload.get("first_name") or first_name,
        "last_name": payload.get("last_name") or (last_name or None),
        "phone": phone,
        "email": _trim_text(payload.get("email")),
        "role": role,
        "employee_id": _trim_text(payload.get("employee_id")),
        "employment_status": _trim_text(payload.get("employment_status")) or "active",
        "max_hours_per_week": _trim_text(payload.get("max_hours_per_week")),
    }
    return {
        "row_number": row_number,
        "entity_type": "worker",
        "outcome": "success",
        "error_code": None,
        "error_message": None,
        "raw_payload": raw_row,
        "normalized_payload": normalized_payload,
    }


def _validate_shift_payload(row_number: int, raw_row: dict[str, str], payload: dict[str, str]) -> dict:
    shift_date = _parse_date(payload.get("date"))
    start_time = _parse_time(payload.get("start_time"))
    end_time = _parse_time(payload.get("end_time"))
    role = _trim_text(payload.get("role"))
    if shift_date is None:
        return {
            "row_number": row_number,
            "entity_type": "shift",
            "outcome": "failed",
            "error_code": "date_invalid",
            "error_message": "Shift date must be a valid date",
            "raw_payload": raw_row,
            "normalized_payload": None,
        }
    if start_time is None or end_time is None:
        return {
            "row_number": row_number,
            "entity_type": "shift",
            "outcome": "failed",
            "error_code": "time_invalid",
            "error_message": "Start and end times must be valid times",
            "raw_payload": raw_row,
            "normalized_payload": None,
        }
    spans_midnight = False
    if end_time == start_time:
        return {
            "row_number": row_number,
            "entity_type": "shift",
            "outcome": "failed",
            "error_code": "time_range_invalid",
            "error_message": "Shift end time must differ from start time",
            "raw_payload": raw_row,
            "normalized_payload": None,
        }
    if end_time < start_time:
        spans_midnight = True
    if not role:
        return {
            "row_number": row_number,
            "entity_type": "shift",
            "outcome": "failed",
            "error_code": "role_missing",
            "error_message": "Shift role is required",
            "raw_payload": raw_row,
            "normalized_payload": None,
        }

    normalized_payload = {
        "role": role,
        "date": shift_date.isoformat(),
        "start_time": start_time.strftime("%H:%M:%S"),
        "end_time": end_time.strftime("%H:%M:%S"),
        "spans_midnight": spans_midnight,
        "week_start_date": _week_start_for(shift_date).isoformat(),
        "worker_name": _trim_text(payload.get("worker_name")),
        "phone": _trim_text(payload.get("phone")),
        "email": _trim_text(payload.get("email")),
        "notes": _trim_text(payload.get("notes")),
        "shift_label": _trim_text(payload.get("shift_label")),
    }
    pay_rate = _trim_text(payload.get("pay_rate"))
    if pay_rate is not None:
        try:
            normalized_payload["pay_rate"] = float(pay_rate)
        except ValueError:
            return {
                "row_number": row_number,
                "entity_type": "shift",
                "outcome": "failed",
                "error_code": "pay_rate_invalid",
                "error_message": "Pay rate must be numeric when supplied",
                "raw_payload": raw_row,
                "normalized_payload": None,
            }

    worker_phone = normalized_payload.get("phone")
    warning_code = None
    warning_message = None
    if worker_phone:
        normalized_phone = _normalize_phone(worker_phone)
        if normalized_phone is None:
            warning_code = "assigned_worker_unresolved"
            warning_message = "Assigned worker phone number could not be normalized"
            normalized_payload["phone"] = None
        else:
            normalized_payload["phone"] = normalized_phone
    elif normalized_payload.get("worker_name"):
        warning_code = "assigned_worker_unresolved"
        warning_message = "Assigned worker is missing a resolvable phone number"

    return {
        "row_number": row_number,
        "entity_type": "shift",
        "outcome": "warning" if warning_code else "success",
        "error_code": warning_code,
        "error_message": warning_message,
        "raw_payload": raw_row,
        "normalized_payload": normalized_payload,
    }


def _validate_import_row(row_number: int, raw_row: dict[str, str], mapping: dict[str, str]) -> dict:
    payload = _normalize_row_payload(raw_row, mapping)
    if any(payload.get(key) for key in ("date", "start_time", "end_time")):
        return _validate_shift_payload(row_number, raw_row, payload)
    if any(payload.get(key) for key in ("worker_name", "first_name", "last_name", "phone", "email")):
        return _validate_worker_payload(row_number, raw_row, payload)
    return {
        "row_number": row_number,
        "entity_type": "worker",
        "outcome": "failed",
        "error_code": "mapping_empty",
        "error_message": "Mapped row does not contain a recognizable worker or shift payload",
        "raw_payload": raw_row,
        "normalized_payload": None,
    }


def _enforce_single_week(results: list[dict]) -> None:
    week_starts = sorted(
        {
            row["normalized_payload"]["week_start_date"]
            for row in results
            if row["entity_type"] == "shift"
            and row["outcome"] in {"success", "warning"}
            and row.get("normalized_payload")
            and row["normalized_payload"].get("week_start_date")
        }
    )
    if len(week_starts) <= 1:
        return
    primary_week = week_starts[0]
    for row in results:
        payload = row.get("normalized_payload") or {}
        if row["entity_type"] != "shift":
            continue
        if payload.get("week_start_date") == primary_week:
            continue
        row["outcome"] = "failed"
        row["error_code"] = "multiple_schedule_weeks"
        row["error_message"] = "This import currently supports a single schedule week per commit"


async def _build_schedule_snapshot(db: aiosqlite.Connection, schedule_id: int) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    shifts = await queries.list_shifts(db, schedule_id=schedule_id)
    assignments = await queries.list_shift_assignments_for_schedule(db, schedule_id)
    assignment_by_shift = {row["shift_id"]: row for row in assignments}
    return {
        "schedule": schedule,
        "shifts": [
            _serialize_schedule_shift_payload(
                shift=shift,
                assignment=assignment_by_shift.get(shift["id"]),
                active_cascade=None,
                pending_claim_worker=None,
            )
            for shift in shifts
        ],
    }


def _serialize_assignment_payload(assignment: dict | None, *, shift: dict) -> dict:
    source = assignment.get("source") if assignment else None
    assignment_status = assignment.get("assignment_status", "open") if assignment else "open"
    worker_id = assignment.get("worker_id") if assignment else None
    filled_via_backfill = bool(
        source == "coverage_engine"
        and worker_id is not None
        and assignment_status in {"claimed", "confirmed"}
        and (
            shift.get("called_out_by") is not None
            or shift.get("confirmation_escalated_at") is not None
            or shift.get("check_in_escalated_at") is not None
        )
    )
    return {
        "worker_id": worker_id,
        "worker_name": assignment.get("worker_name") if assignment else None,
        "assignment_status": assignment_status,
        "source": source,
        "filled_via_backfill": filled_via_backfill,
    }


def _serialize_coverage_payload(
    *,
    shift: dict,
    assignment: dict | None,
    active_cascade: dict | None,
    pending_claim_worker: dict | None = None,
) -> dict:
    assignment_payload = _serialize_assignment_payload(assignment, shift=shift)
    vacancy_kind = outreach_svc.vacancy_kind(shift)
    requires_fill_approval = bool(
        active_cascade is not None and active_cascade.get("pending_claim_worker_id") is not None
    )
    requires_agency_approval = bool(
        active_cascade is not None
        and not requires_fill_approval
        and int(active_cascade.get("current_tier") or 1) >= 3
        and not active_cascade.get("manager_approved_tier3")
    )
    if requires_fill_approval:
        status = "awaiting_manager_approval"
    elif active_cascade is not None:
        status = "active"
    elif assignment_payload["assignment_status"] == "closed":
        status = "closed"
    elif assignment_payload["filled_via_backfill"]:
        status = "backfilled"
    else:
        status = "none"
    return {
        "is_active": active_cascade is not None,
        "status": status,
        "vacancy_kind": vacancy_kind,
        "cascade_id": active_cascade.get("id") if active_cascade else None,
        "manager_action_required": bool(requires_fill_approval or requires_agency_approval),
        "pending_action": (
            "approve_fill"
            if requires_fill_approval
            else "approve_agency"
            if requires_agency_approval
            else None
        ),
        "current_tier": active_cascade.get("current_tier") if active_cascade else None,
        "claimed_by_worker_id": active_cascade.get("pending_claim_worker_id") if active_cascade else None,
        "claimed_by_worker_name": pending_claim_worker.get("name") if pending_claim_worker else None,
        "claimed_at": active_cascade.get("pending_claim_at") if active_cascade else None,
        "called_out_by": shift.get("called_out_by"),
        "filled_by": shift.get("filled_by"),
        "filled_via_backfill": assignment_payload["filled_via_backfill"],
    }


def _serialize_confirmation_payload(
    shift: dict,
    assignment: dict | None,
) -> dict:
    assignment_status = assignment.get("assignment_status") if assignment else None
    has_assigned_worker = bool(
        assignment
        and assignment.get("worker_id") is not None
        and assignment_status in {"assigned", "claimed", "confirmed"}
    )
    if shift.get("confirmation_escalated_at") and (
        not has_assigned_worker or shift.get("status") in {"vacant", "filling", "unfilled"}
    ):
        status = "escalated"
    elif not has_assigned_worker:
        status = "not_applicable"
    elif shift.get("worker_confirmed_at"):
        status = "confirmed"
    elif shift.get("worker_declined_at"):
        status = "declined"
    elif shift.get("confirmation_requested_at"):
        status = "pending"
    else:
        status = "not_requested"
    return {
        "status": status,
        "requested_at": shift.get("confirmation_requested_at"),
        "confirmed_at": shift.get("worker_confirmed_at"),
        "declined_at": shift.get("worker_declined_at"),
        "escalated_at": shift.get("confirmation_escalated_at"),
    }


def _serialize_attendance_payload(
    shift: dict,
    assignment: dict | None,
) -> dict:
    assignment_status = assignment.get("assignment_status") if assignment else None
    has_assigned_worker = bool(
        assignment
        and assignment.get("worker_id") is not None
        and assignment_status in {"assigned", "claimed", "confirmed"}
    )
    if shift.get("checked_in_at"):
        status = "checked_in"
    elif shift.get("check_in_escalated_at") and (
        not has_assigned_worker or shift.get("status") in {"vacant", "filling", "unfilled"}
    ):
        status = "escalated"
    elif shift.get("late_reported_at"):
        status = "late"
    elif not has_assigned_worker:
        status = "not_applicable"
    elif shift.get("check_in_escalated_at"):
        status = "escalated"
    elif shift.get("check_in_requested_at"):
        status = "pending"
    else:
        status = "not_requested"
    return {
        "status": status,
        "requested_at": shift.get("check_in_requested_at"),
        "checked_in_at": shift.get("checked_in_at"),
        "late_reported_at": shift.get("late_reported_at"),
        "late_eta_minutes": shift.get("late_eta_minutes"),
        "escalated_at": shift.get("check_in_escalated_at"),
        "action_state": shift.get("attendance_action_state"),
    }


def _derive_schedule_shift_available_actions(
    *,
    shift: dict,
    assignment: dict,
    coverage: dict,
) -> list[str]:
    vacancy_kind = coverage.get("vacancy_kind") or outreach_svc.vacancy_kind(shift)
    if vacancy_kind != "open_shift":
        return []

    assignment_status = assignment.get("assignment_status")
    pending_action = coverage.get("pending_action")
    coverage_status = coverage.get("status")
    if assignment_status == "closed":
        return ["reopen_shift", "reopen_and_offer"]
    if pending_action == "approve_fill":
        return ["approve_fill", "decline_fill", "close_shift"]
    if pending_action == "approve_agency":
        return ["approve_agency", "cancel_offer", "close_shift"]
    if coverage_status == "active":
        return ["cancel_offer", "close_shift"]
    if assignment_status == "open":
        return ["start_coverage", "close_shift"]
    return []


def _serialize_schedule_shift_payload(
    *,
    shift: dict,
    assignment: dict | None,
    active_cascade: dict | None,
    pending_claim_worker: dict | None = None,
) -> dict:
    assignment_payload = _serialize_assignment_payload(assignment, shift=shift)
    confirmation_payload = _serialize_confirmation_payload(shift, assignment)
    attendance_payload = _serialize_attendance_payload(shift, assignment)
    coverage_payload = _serialize_coverage_payload(
        shift=shift,
        assignment=assignment,
        active_cascade=active_cascade,
        pending_claim_worker=pending_claim_worker,
    )
    return {
        **shift,
        "assignment": assignment_payload,
        "confirmation": confirmation_payload,
        "attendance": attendance_payload,
        "coverage": coverage_payload,
        "available_actions": _derive_schedule_shift_available_actions(
            shift=shift,
            assignment=assignment_payload,
            coverage=coverage_payload,
        ),
    }


def _summarize_outreach_attempts(attempts: list[dict]) -> dict:
    offered_workers: set[int] = set()
    responded_workers: set[int] = set()
    last_outreach_at: str | None = None
    last_response_at: str | None = None

    for attempt in attempts:
        worker_id = attempt.get("worker_id")
        if worker_id is not None:
            offered_workers.add(int(worker_id))
            if attempt.get("responded_at") or attempt.get("outcome") is not None:
                responded_workers.add(int(worker_id))

        sent_at = attempt.get("sent_at")
        if sent_at and (last_outreach_at is None or str(sent_at) > last_outreach_at):
            last_outreach_at = str(sent_at)

        responded_at = attempt.get("responded_at")
        if responded_at and (last_response_at is None or str(responded_at) > last_response_at):
            last_response_at = str(responded_at)

    return {
        "offered_worker_count": len(offered_workers),
        "responded_worker_count": len(responded_workers),
        "last_outreach_at": last_outreach_at,
        "last_response_at": last_response_at,
    }


def _derive_coverage_status(
    *,
    shift: dict,
    assignment: dict | None,
    active_cascade: dict | None,
) -> str:
    if active_cascade is not None:
        if active_cascade.get("pending_claim_worker_id") is not None:
            return "awaiting_manager_approval"
        if int(active_cascade.get("current_tier") or 1) >= 3:
            return (
                "agency_routing"
                if active_cascade.get("manager_approved_tier3")
                else "awaiting_agency_approval"
            )
        return "offering"

    if assignment and assignment.get("assignment_status") == "closed":
        return "closed"
    if shift.get("status") == "unfilled":
        return "unfilled"
    if not assignment or assignment.get("assignment_status") == "open":
        return "unassigned"
    return str(shift.get("status") or "unassigned")


async def _get_pending_claim_worker(
    db: aiosqlite.Connection,
    active_cascade: dict | None,
) -> dict | None:
    if not active_cascade or not active_cascade.get("pending_claim_worker_id"):
        return None
    return await queries.get_worker(db, int(active_cascade["pending_claim_worker_id"]))


async def _build_coverage_entry(
    db: aiosqlite.Connection,
    *,
    shift: dict,
    assignment: dict | None = None,
    cascade: dict | None = None,
) -> dict:
    assignment = assignment if assignment is not None else await queries.get_shift_assignment_with_worker(db, int(shift["id"]))
    cascade = cascade if cascade is not None else await queries.get_active_cascade_for_shift(db, int(shift["id"]))
    attempts = await queries.list_outreach_attempts(
        db,
        cascade_id=int(cascade["id"]) if cascade else None,
        shift_id=None if cascade else int(shift["id"]),
    )
    outreach_summary = _summarize_outreach_attempts(attempts)
    pending_claim_worker = await _get_pending_claim_worker(db, cascade)
    coverage_status = _derive_coverage_status(
        shift=shift,
        assignment=assignment,
        active_cascade=cascade,
    )
    return {
        "shift_id": shift["id"],
        "role": shift["role"],
        "date": shift["date"],
        "start_time": shift["start_time"],
        "current_status": shift["status"],
        "cascade_id": cascade.get("id") if cascade else None,
        "coverage_status": coverage_status,
        "current_tier": cascade.get("current_tier") if cascade else None,
        "outreach_mode": cascade.get("outreach_mode") if cascade else None,
        "manager_action_required": coverage_status in {"awaiting_manager_approval", "awaiting_agency_approval"},
        "standby_depth": len(cascade.get("standby_queue") or []) if cascade else 0,
        "confirmed_worker_id": cascade.get("confirmed_worker_id") if cascade else None,
        "claimed_by_worker_id": cascade.get("pending_claim_worker_id") if cascade else None,
        "claimed_by_worker_name": pending_claim_worker.get("name") if pending_claim_worker else None,
        "claimed_at": cascade.get("pending_claim_at") if cascade else None,
        **outreach_summary,
    }


async def _create_schedule_version(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    version_type: str,
    published_by: Optional[str] = None,
    change_summary: Optional[dict] = None,
) -> int:
    snapshot = await _build_schedule_snapshot(db, schedule_id)
    version_number = await queries.get_next_schedule_version_number(db, schedule_id)
    published_at = datetime.utcnow().isoformat() if version_type == "publish_snapshot" else None
    return await queries.insert_schedule_version(
        db,
        {
            "schedule_id": schedule_id,
            "version_number": version_number,
            "version_type": version_type,
            "snapshot_json": snapshot,
            "change_summary_json": change_summary or {},
            "published_at": published_at,
            "published_by": published_by,
        },
    )


async def _refresh_import_job_state(
    db: aiosqlite.Connection,
    *,
    job_id: int,
) -> tuple[dict, list[dict], int]:
    rows = await queries.list_import_row_results(db, job_id)
    summary = _summarize_import_rows(len(rows), rows)
    action_needed_count = sum(
        1 for row in rows if not row.get("committed_at") and row["outcome"] in {"warning", "failed"}
    )
    await queries.update_import_job(
        db,
        job_id,
        {
            "status": _derive_job_status(rows),
            "summary_json": summary,
        },
    )
    return summary, rows, action_needed_count


async def _upsert_worker_from_payload(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    payload: dict,
) -> tuple[int, bool]:
    phone = payload["phone"]
    role = _trim_text(payload.get("role"))
    existing = await queries.get_worker_by_phone(db, phone)
    if existing is None:
        worker_id = await queries.insert_worker(
            db,
            {
                "name": payload["name"],
                "first_name": payload.get("first_name"),
                "last_name": payload.get("last_name"),
                "phone": phone,
                "email": payload.get("email"),
                "roles": [role] if role else [],
                "location_id": location_id,
                "source": "csv_import",
                "employment_status": payload.get("employment_status"),
                "max_hours_per_week": (
                    int(payload["max_hours_per_week"]) if payload.get("max_hours_per_week") else None
                ),
            },
        )
        return worker_id, True

    roles = list(existing.get("roles") or [])
    if role and role not in roles:
        roles.append(role)
    updates = {
        "name": payload.get("name") or existing.get("name"),
        "first_name": payload.get("first_name") or existing.get("first_name"),
        "last_name": payload.get("last_name") or existing.get("last_name"),
        "email": payload.get("email") or existing.get("email"),
        "roles": roles,
        "location_id": existing.get("location_id") or location_id,
        "employment_status": payload.get("employment_status") or existing.get("employment_status"),
    }
    if payload.get("max_hours_per_week"):
        updates["max_hours_per_week"] = int(payload["max_hours_per_week"])
    await queries.update_worker(db, int(existing["id"]), updates)
    return int(existing["id"]), False


async def _resolve_shift_assignment_worker(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    payload: dict,
) -> tuple[Optional[int], bool]:
    phone = payload.get("phone")
    worker_name = payload.get("worker_name")
    if phone:
        existing = await queries.get_worker_by_phone(db, phone)
        if existing is not None:
            return int(existing["id"]), False
        if worker_name:
            worker_id, created = await _upsert_worker_from_payload(
                db,
                location_id=location_id,
                payload={
                    "name": worker_name,
                    "first_name": worker_name.split()[0],
                    "last_name": " ".join(worker_name.split()[1:]) or None,
                    "phone": phone,
                    "email": payload.get("email"),
                    "role": payload.get("role"),
                    "employment_status": "active",
                },
            )
            return worker_id, created
    return None, False


def _summarize_attendance_exception(
    attendance: dict,
    *,
    late_policy: str,
    missed_policy: str,
) -> dict:
    status = attendance.get("status")
    action_state = attendance.get("action_state")
    late_arrivals = 1 if status == "late" else 0
    late_arrivals_awaiting_decision = (
        1 if status == "late" and late_policy == "manager_action" and action_state != "waiting_for_worker" else 0
    )
    missed_check_ins = 1 if status == "escalated" else 0
    missed_check_ins_awaiting_decision = (
        1
        if status == "escalated" and missed_policy == "manager_action" and action_state != "waiting_for_worker"
        else 0
    )
    missed_check_ins_escalated = max(0, missed_check_ins - missed_check_ins_awaiting_decision)
    return {
        "attendance_issues": 1 if status in {"late", "escalated"} else 0,
        "late_arrivals": late_arrivals,
        "late_arrivals_awaiting_decision": late_arrivals_awaiting_decision,
        "missed_check_ins": missed_check_ins,
        "missed_check_ins_awaiting_decision": missed_check_ins_awaiting_decision,
        "missed_check_ins_escalated": missed_check_ins_escalated,
    }


def _build_schedule_exception(
    *,
    shift: dict,
    exception_type: str,
    code: str,
    message: str,
    severity: str,
    action_required: bool,
    available_actions: list[str] | None = None,
) -> dict:
    assignment = shift.get("assignment") or {}
    coverage = shift.get("coverage") or {}
    attendance = shift.get("attendance") or {}
    shift_id = int(shift["id"])
    return {
        "exception_id": f"{code}:{shift_id}",
        "type": exception_type,
        "code": code,
        "severity": severity,
        "action_required": action_required,
        "available_actions": list(available_actions or []),
        "shift_id": shift_id,
        "role": shift.get("role"),
        "date": shift.get("date"),
        "start_time": shift.get("start_time"),
        "message": message,
        "current_status": shift.get("status"),
        "assignment_status": assignment.get("assignment_status"),
        "cascade_id": coverage.get("cascade_id"),
        "pending_action": coverage.get("pending_action"),
        "coverage_status": coverage.get("status"),
        "vacancy_kind": coverage.get("vacancy_kind"),
        "attendance_status": attendance.get("status"),
        "worker_id": assignment.get("worker_id"),
        "worker_name": assignment.get("worker_name"),
        "claimed_by_worker_id": coverage.get("claimed_by_worker_id"),
        "claimed_by_worker_name": coverage.get("claimed_by_worker_name"),
        "late_eta_minutes": attendance.get("late_eta_minutes"),
    }


def _schedule_view_summary(
    shifts: list[dict],
    *,
    location: dict | None = None,
) -> tuple[dict, list[dict]]:
    exceptions: list[dict] = []
    filled_shifts = 0
    open_shifts = 0
    at_risk_shifts = 0
    attendance_issues = 0
    late_arrivals = 0
    late_arrivals_awaiting_decision = 0
    missed_check_ins = 0
    missed_check_ins_awaiting_decision = 0
    missed_check_ins_escalated = 0
    late_policy = (location or {}).get("late_arrival_policy") or "wait"
    missed_policy = (location or {}).get("missed_check_in_policy") or "start_coverage"
    for shift in shifts:
        assignment = shift.get("assignment") or {}
        attendance = shift.get("attendance") or {}
        coverage = shift.get("coverage") or {}
        assignment_status = assignment.get("assignment_status")
        vacancy_kind = coverage.get("vacancy_kind") or outreach_svc.vacancy_kind(shift)
        if shift.get("status") in {"vacant", "filling", "unfilled"}:
            at_risk_shifts += 1
        if coverage.get("pending_action") == "approve_fill":
            claimed_name = coverage.get("claimed_by_worker_name") or "A worker"
            available_actions = ["approve_fill", "decline_fill"]
            if vacancy_kind == "open_shift":
                available_actions.append("close_shift")
            exceptions.append(
                _build_schedule_exception(
                    shift=shift,
                    exception_type="coverage",
                    code="coverage_fill_approval_required",
                    message=f"{claimed_name} is waiting for manager approval to cover this shift.",
                    severity="critical",
                    action_required=True,
                    available_actions=available_actions,
                )
            )
        elif coverage.get("pending_action") == "approve_agency":
            available_actions = ["approve_agency"]
            if vacancy_kind == "open_shift":
                available_actions.extend(["cancel_offer", "close_shift"])
            exceptions.append(
                _build_schedule_exception(
                    shift=shift,
                    exception_type="coverage",
                    code="coverage_agency_approval_required",
                    message="Agency routing is waiting for manager approval.",
                    severity="critical",
                    action_required=True,
                    available_actions=available_actions,
                )
            )
        elif coverage.get("status") == "active":
            available_actions = ["cancel_offer", "close_shift"] if vacancy_kind == "open_shift" else []
            exceptions.append(
                _build_schedule_exception(
                    shift=shift,
                    exception_type="coverage",
                    code="coverage_active",
                    message=f"Coverage is active for {shift['role']} on {shift['date']}",
                    severity="critical",
                    action_required=False,
                    available_actions=available_actions,
                )
            )
        if assignment.get("worker_id") and assignment_status in {"assigned", "claimed", "confirmed"}:
            filled_shifts += 1
        elif assignment_status != "closed":
            open_shifts += 1
            if coverage.get("status") not in {"active", "awaiting_manager_approval"}:
                available_actions = ["start_coverage"]
                if vacancy_kind == "open_shift":
                    available_actions.append("close_shift")
                exceptions.append(
                    _build_schedule_exception(
                        shift=shift,
                        exception_type="open_shift",
                        code="open_shift_unassigned",
                        message=f"No assignee found for {shift['role']} on {shift['date']}",
                        severity="warning",
                        action_required=True,
                        available_actions=available_actions,
                    )
                )
        attendance_summary = _summarize_attendance_exception(
            attendance,
            late_policy=late_policy,
            missed_policy=missed_policy,
        )
        attendance_issues += attendance_summary["attendance_issues"]
        late_arrivals += attendance_summary["late_arrivals"]
        late_arrivals_awaiting_decision += attendance_summary["late_arrivals_awaiting_decision"]
        missed_check_ins += attendance_summary["missed_check_ins"]
        missed_check_ins_awaiting_decision += attendance_summary["missed_check_ins_awaiting_decision"]
        missed_check_ins_escalated += attendance_summary["missed_check_ins_escalated"]
        if attendance.get("status") == "late":
            message = f"Late arrival reported for {shift['role']} on {shift['date']}"
            code = "late_arrival_reported"
            action_required = False
            if attendance_summary["late_arrivals_awaiting_decision"]:
                message = f"Late arrival needs manager review for {shift['role']} on {shift['date']}"
                code = "late_arrival_needs_review"
                action_required = True
            exceptions.append(
                _build_schedule_exception(
                    shift=shift,
                    exception_type="attendance",
                    code=code,
                    message=message,
                    severity="warning",
                    action_required=action_required,
                    available_actions=["wait_for_worker", "start_coverage"] if action_required else [],
                )
            )
        elif attendance.get("status") == "escalated":
            message = f"Missed check-in escalated for {shift['role']} on {shift['date']}"
            code = "missed_check_in_escalated"
            action_required = False
            if attendance_summary["missed_check_ins_awaiting_decision"]:
                message = f"Missed check-in needs manager review for {shift['role']} on {shift['date']}"
                code = "missed_check_in_needs_review"
                action_required = True
            exceptions.append(
                _build_schedule_exception(
                    shift=shift,
                    exception_type="attendance",
                    code=code,
                    message=message,
                    severity="critical",
                    action_required=action_required,
                    available_actions=["wait_for_worker", "start_coverage"] if action_required else [],
                )
            )
    exceptions.sort(
        key=lambda item: (
            0 if item.get("action_required") else 1,
            0 if item.get("severity") == "critical" else 1,
            str(item.get("date") or ""),
            str(item.get("start_time") or ""),
            int(item.get("shift_id") or 0),
            str(item.get("code") or ""),
        )
    )
    return (
        {
            "filled_shifts": filled_shifts,
            "open_shifts": open_shifts,
            "at_risk_shifts": at_risk_shifts,
            "attendance_issues": attendance_issues,
            "late_arrivals": late_arrivals,
            "late_arrivals_awaiting_decision": late_arrivals_awaiting_decision,
            "missed_check_ins": missed_check_ins,
            "missed_check_ins_awaiting_decision": missed_check_ins_awaiting_decision,
            "missed_check_ins_escalated": missed_check_ins_escalated,
            "action_required_count": sum(1 for item in exceptions if item.get("action_required")),
            "critical_count": sum(1 for item in exceptions if item.get("severity") == "critical"),
            "warning_count": len(exceptions),
        },
        exceptions,
    )


def _build_schedule_publish_readiness(
    *,
    schedule: dict | None,
    summary: dict,
    exceptions: list[dict],
) -> dict:
    lifecycle_state = (schedule or {}).get("lifecycle_state")
    fatal_exception_codes = {
        "coverage_fill_approval_required",
        "coverage_agency_approval_required",
        "late_arrival_needs_review",
        "missed_check_in_needs_review",
    }

    blockers: list[dict] = []
    warnings: list[dict] = []
    for item in exceptions:
        payload = {
            "code": item.get("code"),
            "message": item.get("message"),
            "severity": item.get("severity"),
            "action_required": bool(item.get("action_required")),
            "shift_id": item.get("shift_id"),
            "available_actions": list(item.get("available_actions") or []),
        }
        if payload["code"] in fatal_exception_codes:
            blockers.append(payload)
        else:
            warnings.append(payload)

    state_reason = None
    if schedule is None:
        state_reason = "no_schedule"
        blockers.append(
            {
                "code": "no_schedule",
                "message": "No schedule exists yet for this review surface.",
                "severity": "critical",
                "action_required": True,
                "shift_id": None,
                "available_actions": [],
            }
        )
    elif lifecycle_state == "archived":
        state_reason = "schedule_archived"
        blockers.append(
            {
                "code": "schedule_archived",
                "message": "Archived schedules cannot be published.",
                "severity": "critical",
                "action_required": True,
                "shift_id": None,
                "available_actions": [],
            }
        )
    elif lifecycle_state == "published":
        state_reason = "already_published"
    elif int(summary.get("filled_shifts", 0) or 0) + int(summary.get("open_shifts", 0) or 0) <= 0:
        state_reason = "no_shifts_in_schedule"
        blockers.append(
            {
                "code": "no_shifts_in_schedule",
                "message": "Schedules need at least one shift before publish.",
                "severity": "critical",
                "action_required": True,
                "shift_id": None,
                "available_actions": [],
            }
        )

    can_publish = bool(
        schedule is not None
        and lifecycle_state in {"draft", "amended", "recalled"}
        and not blockers
    )
    status_label = (
        "ready"
        if can_publish
        else "already_live"
        if state_reason == "already_published"
        else "blocked"
    )
    if can_publish:
        status_message = "Schedule is ready to publish."
    elif state_reason == "already_published":
        status_message = "Schedule is already published."
    elif blockers:
        status_message = f"{len(blockers)} blocking issue{'s' if len(blockers) != 1 else ''} need review before publish."
    else:
        status_message = "Schedule needs review before publish."

    return {
        "can_publish": can_publish,
        "lifecycle_state": lifecycle_state,
        "state_reason": state_reason,
        "status_label": status_label,
        "status_message": status_message,
        "blocking_issue_count": len(blockers),
        "warning_issue_count": len(warnings),
        "blocker_codes": [item["code"] for item in blockers],
        "warning_codes": [item["code"] for item in warnings],
        "blockers": blockers,
        "warnings": warnings[:10],
    }


def _schedule_shift_day_of_week(shift: dict) -> int:
    shift_date = shift.get("date")
    if shift_date:
        return date.fromisoformat(str(shift_date)).weekday()
    return int(shift.get("day_of_week") or 0)


def _schedule_shift_assignment(shift: dict) -> dict:
    assignment = shift.get("assignment")
    if assignment is not None:
        return dict(assignment)
    worker_id = shift.get("worker_id")
    assignment_status = shift.get("assignment_status") or ("assigned" if worker_id is not None else "open")
    return {
        "worker_id": worker_id,
        "worker_name": shift.get("worker_name"),
        "assignment_status": assignment_status,
    }


def _schedule_shift_pattern_signature(shift: dict) -> tuple:
    return (
        _schedule_shift_day_of_week(shift),
        str(shift.get("start_time") or ""),
        str(shift.get("end_time") or ""),
        str(shift.get("role") or ""),
        str(shift.get("shift_label") or ""),
        bool(shift.get("spans_midnight")),
    )


def _schedule_shift_weekly_pattern_signature(shift: dict) -> tuple:
    return (
        _schedule_shift_day_of_week(shift),
        str(shift.get("start_time") or ""),
        str(shift.get("end_time") or ""),
        str(shift.get("shift_label") or ""),
        bool(shift.get("spans_midnight")),
    )


def _schedule_shift_display_label(shift: dict) -> str:
    role = shift.get("role") or "shift"
    shift_date = shift.get("date")
    start_time = str(shift.get("start_time") or "")
    if shift_date:
        return f"{role} on {_format_short_day(str(shift_date))} at {start_time[:5]}"
    return f"{role} at {start_time[:5]}"


def _schedule_shift_sort_key(shift: dict) -> tuple:
    return (
        str(shift.get("date") or ""),
        str(shift.get("start_time") or ""),
        str(shift.get("role") or ""),
        int(shift.get("id") or 0),
    )


def _build_schedule_change_item(
    *,
    code: str,
    message: str,
    current_shift: dict | None = None,
    baseline_shift: dict | None = None,
) -> dict:
    current_assignment = _schedule_shift_assignment(current_shift or {})
    baseline_assignment = _schedule_shift_assignment(baseline_shift or {})
    return {
        "code": code,
        "message": message,
        "shift_id": current_shift.get("id") if current_shift else None,
        "baseline_shift_id": baseline_shift.get("id") if baseline_shift else None,
        "current": {
            "date": current_shift.get("date") if current_shift else None,
            "start_time": current_shift.get("start_time") if current_shift else None,
            "end_time": current_shift.get("end_time") if current_shift else None,
            "role": current_shift.get("role") if current_shift else None,
            "worker_id": current_assignment.get("worker_id"),
            "worker_name": current_assignment.get("worker_name"),
            "assignment_status": current_assignment.get("assignment_status"),
        },
        "baseline": {
            "date": baseline_shift.get("date") if baseline_shift else None,
            "start_time": baseline_shift.get("start_time") if baseline_shift else None,
            "end_time": baseline_shift.get("end_time") if baseline_shift else None,
            "role": baseline_shift.get("role") if baseline_shift else None,
            "worker_id": baseline_assignment.get("worker_id"),
            "worker_name": baseline_assignment.get("worker_name"),
            "assignment_status": baseline_assignment.get("assignment_status"),
        },
    }


def _compare_schedule_shift_pair(
    current_shift: dict,
    baseline_shift: dict,
    *,
    compare_mode: str,
) -> list[dict]:
    changes: list[dict] = []
    current_assignment = _schedule_shift_assignment(current_shift)
    baseline_assignment = _schedule_shift_assignment(baseline_shift)
    current_worker_id = current_assignment.get("worker_id")
    baseline_worker_id = baseline_assignment.get("worker_id")

    if (
        str(current_shift.get("role") or "")
        != str(baseline_shift.get("role") or "")
    ):
        changes.append(
            _build_schedule_change_item(
                code="role_changed",
                message=(
                    f"Role changed from {baseline_shift.get('role') or 'shift'} "
                    f"to {current_shift.get('role') or 'shift'} for "
                    f"{_schedule_shift_display_label(current_shift)}"
                ),
                current_shift=current_shift,
                baseline_shift=baseline_shift,
            )
        )
    if (
        str(current_shift.get("start_time") or "") != str(baseline_shift.get("start_time") or "")
        or str(current_shift.get("end_time") or "") != str(baseline_shift.get("end_time") or "")
        or bool(current_shift.get("spans_midnight")) != bool(baseline_shift.get("spans_midnight"))
        or (
            compare_mode == "same_schedule"
            and str(current_shift.get("date") or "") != str(baseline_shift.get("date") or "")
        )
    ):
        changes.append(
            _build_schedule_change_item(
                code="timing_changed",
                message=(
                    f"Timing changed for {current_shift.get('role') or baseline_shift.get('role') or 'shift'} "
                    f"from {str(baseline_shift.get('start_time') or '')[:5]}-{str(baseline_shift.get('end_time') or '')[:5]} "
                    f"to {str(current_shift.get('start_time') or '')[:5]}-{str(current_shift.get('end_time') or '')[:5]}"
                ),
                current_shift=current_shift,
                baseline_shift=baseline_shift,
            )
        )

    if baseline_assignment.get("assignment_status") == "closed" and current_assignment.get("assignment_status") != "closed":
        changes.append(
            _build_schedule_change_item(
                code="shift_reopened",
                message=f"Reopened {_schedule_shift_display_label(current_shift)}",
                current_shift=current_shift,
                baseline_shift=baseline_shift,
            )
        )
    elif baseline_assignment.get("assignment_status") != "closed" and current_assignment.get("assignment_status") == "closed":
        changes.append(
            _build_schedule_change_item(
                code="shift_closed",
                message=f"Closed {_schedule_shift_display_label(current_shift)}",
                current_shift=current_shift,
                baseline_shift=baseline_shift,
            )
        )

    if baseline_worker_id is None and current_worker_id is not None:
        changes.append(
            _build_schedule_change_item(
                code="shift_filled",
                message=f"Filled {_schedule_shift_display_label(current_shift)} with {current_assignment.get('worker_name') or 'a worker'}",
                current_shift=current_shift,
                baseline_shift=baseline_shift,
            )
        )
    elif baseline_worker_id is not None and current_worker_id is None:
        changes.append(
            _build_schedule_change_item(
                code="shift_opened",
                message=f"Opened {_schedule_shift_display_label(current_shift)}",
                current_shift=current_shift,
                baseline_shift=baseline_shift,
            )
        )
    elif (
        baseline_worker_id is not None
        and current_worker_id is not None
        and int(baseline_worker_id) != int(current_worker_id)
    ):
        changes.append(
            _build_schedule_change_item(
                code="assignment_changed",
                message=(
                    f"Reassigned {_schedule_shift_display_label(current_shift)} from "
                    f"{baseline_assignment.get('worker_name') or 'one worker'} to "
                    f"{current_assignment.get('worker_name') or 'another worker'}"
                ),
                current_shift=current_shift,
                baseline_shift=baseline_shift,
            )
        )
    return changes


def _summarize_schedule_change_items(change_items: list[dict]) -> dict:
    counts = {
        "added_shift_count": sum(1 for item in change_items if item["code"] == "shift_added"),
        "removed_shift_count": sum(1 for item in change_items if item["code"] == "shift_removed"),
        "reassigned_count": sum(1 for item in change_items if item["code"] == "assignment_changed"),
        "opened_shift_count": sum(1 for item in change_items if item["code"] == "shift_opened"),
        "filled_shift_count": sum(1 for item in change_items if item["code"] == "shift_filled"),
        "role_change_count": sum(1 for item in change_items if item["code"] == "role_changed"),
        "timing_change_count": sum(1 for item in change_items if item["code"] == "timing_changed"),
        "closed_shift_count": sum(1 for item in change_items if item["code"] == "shift_closed"),
        "reopened_shift_count": sum(1 for item in change_items if item["code"] == "shift_reopened"),
    }
    counts["total_change_count"] = len(change_items)
    counts["has_changes"] = len(change_items) > 0
    return counts


def _build_schedule_change_highlights(*, basis_label: str, counts: dict) -> list[str]:
    highlights: list[str] = []
    if counts["added_shift_count"]:
        highlights.append(f"{counts['added_shift_count']} shift{'s' if counts['added_shift_count'] != 1 else ''} added")
    if counts["removed_shift_count"]:
        highlights.append(f"{counts['removed_shift_count']} shift{'s' if counts['removed_shift_count'] != 1 else ''} removed")
    if counts["reassigned_count"]:
        highlights.append(f"{counts['reassigned_count']} reassignment{'s' if counts['reassigned_count'] != 1 else ''}")
    if counts["opened_shift_count"]:
        highlights.append(f"{counts['opened_shift_count']} shift{'s' if counts['opened_shift_count'] != 1 else ''} reopened to coverage")
    if counts["filled_shift_count"]:
        highlights.append(f"{counts['filled_shift_count']} open shift{'s' if counts['filled_shift_count'] != 1 else ''} filled")
    if counts["timing_change_count"]:
        highlights.append(f"{counts['timing_change_count']} timing change{'s' if counts['timing_change_count'] != 1 else ''}")
    if counts["role_change_count"]:
        highlights.append(f"{counts['role_change_count']} role change{'s' if counts['role_change_count'] != 1 else ''}")
    if counts["closed_shift_count"]:
        highlights.append(f"{counts['closed_shift_count']} shift{'s' if counts['closed_shift_count'] != 1 else ''} closed")
    if counts["reopened_shift_count"]:
        highlights.append(f"{counts['reopened_shift_count']} shift{'s' if counts['reopened_shift_count'] != 1 else ''} reopened")
    if not highlights:
        highlights.append(f"No major changes from {basis_label}.")
    return highlights


def _format_short_day(iso_date: str) -> str:
    parsed = date.fromisoformat(iso_date)
    return f"{parsed.strftime('%a')} {parsed.strftime('%b')} {parsed.day}"


def _should_include_in_manager_digest(
    shift: dict,
    *,
    assignment: dict | None,
    cascade: dict | None,
    now: datetime,
    window_end: datetime,
    recent_issue_lookback_hours: int = 2,
) -> bool:
    shift_start_at = _shift_start_datetime(shift)
    if shift_start_at is None or shift_start_at > window_end:
        return False
    if shift_start_at >= now:
        return True
    if shift_start_at < now - timedelta(hours=recent_issue_lookback_hours):
        return False

    assignment_payload = _serialize_assignment_payload(assignment, shift=shift)
    attendance_payload = _serialize_attendance_payload(shift, assignment)
    is_open = (
        shift.get("status") in {"vacant", "filling", "unfilled"}
        or assignment_payload.get("worker_id") is None
    )
    return bool(
        is_open
        or cascade is not None
        or attendance_payload.get("status") in {"late", "escalated"}
    )


def _describe_import_review_item(row: dict) -> str:
    payload = row.get("normalized_payload") or {}
    worker_name = payload.get("worker_name")
    role = payload.get("role")
    shift_date = payload.get("date")
    error_code = row.get("error_code")

    if error_code == "assigned_worker_unresolved":
        if worker_name and role and shift_date:
            return f"{worker_name} could not be matched for {role} on {_format_short_day(shift_date)}"
        if worker_name:
            return f"{worker_name} could not be matched to a shift"
        return "an assigned worker could not be matched"
    if error_code == "phone_malformed":
        if worker_name:
            return f"phone number needs review for {worker_name}"
        return "a phone number needs review"
    if error_code == "role_missing":
        return "a role is missing on one import row"
    if error_code == "date_missing":
        return "a shift date is missing on one import row"
    if error_code == "time_range_invalid":
        return "a shift time range needs review"
    if error_code == "multiple_weeks_unsupported":
        return "this import spans more than one schedule week"

    message = _trim_text(row.get("error_message"))
    if message:
        return message[0].lower() + message[1:] if len(message) > 1 else message.lower()
    return "an import row needs review"


def _describe_schedule_review_item(exception: dict, shifts_by_id: dict[int, dict]) -> str:
    shift = shifts_by_id.get(int(exception.get("shift_id") or 0))
    if shift is None:
        return exception.get("message") or "a shift needs review"
    role = shift.get("role") or "shift"
    shift_day = _format_short_day(shift["date"])
    code = exception.get("code")
    if code == "coverage_fill_approval_required":
        worker_name = exception.get("claimed_by_worker_name") or "a worker"
        return f"{worker_name} needs approval to cover {role} on {shift_day}"
    if code == "coverage_agency_approval_required":
        return f"agency routing needs approval for {role} on {shift_day}"
    if code == "late_arrival_needs_review":
        return f"late arrival needs review for {role} on {shift_day}"
    if code == "missed_check_in_needs_review":
        return f"missed check-in needs review for {role} on {shift_day}"
    if exception.get("type") == "coverage":
        return f"coverage is active for {role} on {shift_day}"
    if exception.get("type") == "attendance":
        if code == "missed_check_in_escalated":
            return f"missed check-in escalated for {role} on {shift_day}"
        return f"arrival is running late for {role} on {shift_day}"
    return f"{role} is still open on {shift_day}"


def _build_exception_group(
    *,
    key: str,
    label: str,
    items: list[dict],
) -> dict:
    return {
        "key": key,
        "label": label,
        "count": len(items),
        "items": items,
    }


def _build_schedule_exception_queue_payload(
    *,
    location_id: int,
    schedule: dict | None,
    items: list[dict],
    action_required_only: bool,
) -> dict:
    action_required_items = [item for item in items if item.get("action_required")]
    critical_items = [item for item in items if item.get("severity") == "critical"]
    coverage_items = [item for item in items if item.get("type") == "coverage"]
    attendance_items = [item for item in items if item.get("type") == "attendance"]
    open_shift_items = [item for item in items if item.get("type") == "open_shift"]

    groups: list[dict] = []
    if action_required_items:
        groups.append(
            _build_exception_group(
                key="action_required",
                label="Needs action",
                items=action_required_items,
            )
        )
    if coverage_items:
        groups.append(
            _build_exception_group(
                key="coverage",
                label="Coverage",
                items=coverage_items,
            )
        )
    if attendance_items:
        groups.append(
            _build_exception_group(
                key="attendance",
                label="Attendance",
                items=attendance_items,
            )
        )
    if open_shift_items:
        groups.append(
            _build_exception_group(
                key="open_shifts",
                label="Open shifts",
                items=open_shift_items,
            )
        )

    return {
        "location_id": location_id,
        "schedule": schedule,
        "filters": {
            "action_required_only": action_required_only,
        },
        "summary": {
            "total_items": len(items),
            "action_required": len(action_required_items),
            "critical": len(critical_items),
            "coverage": len(coverage_items),
            "attendance": len(attendance_items),
            "open_shifts": len(open_shift_items),
        },
        "groups": groups,
        "items": items,
    }


def _collect_manager_review_items(schedule_view: dict, import_rows: list[dict]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()

    for row in import_rows:
        if row.get("committed_at") is not None:
            continue
        if row.get("outcome") not in {"warning", "failed"}:
            continue
        item = _describe_import_review_item(row)
        if item not in seen:
            seen.add(item)
            items.append(item)

    shifts_by_id = {int(shift["id"]): shift for shift in schedule_view.get("shifts") or []}
    for exception in schedule_view.get("exceptions") or []:
        item = _describe_schedule_review_item(exception, shifts_by_id)
        if item not in seen:
            seen.add(item)
            items.append(item)

    return items


def _get_first_pending_review_row(rows: list[dict]) -> Optional[dict]:
    return next(
        (
            row
            for row in rows
            if row.get("committed_at") is None and row.get("outcome") in {"warning", "failed"}
        ),
        None,
    )


async def _load_enriched_schedule_shifts(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
) -> list[dict]:
    shifts = await queries.list_shifts(db, schedule_id=schedule_id)
    enriched_shifts: list[dict] = []
    for shift in shifts:
        assignment = await queries.get_shift_assignment_with_worker(db, int(shift["id"]))
        active_cascade = await queries.get_active_cascade_for_shift(db, int(shift["id"]))
        pending_claim_worker = await _get_pending_claim_worker(db, active_cascade)
        enriched_shifts.append(
            _serialize_schedule_shift_payload(
                shift=shift,
                assignment=assignment,
                active_cascade=active_cascade,
                pending_claim_worker=pending_claim_worker,
            )
        )
    return enriched_shifts


async def _select_schedule_change_basis(
    db: aiosqlite.Connection,
    *,
    schedule: dict,
) -> dict:
    versions = await queries.list_schedule_versions(db, int(schedule["id"]))
    publish_versions = [item for item in versions if item.get("version_type") == "publish_snapshot"]
    if publish_versions:
        latest_publish = publish_versions[-1]
        snapshot = dict(latest_publish.get("snapshot_json") or {})
        return {
            "basis_type": "published_version",
            "basis_label": "last published version",
            "basis_schedule_id": int(schedule["id"]),
            "basis_version_id": int(latest_publish["id"]),
            "basis_week_start_date": schedule.get("week_start_date"),
            "comparison_mode": "same_schedule",
            "shifts": list(snapshot.get("shifts") or []),
        }

    derived_from_schedule_id = schedule.get("derived_from_schedule_id")
    if derived_from_schedule_id is not None:
        source_schedule = await queries.get_schedule(db, int(derived_from_schedule_id))
        if source_schedule is not None:
            return {
                "basis_type": "derived_schedule",
                "basis_label": "source schedule",
                "basis_schedule_id": int(source_schedule["id"]),
                "basis_version_id": None,
                "basis_week_start_date": source_schedule.get("week_start_date"),
                "comparison_mode": "weekly_pattern",
                "shifts": await _load_enriched_schedule_shifts(
                    db,
                    schedule_id=int(source_schedule["id"]),
                ),
            }

    schedules = await queries.list_schedules_for_location(db, int(schedule["location_id"]))
    current_week_start = str(schedule.get("week_start_date") or "")
    for candidate in schedules:
        if int(candidate["id"]) == int(schedule["id"]):
            continue
        if str(candidate.get("week_start_date") or "") >= current_week_start:
            continue
        candidate_shifts = await queries.list_shifts(db, schedule_id=int(candidate["id"]))
        if not candidate_shifts:
            continue
        return {
            "basis_type": "previous_schedule",
            "basis_label": "previous schedule",
            "basis_schedule_id": int(candidate["id"]),
            "basis_version_id": None,
            "basis_week_start_date": candidate.get("week_start_date"),
            "comparison_mode": "weekly_pattern",
            "shifts": await _load_enriched_schedule_shifts(
                db,
                schedule_id=int(candidate["id"]),
            ),
        }

    return {
        "basis_type": "none",
        "basis_label": "no baseline",
        "basis_schedule_id": None,
        "basis_version_id": None,
        "basis_week_start_date": None,
        "comparison_mode": "none",
        "shifts": [],
    }


def _sort_pattern_group(shifts: list[dict]) -> list[dict]:
    return sorted(
        shifts,
        key=lambda shift: (
            1 if _schedule_shift_assignment(shift).get("worker_id") is None else 0,
            str(_schedule_shift_assignment(shift).get("worker_name") or ""),
            int(_schedule_shift_assignment(shift).get("worker_id") or 0),
            _schedule_shift_sort_key(shift),
        ),
    )


def _empty_schedule_change_summary(
    *,
    basis: dict,
    highlight: str,
    first_publish: bool = False,
) -> dict:
    return {
        "basis": {k: v for k, v in basis.items() if k != "shifts"},
        "summary": {
            "added_shift_count": 0,
            "removed_shift_count": 0,
            "reassigned_count": 0,
            "opened_shift_count": 0,
            "filled_shift_count": 0,
            "role_change_count": 0,
            "timing_change_count": 0,
            "closed_shift_count": 0,
            "reopened_shift_count": 0,
            "total_change_count": 0,
            "has_changes": False,
        },
        "highlights": [highlight],
        "changes": [],
        "first_publish": first_publish,
        "has_prior_publish": not first_publish,
    }


async def _build_schedule_change_summary_for_basis(
    *,
    basis: dict,
    current_shifts: list[dict],
) -> dict:
    comparison_mode = basis["comparison_mode"]
    baseline_shifts = list(basis["shifts"] or [])
    if comparison_mode == "none":
        return _empty_schedule_change_summary(
            basis=basis,
            highlight="No comparison baseline is available yet.",
        )

    change_items: list[dict] = []
    if comparison_mode == "same_schedule":
        current_by_id = {int(shift["id"]): shift for shift in current_shifts}
        baseline_by_id = {int(shift["id"]): shift for shift in baseline_shifts if shift.get("id") is not None}
        matched_ids = sorted(set(current_by_id) & set(baseline_by_id))
        for shift_id in matched_ids:
            change_items.extend(
                _compare_schedule_shift_pair(
                    current_by_id[shift_id],
                    baseline_by_id[shift_id],
                    compare_mode=comparison_mode,
                )
            )
        for shift_id in sorted(set(current_by_id) - set(baseline_by_id)):
            current_shift = current_by_id[shift_id]
            change_items.append(
                _build_schedule_change_item(
                    code="shift_added",
                    message=f"Added {_schedule_shift_display_label(current_shift)}",
                    current_shift=current_shift,
                )
            )
        for shift_id in sorted(set(baseline_by_id) - set(current_by_id)):
            baseline_shift = baseline_by_id[shift_id]
            change_items.append(
                _build_schedule_change_item(
                    code="shift_removed",
                    message=f"Removed {_schedule_shift_display_label(baseline_shift)}",
                    baseline_shift=baseline_shift,
                )
            )
    else:
        current_groups: dict[tuple, list[dict]] = {}
        baseline_groups: dict[tuple, list[dict]] = {}
        for shift in current_shifts:
            current_groups.setdefault(_schedule_shift_weekly_pattern_signature(shift), []).append(shift)
        for shift in baseline_shifts:
            baseline_groups.setdefault(_schedule_shift_weekly_pattern_signature(shift), []).append(shift)
        all_keys = sorted(set(current_groups) | set(baseline_groups))
        for key in all_keys:
            current_group = _sort_pattern_group(current_groups.get(key, []))
            baseline_group = _sort_pattern_group(baseline_groups.get(key, []))
            matched_count = min(len(current_group), len(baseline_group))
            for index in range(matched_count):
                change_items.extend(
                    _compare_schedule_shift_pair(
                        current_group[index],
                        baseline_group[index],
                        compare_mode=comparison_mode,
                    )
                )
            for shift in current_group[matched_count:]:
                change_items.append(
                    _build_schedule_change_item(
                        code="shift_added",
                        message=f"Added {_schedule_shift_display_label(shift)}",
                        current_shift=shift,
                    )
                )
            for shift in baseline_group[matched_count:]:
                change_items.append(
                    _build_schedule_change_item(
                        code="shift_removed",
                        message=f"Removed {_schedule_shift_display_label(shift)}",
                        baseline_shift=shift,
                    )
                )

    change_items.sort(
        key=lambda item: (
            str((item.get("current") or {}).get("date") or (item.get("baseline") or {}).get("date") or ""),
            str((item.get("current") or {}).get("start_time") or (item.get("baseline") or {}).get("start_time") or ""),
            str(item.get("code") or ""),
            int(item.get("shift_id") or item.get("baseline_shift_id") or 0),
        )
    )
    summary = _summarize_schedule_change_items(change_items)
    return {
        "basis": {k: v for k, v in basis.items() if k != "shifts"},
        "summary": summary,
        "highlights": _build_schedule_change_highlights(
            basis_label=str(basis["basis_label"]),
            counts=summary,
        ),
        "changes": change_items,
        "first_publish": False,
        "has_prior_publish": True,
    }


async def _build_schedule_change_summary(
    db: aiosqlite.Connection,
    *,
    schedule: dict,
    current_shifts: list[dict],
    basis_override: dict | None = None,
) -> dict:
    basis = basis_override or await _select_schedule_change_basis(db, schedule=schedule)
    return await _build_schedule_change_summary_for_basis(
        basis=basis,
        current_shifts=current_shifts,
    )


async def _select_schedule_publish_diff_basis(
    db: aiosqlite.Connection,
    *,
    schedule: dict,
) -> dict:
    versions = await queries.list_schedule_versions(db, int(schedule["id"]))
    publish_versions = [item for item in versions if item.get("version_type") == "publish_snapshot"]
    if not publish_versions:
        return {
            "basis_type": "none",
            "basis_label": "first publish",
            "basis_schedule_id": None,
            "basis_version_id": None,
            "basis_week_start_date": None,
            "comparison_mode": "none",
            "shifts": [],
            "empty_highlight": "This will be the first published version of this schedule.",
            "first_publish": True,
        }

    latest_publish = publish_versions[-1]
    snapshot = dict(latest_publish.get("snapshot_json") or {})
    return {
        "basis_type": "last_published_version",
        "basis_label": "last published schedule",
        "basis_schedule_id": int(schedule["id"]),
        "basis_version_id": int(latest_publish["id"]),
        "basis_week_start_date": schedule.get("week_start_date"),
        "comparison_mode": "same_schedule",
        "shifts": list(snapshot.get("shifts") or []),
        "empty_highlight": "No changes from the last published schedule.",
        "first_publish": False,
    }


async def _build_schedule_publish_diff_summary(
    db: aiosqlite.Connection,
    *,
    schedule: dict,
    current_shifts: list[dict],
) -> dict:
    basis = await _select_schedule_publish_diff_basis(db, schedule=schedule)
    if basis["comparison_mode"] == "none":
        payload = _empty_schedule_change_summary(
            basis=basis,
            highlight=str(basis.get("empty_highlight") or "No published baseline is available yet."),
            first_publish=bool(basis.get("first_publish")),
        )
    else:
        payload = await _build_schedule_change_summary_for_basis(
            basis=basis,
            current_shifts=current_shifts,
        )
        payload["first_publish"] = False
        payload["has_prior_publish"] = True
    payload["worker_impact"] = await _build_worker_impact_payload(
        db,
        target_shifts=current_shifts,
        basis_shifts=list(basis.get("shifts") or []),
    )
    return payload


async def _build_schedule_draft_rationale(
    db: aiosqlite.Connection,
    *,
    schedule: dict | None,
    location: dict | None,
    summary: dict,
    change_summary: dict,
    publish_diff: dict,
) -> dict:
    if schedule is None:
        return {
            "headline": "No schedule draft exists yet.",
            "origin_type": "none",
            "origin_reference": None,
            "narrative": "Create, import, or generate a schedule to see draft rationale.",
            "recommended_checks": [],
        }

    versions = await queries.list_schedule_versions(db, int(schedule["id"]))
    first_version = versions[0] if versions else None
    origin_change = dict(first_version.get("change_summary_json") or {}) if first_version else {}
    origin_type = "manual"
    origin_reference: dict | None = None

    if origin_change.get("event") == "schedule_template_applied":
        template_id = origin_change.get("template_id")
        template = await queries.get_schedule_template(db, int(template_id)) if template_id else None
        origin_type = "template"
        origin_reference = {
            "template_id": int(template_id) if template_id else None,
            "template_name": template.get("name") if template else None,
        }
        headline = "Built from a saved weekly template."
        template_label = template.get("name") if template else f"template {template_id}"
        narrative = (
            f"This draft started from {template_label} for "
            f"{str(schedule.get('week_start_date'))}."
        )
    elif origin_change.get("event") == "ai_schedule_draft_generated" and origin_change.get("source_schedule_id"):
        source_schedule_id = int(origin_change["source_schedule_id"])
        source_schedule = await queries.get_schedule(db, source_schedule_id)
        origin_type = "schedule"
        origin_reference = {
            "schedule_id": source_schedule_id,
            "week_start_date": source_schedule.get("week_start_date") if source_schedule else None,
        }
        headline = "Built from a prior schedule pattern."
        narrative = (
            f"This draft started from the week of "
            f"{source_schedule.get('week_start_date') if source_schedule else source_schedule_id} "
            f"and generated a new week for {schedule.get('week_start_date')}."
        )
    elif schedule.get("derived_from_schedule_id"):
        source_schedule = await queries.get_schedule(db, int(schedule["derived_from_schedule_id"]))
        origin_type = "schedule_copy"
        origin_reference = {
            "schedule_id": int(schedule["derived_from_schedule_id"]),
            "week_start_date": source_schedule.get("week_start_date") if source_schedule else None,
        }
        headline = "Built by copying an earlier schedule."
        narrative = (
            f"This draft was copied from the week of "
            f"{source_schedule.get('week_start_date') if source_schedule else schedule['derived_from_schedule_id']}."
        )
    elif change_summary["basis"]["basis_type"] == "previous_schedule":
        origin_type = "previous_schedule"
        origin_reference = {
            "schedule_id": change_summary["basis"].get("basis_schedule_id"),
            "week_start_date": change_summary["basis"].get("basis_week_start_date"),
        }
        headline = "Built from the most recent prior schedule."
        narrative = (
            f"This draft follows the most recent earlier week at "
            f"{location.get('name') if location else 'this location'}."
        )
    else:
        headline = "Built as a net-new schedule draft."
        narrative = "This draft was created directly in Backfill Shifts without a saved baseline."

    recommended_checks: list[str] = []
    if change_summary["summary"].get("reassigned_count"):
        recommended_checks.append("Confirm the reassigned shifts still match worker availability.")
    if change_summary["summary"].get("timing_change_count"):
        recommended_checks.append("Spot-check the shifts with updated times before publishing.")
    if summary.get("open_shifts"):
        recommended_checks.append("Decide whether to leave open shifts unassigned or start outreach.")
    if publish_diff.get("has_prior_publish") and publish_diff["summary"].get("has_changes"):
        recommended_checks.append("Review what employees will receive as an updated schedule.")
    if not recommended_checks:
        recommended_checks.append("Spot-check assignments and shift times before publishing.")

    return {
        "headline": headline,
        "origin_type": origin_type,
        "origin_reference": origin_reference,
        "narrative": narrative,
        "recommended_checks": recommended_checks,
    }


async def _build_schedule_message_preview(
    db: aiosqlite.Connection,
    *,
    location: dict | None,
    schedule: dict | None,
    summary: dict,
    review_items: list[str],
    publish_readiness: dict,
    publish_diff: dict,
    current_shifts: list[dict] | None = None,
) -> dict:
    if location is None or schedule is None:
        return {
            "review_link": None,
            "draft_ready": None,
            "publish_success": None,
            "publish_blocked": None,
        }

    review_link = notifications_svc.build_manager_dashboard_link(
        int(location["id"]),
        tab="schedule",
        week_start=str(schedule["week_start_date"]),
    )
    total_shifts = int(summary.get("filled_shifts", 0) or 0) + int(summary.get("open_shifts", 0) or 0)
    shifts = list(current_shifts or [])
    if not shifts:
        shifts = await _load_enriched_schedule_shifts(db, schedule_id=int(schedule["id"]))
    sms_sent = 0
    sms_removed_sent = 0
    not_enrolled = 0
    publish_mode = "initial"
    if publish_diff.get("has_prior_publish"):
        publish_mode = "update" if publish_diff["summary"].get("has_changes") else "republish"
    worker_impact_items = list((publish_diff.get("worker_impact") or {}).get("workers") or [])
    if publish_mode == "update" and worker_impact_items:
        for item in worker_impact_items:
            worker_id = item.get("worker_id")
            if worker_id is None:
                continue
            worker = await queries.get_worker(db, int(worker_id))
            if worker is None or not worker.get("phone"):
                continue
            if worker.get("sms_consent_status") != "granted":
                if item.get("status") in {"updated_in_both", "added_to_target", "removed_from_target"}:
                    not_enrolled += 1
                continue
            if item.get("status") in {"updated_in_both", "added_to_target"}:
                sms_sent += 1
            elif item.get("status") == "removed_from_target":
                sms_removed_sent += 1
    else:
        assigned_worker_ids = {
            int((shift.get("assignment") or {}).get("worker_id"))
            for shift in shifts
            if (shift.get("assignment") or {}).get("worker_id") is not None
            and (shift.get("assignment") or {}).get("assignment_status") in {"assigned", "claimed", "confirmed"}
        }
        for worker_id in assigned_worker_ids:
            worker = await queries.get_worker(db, worker_id)
            if worker is not None and worker.get("sms_consent_status") == "granted":
                sms_sent += 1
            else:
                not_enrolled += 1

    blocked_items = [item.get("message") for item in (publish_readiness.get("blockers") or []) if item.get("message")]
    publish_blocked = None
    if blocked_items:
        publish_blocked = notifications_svc.build_schedule_publish_blocked_message(
            week_start_date=str(schedule["week_start_date"]),
            blocking_issue_count=int(
                publish_readiness.get("blocking_issue_count", len(blocked_items)) or 0
            ),
            blocked_items=blocked_items,
            review_link=review_link,
        )

    return {
        "review_link": review_link,
        "publish_mode": publish_mode,
        "worker_update_count": int(
            ((publish_diff.get("worker_impact") or {}).get("summary") or {}).get(
                "workers_with_schedule_update_count",
                0,
            )
            or 0
        ),
        "draft_ready": notifications_svc.build_schedule_draft_ready_message(
            location_name=location.get("name") or "your location",
            week_start_date=str(schedule["week_start_date"]),
            filled_shifts=int(summary.get("filled_shifts", 0) or 0),
            total_shifts=total_shifts,
            review_items=review_items,
            review_link=review_link,
            first_draft=False,
        ),
        "publish_success": notifications_svc.build_schedule_published_message(
            sms_sent=sms_sent,
            not_enrolled=not_enrolled,
            sms_failed=0,
            sms_removed_sent=sms_removed_sent,
            week_start_date=str(schedule["week_start_date"]),
            is_update=publish_mode == "update",
            change_highlights=list(publish_diff.get("highlights") or []),
        ),
        "publish_blocked": publish_blocked,
    }


async def _build_schedule_review_summary(
    db: aiosqlite.Connection,
    *,
    location: dict | None,
    schedule: dict | None,
    summary: dict,
    exceptions: list[dict],
    change_summary: dict,
    publish_diff: dict,
    current_shifts: list[dict] | None = None,
    import_rows: list[dict] | None = None,
) -> dict:
    schedule_view = {
        "shifts": (
            list(current_shifts or [])
            if schedule
            else []
        ),
        "exceptions": exceptions,
    }
    review_items = _collect_manager_review_items(schedule_view, import_rows or [])
    publish_readiness = _build_schedule_publish_readiness(
        schedule=schedule,
        summary=summary,
        exceptions=exceptions,
    )

    if publish_readiness["can_publish"] and not review_items:
        headline = "Schedule is ready to publish."
        recommended_action = "approve_by_text"
        approval_prompt = "Reply APPROVE to publish or REVIEW to inspect the week."
    elif publish_readiness["can_publish"]:
        headline = f"{len(review_items)} review item{'s' if len(review_items) != 1 else ''} remain, but publish is allowed."
        recommended_action = "review_before_publish"
        approval_prompt = "Reply APPROVE to publish now, or REVIEW to make changes first."
    else:
        headline = publish_readiness["status_message"]
        recommended_action = "resolve_blockers"
        approval_prompt = "Review the blockers before publishing."

    highlights: list[str] = []
    if change_summary["basis"]["basis_type"] != "none":
        highlights.extend(change_summary["highlights"][:2])
    if review_items:
        highlights.extend(review_items[:2])
    if not highlights:
        highlights.append("No major exceptions are currently active.")

    draft_rationale = await _build_schedule_draft_rationale(
        db,
        schedule=schedule,
        location=location,
        summary=summary,
        change_summary=change_summary,
        publish_diff=publish_diff,
    )
    message_preview = await _build_schedule_message_preview(
        db,
        location=location,
        schedule=schedule,
        summary=summary,
        review_items=review_items,
        publish_readiness=publish_readiness,
        publish_diff=publish_diff,
        current_shifts=current_shifts,
    )
    return {
        "headline": headline,
        "recommended_action": recommended_action,
        "approval_prompt": approval_prompt,
        "review_item_count": len(review_items),
        "review_items": review_items,
        "highlights": highlights,
        "change_highlights": list(change_summary["highlights"]),
        "publish_highlights": list(publish_diff.get("highlights") or []),
        "publish_impact_summary": dict((publish_diff.get("worker_impact") or {}).get("summary") or {}),
        "draft_rationale": draft_rationale,
        "publish_diff": publish_diff,
        "message_preview": message_preview,
    }


async def _notify_manager_schedule_draft(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    schedule_id: int,
    week_start_date: str,
    import_rows: list[dict],
    import_job_id: Optional[int] = None,
    first_draft: bool = False,
) -> Optional[str]:
    location = await queries.get_location(db, location_id)
    schedule = await queries.get_schedule(db, schedule_id)
    if location is None or schedule is None or not location.get("manager_phone"):
        return None

    schedule_view = await get_schedule_view(db, location_id=location_id, week_start=week_start_date)
    review_items = _collect_manager_review_items(schedule_view, import_rows)
    review_row = _get_first_pending_review_row(import_rows)
    if review_row is not None and import_job_id is not None:
        review_link = notifications_svc.build_manager_dashboard_link(
            location_id,
            tab="imports",
            job_id=import_job_id,
            row_number=int(review_row["row_number"]),
        )
    else:
        review_link = notifications_svc.build_manager_dashboard_link(
            location_id,
            tab="schedule",
            week_start=week_start_date,
        )

    summary = schedule_view.get("summary") or {}
    total_shifts = int(summary.get("filled_shifts", 0) or 0) + int(summary.get("open_shifts", 0) or 0)
    return await notifications_svc.fire_schedule_draft_ready_notification(
        db,
        location=location,
        schedule=schedule,
        filled_shifts=int(summary.get("filled_shifts", 0) or 0),
        total_shifts=total_shifts,
        review_items=review_items,
        review_link=review_link,
        import_job_id=import_job_id,
        first_draft=first_draft,
    )


async def upload_import_file(
    db: aiosqlite.Connection,
    *,
    job_id: int,
    filename: str,
    content: bytes,
) -> dict:
    if not filename.lower().endswith(".csv"):
        raise ValueError("File must be a .csv")
    if len(content) > MAX_CSV_BYTES:
        raise ValueError("CSV file exceeds 10 MB limit")
    csv_text = content.decode("utf-8-sig")
    columns, rows = _read_csv_text(csv_text)
    if not columns:
        raise ValueError("CSV header row is required")
    preview_rows = [
        {"row_number": index, "values": row}
        for index, row in enumerate(rows[:_PREVIEW_ROW_LIMIT], start=2)
    ]
    await queries.clear_import_row_results(db, job_id)
    await queries.update_import_job(
        db,
        job_id,
        {
            "filename": filename,
            "status": "mapping",
            "columns_json": columns,
            "uploaded_csv": csv_text,
            "summary_json": _summarize_import_rows(len(rows), []),
        },
    )
    return {
        "id": job_id,
        "status": "mapping",
        "columns": columns,
        "preview_rows": preview_rows,
    }


async def validate_import_mapping(
    db: aiosqlite.Connection,
    *,
    job_id: int,
    mapping: dict[str, str],
) -> dict:
    job = await queries.get_import_job(db, job_id)
    if job is None:
        raise ValueError("Import job not found")
    csv_text = job.get("uploaded_csv")
    if not csv_text:
        raise ValueError("Upload a CSV before saving a mapping")

    _, rows = _read_csv_text(csv_text)
    await queries.clear_import_row_results(db, job_id)

    results = [
        _validate_import_row(index, row, mapping)
        for index, row in enumerate(rows, start=2)
    ]
    _enforce_single_week(results)
    for result in results:
        await queries.insert_import_row_result(
            db,
            {
                "import_job_id": job_id,
                **result,
            },
        )
    summary = _summarize_import_rows(len(rows), results)
    action_needed_count = summary["warning_rows"] + summary["failed_rows"]
    status = _derive_job_status(results)
    await queries.update_import_job(
        db,
        job_id,
        {
            "status": status,
            "mapping_json": mapping,
            "summary_json": summary,
        },
    )
    return {
        "id": job_id,
        "status": status,
        "summary": summary,
        "action_needed_count": action_needed_count,
    }


async def resolve_import_row(
    db: aiosqlite.Connection,
    *,
    row_id: int,
    action: str,
    normalized_payload: Optional[dict[str, str]] = None,
    actor: str = "system",
) -> dict:
    row = await queries.get_import_row_result(db, row_id)
    if row is None:
        raise ValueError("Import row not found")
    if row.get("committed_at"):
        raise ValueError("Committed import rows cannot be edited; update the schedule or roster directly")

    job = await queries.get_import_job(db, int(row["import_job_id"]))
    if job is None:
        raise ValueError("Import job not found")

    action_value = (action or "").strip().lower()
    if action_value not in {"fix", "ignore", "retry"}:
        raise ValueError("Action must be one of: fix, ignore, retry")

    updates: dict[str, object] = {
        "resolution_action": action_value,
        "resolved_at": datetime.utcnow().isoformat(),
        "resolved_by": actor,
    }
    if action_value == "ignore":
        updates.update(
            {
                "outcome": "skipped",
                "error_code": "ignored_by_manager",
                "error_message": "Row ignored by manager",
            }
        )
    else:
        raw_payload = row.get("raw_payload") or {}
        mapping = job.get("mapping_json") or {}
        base_payload = dict(row.get("normalized_payload") or _normalize_row_payload(raw_payload, mapping))
        override_payload = _normalize_override_payload(normalized_payload or {})
        for key, value in override_payload.items():
            if value is None:
                base_payload.pop(key, None)
            else:
                base_payload[key] = value
        result = _validate_entity_payload(
            row_number=int(row["row_number"]),
            raw_row=raw_payload,
            entity_type=row["entity_type"],
            payload=base_payload,
        )
        updates.update(
            {
                "entity_type": result["entity_type"],
                "outcome": result["outcome"],
                "error_code": result["error_code"],
                "error_message": result["error_message"],
                "normalized_payload": result["normalized_payload"],
            }
        )

    await queries.update_import_row_result(db, row_id, updates)
    summary, _, action_needed_count = await _refresh_import_job_state(
        db,
        job_id=int(row["import_job_id"]),
    )
    refreshed_row = await queries.get_import_row_result(db, row_id)
    assert refreshed_row is not None
    refreshed_job = await queries.get_import_job(db, int(row["import_job_id"]))
    assert refreshed_job is not None
    return {
        "row": refreshed_row,
        "job": {
            "id": refreshed_job["id"],
            "status": refreshed_job["status"],
            "summary": summary,
        },
        "action_needed_count": action_needed_count,
    }


async def export_import_errors_csv(
    db: aiosqlite.Connection,
    *,
    job_id: int,
) -> dict:
    job = await queries.get_import_job(db, job_id)
    if job is None:
        raise ValueError("Import job not found")
    rows = [
        row
        for row in await queries.list_import_row_results(db, job_id)
        if row["outcome"] in {"warning", "failed", "skipped"}
    ]
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "row_number",
            "entity_type",
            "outcome",
            "error_code",
            "error_message",
            "raw_payload",
            "normalized_payload",
            "committed_at",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "row_number": row.get("row_number"),
                "entity_type": row.get("entity_type"),
                "outcome": row.get("outcome"),
                "error_code": row.get("error_code"),
                "error_message": row.get("error_message"),
                "raw_payload": row.get("raw_payload"),
                "normalized_payload": row.get("normalized_payload"),
                "committed_at": row.get("committed_at"),
            }
        )
    return {
        "job_id": job_id,
        "csv": output.getvalue(),
        "count": len(rows),
    }


async def commit_import_job(
    db: aiosqlite.Connection,
    *,
    job_id: int,
    actor: str = "system",
) -> dict:
    job = await queries.get_import_job(db, job_id)
    if job is None:
        raise ValueError("Import job not found")
    rows = await queries.list_import_row_results(db, job_id)
    if not rows:
        raise ValueError("Validate an import mapping before committing")

    prior_summary = dict(job.get("summary_json") or {})
    prior_notification_stage = prior_summary.get("manager_draft_notification_stage")
    created_workers = 0
    updated_workers = 0
    created_shifts = 0
    schedule_id: Optional[int] = prior_summary.get("schedule_id")
    week_start_date: Optional[str] = prior_summary.get("week_start_date")
    version_id: Optional[int] = prior_summary.get("version_id")

    valid_rows = [
        row
        for row in rows
        if row["outcome"] in {"success", "warning"} and not row.get("committed_at")
    ]
    valid_shift_rows = [row for row in valid_rows if row["entity_type"] == "shift"]
    if valid_shift_rows:
        week_start_date = week_start_date or valid_shift_rows[0]["normalized_payload"]["week_start_date"]
        if schedule_id is None:
            existing_schedule = await queries.get_schedule_by_location_week(
                db,
                int(job["location_id"]),
                week_start_date,
            )
            if existing_schedule is None:
                week_start = date.fromisoformat(week_start_date)
                schedule_id = await queries.insert_schedule(
                    db,
                    {
                        "location_id": int(job["location_id"]),
                        "week_start_date": week_start_date,
                        "week_end_date": _week_end_for(week_start).isoformat(),
                        "lifecycle_state": "draft",
                        "created_by": actor,
                    },
                )
                await audit_svc.append(
                    db,
                    AuditAction.schedule_created,
                    actor=actor,
                    entity_type="schedule",
                    entity_id=schedule_id,
                    details={"source": "import_job", "import_job_id": job_id},
                )
            else:
                schedule_id = int(existing_schedule["id"])

    for row in valid_rows:
        payload = row.get("normalized_payload") or {}
        if row["entity_type"] == "worker":
            worker_id, created = await _upsert_worker_from_payload(
                db,
                location_id=int(job["location_id"]),
                payload=payload,
            )
            if created:
                created_workers += 1
            else:
                updated_workers += 1
            await queries.update_import_row_result(
                db,
                int(row["id"]),
                {
                    "committed_at": datetime.utcnow().isoformat(),
                    "committed_entity_id": worker_id,
                },
            )
            continue

        assignment_worker_id, worker_created = await _resolve_shift_assignment_worker(
            db,
            location_id=int(job["location_id"]),
            payload=payload,
        )
        if worker_created:
            created_workers += 1
        shift_id = await queries.insert_shift(
            db,
            {
                "location_id": int(job["location_id"]),
                "schedule_id": schedule_id,
                "role": payload["role"],
                "date": payload["date"],
                "start_time": payload["start_time"],
                "end_time": payload["end_time"],
                "spans_midnight": bool(payload.get("spans_midnight")),
                "pay_rate": payload.get("pay_rate", 0.0),
                "requirements": [],
                "status": "scheduled",
                "source_platform": "backfill_native",
                "shift_label": payload.get("shift_label"),
                "notes": payload.get("notes"),
                "published_state": "draft",
            },
        )
        created_shifts += 1
        await queries.upsert_shift_assignment(
            db,
            {
                "shift_id": shift_id,
                "worker_id": assignment_worker_id,
                "assignment_status": "assigned" if assignment_worker_id else "open",
                "source": "import",
            },
        )
        await queries.update_import_row_result(
            db,
            int(row["id"]),
            {
                "committed_at": datetime.utcnow().isoformat(),
                "committed_entity_id": shift_id,
            },
        )

    if schedule_id is not None and valid_shift_rows:
        version_id = await _create_schedule_version(
            db,
            schedule_id=schedule_id,
            version_type="draft_snapshot",
            change_summary={"import_job_id": job_id},
        )
        await queries.update_schedule(
            db,
            schedule_id,
            {"current_version_id": version_id, "lifecycle_state": "draft"},
        )

    summary, refreshed_rows, _ = await _refresh_import_job_state(db, job_id=job_id)
    status = _derive_job_status(refreshed_rows)
    summary.update(
        {
            "created_workers": created_workers,
            "updated_workers": updated_workers,
            "created_shifts": created_shifts,
            "schedule_id": schedule_id,
            "week_start_date": week_start_date,
            "version_id": version_id,
            "committed": True,
        }
    )
    notification_stage = None
    if schedule_id is not None and week_start_date and created_shifts > 0:
        notification_stage = "completed" if status == "completed" else "draft_ready"
        if prior_notification_stage != notification_stage:
            message_sid = await _notify_manager_schedule_draft(
                db,
                location_id=int(job["location_id"]),
                schedule_id=int(schedule_id),
                week_start_date=week_start_date,
                import_rows=refreshed_rows,
                import_job_id=job_id,
                first_draft=prior_summary.get("schedule_id") is None,
            )
            summary["manager_draft_notification_stage"] = notification_stage
            summary["manager_draft_notification_at"] = datetime.utcnow().isoformat()
            summary["manager_draft_notification_sid"] = message_sid
    await queries.update_import_job(
        db,
        job_id,
        {
            "status": status,
            "summary_json": summary,
        },
    )
    await audit_svc.append(
        db,
        AuditAction.import_job_committed,
        actor=actor,
        entity_type="import_job",
        entity_id=job_id,
        details=summary,
    )
    return {
        "job_id": job_id,
        "status": status,
        "created_workers": created_workers,
        "updated_workers": updated_workers,
        "created_shifts": created_shifts,
        "schedule_id": schedule_id,
        "week_start_date": week_start_date,
    }


async def get_schedule_view(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    week_start: Optional[str] = None,
) -> dict:
    schedule = (
        await queries.get_schedule_by_location_week(db, location_id, week_start)
        if week_start
        else await queries.get_latest_schedule_for_location(db, location_id)
    )
    location = await queries.get_location(db, location_id)
    return await _build_schedule_view_payload(
        db,
        schedule=schedule,
        location=location,
    )


async def _build_schedule_view_payload(
    db: aiosqlite.Connection,
    *,
    schedule: dict | None,
    location: dict | None,
) -> dict:
    if schedule is None:
        summary = {
            "filled_shifts": 0,
            "open_shifts": 0,
            "at_risk_shifts": 0,
            "attendance_issues": 0,
            "late_arrivals": 0,
            "late_arrivals_awaiting_decision": 0,
            "missed_check_ins": 0,
            "missed_check_ins_awaiting_decision": 0,
            "missed_check_ins_escalated": 0,
            "action_required_count": 0,
            "critical_count": 0,
            "warning_count": 0,
        }
        return {
            "schedule": None,
            "summary": summary,
            "publish_readiness": _build_schedule_publish_readiness(
                schedule=None,
                summary=summary,
                exceptions=[],
            ),
            "change_summary": {
                "basis": {
                    "basis_type": "none",
                    "basis_label": "no baseline",
                    "basis_schedule_id": None,
                    "basis_version_id": None,
                    "basis_week_start_date": None,
                    "comparison_mode": "none",
                },
                "summary": {
                    "added_shift_count": 0,
                    "removed_shift_count": 0,
                    "reassigned_count": 0,
                    "opened_shift_count": 0,
                    "filled_shift_count": 0,
                    "role_change_count": 0,
                    "timing_change_count": 0,
                    "closed_shift_count": 0,
                    "reopened_shift_count": 0,
                    "total_change_count": 0,
                    "has_changes": False,
                },
                "highlights": ["No comparison baseline is available yet."],
                "changes": [],
                "first_publish": True,
                "has_prior_publish": False,
            },
            "publish_diff": {
                "basis": {
                    "basis_type": "none",
                    "basis_label": "first publish",
                    "basis_schedule_id": None,
                    "basis_version_id": None,
                    "basis_week_start_date": None,
                    "comparison_mode": "none",
                },
                "summary": {
                    "added_shift_count": 0,
                    "removed_shift_count": 0,
                    "reassigned_count": 0,
                    "opened_shift_count": 0,
                    "filled_shift_count": 0,
                    "role_change_count": 0,
                    "timing_change_count": 0,
                    "closed_shift_count": 0,
                    "reopened_shift_count": 0,
                    "total_change_count": 0,
                    "has_changes": False,
                },
                "highlights": ["This will be the first published version of this schedule."],
                "changes": [],
                "first_publish": True,
                "has_prior_publish": False,
            },
            "review_summary": {
                "headline": "No schedule exists yet.",
                "recommended_action": "create_schedule",
                "approval_prompt": "Create or import a schedule first.",
                "review_item_count": 0,
                "review_items": [],
                "highlights": ["Create or import a schedule to begin review."],
                "change_highlights": [],
                "publish_highlights": [],
                "publish_impact_summary": {
                    "target_worker_count": 0,
                    "basis_worker_count": 0,
                    "affected_worker_count": 0,
                    "added_to_target_count": 0,
                    "removed_from_target_count": 0,
                    "updated_in_both_count": 0,
                    "unchanged_worker_count": 0,
                    "workers_with_schedule_update_count": 0,
                    "workers_removed_from_schedule_count": 0,
                    "new_assignment_count": 0,
                    "changed_shift_count": 0,
                    "added_shift_only_count": 0,
                    "removed_shift_only_count": 0,
                },
                "draft_rationale": {
                    "headline": "No schedule draft exists yet.",
                    "origin_type": "none",
                    "origin_reference": None,
                    "narrative": "Create, import, or generate a schedule to see draft rationale.",
                    "recommended_checks": [],
                },
                "publish_diff": {
                    "basis": {
                        "basis_type": "none",
                        "basis_label": "first publish",
                        "basis_schedule_id": None,
                        "basis_version_id": None,
                        "basis_week_start_date": None,
                        "comparison_mode": "none",
                    },
                    "summary": {
                        "added_shift_count": 0,
                        "removed_shift_count": 0,
                        "reassigned_count": 0,
                        "opened_shift_count": 0,
                        "filled_shift_count": 0,
                        "role_change_count": 0,
                        "timing_change_count": 0,
                        "closed_shift_count": 0,
                        "reopened_shift_count": 0,
                        "total_change_count": 0,
                        "has_changes": False,
                    },
                    "highlights": ["This will be the first published version of this schedule."],
                    "changes": [],
                    "first_publish": True,
                    "has_prior_publish": False,
                },
                "message_preview": {
                    "review_link": None,
                    "publish_mode": "initial",
                    "worker_update_count": 0,
                    "draft_ready": None,
                    "publish_success": None,
                    "publish_blocked": None,
                },
            },
            "shifts": [],
            "exceptions": [],
        }

    enriched_shifts = await _load_enriched_schedule_shifts(
        db,
        schedule_id=int(schedule["id"]),
    )
    summary, exceptions = _schedule_view_summary(enriched_shifts, location=location)
    publish_readiness = _build_schedule_publish_readiness(
        schedule=schedule,
        summary=summary,
        exceptions=exceptions,
    )
    change_summary = await _build_schedule_change_summary(
        db,
        schedule=schedule,
        current_shifts=enriched_shifts,
    )
    publish_diff = await _build_schedule_publish_diff_summary(
        db,
        schedule=schedule,
        current_shifts=enriched_shifts,
    )
    review_summary = await _build_schedule_review_summary(
        db,
        location=location,
        schedule=schedule,
        summary=summary,
        exceptions=exceptions,
        change_summary=change_summary,
        publish_diff=publish_diff,
        current_shifts=enriched_shifts,
    )
    return {
        "schedule": schedule,
        "summary": summary,
        "publish_readiness": publish_readiness,
        "change_summary": change_summary,
        "publish_diff": publish_diff,
        "review_summary": review_summary,
        "shifts": enriched_shifts,
        "exceptions": exceptions,
    }


async def get_schedule_review(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    location = await queries.get_location(db, int(schedule["location_id"]))
    payload = await _build_schedule_view_payload(
        db,
        schedule=schedule,
        location=location,
    )
    payload["schedule_id"] = schedule_id
    return payload


async def get_schedule_publish_readiness(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
) -> dict:
    review = await get_schedule_review(db, schedule_id=schedule_id)
    return {
        "schedule_id": schedule_id,
        "schedule": review["schedule"],
        "summary": review["summary"],
        "publish_readiness": review["publish_readiness"],
        "exceptions": review["exceptions"],
    }


async def get_schedule_change_summary(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
) -> dict:
    review = await get_schedule_review(db, schedule_id=schedule_id)
    return {
        "schedule_id": schedule_id,
        "schedule": review["schedule"],
        "change_summary": review["change_summary"],
        "publish_diff": review["publish_diff"],
        "review_summary": review["review_summary"],
    }


async def get_schedule_publish_diff(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
) -> dict:
    review = await get_schedule_review(db, schedule_id=schedule_id)
    return {
        "schedule_id": schedule_id,
        "schedule": review["schedule"],
        "publish_diff": review["publish_diff"],
        "review_summary": review["review_summary"],
    }


async def get_schedule_publish_impact(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
) -> dict:
    review = await get_schedule_review(db, schedule_id=schedule_id)
    return {
        "schedule_id": schedule_id,
        "schedule": review["schedule"],
        "publish_diff": review["publish_diff"],
        "worker_impact": (review["publish_diff"].get("worker_impact") or {}),
        "review_summary": review["review_summary"],
    }


async def get_schedule_publish_preview(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
) -> dict:
    review = await get_schedule_review(db, schedule_id=schedule_id)
    return {
        "schedule_id": schedule_id,
        "schedule": review["schedule"],
        "publish_diff": review["publish_diff"],
        "review_summary": review["review_summary"],
        "message_preview": review["review_summary"]["message_preview"],
        "publish_preview": await _build_schedule_publish_preview(
            db,
            location=await queries.get_location(db, int(review["schedule"]["location_id"])),
            schedule=review["schedule"],
            current_shifts=review["shifts"],
            publish_diff=review["publish_diff"],
            message_preview=review["review_summary"]["message_preview"],
        ),
    }


async def get_schedule_draft_rationale(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
) -> dict:
    review = await get_schedule_review(db, schedule_id=schedule_id)
    return {
        "schedule_id": schedule_id,
        "schedule": review["schedule"],
        "draft_rationale": review["review_summary"]["draft_rationale"],
        "review_summary": review["review_summary"],
    }


def _snapshot_shifts_from_version(version: dict) -> list[dict]:
    snapshot = dict(version.get("snapshot_json") or {})
    return list(snapshot.get("shifts") or [])


def _build_schedule_version_basis_from_snapshot(
    *,
    version: dict,
    basis_type: str,
    basis_label: str,
) -> dict:
    snapshot = dict(version.get("snapshot_json") or {})
    schedule = dict(snapshot.get("schedule") or {})
    return {
        "basis_type": basis_type,
        "basis_label": basis_label,
        "basis_schedule_id": schedule.get("id"),
        "basis_version_id": int(version["id"]),
        "basis_week_start_date": schedule.get("week_start_date"),
        "comparison_mode": "same_schedule",
        "shifts": _snapshot_shifts_from_version(version),
    }


def _build_schedule_impact_summary(diff_summary: dict) -> dict:
    open_shift_impact_count = int(diff_summary.get("opened_shift_count", 0) or 0) + int(
        diff_summary.get("filled_shift_count", 0) or 0
    )
    structural_change_count = (
        int(diff_summary.get("added_shift_count", 0) or 0)
        + int(diff_summary.get("removed_shift_count", 0) or 0)
        + int(diff_summary.get("closed_shift_count", 0) or 0)
        + int(diff_summary.get("reopened_shift_count", 0) or 0)
    )
    return {
        "reassignment_count": int(diff_summary.get("reassigned_count", 0) or 0),
        "timing_change_count": int(diff_summary.get("timing_change_count", 0) or 0),
        "role_change_count": int(diff_summary.get("role_change_count", 0) or 0),
        "open_shift_impact_count": open_shift_impact_count,
        "structural_change_count": structural_change_count,
        "total_change_count": int(diff_summary.get("total_change_count", 0) or 0),
        "has_changes": bool(diff_summary.get("has_changes")),
    }


def _format_worker_schedule_time(value: str) -> str:
    return str(value or "")[:5]


def _format_worker_schedule_line_for_compare(shift: dict) -> str:
    shift_date = str(shift.get("date") or "")
    parsed_date = date.fromisoformat(shift_date)
    return (
        f"{parsed_date.strftime('%a')} {parsed_date.strftime('%b')} {parsed_date.day} "
        f"{_format_worker_schedule_time(str(shift.get('start_time') or ''))}-"
        f"{_format_worker_schedule_time(str(shift.get('end_time') or ''))} "
        f"{shift.get('role') or 'shift'}"
    )


def _worker_schedule_line_signature(shift: dict) -> tuple:
    return (
        str(shift.get("date") or ""),
        str(shift.get("start_time") or ""),
        str(shift.get("end_time") or ""),
        str(shift.get("role") or ""),
        str(shift.get("shift_label") or ""),
        bool(shift.get("spans_midnight")),
    )


def _group_assigned_schedule_lines_by_worker(shifts: list[dict]) -> dict[str, dict]:
    grouped: dict[str, dict] = {}
    for shift in shifts:
        assignment = _schedule_shift_assignment(shift)
        worker_id = assignment.get("worker_id")
        assignment_status = assignment.get("assignment_status")
        if worker_id is None or assignment_status not in {"assigned", "claimed", "confirmed"}:
            continue
        worker_name = assignment.get("worker_name") or "Assigned worker"
        worker_key = f"id:{int(worker_id)}"
        bucket = grouped.setdefault(
            worker_key,
            {
                "worker_id": int(worker_id),
                "worker_name": worker_name,
                "line_signatures": set(),
                "line_labels": {},
                "shift_ids": set(),
            },
        )
        signature = _worker_schedule_line_signature(shift)
        bucket["line_signatures"].add(signature)
        bucket["line_labels"][signature] = _format_worker_schedule_line_for_compare(shift)
        if shift.get("id") is not None:
            bucket["shift_ids"].add(int(shift["id"]))
    return grouped


async def _build_worker_impact_payload(
    db: aiosqlite.Connection,
    *,
    target_shifts: list[dict],
    basis_shifts: list[dict],
) -> dict:
    target_workers = _group_assigned_schedule_lines_by_worker(target_shifts)
    basis_workers = _group_assigned_schedule_lines_by_worker(basis_shifts)
    all_keys = sorted(set(target_workers) | set(basis_workers))
    items: list[dict] = []

    for worker_key in all_keys:
        target = target_workers.get(worker_key)
        basis = basis_workers.get(worker_key)
        worker_id = (target or basis).get("worker_id")
        worker_name = (target or basis).get("worker_name") or "Assigned worker"

        target_lines = set((target or {}).get("line_signatures") or set())
        basis_lines = set((basis or {}).get("line_signatures") or set())
        added_lines = sorted(target_lines - basis_lines)
        removed_lines = sorted(basis_lines - target_lines)
        if target and not basis:
            status = "added_to_target"
            change_type = "new_assignment"
        elif basis and not target:
            status = "removed_from_target"
            change_type = "removed_assignment"
        elif added_lines or removed_lines:
            status = "updated_in_both"
            if added_lines and removed_lines:
                change_type = "shift_changed"
            elif added_lines:
                change_type = "shift_added"
            else:
                change_type = "shift_removed"
        else:
            status = "unchanged"
            change_type = "unchanged"

        worker_record = await queries.get_worker(db, int(worker_id)) if worker_id is not None else None
        sms_consent_status = worker_record.get("sms_consent_status") if worker_record else None
        has_phone = bool(worker_record.get("phone")) if worker_record else False
        items.append(
            {
                "worker_id": worker_id,
                "worker_name": worker_name,
                "status": status,
                "change_type": change_type,
                "target_shift_count": len(target_lines),
                "basis_shift_count": len(basis_lines),
                "added_shift_count": len(added_lines),
                "removed_shift_count": len(removed_lines),
                "target_shift_ids": sorted((target or {}).get("shift_ids") or []),
                "basis_shift_ids": sorted((basis or {}).get("shift_ids") or []),
                "target_lines": sorted(
                    ((target or {}).get("line_labels") or {}).values()
                ),
                "basis_lines": sorted(
                    ((basis or {}).get("line_labels") or {}).values()
                ),
                "added_lines": [
                    ((target or {}).get("line_labels") or {}).get(signature)
                    for signature in added_lines
                ],
                "removed_lines": [
                    ((basis or {}).get("line_labels") or {}).get(signature)
                    for signature in removed_lines
                ],
                "sms_consent_status": sms_consent_status,
                "has_phone": has_phone,
                "in_current_delivery_audience": bool(target),
                "in_changed_delivery_audience": status in {"added_to_target", "updated_in_both"},
            }
        )

    status_order = {
        "updated_in_both": 0,
        "added_to_target": 1,
        "removed_from_target": 2,
        "unchanged": 3,
    }
    items.sort(
        key=lambda item: (
            status_order.get(str(item.get("status") or ""), 99),
            str(item.get("worker_name") or ""),
            int(item.get("worker_id") or 0),
        )
    )

    changed_delivery_workers = [item for item in items if item["in_changed_delivery_audience"]]
    current_delivery_workers = [item for item in items if item["in_current_delivery_audience"]]

    def _estimate_delivery(candidates: list[dict]) -> dict:
        sms_enrolled = sum(
            1
            for item in candidates
            if item.get("sms_consent_status") == "granted" and item.get("has_phone")
        )
        not_enrolled = sum(
            1
            for item in candidates
            if item.get("sms_consent_status") != "granted"
        )
        unreachable = sum(
            1
            for item in candidates
            if item.get("sms_consent_status") == "granted" and not item.get("has_phone")
        )
        return {
            "worker_count": len(candidates),
            "sms_enrolled_count": sms_enrolled,
            "not_enrolled_count": not_enrolled,
            "unreachable_count": unreachable,
        }

    summary = {
        "target_worker_count": len(target_workers),
        "basis_worker_count": len(basis_workers),
        "affected_worker_count": sum(1 for item in items if item["status"] != "unchanged"),
        "added_to_target_count": sum(1 for item in items if item["status"] == "added_to_target"),
        "removed_from_target_count": sum(1 for item in items if item["status"] == "removed_from_target"),
        "updated_in_both_count": sum(1 for item in items if item["status"] == "updated_in_both"),
        "unchanged_worker_count": sum(1 for item in items if item["status"] == "unchanged"),
        "workers_with_schedule_update_count": len(changed_delivery_workers),
        "workers_removed_from_schedule_count": sum(
            1 for item in items if item["status"] == "removed_from_target"
        ),
        "new_assignment_count": sum(1 for item in items if item["change_type"] == "new_assignment"),
        "changed_shift_count": sum(1 for item in items if item["change_type"] == "shift_changed"),
        "added_shift_only_count": sum(1 for item in items if item["change_type"] == "shift_added"),
        "removed_shift_only_count": sum(1 for item in items if item["change_type"] == "shift_removed"),
    }
    return {
        "summary": summary,
        "delivery_estimate": {
            "current_delivery": _estimate_delivery(current_delivery_workers),
            "changed_workers_only": _estimate_delivery(changed_delivery_workers),
        },
        "workers": items,
    }


def _group_delivery_schedule_shifts_by_worker(shifts: list[dict]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for shift in shifts:
        assignment = _schedule_shift_assignment(shift)
        worker_id = assignment.get("worker_id")
        assignment_status = assignment.get("assignment_status")
        if worker_id is None or assignment_status not in {"assigned", "claimed", "confirmed"}:
            continue
        grouped.setdefault(int(worker_id), []).append(shift)
    return grouped


def _resolve_schedule_publish_preview_delivery_state(
    *,
    publish_mode: str,
    impact_item: dict,
) -> tuple[bool, str, str]:
    if publish_mode == "initial":
        in_delivery_audience = bool(impact_item.get("in_current_delivery_audience"))
    else:
        in_delivery_audience = str(impact_item.get("status") or "") in {
            "updated_in_both",
            "added_to_target",
            "removed_from_target",
        }

    if not in_delivery_audience:
        return (
            False,
            "skipped_unchanged",
            "Unchanged workers are skipped on amended publishes.",
        )
    if impact_item.get("sms_consent_status") != "granted":
        return True, "not_enrolled", "Worker is not enrolled for SMS."
    if not bool(impact_item.get("has_phone")):
        return True, "unreachable", "Worker does not have a reachable phone number."
    return True, "will_send", "Worker will receive this SMS when the schedule is published."


async def _build_schedule_publish_preview(
    db: aiosqlite.Connection,
    *,
    location: dict | None,
    schedule: dict | None,
    current_shifts: list[dict] | None,
    publish_diff: dict,
    message_preview: dict | None = None,
) -> dict:
    if location is None or schedule is None:
        return {
            "review_link": None,
            "publish_mode": "initial",
            "manager_message_preview": {
                "draft_ready": None,
                "publish_success": None,
                "publish_blocked": None,
            },
            "delivery_estimate": {
                "eligible_workers": 0,
                "sms_sent": 0,
                "sms_removed_sent": 0,
                "not_enrolled": 0,
                "unreachable_count": 0,
                "changed_worker_count": 0,
                "removed_worker_count": 0,
                "unchanged_worker_count": 0,
                "skipped_unchanged_workers": 0,
            },
            "worker_message_previews": [],
        }

    manager_preview = dict(message_preview or {})
    publish_mode = str(manager_preview.get("publish_mode") or "initial")
    impact_payload = dict(publish_diff.get("worker_impact") or {})
    impact_workers = list(impact_payload.get("workers") or [])
    current_worker_shifts = _group_delivery_schedule_shifts_by_worker(list(current_shifts or []))
    delivery_estimate = {
        "eligible_workers": 0,
        "sms_sent": 0,
        "sms_removed_sent": 0,
        "not_enrolled": 0,
        "unreachable_count": 0,
        "changed_worker_count": 0,
        "removed_worker_count": 0,
        "unchanged_worker_count": 0,
        "skipped_unchanged_workers": 0,
    }
    worker_message_previews: list[dict] = []

    for impact_item in impact_workers:
        preview_item = dict(impact_item)
        preview_item["current_lines"] = list(impact_item.get("target_lines") or [])
        in_delivery_audience, delivery_status, delivery_reason = (
            _resolve_schedule_publish_preview_delivery_state(
                publish_mode=publish_mode,
                impact_item=impact_item,
            )
        )
        preview_item["in_delivery_audience"] = in_delivery_audience
        preview_item["delivery_status"] = delivery_status
        preview_item["delivery_reason"] = delivery_reason
        preview_item["will_receive_sms"] = delivery_status == "will_send"
        preview_item["message_type"] = None
        preview_item["message_body"] = None

        worker_name = str(impact_item.get("worker_name") or "there")
        status = str(impact_item.get("status") or "")
        change_type = str(impact_item.get("change_type") or "")
        worker_id = impact_item.get("worker_id")

        if status == "removed_from_target":
            delivery_estimate["removed_worker_count"] += 1
        elif status == "unchanged":
            delivery_estimate["unchanged_worker_count"] += 1
        else:
            delivery_estimate["changed_worker_count"] += 1

        if in_delivery_audience:
            delivery_estimate["eligible_workers"] += 1
            if publish_mode == "initial":
                preview_item["message_type"] = "schedule_published"
                preview_item["message_body"] = notifications_svc.build_worker_schedule_published_message(
                    worker_name=worker_name,
                    location_name=location.get("name") or "your location",
                    week_start_date=str(schedule["week_start_date"]),
                    shifts=list(current_worker_shifts.get(int(worker_id or 0)) or []),
                    is_update=False,
                )
            elif status == "removed_from_target":
                preview_item["message_type"] = "schedule_removed"
                preview_item["message_body"] = notifications_svc.build_worker_schedule_removed_message(
                    worker_name=worker_name,
                    location_name=location.get("name") or "your location",
                    week_start_date=str(schedule["week_start_date"]),
                    removed_lines=list(impact_item.get("removed_lines") or []),
                )
            elif change_type == "new_assignment":
                preview_item["message_type"] = "schedule_added"
                preview_item["message_body"] = notifications_svc.build_worker_schedule_added_message(
                    worker_name=worker_name,
                    location_name=location.get("name") or "your location",
                    week_start_date=str(schedule["week_start_date"]),
                    added_lines=list(
                        impact_item.get("added_lines") or impact_item.get("target_lines") or []
                    ),
                )
            else:
                preview_item["message_type"] = "schedule_changed"
                preview_item["message_body"] = notifications_svc.build_worker_schedule_changed_message(
                    worker_name=worker_name,
                    location_name=location.get("name") or "your location",
                    week_start_date=str(schedule["week_start_date"]),
                    added_lines=list(impact_item.get("added_lines") or []),
                    removed_lines=list(impact_item.get("removed_lines") or []),
                    current_lines=list(impact_item.get("target_lines") or []),
                )

            if delivery_status == "will_send":
                if preview_item["message_type"] == "schedule_removed":
                    delivery_estimate["sms_removed_sent"] += 1
                else:
                    delivery_estimate["sms_sent"] += 1
            elif delivery_status == "not_enrolled":
                delivery_estimate["not_enrolled"] += 1
            elif delivery_status == "unreachable":
                delivery_estimate["unreachable_count"] += 1
        elif delivery_status == "skipped_unchanged":
            delivery_estimate["skipped_unchanged_workers"] += 1

        worker_message_previews.append(preview_item)

    return {
        "review_link": manager_preview.get("review_link"),
        "publish_mode": publish_mode,
        "manager_message_preview": {
            "draft_ready": manager_preview.get("draft_ready"),
            "publish_success": manager_preview.get("publish_success"),
            "publish_blocked": manager_preview.get("publish_blocked"),
        },
        "delivery_estimate": delivery_estimate,
        "worker_message_previews": worker_message_previews,
    }


def _format_schedule_version_label(version: dict) -> str:
    version_type = str(version.get("version_type") or "")
    return {
        "draft_snapshot": "Draft saved",
        "amendment_snapshot": "Draft amended",
        "publish_snapshot": "Schedule published",
    }.get(version_type, "Schedule version")


def _build_schedule_version_narrative(
    *,
    version: dict,
    diff_payload: dict,
) -> str:
    label = _format_schedule_version_label(version)
    highlights = [
        item for item in (diff_payload.get("highlights") or []) if item and not item.startswith("No changes")
    ]
    if diff_payload.get("first_publish"):
        return f"{label}. This was the first published version of the week."
    if highlights:
        return f"{label}. {'; '.join(highlights[:2])}."
    if diff_payload.get("basis", {}).get("basis_type") == "none":
        return f"{label}. No earlier version is available for comparison."
    return f"{label}. No major changes from the comparison baseline."


async def _select_schedule_version_diff_basis(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    version: dict,
    compare_to: str = "default",
    compare_to_version_id: int | None = None,
) -> tuple[dict, str]:
    versions = await queries.list_schedule_versions(db, schedule_id)
    version_id = int(version["id"])
    prior_versions = [item for item in versions if int(item["id"]) < version_id]

    if compare_to_version_id is not None:
        explicit = await queries.get_schedule_version(db, int(compare_to_version_id))
        if explicit is None or int(explicit["schedule_id"]) != schedule_id:
            raise ValueError("Comparison schedule version not found")
        return (
            _build_schedule_version_basis_from_snapshot(
                version=explicit,
                basis_type="version",
                basis_label=f"version {explicit['version_number']}",
            ),
            "explicit_version",
        )

    if compare_to == "current":
        schedule = await queries.get_schedule(db, schedule_id)
        if schedule is None:
            raise ValueError("Schedule not found")
        current_shifts = await _load_enriched_schedule_shifts(db, schedule_id=schedule_id)
        return (
            {
                "basis_type": "current_schedule",
                "basis_label": "current schedule",
                "basis_schedule_id": schedule_id,
                "basis_version_id": None,
                "basis_week_start_date": schedule.get("week_start_date"),
                "comparison_mode": "same_schedule",
                "shifts": current_shifts,
            },
            "current",
        )

    if compare_to in {"previous_publish", "default"} and version.get("version_type") == "publish_snapshot":
        prior_publish_versions = [
            item for item in prior_versions if item.get("version_type") == "publish_snapshot"
        ]
        if prior_publish_versions:
            prior_publish = prior_publish_versions[-1]
            return (
                _build_schedule_version_basis_from_snapshot(
                    version=prior_publish,
                    basis_type="previous_publish_version",
                    basis_label="previous published version",
                ),
                "previous_publish",
            )
        if compare_to == "previous_publish":
            return (
                {
                    "basis_type": "none",
                    "basis_label": "first publish",
                    "basis_schedule_id": None,
                    "basis_version_id": None,
                    "basis_week_start_date": None,
                    "comparison_mode": "none",
                    "shifts": [],
                    "empty_highlight": "This was the first published version of the schedule.",
                    "first_publish": True,
                },
                "first_publish",
            )
        if compare_to == "default":
            return (
                {
                    "basis_type": "none",
                    "basis_label": "first publish",
                    "basis_schedule_id": None,
                    "basis_version_id": None,
                    "basis_week_start_date": None,
                    "comparison_mode": "none",
                    "shifts": [],
                    "empty_highlight": "This was the first published version of the schedule.",
                    "first_publish": True,
                },
                "first_publish",
            )

    if compare_to in {"previous", "default", "previous_publish"}:
        if prior_versions:
            previous_version = prior_versions[-1]
            return (
                _build_schedule_version_basis_from_snapshot(
                    version=previous_version,
                    basis_type="previous_version",
                    basis_label=f"version {previous_version['version_number']}",
                ),
                "previous",
            )

    return (
        {
            "basis_type": "none",
            "basis_label": "first version",
            "basis_schedule_id": None,
            "basis_version_id": None,
            "basis_week_start_date": None,
            "comparison_mode": "none",
            "shifts": [],
            "empty_highlight": "No earlier version is available for comparison.",
            "first_publish": False,
        },
        "none",
    )


async def _build_schedule_version_diff_payload(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    version: dict,
    compare_to: str = "default",
    compare_to_version_id: int | None = None,
) -> dict:
    basis, compare_mode = await _select_schedule_version_diff_basis(
        db,
        schedule_id=schedule_id,
        version=version,
        compare_to=compare_to,
        compare_to_version_id=compare_to_version_id,
    )
    if basis["comparison_mode"] == "none":
        diff_payload = _empty_schedule_change_summary(
            basis=basis,
            highlight=str(basis.get("empty_highlight") or "No earlier version is available for comparison."),
            first_publish=bool(basis.get("first_publish")),
        )
    else:
        diff_payload = await _build_schedule_change_summary_for_basis(
            basis=basis,
            current_shifts=_snapshot_shifts_from_version(version),
        )
    diff_payload["compare_mode"] = compare_mode
    diff_payload["impact_summary"] = _build_schedule_impact_summary(diff_payload["summary"])
    diff_payload["worker_impact"] = await _build_worker_impact_payload(
        db,
        target_shifts=_snapshot_shifts_from_version(version),
        basis_shifts=list(basis.get("shifts") or []),
    )
    diff_payload["event_label"] = _format_schedule_version_label(version)
    diff_payload["event_narrative"] = _build_schedule_version_narrative(
        version=version,
        diff_payload=diff_payload,
    )
    return diff_payload


async def get_schedule_message_preview(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
) -> dict:
    review = await get_schedule_review(db, schedule_id=schedule_id)
    return {
        "schedule_id": schedule_id,
        "schedule": review["schedule"],
        "review_summary": review["review_summary"],
        "publish_diff": review["publish_diff"],
        "message_preview": review["review_summary"]["message_preview"],
    }


async def list_schedule_history_versions(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    versions = await queries.list_schedule_versions(db, schedule_id)
    items: list[dict] = []
    for version in versions:
        snapshot = dict(version.get("snapshot_json") or {})
        snapshot_shifts = list(snapshot.get("shifts") or [])
        diff_payload = await _build_schedule_version_diff_payload(
            db,
            schedule_id=schedule_id,
            version=version,
        )
        items.append(
            {
                "id": int(version["id"]),
                "version_number": int(version["version_number"]),
                "version_type": version.get("version_type"),
                "created_at": version.get("created_at"),
                "published_at": version.get("published_at"),
                "published_by": version.get("published_by"),
                "change_summary": dict(version.get("change_summary_json") or {}),
                "shift_count": len(snapshot_shifts),
                "assigned_shift_count": sum(
                    1
                    for shift in snapshot_shifts
                    if (shift.get("assignment") or {}).get("worker_id") is not None
                    and (shift.get("assignment") or {}).get("assignment_status") in {"assigned", "claimed", "confirmed"}
                ),
                "open_shift_count": sum(
                    1
                    for shift in snapshot_shifts
                    if (shift.get("assignment") or {}).get("assignment_status") == "open"
                ),
                "event_label": diff_payload["event_label"],
                "event_narrative": diff_payload["event_narrative"],
                "default_compare_mode": diff_payload["compare_mode"],
                "diff_summary": diff_payload["summary"],
                "impact_summary": diff_payload["impact_summary"],
                "worker_impact_summary": dict((diff_payload.get("worker_impact") or {}).get("summary") or {}),
                "highlights": diff_payload["highlights"],
                "is_current_version": int(schedule.get("current_version_id") or 0) == int(version["id"]),
                "compare_to_current_available": True,
                "compare_to_previous_available": int(version["version_number"]) > 1,
                "compare_to_previous_publish_available": bool(
                    version.get("version_type") == "publish_snapshot"
                ),
            }
        )
    return {
        "schedule": schedule,
        "versions": items,
    }


async def get_schedule_version_diff(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    version_id: int,
    compare_to: str = "default",
    compare_to_version_id: int | None = None,
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    version = await queries.get_schedule_version(db, version_id)
    if version is None or int(version["schedule_id"]) != schedule_id:
        raise ValueError("Schedule version not found")
    diff_payload = await _build_schedule_version_diff_payload(
        db,
        schedule_id=schedule_id,
        version=version,
        compare_to=compare_to,
        compare_to_version_id=compare_to_version_id,
    )
    return {
        "schedule": schedule,
        "version": {
            "id": int(version["id"]),
            "version_number": int(version["version_number"]),
            "version_type": version.get("version_type"),
            "created_at": version.get("created_at"),
            "published_at": version.get("published_at"),
            "published_by": version.get("published_by"),
            "change_summary": dict(version.get("change_summary_json") or {}),
        },
        "worker_impact": diff_payload.get("worker_impact") or {},
        "version_diff": diff_payload,
    }


async def get_schedule_exception_queue(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    week_start: Optional[str] = None,
    action_required_only: bool = False,
) -> dict:
    schedule_view = await get_schedule_view(
        db,
        location_id=location_id,
        week_start=week_start,
    )
    items = list(schedule_view.get("exceptions") or [])
    if action_required_only:
        items = [item for item in items if item.get("action_required")]
    return _build_schedule_exception_queue_payload(
        location_id=location_id,
        schedule=schedule_view.get("schedule"),
        items=items,
        action_required_only=action_required_only,
    )


async def apply_schedule_exception_actions(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    actions: list[dict],
    week_start: Optional[str] = None,
    actor: str = "manager_api",
) -> dict:
    queue = await get_schedule_exception_queue(
        db,
        location_id=location_id,
        week_start=week_start,
        action_required_only=False,
    )
    items_by_key = {
        (int(item.get("shift_id") or 0), str(item.get("code") or "")): item
        for item in queue.get("items") or []
    }
    results: list[dict] = []

    for requested in actions:
        shift_id = int(requested.get("shift_id") or 0)
        code = str(requested.get("code") or "")
        action = str(requested.get("action") or "")
        item = items_by_key.get((shift_id, code))
        result = {
            "shift_id": shift_id,
            "code": code,
            "action": action,
        }
        if item is None:
            results.append(
                {
                    **result,
                    "status": "error",
                    "error": "exception_not_found",
                }
            )
            continue
        if action not in set(item.get("available_actions") or []):
            results.append(
                {
                    **result,
                    "status": "error",
                    "error": "action_not_allowed",
                    "available_actions": list(item.get("available_actions") or []),
                }
            )
            continue

        try:
            if action == "approve_fill":
                cascade_id = item.get("cascade_id")
                if cascade_id is None:
                    raise ValueError("Coverage approval requires an active cascade")
                outcome = await cascade_svc.approve_pending_claim(
                    db,
                    cascade_id=int(cascade_id),
                    summary="Approved from schedule exception queue",
                )
            elif action == "decline_fill":
                cascade_id = item.get("cascade_id")
                if cascade_id is None:
                    raise ValueError("Coverage decline requires an active cascade")
                outcome = await cascade_svc.decline_pending_claim(
                    db,
                    cascade_id=int(cascade_id),
                    summary="Declined from schedule exception queue",
                )
            elif action == "approve_agency":
                cascade_id = item.get("cascade_id")
                if cascade_id is None:
                    raise ValueError("Agency approval requires an active cascade")
                outcome = await cascade_svc.approve_agency_routing(
                    db,
                    cascade_id=int(cascade_id),
                    summary="Approved from schedule exception queue",
                )
            elif action == "start_coverage" and code == "open_shift_unassigned":
                outcome = await start_coverage_for_open_shift(
                    db,
                    shift_id=shift_id,
                    actor=actor,
                )
            elif action == "cancel_offer":
                outcome = await cancel_open_shift_offer(
                    db,
                    shift_id=shift_id,
                    actor=actor,
                )
            elif action == "close_shift":
                outcome = await close_open_shift(
                    db,
                    shift_id=shift_id,
                    actor=actor,
                )
            elif action == "wait_for_worker":
                outcome = await wait_for_attendance_issue(
                    db,
                    shift_id=shift_id,
                    actor=actor,
                )
            elif action == "start_coverage":
                outcome = await start_coverage_for_attendance_issue(
                    db,
                    shift_id=shift_id,
                    actor=actor,
                )
            else:
                outcome = {"status": "error", "error": "unknown_action"}
        except ValueError as exc:
            results.append(
                {
                    **result,
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        outcome_status = str(outcome.get("status") or "ok")
        if outcome_status == "error":
            results.append({**result, **outcome})
            continue
        results.append(
            {
                **result,
                "status": "ok",
                "result": outcome,
            }
        )

    refreshed_queue = await get_schedule_exception_queue(
        db,
        location_id=location_id,
        week_start=week_start,
        action_required_only=False,
    )
    success_count = sum(1 for item in results if item.get("status") == "ok")
    return {
        "processed_count": len(actions),
        "success_count": success_count,
        "error_count": len(results) - success_count,
        "results": results,
        "queue": refreshed_queue,
    }


async def start_coverage_for_open_shift(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    actor: str = "manager_api",
) -> dict:
    shift = await queries.get_shift(db, shift_id)
    if shift is None:
        raise ValueError("Shift not found")
    await _assert_shift_schedule_mutable(db, shift)

    active_cascade = await queries.get_active_cascade_for_shift(db, shift_id)
    if active_cascade is not None:
        return {
            "status": "coverage_active",
            "shift_id": shift_id,
            "cascade_id": int(active_cascade["id"]),
            "idempotent": True,
        }

    assignment = await queries.get_shift_assignment(db, shift_id)
    if assignment and assignment.get("worker_id") is not None and assignment.get("assignment_status") in {
        "assigned",
        "claimed",
        "confirmed",
    }:
        raise ValueError("Shift already has an assignee")
    if assignment and assignment.get("assignment_status") == "closed":
        raise ValueError("Shift is closed")
    if shift.get("status") == "filled":
        raise ValueError("Shift is already filled")
    if shift.get("status") not in {"scheduled", "vacant", "filling", "unfilled"}:
        raise ValueError("Shift cannot start coverage in its current state")

    cascade = await shift_manager.create_vacancy(
        db,
        shift_id=shift_id,
        called_out_by_worker_id=None,
        actor=actor,
    )
    await cascade_svc.advance(db, int(cascade["id"]))
    refreshed_shift = await queries.get_shift(db, shift_id)
    refreshed_cascade = await queries.get_active_cascade_for_shift(db, shift_id) or cascade
    return {
        "status": "coverage_started",
        "shift_id": shift_id,
        "cascade_id": int(refreshed_cascade["id"]),
        "idempotent": False,
        "shift": refreshed_shift,
    }


async def _assert_shift_schedule_mutable(
    db: aiosqlite.Connection,
    shift: dict,
) -> dict | None:
    if not shift.get("schedule_id"):
        return None
    schedule = await queries.get_schedule(db, int(shift["schedule_id"]))
    if schedule is not None and (schedule.get("lifecycle_state") or "draft") == "archived":
        raise ValueError("Archived schedules are read-only")
    return schedule


async def _get_open_shift_lifecycle_context(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
) -> tuple[dict, dict | None, dict | None]:
    shift = await queries.get_shift(db, shift_id)
    if shift is None:
        raise ValueError("Shift not found")
    await _assert_shift_schedule_mutable(db, shift)
    if outreach_svc.vacancy_kind(shift) != "open_shift":
        raise ValueError("Shift is not a manager-created open shift")
    assignment = await queries.get_shift_assignment(db, shift_id)
    active_cascade = await queries.get_active_cascade_for_shift(db, shift_id)
    return shift, assignment, active_cascade


async def cancel_open_shift_offer(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    actor: str = "manager_api",
) -> dict:
    shift, assignment, active_cascade = await _get_open_shift_lifecycle_context(
        db,
        shift_id=shift_id,
    )
    if active_cascade is None:
        return {
            "status": "offer_not_active",
            "shift_id": shift_id,
            "idempotent": True,
        }

    pending_claim_worker_id = active_cascade.get("pending_claim_worker_id")
    pending_claim_message_sid = None
    if pending_claim_worker_id is not None:
        pending_worker = await queries.get_worker(db, int(pending_claim_worker_id))
        if pending_worker and pending_worker.get("phone"):
            pending_claim_message_sid = notifications_svc.notify_worker_open_shift_closed(
                str(pending_worker["phone"]),
                role=str(shift.get("role") or "scheduled"),
                shift_date=str(shift["date"]),
                start_time=str(shift["start_time"]),
            )

    await queries.update_cascade(
        db,
        int(active_cascade["id"]),
        status="cancelled",
        pending_claim_worker_id=None,
        pending_claim_at=None,
    )
    await queries.update_shift_status(
        db,
        shift_id=shift_id,
        status="scheduled",
        filled_by=None,
        fill_tier=None,
        called_out_by=None,
    )
    await audit_svc.append(
        db,
        AuditAction.open_shift_offer_cancelled,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={
            "cascade_id": int(active_cascade["id"]),
            "pending_claim_worker_id": pending_claim_worker_id,
            "pending_claim_message_sid": pending_claim_message_sid,
            "previous_shift_status": shift.get("status"),
            "previous_assignment_status": assignment.get("assignment_status") if assignment else None,
        },
    )
    refreshed_shift = await queries.get_shift(db, shift_id)
    return {
        "status": "offer_cancelled",
        "shift_id": shift_id,
        "cascade_id": int(active_cascade["id"]),
        "idempotent": False,
        "shift": refreshed_shift,
    }


async def close_open_shift(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    actor: str = "manager_api",
) -> dict:
    shift, assignment, active_cascade = await _get_open_shift_lifecycle_context(
        db,
        shift_id=shift_id,
    )
    assignment_status = assignment.get("assignment_status") if assignment else None
    if assignment and assignment.get("worker_id") is not None and assignment_status in {"assigned", "claimed", "confirmed"}:
        raise ValueError("Shift already has an assignee")
    if assignment_status == "closed" and active_cascade is None and shift.get("status") == "scheduled":
        return {
            "status": "closed",
            "shift_id": shift_id,
            "cascade_cancelled": False,
            "idempotent": True,
        }

    cascade_cancelled = False
    if active_cascade is not None:
        cancel_result = await cancel_open_shift_offer(
            db,
            shift_id=shift_id,
            actor=actor,
        )
        cascade_cancelled = cancel_result.get("status") == "offer_cancelled"
        shift = await queries.get_shift(db, shift_id)
        assignment = await queries.get_shift_assignment(db, shift_id)

    await queries.update_shift_status(
        db,
        shift_id=shift_id,
        status="scheduled",
        filled_by=None,
        fill_tier=None,
        called_out_by=None,
    )
    await queries.upsert_shift_assignment(
        db,
        {
            "shift_id": shift_id,
            "worker_id": None,
            "assignment_status": "closed",
            "source": assignment.get("source") if assignment else "manual",
        },
    )
    await audit_svc.append(
        db,
        AuditAction.open_shift_closed,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={
            "cascade_cancelled": cascade_cancelled,
            "previous_assignment_status": assignment.get("assignment_status") if assignment else None,
            "previous_shift_status": shift.get("status") if shift else None,
        },
    )

    refreshed_shift = await queries.get_shift(db, shift_id)
    refreshed_assignment = await queries.get_shift_assignment_with_worker(db, shift_id)
    shift_payload = _serialize_schedule_shift_payload(
        shift=refreshed_shift,
        assignment=refreshed_assignment,
        active_cascade=None,
        pending_claim_worker=None,
    )
    return {
        "status": "closed",
        "shift_id": shift_id,
        "cascade_cancelled": cascade_cancelled,
        "idempotent": False,
        "shift": refreshed_shift,
        "assignment": shift_payload["assignment"],
        "coverage": shift_payload["coverage"],
        "available_actions": shift_payload["available_actions"],
    }


async def reopen_open_shift(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    start_open_shift_offer: bool = False,
    actor: str = "manager_api",
) -> dict:
    shift, assignment, active_cascade = await _get_open_shift_lifecycle_context(
        db,
        shift_id=shift_id,
    )
    assignment_status = assignment.get("assignment_status") if assignment else None
    if active_cascade is not None:
        raise ValueError("Shift already has an active offer")
    if assignment and assignment.get("worker_id") is not None and assignment_status in {"assigned", "claimed", "confirmed"}:
        raise ValueError("Shift already has an assignee")
    if assignment_status != "closed":
        raise ValueError("Shift is not closed")

    await queries.update_shift_status(
        db,
        shift_id=shift_id,
        status="scheduled",
        filled_by=None,
        fill_tier=None,
        called_out_by=None,
    )
    await queries.upsert_shift_assignment(
        db,
        {
            "shift_id": shift_id,
            "worker_id": None,
            "assignment_status": "open",
            "source": assignment.get("source") if assignment else "manual",
        },
    )
    await audit_svc.append(
        db,
        AuditAction.open_shift_reopened,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={
            "start_open_shift_offer": start_open_shift_offer,
            "previous_assignment_status": assignment_status,
            "previous_shift_status": shift.get("status"),
        },
    )

    if start_open_shift_offer:
        coverage_result = await start_coverage_for_open_shift(
            db,
            shift_id=shift_id,
            actor=actor,
        )
        return {
            **coverage_result,
            "reopened": True,
        }

    refreshed_shift = await queries.get_shift(db, shift_id)
    refreshed_assignment = await queries.get_shift_assignment_with_worker(db, shift_id)
    shift_payload = _serialize_schedule_shift_payload(
        shift=refreshed_shift,
        assignment=refreshed_assignment,
        active_cascade=None,
        pending_claim_worker=None,
    )
    return {
        "status": "reopened",
        "shift_id": shift_id,
        "idempotent": False,
        "shift": refreshed_shift,
        "assignment": shift_payload["assignment"],
        "coverage": shift_payload["coverage"],
        "available_actions": shift_payload["available_actions"],
    }


async def copy_schedule_week(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    source_schedule_id: int,
    target_week_start_date: str,
    actor: str = "system",
) -> dict:
    source_schedule = await queries.get_schedule(db, source_schedule_id)
    if source_schedule is None or int(source_schedule["location_id"]) != location_id:
        raise ValueError("Source schedule not found")
    existing_target = await queries.get_schedule_by_location_week(db, location_id, target_week_start_date)
    if existing_target is not None:
        raise ValueError("A schedule already exists for the target week")

    source_week_start = date.fromisoformat(source_schedule["week_start_date"])
    target_week_start = date.fromisoformat(target_week_start_date)
    day_delta = (target_week_start - source_week_start).days

    target_schedule_id = await queries.insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": target_week_start_date,
            "week_end_date": _week_end_for(target_week_start).isoformat(),
            "lifecycle_state": "draft",
            "derived_from_schedule_id": source_schedule_id,
            "created_by": actor,
        },
    )

    copied_shift_count = 0
    open_shift_count = 0
    source_shifts = await queries.list_shifts(db, schedule_id=source_schedule_id)
    for source_shift in source_shifts:
        source_date = date.fromisoformat(source_shift["date"])
        target_date = source_date + timedelta(days=day_delta)
        shift_id = await queries.insert_shift(
            db,
            {
                "location_id": location_id,
                "schedule_id": target_schedule_id,
                "role": source_shift["role"],
                "date": target_date.isoformat(),
                "start_time": source_shift["start_time"],
                "end_time": source_shift["end_time"],
                "spans_midnight": bool(source_shift.get("spans_midnight")),
                "pay_rate": source_shift.get("pay_rate", 0.0),
                "requirements": source_shift.get("requirements") or [],
                "status": "scheduled",
                "source_platform": source_shift.get("source_platform", "backfill_native"),
                "shift_label": source_shift.get("shift_label"),
                "notes": source_shift.get("notes"),
                "published_state": "draft",
            },
        )
        copied_shift_count += 1
        assignment = await queries.get_shift_assignment(db, source_shift["id"])
        worker_id = assignment.get("worker_id") if assignment else None
        assignment_status = "assigned" if worker_id else "open"
        if worker_id is None:
            open_shift_count += 1
        await queries.upsert_shift_assignment(
            db,
            {
                "shift_id": shift_id,
                "worker_id": worker_id,
                "assignment_status": assignment_status,
                "source": "copy_last_week",
            },
        )

    version_id = await _create_schedule_version(
        db,
        schedule_id=target_schedule_id,
        version_type="draft_snapshot",
        change_summary={"source_schedule_id": source_schedule_id},
    )
    await queries.update_schedule(db, target_schedule_id, {"current_version_id": version_id})
    await _notify_manager_schedule_draft(
        db,
        location_id=location_id,
        schedule_id=target_schedule_id,
        week_start_date=target_week_start_date,
        import_rows=[],
        first_draft=False,
    )
    return {
        "schedule_id": target_schedule_id,
        "location_id": location_id,
        "week_start_date": target_week_start_date,
        "lifecycle_state": "draft",
        "copied_shift_count": copied_shift_count,
        "open_shift_count": open_shift_count,
        "warning_count": open_shift_count,
    }


async def copy_schedule_day(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    source_date: str,
    target_date: str,
    copy_assignments: bool = False,
    replace_target_day: bool = False,
    actor: str = "manager_api",
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    current_state = schedule.get("lifecycle_state") or "draft"
    if current_state == "archived":
        raise ValueError("Archived schedules are read-only")

    week_start = date.fromisoformat(str(schedule["week_start_date"]))
    week_end = date.fromisoformat(str(schedule["week_end_date"]))
    source_day = date.fromisoformat(source_date)
    target_day = date.fromisoformat(target_date)
    if source_day == target_day:
        raise ValueError("Source and target dates must differ")
    if source_day < week_start or source_day > week_end:
        raise ValueError("Source date must be within the schedule week")
    if target_day < week_start or target_day > week_end:
        raise ValueError("Target date must be within the schedule week")

    schedule_shifts = await queries.list_shifts(db, schedule_id=schedule_id)
    source_shifts = [shift for shift in schedule_shifts if shift.get("date") == source_date]
    target_shifts = [shift for shift in schedule_shifts if shift.get("date") == target_date]
    if not source_shifts:
        raise ValueError("Source date has no shifts to copy")
    if target_shifts and not replace_target_day:
        raise ValueError("Target date already has shifts")

    for shift in target_shifts:
        active_cascade = await queries.get_active_cascade_for_shift(db, int(shift["id"]))
        if active_cascade is not None:
            raise ValueError("Cannot replace target date with active coverage workflow")
        if shift.get("status") != "scheduled":
            raise ValueError("Only scheduled target shifts can be replaced")

    created_shift_ids: list[int] = []
    replaced_shift_count = 0
    copied_assignments_count = 0
    skipped_assignments_count = 0

    if replace_target_day:
        replaced_shift_count = len(target_shifts)
        for target_shift in target_shifts:
            await queries.delete_shift_assignment(db, int(target_shift["id"]))
            await queries.delete_shift(db, int(target_shift["id"]))

    for source_shift in source_shifts:
        shift_id = await queries.insert_shift(
            db,
            {
                "location_id": int(schedule["location_id"]),
                "schedule_id": schedule_id,
                "role": source_shift["role"],
                "date": target_date,
                "start_time": source_shift["start_time"],
                "end_time": source_shift["end_time"],
                "spans_midnight": bool(source_shift.get("spans_midnight")),
                "pay_rate": source_shift.get("pay_rate", 0.0),
                "requirements": source_shift.get("requirements") or [],
                "status": "scheduled",
                "source_platform": source_shift.get("source_platform", "backfill_native"),
                "shift_label": source_shift.get("shift_label"),
                "notes": source_shift.get("notes"),
                "published_state": "amended" if current_state in {"published", "amended"} else "draft",
            },
        )
        created_shift_ids.append(shift_id)

        assignment = await queries.get_shift_assignment(db, int(source_shift["id"]))
        target_worker_id = None
        target_assignment_status = "open"
        if copy_assignments and assignment and assignment.get("worker_id") is not None:
            worker = await queries.get_worker(db, int(assignment["worker_id"]))
            if (
                worker is not None
                and (worker.get("employment_status") or "active") == "active"
                and worker.get("location_id") == schedule.get("location_id")
                and source_shift.get("role") in (worker.get("roles") or [])
                and assignment.get("assignment_status") in {"assigned", "claimed", "confirmed"}
            ):
                target_worker_id = int(worker["id"])
                target_assignment_status = "assigned"
                copied_assignments_count += 1
            else:
                skipped_assignments_count += 1
        await queries.upsert_shift_assignment(
            db,
            {
                "shift_id": shift_id,
                "worker_id": target_worker_id,
                "assignment_status": target_assignment_status,
                "source": "copy_day",
            },
        )

    next_state, version_id = await _apply_schedule_mutation(
        db,
        schedule=schedule,
        actor=actor,
        change_summary={
            "event": "day_copied",
            "source_date": source_date,
            "target_date": target_date,
            "copied_shift_count": len(created_shift_ids),
            "replace_target_day": replace_target_day,
            "copy_assignments": copy_assignments,
        },
    )
    if next_state == "amended":
        for shift_id in created_shift_ids:
            await queries.update_shift(db, shift_id, {"published_state": "amended"})
        await audit_svc.append(
            db,
            AuditAction.schedule_amended,
            actor=actor,
            entity_type="schedule",
            entity_id=schedule_id,
            details={
                "source_date": source_date,
                "target_date": target_date,
                "version_id": version_id,
            },
        )

    refreshed_schedule_view = await get_schedule_view(
        db,
        location_id=int(schedule["location_id"]),
        week_start=str(schedule["week_start_date"]),
    )
    return {
        "schedule_id": schedule_id,
        "source_date": source_date,
        "target_date": target_date,
        "copied_shift_count": len(created_shift_ids),
        "replaced_shift_count": replaced_shift_count,
        "copied_assignments": copied_assignments_count,
        "skipped_assignments": skipped_assignments_count,
        "schedule_lifecycle_state": next_state,
        "version_id": version_id,
        "schedule_view": refreshed_schedule_view,
    }


async def list_schedule_templates(
    db: aiosqlite.Connection,
    *,
    location_id: int,
) -> dict:
    templates = await queries.list_schedule_templates_for_location(db, location_id)
    items: list[dict] = []
    for template in templates:
        slots = await queries.list_schedule_template_shifts(db, int(template["id"]))
        items.append(
            await _serialize_schedule_template_detail(
                db,
                template=template,
                slots=slots,
            )
        )
    return {
        "location_id": location_id,
        "templates": items,
    }


async def get_schedule_template_detail(
    db: aiosqlite.Connection,
    *,
    template_id: int,
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    slots = await queries.list_schedule_template_shifts(db, template_id)
    template_payload = await _serialize_schedule_template_detail(
        db,
        template=template,
        slots=slots,
    )
    template_payload["staffing_plan"] = await _build_template_staffing_plan(
        db,
        template=template,
        slots=slots,
    )
    return {
        "template": template_payload,
    }


async def _find_latest_schedule_with_shifts_for_location(
    db: aiosqlite.Connection,
    *,
    location_id: int,
) -> dict | None:
    schedules = await queries.list_schedules_for_location(db, location_id)
    for schedule in schedules:
        shifts = await queries.list_shifts(db, schedule_id=int(schedule["id"]))
        if shifts:
            return schedule
    return None


async def get_schedule_draft_options(
    db: aiosqlite.Connection,
    *,
    location_id: int,
) -> dict:
    templates = await queries.list_schedule_templates_for_location(db, location_id)
    template_items: list[dict] = []
    for template in templates:
        slots = await queries.list_schedule_template_shifts(db, int(template["id"]))
        template_items.append(
            await _serialize_schedule_template_detail(
                db,
                template=template,
                slots=slots,
            )
        )

    latest_schedule = await _find_latest_schedule_with_shifts_for_location(
        db,
        location_id=location_id,
    )
    latest_schedule_summary = None
    if latest_schedule is not None:
        review = await get_schedule_review(db, schedule_id=int(latest_schedule["id"]))
        latest_schedule_summary = {
            "id": int(latest_schedule["id"]),
            "week_start_date": latest_schedule.get("week_start_date"),
            "week_end_date": latest_schedule.get("week_end_date"),
            "lifecycle_state": latest_schedule.get("lifecycle_state"),
            "filled_shifts": review["summary"]["filled_shifts"],
            "open_shifts": review["summary"]["open_shifts"],
            "warning_count": review["summary"]["warning_count"],
            "publish_readiness": review["publish_readiness"],
        }

    recommended_basis = None
    if template_items:
        recommended_basis = {
            "basis_type": "template",
            "template_id": int(template_items[0]["id"]),
        }
    elif latest_schedule_summary is not None:
        recommended_basis = {
            "basis_type": "schedule",
            "schedule_id": int(latest_schedule_summary["id"]),
        }

    return {
        "location_id": location_id,
        "recommended_basis": recommended_basis,
        "can_generate_ai_draft": bool(template_items or latest_schedule_summary),
        "can_create_from_template": bool(template_items),
        "templates": template_items,
        "latest_schedule": latest_schedule_summary,
    }


def _filter_template_slots_by_day(
    slots: list[dict],
    day_of_week_filter: list[int] | None,
) -> list[dict]:
    normalized_days = _normalize_day_of_week_filter(day_of_week_filter)
    if not normalized_days:
        return list(slots)
    return [slot for slot in slots if int(slot["day_of_week"]) in normalized_days]


def _template_worker_roles(worker: dict) -> list[str]:
    values = list(worker.get("active_assignment", {}).get("roles") or []) + list(worker.get("roles") or [])
    result: list[str] = []
    for value in values:
        text = (value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _template_slots_overlap(left: dict, right: dict) -> bool:
    left_start, left_end = _slot_interval(left)
    right_start, right_end = _slot_interval(right)
    return max(left_start, right_start) < min(left_end, right_end)


async def _list_template_candidate_workers(
    db: aiosqlite.Connection,
    *,
    location_id: int,
) -> list[dict]:
    from app.services import roster as roster_svc

    roster = await roster_svc.list_roster_for_location(
        db,
        location_id=location_id,
        include_inactive=False,
    )
    candidates: list[dict] = []
    for worker in roster["workers"]:
        if worker.get("worker_type") not in {None, "internal"}:
            continue
        if not worker.get("is_active_at_location"):
            continue
        candidates.append(
            {
                **worker,
                "eligible_roles": _template_worker_roles(worker),
            }
        )
    candidates.sort(
        key=lambda worker: (
            _template_worker_priority_rank(worker),
            (worker.get("name") or "").lower(),
            int(worker.get("id") or 0),
        )
    )
    return candidates


async def _build_template_staffing_plan(
    db: aiosqlite.Connection,
    *,
    template: dict,
    slots: list[dict],
    assignment_strategy: str = "priority_first",
) -> dict:
    strategy = _normalize_assignment_strategy(assignment_strategy)
    location_id = int(template["location_id"])
    candidates = await _list_template_candidate_workers(db, location_id=location_id)

    role_summary_map: dict[str, dict] = {}
    worker_summary_map: dict[int, dict] = {}
    fixed_assignments: dict[int, list[dict]] = {}
    worker_shift_counts: dict[int, int] = {}
    assigned_hours = 0.0
    open_hours = 0.0
    overtime_risk_count = 0
    staffing_gap_count = 0
    auto_assignable_shift_count = 0
    planning_shifts: list[dict] = []

    serialized_slots: list[dict] = []
    overlap_warnings_by_slot, template_warnings = _collect_template_overlap_warnings(slots)
    for slot in slots:
        slot_payload = _serialize_schedule_template_shift(slot)
        warnings = await _build_template_slot_warnings(
            db,
            location_id=location_id,
            slot=slot,
        )
        warnings.extend(overlap_warnings_by_slot.get(int(slot["id"]), []))
        slot_payload["warnings"] = warnings
        serialized_slots.append(slot_payload)

    for worker in candidates:
        worker_summary_map[int(worker["id"])] = {
            "worker_id": int(worker["id"]),
            "worker_name": worker.get("name"),
            "priority_rank": _template_worker_priority_rank(worker),
            "eligible_roles": list(worker.get("eligible_roles") or []),
            "max_hours_per_week": worker.get("max_hours_per_week"),
            "assigned_template_hours": 0.0,
            "assigned_shift_count": 0,
        }

    for slot in serialized_slots:
        duration_hours = _slot_duration_hours(slot)
        role_entry = role_summary_map.setdefault(
            str(slot["role"]),
            {
                "role": str(slot["role"]),
                "shift_count": 0,
                "assigned_shift_count": 0,
                "open_shift_count": 0,
                "total_hours": 0.0,
                "assigned_hours": 0.0,
                "open_hours": 0.0,
                "eligible_worker_count": 0,
            },
        )
        role_entry["shift_count"] += 1
        role_entry["total_hours"] = round(role_entry["total_hours"] + duration_hours, 2)

        valid_assigned = _slot_worker_is_assigned(slot) and not slot.get("warnings")
        if valid_assigned:
            assigned_hours = round(assigned_hours + duration_hours, 2)
            role_entry["assigned_shift_count"] += 1
            role_entry["assigned_hours"] = round(role_entry["assigned_hours"] + duration_hours, 2)
            worker_id = int(slot["worker_id"])
            fixed_assignments.setdefault(worker_id, []).append(slot)
            if worker_id in worker_summary_map:
                worker_summary_map[worker_id]["assigned_template_hours"] = round(
                    worker_summary_map[worker_id]["assigned_template_hours"] + duration_hours,
                    2,
                )
                worker_summary_map[worker_id]["assigned_shift_count"] += 1
                worker_shift_counts[worker_id] = worker_shift_counts.get(worker_id, 0) + 1
        else:
            open_hours = round(open_hours + duration_hours, 2)
            role_entry["open_shift_count"] += 1
            role_entry["open_hours"] = round(role_entry["open_hours"] + duration_hours, 2)

    for role, role_entry in role_summary_map.items():
        role_entry["eligible_worker_count"] = sum(
            1 for worker in candidates if role in (worker.get("eligible_roles") or [])
        )

    for slot in serialized_slots:
        duration_hours = _slot_duration_hours(slot)
        valid_assigned = _slot_worker_is_assigned(slot) and not slot.get("warnings")
        current_worker_id = int(slot["worker_id"]) if slot.get("worker_id") is not None else None
        current_worker_summary = worker_summary_map.get(current_worker_id) if current_worker_id is not None else None
        overtime_risk = False
        if valid_assigned and current_worker_summary is not None and current_worker_summary.get("max_hours_per_week") is not None:
            overtime_risk = bool(
                current_worker_summary["assigned_template_hours"] > float(current_worker_summary["max_hours_per_week"])
            )
            if overtime_risk:
                overtime_risk_count += 1

        suggested_workers: list[dict] = []
        if not valid_assigned:
            suggested_workers = _build_template_worker_suggestions(
                slot=slot,
                candidates=candidates,
                worker_assignments=fixed_assignments,
                worker_hours={
                    worker_id: float(summary["assigned_template_hours"])
                    for worker_id, summary in worker_summary_map.items()
                },
                worker_shift_counts=worker_shift_counts,
                assignment_strategy=strategy,
            )
            if suggested_workers:
                auto_assignable_shift_count += 1
            else:
                staffing_gap_count += 1

        recommended_worker = suggested_workers[0] if suggested_workers else None
        planning_shifts.append(
            {
                "shift_id": int(slot["id"]),
                "day_of_week": int(slot["day_of_week"]),
                "role": slot["role"],
                "start_time": slot["start_time"],
                "end_time": slot["end_time"],
                "spans_midnight": bool(slot.get("spans_midnight")),
                "duration_hours": duration_hours,
                "current_worker_id": current_worker_id,
                "current_worker_name": slot.get("worker_name"),
                "current_assignment_status": slot.get("assignment_status") or "open",
                "warning_count": len(slot.get("warnings") or []),
                "warnings": list(slot.get("warnings") or []),
                "is_assigned": valid_assigned,
                "needs_review": (not valid_assigned) or overtime_risk,
                "overtime_risk": overtime_risk,
                "staffing_gap": (not valid_assigned and not suggested_workers),
                "suggestion_strategy": strategy,
                "suggestion_count": len(suggested_workers),
                "recommended_worker_id": recommended_worker.get("worker_id") if recommended_worker else None,
                "recommended_worker_name": recommended_worker.get("worker_name") if recommended_worker else None,
                "recommended_confidence": recommended_worker.get("confidence") if recommended_worker else None,
                "suggested_workers": suggested_workers,
            }
        )

    workers_summary: list[dict] = []
    over_capacity_worker_count = 0
    for item in sorted(worker_summary_map.values(), key=lambda row: (row["priority_rank"], row["worker_name"] or "", row["worker_id"])):
        max_hours = item.get("max_hours_per_week")
        assigned_template_hours = float(item["assigned_template_hours"])
        remaining_hours = round(float(max_hours) - assigned_template_hours, 2) if max_hours is not None else None
        if max_hours is None:
            load_status = "no_limit"
        elif assigned_template_hours > float(max_hours):
            load_status = "over_capacity"
            over_capacity_worker_count += 1
        elif assigned_template_hours == float(max_hours):
            load_status = "at_capacity"
        else:
            load_status = "available"
        workers_summary.append(
            {
                **item,
                "remaining_hours": remaining_hours,
                "load_status": load_status,
            }
        )

    review_required_count = sum(1 for shift in planning_shifts if shift["needs_review"])
    recommended_assignment_count = sum(
        1 for shift in planning_shifts if shift.get("recommended_worker_id") is not None
    )
    coverage_risk_count = sum(1 for shift in planning_shifts if not shift["is_assigned"])

    return {
        "summary": {
            "shift_count": len(serialized_slots),
            "total_hours": round(assigned_hours + open_hours, 2),
            "assigned_shift_count": sum(1 for slot in serialized_slots if _slot_worker_is_assigned(slot) and not slot.get("warnings")),
            "open_shift_count": sum(1 for slot in serialized_slots if not (_slot_worker_is_assigned(slot) and not slot.get("warnings"))),
            "assigned_hours": assigned_hours,
            "open_hours": open_hours,
            "eligible_worker_count": len(candidates),
            "staffing_gap_count": staffing_gap_count,
            "auto_assignable_shift_count": auto_assignable_shift_count,
            "overtime_risk_count": overtime_risk_count,
            "over_capacity_worker_count": over_capacity_worker_count,
            "review_required_count": review_required_count,
            "recommended_assignment_count": recommended_assignment_count,
            "coverage_risk_count": coverage_risk_count,
            "assignment_strategy": strategy,
            "ready_to_generate": len(serialized_slots) > 0,
            "ready_to_publish": len(serialized_slots) > 0 and review_required_count == 0,
        },
        "roles": sorted(role_summary_map.values(), key=lambda item: item["role"]),
        "workers": workers_summary,
        "shifts": planning_shifts,
        "template_warnings": template_warnings,
        "assignment_strategy": strategy,
    }


def _normalize_template_slot_payload(
    payload: dict,
    *,
    existing: dict | None = None,
) -> dict:
    merged = dict(existing or {})
    merged.update(payload)

    role = _trim_text(merged.get("role"))
    if not role:
        raise ValueError("Role is required")
    day_of_week = merged.get("day_of_week")
    if day_of_week is None or int(day_of_week) < 0 or int(day_of_week) > 6:
        raise ValueError("Day of week must be between 0 and 6")
    start_time = _parse_time(merged.get("start_time"))
    end_time = _parse_time(merged.get("end_time"))
    if start_time is None or end_time is None:
        raise ValueError("Start and end times are required")
    spans_midnight = bool(merged.get("spans_midnight", False))
    if not spans_midnight and end_time <= start_time:
        raise ValueError("End time must be after start time unless spans_midnight is true")

    worker_id = merged.get("worker_id")
    assignment_status = merged.get("assignment_status")
    normalized_assignment_status = assignment_status or ("assigned" if worker_id is not None else "open")
    if worker_id is None and normalized_assignment_status in {"assigned", "claimed", "confirmed"}:
        raise ValueError("Assigned template shifts require a worker")
    if worker_id is not None and normalized_assignment_status in {"open", "closed"}:
        raise ValueError("Open or closed template shifts cannot keep a worker assigned")
    if normalized_assignment_status not in {"open", "assigned", "claimed", "confirmed"}:
        raise ValueError("Unsupported assignment status")

    return {
        "day_of_week": int(day_of_week),
        "role": role,
        "start_time": start_time.strftime("%H:%M:%S"),
        "end_time": end_time.strftime("%H:%M:%S"),
        "spans_midnight": spans_midnight,
        "pay_rate": float(merged.get("pay_rate") or 0.0),
        "requirements": list(merged.get("requirements") or []),
        "shift_label": _trim_text(merged.get("shift_label")),
        "notes": _trim_text(merged.get("notes")),
        "worker_id": int(worker_id) if worker_id is not None else None,
        "assignment_status": normalized_assignment_status,
    }


async def _assert_template_slot_worker_valid(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    role: str,
    worker_id: int | None,
    assignment_status: str,
) -> None:
    if worker_id is None or assignment_status not in {"assigned", "claimed", "confirmed"}:
        return
    worker = await queries.get_worker(db, worker_id)
    if worker is None:
        raise ValueError("Worker not found")
    if (worker.get("employment_status") or "active") != "active":
        raise ValueError("Worker is not active")
    if worker.get("location_id") != location_id:
        raise ValueError("Worker is not assigned to this location")
    if role not in (worker.get("roles") or []):
        raise ValueError("Worker is not eligible for this role")


async def create_manual_schedule_template(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    name: str,
    description: str | None = None,
    actor: str = "manager_api",
) -> dict:
    template_name = name.strip()
    if not template_name:
        raise ValueError("Template name is required")
    template_id = await queries.insert_schedule_template(
        db,
        {
            "location_id": location_id,
            "name": template_name,
            "description": description,
            "created_by": actor,
        },
    )
    await audit_svc.append(
        db,
        AuditAction.schedule_template_created,
        actor=actor,
        entity_type="schedule_template",
        entity_id=template_id,
        details={"source": "manual"},
    )
    template = await queries.get_schedule_template(db, template_id)
    assert template is not None
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=template,
            slots=[],
        ),
    }


async def _extract_schedule_template_slots_from_schedule(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    include_assignments: bool,
) -> tuple[dict, list[dict], int]:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")

    source_shifts = await queries.list_shifts(db, schedule_id=schedule_id)
    template_shift_payloads: list[dict] = []
    assigned_shift_count = 0
    for shift in source_shifts:
        assignment = await queries.get_shift_assignment_with_worker(db, int(shift["id"]))
        assignment_status = assignment.get("assignment_status") if assignment else None
        if assignment_status == "closed":
            continue

        worker_id = None
        slot_assignment_status = "open"
        if (
            include_assignments
            and assignment
            and assignment.get("worker_id") is not None
            and assignment_status in {"assigned", "claimed", "confirmed"}
        ):
            worker_id = int(assignment["worker_id"])
            slot_assignment_status = "assigned"
            assigned_shift_count += 1

        template_shift_payloads.append(
            {
                "day_of_week": date.fromisoformat(str(shift["date"])).weekday(),
                "role": shift["role"],
                "start_time": shift["start_time"],
                "end_time": shift["end_time"],
                "spans_midnight": bool(shift.get("spans_midnight")),
                "pay_rate": shift.get("pay_rate", 0.0),
                "requirements": shift.get("requirements") or [],
                "shift_label": shift.get("shift_label"),
                "notes": shift.get("notes"),
                "worker_id": worker_id,
                "assignment_status": slot_assignment_status,
            }
        )

    if not template_shift_payloads:
        raise ValueError("Schedule has no reusable shifts")
    return schedule, template_shift_payloads, assigned_shift_count


async def create_schedule_template_from_schedule(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    name: str,
    description: str | None = None,
    include_assignments: bool = True,
    actor: str = "manager_api",
) -> dict:
    template_name = name.strip()
    if not template_name:
        raise ValueError("Template name is required")

    schedule, template_shift_payloads, assigned_shift_count = await _extract_schedule_template_slots_from_schedule(
        db,
        schedule_id=schedule_id,
        include_assignments=include_assignments,
    )

    template_id = await queries.insert_schedule_template(
        db,
        {
            "location_id": int(schedule["location_id"]),
            "name": template_name,
            "description": description,
            "source_schedule_id": schedule_id,
            "created_by": actor,
        },
    )
    for slot in template_shift_payloads:
        await queries.insert_schedule_template_shift(
            db,
            {
                "template_id": template_id,
                **slot,
            },
        )

    await audit_svc.append(
        db,
        AuditAction.schedule_template_created,
        actor=actor,
        entity_type="schedule_template",
        entity_id=template_id,
        details={
            "schedule_id": schedule_id,
            "include_assignments": include_assignments,
            "shift_count": len(template_shift_payloads),
            "assigned_shift_count": assigned_shift_count,
        },
    )

    template = await queries.get_schedule_template(db, template_id)
    assert template is not None
    slots = await queries.list_schedule_template_shifts(db, template_id)
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=template,
            slots=slots,
        ),
    }


async def update_schedule_template(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    patch: dict,
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")

    updates: dict[str, object] = {}
    if "name" in patch:
        name = str(patch.get("name") or "").strip()
        if not name:
            raise ValueError("Template name is required")
        updates["name"] = name
    if "description" in patch:
        updates["description"] = patch.get("description")
    if updates:
        await queries.update_schedule_template(db, template_id, updates)
        await audit_svc.append(
            db,
            AuditAction.schedule_template_updated,
            actor=actor,
            entity_type="schedule_template",
            entity_id=template_id,
            details={"updated_fields": sorted(updates.keys())},
        )

    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, template_id)
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
    }


async def clone_schedule_template(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    name: str | None = None,
    description: str | None = None,
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    cloned_name = (name or f"{template['name']} Copy").strip()
    if not cloned_name:
        raise ValueError("Template name is required")
    source_slots = await queries.list_schedule_template_shifts(db, template_id)
    cloned_template_id = await queries.insert_schedule_template(
        db,
        {
            "location_id": int(template["location_id"]),
            "name": cloned_name,
            "description": description if description is not None else template.get("description"),
            "source_schedule_id": template.get("source_schedule_id"),
            "created_by": actor,
        },
    )
    for slot in source_slots:
        await queries.insert_schedule_template_shift(
            db,
            {
                "template_id": cloned_template_id,
                "day_of_week": int(slot["day_of_week"]),
                "role": slot["role"],
                "start_time": slot["start_time"],
                "end_time": slot["end_time"],
                "spans_midnight": bool(slot.get("spans_midnight")),
                "pay_rate": slot.get("pay_rate", 0.0),
                "requirements": slot.get("requirements") or [],
                "shift_label": slot.get("shift_label"),
                "notes": slot.get("notes"),
                "worker_id": slot.get("worker_id"),
                "assignment_status": slot.get("assignment_status") or "open",
            },
        )
    await audit_svc.append(
        db,
        AuditAction.schedule_template_created,
        actor=actor,
        entity_type="schedule_template",
        entity_id=cloned_template_id,
        details={"source": "clone", "template_id": template_id},
    )
    cloned_template = await queries.get_schedule_template(db, cloned_template_id)
    assert cloned_template is not None
    cloned_slots = await queries.list_schedule_template_shifts(db, cloned_template_id)
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=cloned_template,
            slots=cloned_slots,
        ),
    }


async def refresh_schedule_template_from_schedule(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    source_schedule_id: int | None = None,
    include_assignments: bool = True,
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")

    resolved_source_schedule_id = int(source_schedule_id or template.get("source_schedule_id") or 0)
    if resolved_source_schedule_id <= 0:
        raise ValueError("Source schedule is required")

    source_schedule, template_shift_payloads, assigned_shift_count = await _extract_schedule_template_slots_from_schedule(
        db,
        schedule_id=resolved_source_schedule_id,
        include_assignments=include_assignments,
    )
    if int(source_schedule["location_id"]) != int(template["location_id"]):
        raise ValueError("Source schedule must belong to the same location")

    existing_slots = await queries.list_schedule_template_shifts(db, template_id)
    await queries.delete_schedule_template_shifts(db, template_id)
    for slot in template_shift_payloads:
        await queries.insert_schedule_template_shift(
            db,
            {
                "template_id": template_id,
                **slot,
            },
        )
    await queries.update_schedule_template(
        db,
        template_id,
        {"source_schedule_id": resolved_source_schedule_id},
    )
    await audit_svc.append(
        db,
        AuditAction.schedule_template_updated,
        actor=actor,
        entity_type="schedule_template",
        entity_id=template_id,
        details={
            "source_schedule_id": resolved_source_schedule_id,
            "include_assignments": include_assignments,
            "replaced_shift_count": len(existing_slots),
            "shift_count": len(template_shift_payloads),
        },
    )

    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, template_id)
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
        "source_schedule_id": resolved_source_schedule_id,
        "replaced_shift_count": len(existing_slots),
        "shift_count": len(template_shift_payloads),
        "assigned_shift_count": assigned_shift_count,
    }


async def preview_schedule_template(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    target_week_start_date: str,
    day_of_week_filter: list[int] | None = None,
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    slots = _filter_template_slots_by_day(
        await queries.list_schedule_template_shifts(db, template_id),
        day_of_week_filter,
    )
    if not slots:
        raise ValueError("Schedule template has no shifts for the selected days")
    week_start = date.fromisoformat(target_week_start_date)
    week_end = _week_end_for(week_start)
    existing_schedule = await queries.get_schedule_by_location_week(
        db,
        int(template["location_id"]),
        target_week_start_date,
    )
    existing_shift_count = 0
    if existing_schedule is not None:
        existing_shift_count = len(await queries.list_shifts(db, schedule_id=int(existing_schedule["id"])))

    preview_shifts: list[dict] = []
    copied_assignment_count = 0
    skipped_assignment_count = 0
    for slot in slots:
        warnings = await _build_template_slot_warnings(
            db,
            location_id=int(template["location_id"]),
            slot=slot,
        )
        shift_date = week_start + timedelta(days=int(slot["day_of_week"]))
        can_copy_assignment = (
            slot.get("worker_id") is not None
            and slot.get("assignment_status") in {"assigned", "claimed", "confirmed"}
            and not warnings
        )
        if can_copy_assignment:
            copied_assignment_count += 1
        elif slot.get("worker_id") is not None and slot.get("assignment_status") in {"assigned", "claimed", "confirmed"}:
            skipped_assignment_count += 1
        preview_shifts.append(
            {
                "day_of_week": int(slot["day_of_week"]),
                "date": shift_date.isoformat(),
                "role": slot["role"],
                "start_time": slot["start_time"],
                "end_time": slot["end_time"],
                "spans_midnight": bool(slot.get("spans_midnight")),
                "pay_rate": float(slot.get("pay_rate") or 0.0),
                "requirements": list(slot.get("requirements") or []),
                "shift_label": slot.get("shift_label"),
                "notes": slot.get("notes"),
                "assignment": {
                    "worker_id": slot.get("worker_id") if can_copy_assignment else None,
                    "worker_name": slot.get("worker_name") if can_copy_assignment else None,
                    "assignment_status": "assigned" if can_copy_assignment else "open",
                },
                "warnings": warnings,
            }
        )

    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=template,
            slots=slots,
        ),
        "staffing_plan": await _build_template_staffing_plan(
            db,
            template=template,
            slots=slots,
        ),
        "target_week_start_date": target_week_start_date,
        "target_week_end_date": week_end.isoformat(),
        "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
        "existing_schedule_id": int(existing_schedule["id"]) if existing_schedule else None,
        "existing_shift_count": existing_shift_count,
        "replace_required": existing_shift_count > 0,
        "summary": {
            "shift_count": len(preview_shifts),
            "copied_assignment_count": copied_assignment_count,
            "skipped_assignment_count": skipped_assignment_count,
        },
        "shifts": preview_shifts,
    }


async def get_schedule_template_staffing_plan(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    day_of_week_filter: list[int] | None = None,
    assignment_strategy: str = "priority_first",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    slots = _filter_template_slots_by_day(
        await queries.list_schedule_template_shifts(db, template_id),
        day_of_week_filter,
    )
    if not slots:
        raise ValueError("Schedule template has no shifts for the selected days")
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=template,
            slots=slots,
        ),
        "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
        "assignment_strategy": _normalize_assignment_strategy(assignment_strategy),
        "staffing_plan": await _build_template_staffing_plan(
            db,
            template=template,
            slots=slots,
            assignment_strategy=assignment_strategy,
        ),
    }


async def get_schedule_template_suggestions(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    day_of_week_filter: list[int] | None = None,
    assignment_strategy: str = "priority_first",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    slots = _filter_template_slots_by_day(
        await queries.list_schedule_template_shifts(db, template_id),
        day_of_week_filter,
    )
    if not slots:
        raise ValueError("Schedule template has no shifts for the selected days")

    normalized_strategy = _normalize_assignment_strategy(assignment_strategy)
    staffing_plan = await _build_template_staffing_plan(
        db,
        template=template,
        slots=slots,
        assignment_strategy=normalized_strategy,
    )
    suggestions = [item for item in staffing_plan["shifts"] if item.get("needs_review")]
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=template,
            slots=slots,
        ),
        "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
        "assignment_strategy": normalized_strategy,
        "summary": {
            **staffing_plan["summary"],
            "suggestion_shift_count": len(suggestions),
        },
        "suggestions": suggestions,
        "staffing_plan": staffing_plan,
    }


async def apply_schedule_template_suggestions(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    shift_ids: list[int] | None = None,
    selections: list[dict] | None = None,
    day_of_week_filter: list[int] | None = None,
    overwrite_existing_assignments: bool = False,
    assignment_strategy: str = "priority_first",
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")

    all_slots = await queries.list_schedule_template_shifts(db, template_id)
    selected_slots = _filter_template_slots_by_day(all_slots, day_of_week_filter)
    if not selected_slots:
        raise ValueError("Schedule template has no shifts for the selected days")

    normalized_strategy = _normalize_assignment_strategy(assignment_strategy)
    selection_map = {
        int(item["shift_id"]): int(item["worker_id"])
        for item in (selections or [])
    }
    target_ids = {int(shift_id) for shift_id in (shift_ids or [])}
    if not target_ids:
        target_ids = set(selection_map)
    if not target_ids:
        suggestions_payload = await get_schedule_template_suggestions(
            db,
            template_id=template_id,
            day_of_week_filter=day_of_week_filter,
            assignment_strategy=normalized_strategy,
        )
        target_ids = {
            int(item["shift_id"])
            for item in suggestions_payload["suggestions"]
            if item.get("recommended_worker_id") is not None
        }
    if not target_ids:
        raise ValueError("No template shifts selected for suggestion application")

    selected_scope_ids = {int(slot["id"]) for slot in selected_slots}
    if not target_ids.issubset(selected_scope_ids):
        raise ValueError("Some template shifts are not part of the selected template scope")

    slot_map = {int(slot["id"]): dict(slot) for slot in all_slots}
    candidates = await _list_template_candidate_workers(db, location_id=int(template["location_id"]))
    results: list[dict] = []
    applied_count = 0

    ordered_shift_ids = [
        int(slot["id"])
        for slot in sorted(
            [slot_map[shift_id] for shift_id in target_ids],
            key=lambda slot: (int(slot["day_of_week"]), str(slot["start_time"]), int(slot["id"])),
        )
    ]
    for shift_id in ordered_shift_ids:
        current_slot = slot_map[shift_id]
        warnings_by_slot = await _build_template_warning_map(
            db,
            location_id=int(template["location_id"]),
            slots=list(slot_map.values()),
        )
        current_warnings = warnings_by_slot.get(shift_id, [])
        valid_assigned = _slot_worker_is_assigned(current_slot) and not current_warnings
        if valid_assigned and not overwrite_existing_assignments:
            results.append(
                {
                    "shift_id": shift_id,
                    "status": "error",
                    "error": "Shift already has a valid assignment",
                }
            )
            continue

        worker_assignments, worker_hours, worker_shift_counts = _build_template_assignment_maps(
            slots=list(slot_map.values()),
            warnings_by_slot=warnings_by_slot,
            exclude_shift_id=shift_id,
        )
        suggested_workers = _build_template_worker_suggestions(
            slot=current_slot,
            candidates=candidates,
            worker_assignments=worker_assignments,
            worker_hours=worker_hours,
            worker_shift_counts=worker_shift_counts,
            assignment_strategy=normalized_strategy,
        )
        suggested_worker_ids = {int(item["worker_id"]) for item in suggested_workers}
        target_worker_id = selection_map.get(shift_id)
        if target_worker_id is None and suggested_workers:
            target_worker_id = int(suggested_workers[0]["worker_id"])

        if target_worker_id is None:
            results.append(
                {
                    "shift_id": shift_id,
                    "status": "error",
                    "error": "No suggested worker is available for this shift",
                }
            )
            continue
        if target_worker_id not in suggested_worker_ids:
            results.append(
                {
                    "shift_id": shift_id,
                    "status": "error",
                    "error": "Selected worker is not a current suggestion for this shift",
                }
            )
            continue

        chosen_worker = next(
            item for item in suggested_workers if int(item["worker_id"]) == target_worker_id
        )
        await queries.update_schedule_template_shift(
            db,
            shift_id,
            {"worker_id": target_worker_id, "assignment_status": "assigned"},
        )
        slot_map[shift_id]["worker_id"] = target_worker_id
        slot_map[shift_id]["worker_name"] = chosen_worker.get("worker_name")
        slot_map[shift_id]["assignment_status"] = "assigned"
        applied_count += 1
        results.append(
            {
                "shift_id": shift_id,
                "status": "ok",
                "worker_id": target_worker_id,
                "worker_name": chosen_worker.get("worker_name"),
                "confidence": chosen_worker.get("confidence"),
            }
        )

    if applied_count:
        await queries.update_schedule_template(db, template_id, {"updated_at": datetime.utcnow().isoformat()})
        await audit_svc.append(
            db,
            AuditAction.schedule_template_updated,
            actor=actor,
            entity_type="schedule_template",
            entity_id=template_id,
            details={
                "action": "suggestions_applied",
                "applied_count": applied_count,
                "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
                "assignment_strategy": normalized_strategy,
            },
        )

    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, template_id)
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
        "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
        "assignment_strategy": normalized_strategy,
        "processed_count": len(ordered_shift_ids),
        "applied_count": applied_count,
        "error_count": len(ordered_shift_ids) - applied_count,
        "results": results,
        "staffing_plan": await _build_template_staffing_plan(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
            assignment_strategy=normalized_strategy,
        ),
    }


async def clear_schedule_template_assignments(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    shift_ids: list[int] | None = None,
    day_of_week_filter: list[int] | None = None,
    only_invalid: bool = False,
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")

    all_slots = await queries.list_schedule_template_shifts(db, template_id)
    selected_slots = _filter_template_slots_by_day(all_slots, day_of_week_filter)
    if not selected_slots:
        raise ValueError("Schedule template has no shifts for the selected days")

    target_ids = {int(shift_id) for shift_id in (shift_ids or [])}
    if target_ids:
        selected_slots = [slot for slot in selected_slots if int(slot["id"]) in target_ids]
    if not selected_slots:
        raise ValueError("No template shifts selected for assignment clearing")

    warnings_by_slot = await _build_template_warning_map(
        db,
        location_id=int(template["location_id"]),
        slots=all_slots,
    )
    cleared_count = 0
    skipped_count = 0
    results: list[dict] = []
    for slot in selected_slots:
        shift_id = int(slot["id"])
        if only_invalid and not warnings_by_slot.get(shift_id):
            skipped_count += 1
            results.append(
                {
                    "shift_id": shift_id,
                    "status": "skipped",
                    "reason": "Shift does not have an invalid assignment",
                }
            )
            continue
        if not _slot_worker_is_assigned(slot):
            skipped_count += 1
            results.append(
                {
                    "shift_id": shift_id,
                    "status": "skipped",
                    "reason": "Shift is already open",
                }
            )
            continue

        await queries.update_schedule_template_shift(
            db,
            shift_id,
            {"worker_id": None, "assignment_status": "open"},
        )
        cleared_count += 1
        results.append({"shift_id": shift_id, "status": "ok"})

    if cleared_count:
        await queries.update_schedule_template(db, template_id, {"updated_at": datetime.utcnow().isoformat()})
        await audit_svc.append(
            db,
            AuditAction.schedule_template_updated,
            actor=actor,
            entity_type="schedule_template",
            entity_id=template_id,
            details={
                "action": "assignments_cleared",
                "cleared_count": cleared_count,
                "only_invalid": only_invalid,
                "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
            },
        )

    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, template_id)
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
        "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
        "only_invalid": only_invalid,
        "processed_count": len(selected_slots),
        "cleared_count": cleared_count,
        "skipped_count": skipped_count,
        "results": results,
        "staffing_plan": await _build_template_staffing_plan(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
    }


async def create_schedule_template_shift(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    slot: dict,
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    normalized = _normalize_template_slot_payload(slot)
    await _assert_template_slot_worker_valid(
        db,
        location_id=int(template["location_id"]),
        role=normalized["role"],
        worker_id=normalized["worker_id"],
        assignment_status=normalized["assignment_status"],
    )
    template_shift_id = await queries.insert_schedule_template_shift(
        db,
        {
            "template_id": template_id,
            **normalized,
        },
    )
    await queries.update_schedule_template(db, template_id, {"updated_at": datetime.utcnow().isoformat()})
    await audit_svc.append(
        db,
        AuditAction.schedule_template_updated,
        actor=actor,
        entity_type="schedule_template",
        entity_id=template_id,
        details={"action": "shift_created", "template_shift_id": template_shift_id},
    )
    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, template_id)
    created_slot = await queries.get_schedule_template_shift(db, template_shift_id)
    assert created_slot is not None
    slot_payload = _serialize_schedule_template_shift(created_slot)
    slot_payload["warnings"] = await _build_template_slot_warnings(
        db,
        location_id=int(template["location_id"]),
        slot=created_slot,
    )
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
        "shift": slot_payload,
    }


async def create_schedule_template_shifts_bulk(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    slots: list[dict],
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    if not slots:
        raise ValueError("At least one template shift is required")
    results: list[dict] = []
    for slot in slots:
        try:
            outcome = await create_schedule_template_shift(
                db,
                template_id=template_id,
                slot=slot,
                actor=actor,
            )
            results.append({"status": "ok", "shift": outcome["shift"]})
        except ValueError as exc:
            results.append({"status": "error", "error": str(exc), "slot": slot})
    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, template_id)
    success_count = sum(1 for item in results if item["status"] == "ok")
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
        "processed_count": len(slots),
        "success_count": success_count,
        "error_count": len(results) - success_count,
        "results": results,
    }


async def update_schedule_template_shift(
    db: aiosqlite.Connection,
    *,
    template_shift_id: int,
    patch: dict,
    actor: str = "manager_api",
) -> dict:
    existing_slot = await queries.get_schedule_template_shift(db, template_shift_id)
    if existing_slot is None:
        raise ValueError("Schedule template shift not found")
    template = await queries.get_schedule_template(db, int(existing_slot["template_id"]))
    if template is None:
        raise ValueError("Schedule template not found")
    normalized = _normalize_template_slot_payload(patch, existing=existing_slot)
    await _assert_template_slot_worker_valid(
        db,
        location_id=int(template["location_id"]),
        role=normalized["role"],
        worker_id=normalized["worker_id"],
        assignment_status=normalized["assignment_status"],
    )
    await queries.update_schedule_template_shift(db, template_shift_id, normalized)
    await queries.update_schedule_template(
        db,
        int(template["id"]),
        {"updated_at": datetime.utcnow().isoformat()},
    )
    await audit_svc.append(
        db,
        AuditAction.schedule_template_updated,
        actor=actor,
        entity_type="schedule_template",
        entity_id=int(template["id"]),
        details={
            "action": "shift_updated",
            "template_shift_id": template_shift_id,
            "updated_fields": sorted(patch.keys()),
        },
    )
    refreshed_template = await queries.get_schedule_template(db, int(template["id"]))
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, int(template["id"]))
    refreshed_slot = await queries.get_schedule_template_shift(db, template_shift_id)
    assert refreshed_slot is not None
    slot_payload = _serialize_schedule_template_shift(refreshed_slot)
    slot_payload["warnings"] = await _build_template_slot_warnings(
        db,
        location_id=int(template["location_id"]),
        slot=refreshed_slot,
    )
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
        "shift": slot_payload,
    }


async def update_schedule_template_shifts_bulk(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    shift_ids: list[int],
    patch: dict,
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    if not shift_ids:
        raise ValueError("At least one template shift is required")
    results: list[dict] = []
    for shift_id in [int(item) for item in shift_ids]:
        existing_slot = await queries.get_schedule_template_shift(db, shift_id)
        if existing_slot is None or int(existing_slot["template_id"]) != template_id:
            results.append({"template_shift_id": shift_id, "status": "error", "error": "Schedule template shift not found"})
            continue
        try:
            outcome = await update_schedule_template_shift(
                db,
                template_shift_id=shift_id,
                patch=patch,
                actor=actor,
            )
            results.append({"template_shift_id": shift_id, "status": "ok", "shift": outcome["shift"]})
        except ValueError as exc:
            results.append({"template_shift_id": shift_id, "status": "error", "error": str(exc)})
    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, template_id)
    success_count = sum(1 for item in results if item["status"] == "ok")
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
        "processed_count": len(shift_ids),
        "success_count": success_count,
        "error_count": len(results) - success_count,
        "updated_fields": sorted(patch.keys()),
        "results": results,
    }


async def duplicate_schedule_template_shift(
    db: aiosqlite.Connection,
    *,
    template_shift_id: int,
    day_of_week: int | None = None,
    actor: str = "manager_api",
) -> dict:
    existing_slot = await queries.get_schedule_template_shift(db, template_shift_id)
    if existing_slot is None:
        raise ValueError("Schedule template shift not found")
    template = await queries.get_schedule_template(db, int(existing_slot["template_id"]))
    if template is None:
        raise ValueError("Schedule template not found")
    duplicated_shift_id = await queries.insert_schedule_template_shift(
        db,
        {
            "template_id": int(existing_slot["template_id"]),
            "day_of_week": int(day_of_week if day_of_week is not None else existing_slot["day_of_week"]),
            "role": existing_slot["role"],
            "start_time": existing_slot["start_time"],
            "end_time": existing_slot["end_time"],
            "spans_midnight": bool(existing_slot.get("spans_midnight")),
            "pay_rate": existing_slot.get("pay_rate", 0.0),
            "requirements": existing_slot.get("requirements") or [],
            "shift_label": existing_slot.get("shift_label"),
            "notes": existing_slot.get("notes"),
            "worker_id": existing_slot.get("worker_id"),
            "assignment_status": existing_slot.get("assignment_status") or "open",
        },
    )
    await queries.update_schedule_template(
        db,
        int(template["id"]),
        {"updated_at": datetime.utcnow().isoformat()},
    )
    await audit_svc.append(
        db,
        AuditAction.schedule_template_updated,
        actor=actor,
        entity_type="schedule_template",
        entity_id=int(template["id"]),
        details={
            "action": "shift_duplicated",
            "source_template_shift_id": template_shift_id,
            "template_shift_id": duplicated_shift_id,
            "day_of_week": int(day_of_week if day_of_week is not None else existing_slot["day_of_week"]),
        },
    )
    refreshed_template = await queries.get_schedule_template(db, int(template["id"]))
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, int(template["id"]))
    duplicated_slot = await queries.get_schedule_template_shift(db, duplicated_shift_id)
    assert duplicated_slot is not None
    slot_payload = _serialize_schedule_template_shift(duplicated_slot)
    slot_payload["warnings"] = await _build_template_slot_warnings(
        db,
        location_id=int(template["location_id"]),
        slot=duplicated_slot,
    )
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
        "shift": slot_payload,
    }


async def duplicate_schedule_template_shifts_bulk(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    shift_ids: list[int],
    day_of_week: int | None = None,
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    if not shift_ids:
        raise ValueError("At least one template shift is required")
    results: list[dict] = []
    for shift_id in [int(item) for item in shift_ids]:
        existing_slot = await queries.get_schedule_template_shift(db, shift_id)
        if existing_slot is None or int(existing_slot["template_id"]) != template_id:
            results.append({"template_shift_id": shift_id, "status": "error", "error": "Schedule template shift not found"})
            continue
        try:
            outcome = await duplicate_schedule_template_shift(
                db,
                template_shift_id=shift_id,
                day_of_week=day_of_week,
                actor=actor,
            )
            results.append({"template_shift_id": shift_id, "status": "ok", "shift": outcome["shift"]})
        except ValueError as exc:
            results.append({"template_shift_id": shift_id, "status": "error", "error": str(exc)})
    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, template_id)
    success_count = sum(1 for item in results if item["status"] == "ok")
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
        "processed_count": len(shift_ids),
        "success_count": success_count,
        "error_count": len(results) - success_count,
        "results": results,
    }


async def delete_schedule_template(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    existing_slots = await queries.list_schedule_template_shifts(db, template_id)
    await queries.delete_schedule_template_shifts(db, template_id)
    await queries.delete_schedule_template(db, template_id)
    await audit_svc.append(
        db,
        AuditAction.schedule_template_deleted,
        actor=actor,
        entity_type="schedule_template",
        entity_id=template_id,
        details={
            "location_id": int(template["location_id"]),
            "shift_count": len(existing_slots),
        },
    )
    return {
        "template_id": template_id,
        "location_id": int(template["location_id"]),
        "deleted": True,
        "shift_count": len(existing_slots),
    }


async def delete_schedule_template_shift(
    db: aiosqlite.Connection,
    *,
    template_shift_id: int,
    actor: str = "manager_api",
) -> dict:
    existing_slot = await queries.get_schedule_template_shift(db, template_shift_id)
    if existing_slot is None:
        raise ValueError("Schedule template shift not found")
    template = await queries.get_schedule_template(db, int(existing_slot["template_id"]))
    if template is None:
        raise ValueError("Schedule template not found")
    await queries.delete_schedule_template_shift_by_id(db, template_shift_id)
    await queries.update_schedule_template(
        db,
        int(template["id"]),
        {"updated_at": datetime.utcnow().isoformat()},
    )
    await audit_svc.append(
        db,
        AuditAction.schedule_template_updated,
        actor=actor,
        entity_type="schedule_template",
        entity_id=int(template["id"]),
        details={"action": "shift_deleted", "template_shift_id": template_shift_id},
    )
    refreshed_template = await queries.get_schedule_template(db, int(template["id"]))
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, int(template["id"]))
    return {
        "template_id": int(template["id"]),
        "template_shift_id": template_shift_id,
        "deleted": True,
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
    }


async def delete_schedule_template_shifts_bulk(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    shift_ids: list[int],
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    if not shift_ids:
        raise ValueError("At least one template shift is required")
    results: list[dict] = []
    for shift_id in [int(item) for item in shift_ids]:
        existing_slot = await queries.get_schedule_template_shift(db, shift_id)
        if existing_slot is None or int(existing_slot["template_id"]) != template_id:
            results.append({"template_shift_id": shift_id, "status": "error", "error": "Schedule template shift not found"})
            continue
        try:
            outcome = await delete_schedule_template_shift(
                db,
                template_shift_id=shift_id,
                actor=actor,
            )
            results.append({"template_shift_id": shift_id, "status": "ok", "deleted": outcome["deleted"]})
        except ValueError as exc:
            results.append({"template_shift_id": shift_id, "status": "error", "error": str(exc)})
    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, template_id)
    success_count = sum(1 for item in results if item["status"] == "ok")
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
        "processed_count": len(shift_ids),
        "success_count": success_count,
        "error_count": len(results) - success_count,
        "results": results,
    }


async def _build_auto_assigned_template_slots(
    db: aiosqlite.Connection,
    *,
    template: dict,
    slots: list[dict],
    overwrite_invalid_assignments: bool,
    assignment_strategy: str = "priority_first",
) -> tuple[list[dict], dict]:
    strategy = _normalize_assignment_strategy(assignment_strategy)
    location_id = int(template["location_id"])
    candidates = await _list_template_candidate_workers(db, location_id=location_id)
    fixed_slots: list[dict] = []
    worker_loads: dict[int, float] = {}
    worker_shift_counts: dict[int, int] = {}
    for slot in slots:
        warnings = await _build_template_slot_warnings(
            db,
            location_id=location_id,
            slot=slot,
        )
        valid_assigned = _slot_worker_is_assigned(slot) and not warnings
        if valid_assigned:
            fixed_slots.append(
                {
                    "worker_id": int(slot["worker_id"]),
                    **slot,
                }
            )
            worker_loads[int(slot["worker_id"])] = round(
                worker_loads.get(int(slot["worker_id"]), 0.0) + _slot_duration_hours(slot),
                2,
            )
            worker_shift_counts[int(slot["worker_id"])] = worker_shift_counts.get(int(slot["worker_id"]), 0) + 1

    resolved_slots: list[dict] = []
    auto_assigned_count = 0
    cleared_invalid_count = 0
    unchanged_assigned_count = 0
    unassigned_count = 0

    ordered_slots = sorted(
        slots,
        key=lambda slot: (
            int(slot["day_of_week"]),
            str(slot["start_time"]),
            int(slot.get("id") or 0),
        ),
    )
    for slot in ordered_slots:
        slot_copy = dict(slot)
        warnings = await _build_template_slot_warnings(
            db,
            location_id=location_id,
            slot=slot,
        )
        valid_assigned = _slot_worker_is_assigned(slot) and not warnings
        if valid_assigned:
            resolved_slots.append(slot_copy)
            unchanged_assigned_count += 1
            continue

        if _slot_worker_is_assigned(slot) and warnings and overwrite_invalid_assignments:
            slot_copy["worker_id"] = None
            slot_copy["assignment_status"] = "open"
            cleared_invalid_count += 1

        duration_hours = _slot_duration_hours(slot_copy)
        current_assignments: dict[int, list[dict]] = {}
        for other in fixed_slots + resolved_slots:
            if other.get("worker_id") is None:
                continue
            current_assignments.setdefault(int(other["worker_id"]), []).append(other)

        suggestions = _build_template_worker_suggestions(
            slot=slot_copy,
            candidates=candidates,
            worker_assignments=current_assignments,
            worker_hours=worker_loads,
            worker_shift_counts=worker_shift_counts,
            assignment_strategy=strategy,
        )
        chosen_worker_id = None
        for suggestion in suggestions:
            if suggestion["would_exceed_max_hours"]:
                continue
            chosen_worker_id = int(suggestion["worker_id"])
            break

        if chosen_worker_id is not None:
            slot_copy["worker_id"] = chosen_worker_id
            slot_copy["assignment_status"] = "assigned"
            auto_assigned_count += 1
            worker_loads[chosen_worker_id] = round(
                worker_loads.get(chosen_worker_id, 0.0) + duration_hours,
                2,
            )
            worker_shift_counts[chosen_worker_id] = worker_shift_counts.get(chosen_worker_id, 0) + 1
        else:
            slot_copy["worker_id"] = None
            slot_copy["assignment_status"] = "open"
            unassigned_count += 1

        resolved_slots.append(slot_copy)

    return resolved_slots, {
        "processed_count": len(ordered_slots),
        "auto_assigned_count": auto_assigned_count,
        "cleared_invalid_count": cleared_invalid_count,
        "unchanged_assigned_count": unchanged_assigned_count,
        "unassigned_count": unassigned_count,
        "assignment_strategy": strategy,
    }


async def auto_assign_schedule_template(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    overwrite_invalid_assignments: bool = True,
    day_of_week_filter: list[int] | None = None,
    assignment_strategy: str = "priority_first",
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    all_slots = await queries.list_schedule_template_shifts(db, template_id)
    selected_slots = _filter_template_slots_by_day(all_slots, day_of_week_filter)
    if not selected_slots:
        raise ValueError("Schedule template has no shifts for the selected days")

    resolved_slots, summary = await _build_auto_assigned_template_slots(
        db,
        template=template,
        slots=selected_slots,
        overwrite_invalid_assignments=overwrite_invalid_assignments,
        assignment_strategy=assignment_strategy,
    )

    by_id = {int(slot["id"]): slot for slot in resolved_slots}
    for slot in selected_slots:
        resolved = by_id[int(slot["id"])]
        await queries.update_schedule_template_shift(
            db,
            int(slot["id"]),
            {
                "worker_id": resolved.get("worker_id"),
                "assignment_status": resolved.get("assignment_status") or "open",
            },
        )
    await queries.update_schedule_template(db, template_id, {"updated_at": datetime.utcnow().isoformat()})
    await audit_svc.append(
        db,
        AuditAction.schedule_template_updated,
        actor=actor,
        entity_type="schedule_template",
        entity_id=template_id,
        details={
            "action": "auto_assigned",
            "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
            **summary,
        },
    )
    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_slots = await queries.list_schedule_template_shifts(db, template_id)
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
        ),
        "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
        "assignment_strategy": _normalize_assignment_strategy(assignment_strategy),
        "summary": summary,
        "staffing_plan": await _build_template_staffing_plan(
            db,
            template=refreshed_template,
            slots=refreshed_slots,
            assignment_strategy=assignment_strategy,
        ),
    }


async def _materialize_schedule_from_slot_payloads(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    target_week_start_date: str,
    slot_payloads: list[dict],
    replace_existing: bool,
    actor: str,
    assignment_source: str,
    created_source_details: dict,
    change_summary: dict,
    derived_from_schedule_id: int | None = None,
    amendment_details: dict | None = None,
) -> dict:
    week_start = date.fromisoformat(target_week_start_date)
    week_end = _week_end_for(week_start)
    schedule = await queries.get_schedule_by_location_week(
        db,
        location_id,
        target_week_start_date,
    )
    created_schedule = False
    replaced_shift_count = 0
    if schedule is None:
        schedule_id = await queries.insert_schedule(
            db,
            {
                "location_id": location_id,
                "week_start_date": target_week_start_date,
                "week_end_date": week_end.isoformat(),
                "lifecycle_state": "draft",
                "derived_from_schedule_id": derived_from_schedule_id,
                "created_by": actor,
            },
        )
        schedule = await queries.get_schedule(db, schedule_id)
        assert schedule is not None
        created_schedule = True
        await audit_svc.append(
            db,
            AuditAction.schedule_created,
            actor=actor,
            entity_type="schedule",
            entity_id=schedule_id,
            details=created_source_details,
        )
    else:
        if (schedule.get("lifecycle_state") or "draft") == "archived":
            raise ValueError("Archived schedules are read-only")
        existing_shifts = await queries.list_shifts(db, schedule_id=int(schedule["id"]))
        if existing_shifts and not replace_existing:
            raise ValueError("Target schedule already has shifts")
        if replace_existing:
            replaced_shift_count = len(existing_shifts)
            for existing_shift in existing_shifts:
                active_cascade = await queries.get_active_cascade_for_shift(db, int(existing_shift["id"]))
                if active_cascade is not None:
                    raise ValueError("Cannot replace target week with active coverage workflow")
                if existing_shift.get("status") != "scheduled":
                    raise ValueError("Only scheduled target shifts can be replaced")
            for existing_shift in existing_shifts:
                await queries.delete_shift_assignment(db, int(existing_shift["id"]))
                await queries.delete_shift(db, int(existing_shift["id"]))
        if (
            derived_from_schedule_id is not None
            and int(schedule.get("derived_from_schedule_id") or 0) != int(derived_from_schedule_id)
        ):
            await queries.update_schedule(
                db,
                int(schedule["id"]),
                {"derived_from_schedule_id": derived_from_schedule_id},
            )
            schedule = await queries.get_schedule(db, int(schedule["id"]))
            assert schedule is not None

    current_state = schedule.get("lifecycle_state") or "draft"
    created_shift_ids: list[int] = []
    copied_assignments_count = 0
    skipped_assignments_count = 0
    for slot in slot_payloads:
        shift_date = week_start + timedelta(days=int(slot["day_of_week"]))
        shift_id = await queries.insert_shift(
            db,
            {
                "location_id": location_id,
                "schedule_id": int(schedule["id"]),
                "role": slot["role"],
                "date": shift_date.isoformat(),
                "start_time": slot["start_time"],
                "end_time": slot["end_time"],
                "spans_midnight": bool(slot.get("spans_midnight")),
                "pay_rate": slot.get("pay_rate", 0.0),
                "requirements": slot.get("requirements") or [],
                "status": "scheduled",
                "source_platform": "backfill_native",
                "shift_label": slot.get("shift_label"),
                "notes": slot.get("notes"),
                "published_state": "amended" if current_state in {"published", "amended"} else "draft",
            },
        )
        created_shift_ids.append(shift_id)

        target_worker_id = None
        target_assignment_status = "open"
        if (
            slot.get("worker_id") is not None
            and slot.get("assignment_status") in {"assigned", "claimed", "confirmed"}
        ):
            worker = await queries.get_worker(db, int(slot["worker_id"]))
            if (
                worker is not None
                and (worker.get("employment_status") or "active") == "active"
                and worker.get("location_id") == location_id
                and slot.get("role") in (worker.get("roles") or [])
            ):
                target_worker_id = int(worker["id"])
                target_assignment_status = "assigned"
                copied_assignments_count += 1
            else:
                skipped_assignments_count += 1

        await queries.upsert_shift_assignment(
            db,
            {
                "shift_id": shift_id,
                "worker_id": target_worker_id,
                "assignment_status": target_assignment_status,
                "source": assignment_source,
            },
        )

    next_state, version_id = await _apply_schedule_mutation(
        db,
        schedule=schedule,
        actor=actor,
        change_summary=change_summary,
    )
    if next_state == "amended":
        for shift_id in created_shift_ids:
            await queries.update_shift(db, shift_id, {"published_state": "amended"})
        await audit_svc.append(
            db,
            AuditAction.schedule_amended,
            actor=actor,
            entity_type="schedule",
            entity_id=int(schedule["id"]),
            details={"version_id": version_id, **(amendment_details or {})},
        )

    refreshed_schedule_view = await get_schedule_view(
        db,
        location_id=location_id,
        week_start=target_week_start_date,
    )
    return {
        "schedule": schedule,
        "schedule_id": int(schedule["id"]),
        "created_schedule": created_schedule,
        "target_week_start_date": target_week_start_date,
        "replaced_shift_count": replaced_shift_count,
        "created_shift_count": len(created_shift_ids),
        "copied_assignments": copied_assignments_count,
        "skipped_assignments": skipped_assignments_count,
        "schedule_lifecycle_state": next_state,
        "version_id": version_id,
        "schedule_view": refreshed_schedule_view,
    }


async def apply_schedule_template(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    target_week_start_date: str,
    replace_existing: bool = False,
    day_of_week_filter: list[int] | None = None,
    auto_assign_open_shifts: bool = False,
    assignment_strategy: str = "priority_first",
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")

    template_slots = _filter_template_slots_by_day(
        await queries.list_schedule_template_shifts(db, template_id),
        day_of_week_filter,
    )
    if not template_slots:
        raise ValueError("Schedule template has no shifts for the selected days")
    auto_assign_summary = {
        "processed_count": 0,
        "auto_assigned_count": 0,
        "cleared_invalid_count": 0,
        "unchanged_assigned_count": 0,
        "unassigned_count": 0,
        "assignment_strategy": _normalize_assignment_strategy(assignment_strategy),
    }
    if auto_assign_open_shifts:
        template_slots, auto_assign_summary = await _build_auto_assigned_template_slots(
            db,
            template=template,
            slots=template_slots,
            overwrite_invalid_assignments=True,
            assignment_strategy=assignment_strategy,
        )

    materialized = await _materialize_schedule_from_slot_payloads(
        db,
        location_id=int(template["location_id"]),
        target_week_start_date=target_week_start_date,
        slot_payloads=template_slots,
        replace_existing=replace_existing,
        actor=actor,
        assignment_source="template_apply",
        created_source_details={"source": "schedule_template", "template_id": template_id},
        change_summary={
            "event": "schedule_template_applied",
            "template_id": template_id,
            "target_week_start_date": target_week_start_date,
            "replace_existing": replace_existing,
            "created_shift_count": len(template_slots),
        },
        amendment_details={
            "template_id": template_id,
            "target_week_start_date": target_week_start_date,
        },
    )

    await audit_svc.append(
        db,
        AuditAction.schedule_template_applied,
        actor=actor,
        entity_type="schedule_template",
        entity_id=template_id,
        details={
            "schedule_id": materialized["schedule_id"],
            "created_schedule": materialized["created_schedule"],
            "target_week_start_date": target_week_start_date,
            "replace_existing": replace_existing,
            "created_shift_count": materialized["created_shift_count"],
            "copied_assignments": materialized["copied_assignments"],
            "skipped_assignments": materialized["skipped_assignments"],
            "version_id": materialized["version_id"],
        },
    )
    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_template_slots = await queries.list_schedule_template_shifts(db, template_id)
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_template_slots,
        ),
        "schedule_id": materialized["schedule_id"],
        "created_schedule": materialized["created_schedule"],
        "target_week_start_date": target_week_start_date,
        "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
        "auto_assign_open_shifts": auto_assign_open_shifts,
        "assignment_strategy": _normalize_assignment_strategy(assignment_strategy),
        "auto_assign_summary": auto_assign_summary,
        "replaced_shift_count": materialized["replaced_shift_count"],
        "created_shift_count": materialized["created_shift_count"],
        "copied_assignments": materialized["copied_assignments"],
        "skipped_assignments": materialized["skipped_assignments"],
        "schedule_lifecycle_state": materialized["schedule_lifecycle_state"],
        "version_id": materialized["version_id"],
        "schedule_view": materialized["schedule_view"],
    }


async def apply_schedule_template_range(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    target_week_start_dates: list[str],
    replace_existing: bool = False,
    day_of_week_filter: list[int] | None = None,
    auto_assign_open_shifts: bool = False,
    assignment_strategy: str = "priority_first",
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None:
        raise ValueError("Schedule template not found")
    if not target_week_start_dates:
        raise ValueError("At least one target week start date is required")

    seen: set[str] = set()
    ordered_dates: list[str] = []
    for week_start in target_week_start_dates:
        if week_start not in seen:
            seen.add(week_start)
            ordered_dates.append(week_start)

    results: list[dict] = []
    success_count = 0
    for week_start in ordered_dates:
        try:
            outcome = await apply_schedule_template(
                db,
                template_id=template_id,
                target_week_start_date=week_start,
                replace_existing=replace_existing,
                day_of_week_filter=day_of_week_filter,
                auto_assign_open_shifts=auto_assign_open_shifts,
                assignment_strategy=assignment_strategy,
                actor=actor,
            )
        except ValueError as exc:
            results.append(
                {
                    "target_week_start_date": week_start,
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        success_count += 1
        results.append(
            {
                "target_week_start_date": week_start,
                "status": "ok",
                "schedule_id": outcome["schedule_id"],
                "created_schedule": outcome["created_schedule"],
                "created_shift_count": outcome["created_shift_count"],
                "replaced_shift_count": outcome["replaced_shift_count"],
                "copied_assignments": outcome["copied_assignments"],
                "skipped_assignments": outcome["skipped_assignments"],
                "auto_assign_summary": outcome["auto_assign_summary"],
                "schedule_lifecycle_state": outcome["schedule_lifecycle_state"],
            }
        )

    refreshed_template = await queries.get_schedule_template(db, template_id)
    assert refreshed_template is not None
    refreshed_template_slots = await queries.list_schedule_template_shifts(db, template_id)
    return {
        "template": await _serialize_schedule_template_detail(
            db,
            template=refreshed_template,
            slots=refreshed_template_slots,
        ),
        "replace_existing": replace_existing,
        "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
        "auto_assign_open_shifts": auto_assign_open_shifts,
        "assignment_strategy": _normalize_assignment_strategy(assignment_strategy),
        "processed_count": len(ordered_dates),
        "success_count": success_count,
        "error_count": len(ordered_dates) - success_count,
        "results": results,
    }


async def create_schedule_from_template_for_location(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    template_id: int,
    target_week_start_date: str,
    replace_existing: bool = False,
    day_of_week_filter: list[int] | None = None,
    auto_assign_open_shifts: bool = False,
    assignment_strategy: str = "priority_first",
    actor: str = "manager_api",
) -> dict:
    template = await queries.get_schedule_template(db, template_id)
    if template is None or int(template["location_id"]) != location_id:
        raise ValueError("Schedule template not found")
    outcome = await apply_schedule_template(
        db,
        template_id=template_id,
        target_week_start_date=target_week_start_date,
        replace_existing=replace_existing,
        day_of_week_filter=day_of_week_filter,
        auto_assign_open_shifts=auto_assign_open_shifts,
        assignment_strategy=assignment_strategy,
        actor=actor,
    )
    return {
        **outcome,
        "generation_mode": "template_apply",
        "basis_type": "template",
        "basis_template_id": template_id,
        "basis_schedule_id": template.get("source_schedule_id"),
    }


async def generate_ai_schedule_draft(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    target_week_start_date: str,
    template_id: int | None = None,
    source_schedule_id: int | None = None,
    replace_existing: bool = False,
    day_of_week_filter: list[int] | None = None,
    auto_assign_open_shifts: bool = True,
    assignment_strategy: str = "priority_first",
    include_assignments_from_source: bool = True,
    actor: str = "manager_api",
) -> dict:
    normalized_strategy = _normalize_assignment_strategy(assignment_strategy)
    if template_id is None and source_schedule_id is None:
        templates = await queries.list_schedule_templates_for_location(db, location_id)
        if templates:
            template_id = int(templates[0]["id"])
        else:
            source_schedule = await _find_latest_schedule_with_shifts_for_location(
                db,
                location_id=location_id,
            )
            source_schedule_id = int(source_schedule["id"]) if source_schedule else None

    if template_id is not None:
        template = await queries.get_schedule_template(db, template_id)
        if template is None or int(template["location_id"]) != location_id:
            raise ValueError("Schedule template not found")
        outcome = await generate_schedule_draft_from_template(
            db,
            template_id=template_id,
            target_week_start_date=target_week_start_date,
            replace_existing=replace_existing,
            day_of_week_filter=day_of_week_filter,
            auto_assign_open_shifts=auto_assign_open_shifts,
            assignment_strategy=normalized_strategy,
            actor=actor,
        )
        return {
            **outcome,
            "generation_mode": "ai_draft",
            "basis_type": "template",
            "basis_template_id": template_id,
            "basis_schedule_id": template.get("source_schedule_id"),
            "generated_from_schedule": False,
        }

    if source_schedule_id is None:
        raise ValueError("No template or prior schedule is available to generate a draft")

    source_schedule, slot_payloads, copied_assignments = await _extract_schedule_template_slots_from_schedule(
        db,
        schedule_id=source_schedule_id,
        include_assignments=include_assignments_from_source,
    )
    if int(source_schedule["location_id"]) != location_id:
        raise ValueError("Source schedule not found")
    selected_slots = _filter_template_slots_by_day(slot_payloads, day_of_week_filter)
    if not selected_slots:
        raise ValueError("Source schedule has no reusable shifts for the selected days")

    auto_assign_summary = {
        "processed_count": 0,
        "auto_assigned_count": 0,
        "cleared_invalid_count": 0,
        "unchanged_assigned_count": 0,
        "unassigned_count": 0,
        "assignment_strategy": normalized_strategy,
    }
    if auto_assign_open_shifts:
        selected_slots, auto_assign_summary = await _build_auto_assigned_template_slots(
            db,
            template={"location_id": location_id},
            slots=selected_slots,
            overwrite_invalid_assignments=True,
            assignment_strategy=normalized_strategy,
        )

    materialized = await _materialize_schedule_from_slot_payloads(
        db,
        location_id=location_id,
        target_week_start_date=target_week_start_date,
        slot_payloads=selected_slots,
        replace_existing=replace_existing,
        actor=actor,
        assignment_source="draft_engine",
        created_source_details={
            "source": "ai_draft",
            "basis_type": "schedule",
            "source_schedule_id": source_schedule_id,
        },
        change_summary={
            "event": "ai_schedule_draft_generated",
            "target_week_start_date": target_week_start_date,
            "replace_existing": replace_existing,
            "source_schedule_id": source_schedule_id,
            "created_shift_count": len(selected_slots),
        },
        amendment_details={
            "source_schedule_id": source_schedule_id,
            "target_week_start_date": target_week_start_date,
        },
        derived_from_schedule_id=source_schedule_id,
    )
    return {
        "schedule_id": materialized["schedule_id"],
        "created_schedule": materialized["created_schedule"],
        "target_week_start_date": target_week_start_date,
        "day_of_week_filter": _normalize_day_of_week_filter(day_of_week_filter),
        "auto_assign_open_shifts": auto_assign_open_shifts,
        "assignment_strategy": normalized_strategy,
        "auto_assign_summary": auto_assign_summary,
        "replaced_shift_count": materialized["replaced_shift_count"],
        "created_shift_count": materialized["created_shift_count"],
        "copied_assignments": (
            materialized["copied_assignments"]
            if auto_assign_open_shifts
            else copied_assignments
        ),
        "skipped_assignments": materialized["skipped_assignments"],
        "schedule_lifecycle_state": materialized["schedule_lifecycle_state"],
        "version_id": materialized["version_id"],
        "schedule_view": materialized["schedule_view"],
        "generation_mode": "ai_draft",
        "generated_from_template": False,
        "generated_from_schedule": True,
        "basis_type": "schedule",
        "basis_template_id": None,
        "basis_schedule_id": source_schedule_id,
        "source_week_start_date": source_schedule.get("week_start_date"),
    }


async def generate_schedule_draft_from_template(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    target_week_start_date: str,
    replace_existing: bool = False,
    day_of_week_filter: list[int] | None = None,
    auto_assign_open_shifts: bool = True,
    assignment_strategy: str = "priority_first",
    actor: str = "manager_api",
) -> dict:
    outcome = await apply_schedule_template(
        db,
        template_id=template_id,
        target_week_start_date=target_week_start_date,
        replace_existing=replace_existing,
        day_of_week_filter=day_of_week_filter,
        auto_assign_open_shifts=auto_assign_open_shifts,
        assignment_strategy=assignment_strategy,
        actor=actor,
    )
    return {
        **outcome,
        "generation_mode": "draft",
        "generated_from_template": True,
    }


async def _apply_schedule_mutation(
    db: aiosqlite.Connection,
    *,
    schedule: dict,
    actor: str,
    change_summary: dict,
) -> tuple[str, int]:
    current_state = schedule.get("lifecycle_state") or "draft"
    if current_state == "archived":
        raise ValueError("Archived schedules are read-only")

    if current_state == "draft":
        next_state = "draft"
        version_type = "draft_snapshot"
    elif current_state in {"published", "amended", "recalled"}:
        next_state = "amended" if current_state in {"published", "amended"} else "recalled"
        version_type = "amendment_snapshot"
    else:
        raise ValueError(f"Unsupported schedule lifecycle state: {current_state}")

    version_id = await _create_schedule_version(
        db,
        schedule_id=int(schedule["id"]),
        version_type=version_type,
        published_by=actor if version_type == "publish_snapshot" else None,
        change_summary=change_summary,
    )
    await queries.update_schedule(
        db,
        int(schedule["id"]),
        {"current_version_id": version_id, "lifecycle_state": next_state},
    )
    return next_state, version_id


async def publish_schedule(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    actor: str = "system",
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    lifecycle_state = schedule.get("lifecycle_state") or "draft"
    if lifecycle_state == "archived":
        raise ValueError("Archived schedules cannot be published")
    if lifecycle_state == "published":
        raise ValueError("Schedule is already published")
    publish_readiness = await get_schedule_publish_readiness(db, schedule_id=schedule_id)
    if not publish_readiness["publish_readiness"]["can_publish"]:
        blockers = publish_readiness["publish_readiness"].get("blockers") or []
        if blockers:
            preview = ", ".join(item["code"] for item in blockers[:3])
            raise ValueError(
                f"Schedule has {len(blockers)} blocking issue(s): {preview}"
            )
        raise ValueError(publish_readiness["publish_readiness"]["status_message"])
    enriched_shifts = await _load_enriched_schedule_shifts(
        db,
        schedule_id=schedule_id,
    )
    publish_diff = await _build_schedule_publish_diff_summary(
        db,
        schedule=schedule,
        current_shifts=enriched_shifts,
    )
    version_id = await _create_schedule_version(
        db,
        schedule_id=schedule_id,
        version_type="publish_snapshot",
        published_by=actor,
    )
    await queries.update_schedule(
        db,
        schedule_id,
        {
            "current_version_id": version_id,
            "lifecycle_state": "published",
        },
    )
    shifts = await queries.list_shifts(db, schedule_id=schedule_id)
    worker_shift_groups: dict[int, list[dict]] = {}
    for shift in shifts:
        await queries.update_shift(db, int(shift["id"]), {"published_state": "published"})
        assignment = await queries.get_shift_assignment_with_worker(db, int(shift["id"]))
        if (
            assignment
            and assignment.get("worker_id")
            and assignment.get("assignment_status") in {"assigned", "claimed", "confirmed"}
        ):
            worker_shift_groups.setdefault(int(assignment["worker_id"]), []).append(shift)

    published_at = datetime.utcnow().isoformat()
    await audit_svc.append(
        db,
        AuditAction.schedule_published,
        actor=actor,
        entity_type="schedule",
        entity_id=schedule_id,
        details={"version_id": version_id},
    )
    location = await queries.get_location(db, int(schedule["location_id"]))
    delivery_summary = {
        "eligible_workers": len(worker_shift_groups),
        "sms_sent": 0,
        "not_enrolled": 0,
        "sms_failed": 0,
    }
    if location is not None:
        delivery_summary = await notifications_svc.fire_schedule_worker_delivery_notifications(
            db,
            location=location,
            schedule=schedule,
            worker_shift_groups=worker_shift_groups,
            actor=actor,
            is_update=lifecycle_state in {"amended", "recalled"},
            worker_impact=publish_diff.get("worker_impact") if lifecycle_state in {"amended", "recalled"} else None,
        )
    if location is not None:
        await notifications_svc.fire_schedule_published_notification(
            db,
            location=location,
            schedule=schedule,
            delivery_summary=delivery_summary,
            publish_diff=publish_diff,
            is_update=lifecycle_state in {"amended", "recalled"},
        )
    return {
        "schedule_id": schedule_id,
        "lifecycle_state": "published",
        "version_id": version_id,
        "published_at": published_at,
        "delivery_summary": delivery_summary,
        "publish_diff": publish_diff,
    }


async def offer_open_shifts_for_schedule(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    shift_ids: Optional[list[int]] = None,
    actor: str = "system",
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    lifecycle_state = schedule.get("lifecycle_state") or "draft"
    if lifecycle_state not in {"published", "amended"}:
        raise ValueError("Only published or amended schedules can offer open shifts")

    shifts = await queries.list_shifts(db, schedule_id=schedule_id)
    shifts_by_id = {int(shift["id"]): shift for shift in shifts}
    requested_shift_ids = [int(shift_id) for shift_id in (shift_ids or [])]
    if requested_shift_ids:
        missing_shift_ids = [shift_id for shift_id in requested_shift_ids if shift_id not in shifts_by_id]
        if missing_shift_ids:
            raise ValueError("One or more shifts do not belong to this schedule")
        target_shifts = [shifts_by_id[shift_id] for shift_id in requested_shift_ids]
    else:
        target_shifts = shifts

    results: list[dict] = []
    summary = {
        "requested": 0,
        "started": 0,
        "already_active": 0,
        "skipped_assigned": 0,
        "skipped_not_open": 0,
    }

    for shift in target_shifts:
        shift_id = int(shift["id"])
        assignment = await queries.get_shift_assignment(db, shift_id)
        if assignment and assignment.get("worker_id") is not None and assignment.get("assignment_status") in {
            "assigned",
            "claimed",
            "confirmed",
        }:
            summary["skipped_assigned"] += 1
            results.append({"shift_id": shift_id, "status": "skipped_assigned"})
            continue
        summary["requested"] += 1
        if assignment and assignment.get("assignment_status") not in {None, "open"} and assignment.get("worker_id") is None:
            summary["skipped_not_open"] += 1
            results.append({"shift_id": shift_id, "status": "skipped_not_open"})
            continue

        result = await start_coverage_for_open_shift(
            db,
            shift_id=shift_id,
            actor=actor,
        )
        result_status = str(result.get("status") or "")
        if result_status == "coverage_started":
            summary["started"] += 1
        elif result_status == "coverage_active":
            summary["already_active"] += 1
        else:
            summary["skipped_not_open"] += 1
        results.append(
            {
                "shift_id": shift_id,
                "status": result_status,
                "cascade_id": result.get("cascade_id"),
                "idempotent": bool(result.get("idempotent", False)),
            }
        )

    location_id = int(schedule["location_id"])
    return {
        "schedule_id": schedule_id,
        "week_start_date": str(schedule["week_start_date"]),
        "summary": summary,
        "results": results,
        "review_link": notifications_svc.build_manager_dashboard_link(
            location_id,
            tab="coverage",
            week_start=str(schedule["week_start_date"]),
        ),
    }


async def apply_schedule_shift_actions(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    shift_ids: list[int],
    action: str,
    actor: str = "manager_api",
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    if not shift_ids:
        raise ValueError("At least one shift is required")

    schedule_view = await get_schedule_view(
        db,
        location_id=int(schedule["location_id"]),
        week_start=str(schedule["week_start_date"]),
    )
    current_schedule = schedule_view.get("schedule")
    if current_schedule is None or int(current_schedule["id"]) != schedule_id:
        raise ValueError("Schedule not found")

    shifts_by_id = {
        int(shift.get("id") or 0): shift
        for shift in schedule_view.get("shifts") or []
    }
    results: list[dict] = []
    for shift_id in [int(shift_id) for shift_id in shift_ids]:
        shift = shifts_by_id.get(shift_id)
        result = {
            "shift_id": shift_id,
            "action": action,
        }
        if shift is None:
            results.append(
                {
                    **result,
                    "status": "error",
                    "error": "shift_not_found",
                }
            )
            continue
        available_actions = list(shift.get("available_actions") or [])
        if action not in set(available_actions):
            results.append(
                {
                    **result,
                    "status": "error",
                    "error": "action_not_allowed",
                    "available_actions": available_actions,
                }
            )
            continue

        try:
            if action == "start_coverage":
                outcome = await start_coverage_for_open_shift(
                    db,
                    shift_id=shift_id,
                    actor=actor,
                )
            elif action == "cancel_offer":
                outcome = await cancel_open_shift_offer(
                    db,
                    shift_id=shift_id,
                    actor=actor,
                )
            elif action == "close_shift":
                outcome = await close_open_shift(
                    db,
                    shift_id=shift_id,
                    actor=actor,
                )
            elif action == "reopen_shift":
                outcome = await reopen_open_shift(
                    db,
                    shift_id=shift_id,
                    start_open_shift_offer=False,
                    actor=actor,
                )
            elif action == "reopen_and_offer":
                outcome = await reopen_open_shift(
                    db,
                    shift_id=shift_id,
                    start_open_shift_offer=True,
                    actor=actor,
                )
            else:
                outcome = {
                    "status": "error",
                    "error": "unknown_action",
                }
        except ValueError as exc:
            results.append(
                {
                    **result,
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        if str(outcome.get("status") or "") == "error":
            results.append({**result, **outcome})
            continue
        results.append(
            {
                **result,
                "status": "ok",
                "result": outcome,
            }
        )

    refreshed_schedule_view = await get_schedule_view(
        db,
        location_id=int(schedule["location_id"]),
        week_start=str(schedule["week_start_date"]),
    )
    success_count = sum(1 for item in results if item.get("status") == "ok")
    return {
        "schedule_id": schedule_id,
        "action": action,
        "processed_count": len(shift_ids),
        "success_count": success_count,
        "error_count": len(results) - success_count,
        "results": results,
        "schedule_view": refreshed_schedule_view,
    }


async def recall_schedule(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    actor: str = "system",
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    lifecycle_state = schedule.get("lifecycle_state") or "draft"
    if lifecycle_state not in {"published", "amended"}:
        raise ValueError("Only published or amended schedules can be recalled")

    version_id = await _create_schedule_version(
        db,
        schedule_id=schedule_id,
        version_type="amendment_snapshot",
        change_summary={"event": "recalled"},
    )
    await queries.update_schedule(
        db,
        schedule_id,
        {"current_version_id": version_id, "lifecycle_state": "recalled"},
    )
    await audit_svc.append(
        db,
        AuditAction.schedule_recalled,
        actor=actor,
        entity_type="schedule",
        entity_id=schedule_id,
        details={"version_id": version_id},
    )
    return {
        "schedule_id": schedule_id,
        "lifecycle_state": "recalled",
        "version_id": version_id,
    }


async def archive_schedule(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    actor: str = "system",
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    lifecycle_state = schedule.get("lifecycle_state") or "draft"
    if lifecycle_state == "archived":
        raise ValueError("Schedule is already archived")
    if lifecycle_state not in {"draft", "published", "amended", "recalled"}:
        raise ValueError("Schedule cannot be archived from its current state")

    version_type = "draft_snapshot" if lifecycle_state == "draft" else "amendment_snapshot"
    version_id = await _create_schedule_version(
        db,
        schedule_id=schedule_id,
        version_type=version_type,
        change_summary={"event": "archived"},
    )
    await queries.update_schedule(
        db,
        schedule_id,
        {"current_version_id": version_id, "lifecycle_state": "archived"},
    )
    await audit_svc.append(
        db,
        AuditAction.schedule_archived,
        actor=actor,
        entity_type="schedule",
        entity_id=schedule_id,
        details={"version_id": version_id},
    )
    return {
        "schedule_id": schedule_id,
        "lifecycle_state": "archived",
        "version_id": version_id,
    }


async def create_schedule_shift(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    shift_payload: dict,
    actor: str = "system",
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    lifecycle_state = schedule.get("lifecycle_state") or "draft"
    if lifecycle_state == "archived":
        raise ValueError("Archived schedules are read-only")

    worker_id = shift_payload.get("worker_id")
    start_open_shift_offer = bool(shift_payload.get("start_open_shift_offer"))
    if worker_id is not None:
        worker = await queries.get_worker(db, int(worker_id))
        if worker is None:
            raise ValueError("Worker not found")
    if start_open_shift_offer and worker_id is not None:
        raise ValueError("Open shift offers can only start for unassigned shifts")
    if start_open_shift_offer and lifecycle_state not in {"published", "amended"}:
        raise ValueError("Open shift offers require a published or amended schedule")

    start_time = shift_payload["start_time"]
    end_time = shift_payload["end_time"]
    spans_midnight = shift_payload.get("spans_midnight")
    if spans_midnight is None:
        spans_midnight = end_time < start_time
    if end_time == start_time:
        raise ValueError("Shift end time must differ from start time")

    shift_id = await queries.insert_shift(
        db,
        {
            "location_id": int(schedule["location_id"]),
            "schedule_id": schedule_id,
            "role": shift_payload["role"],
            "date": shift_payload["date"],
            "start_time": start_time,
            "end_time": end_time,
            "spans_midnight": spans_midnight,
            "pay_rate": shift_payload.get("pay_rate", 0.0),
            "requirements": shift_payload.get("requirements") or [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "shift_label": shift_payload.get("shift_label"),
            "notes": shift_payload.get("notes"),
            "published_state": "amended" if lifecycle_state in {"published", "amended"} else "draft",
        },
    )
    assignment_status = shift_payload.get("assignment_status") or ("assigned" if worker_id else "open")
    await queries.upsert_shift_assignment(
        db,
        {
            "shift_id": shift_id,
            "worker_id": worker_id,
            "assignment_status": assignment_status,
            "source": "manual",
        },
    )

    next_state, version_id = await _apply_schedule_mutation(
        db,
        schedule=schedule,
        actor=actor,
        change_summary={"event": "shift_created", "shift_id": shift_id},
    )
    offer_result = None
    if start_open_shift_offer:
        offer_result = await start_coverage_for_open_shift(
            db,
            shift_id=shift_id,
            actor=actor,
        )
    shift = await queries.get_shift(db, shift_id)
    assignment = await queries.get_shift_assignment_with_worker(db, shift_id)
    active_cascade = await queries.get_active_cascade_for_shift(db, shift_id)
    pending_claim_worker = await _get_pending_claim_worker(db, active_cascade)
    shift_payload = _serialize_schedule_shift_payload(
        shift=shift,
        assignment=assignment,
        active_cascade=active_cascade,
        pending_claim_worker=pending_claim_worker,
    )
    return {
        "shift": shift,
        "assignment": shift_payload["assignment"],
        "confirmation": shift_payload["confirmation"],
        "attendance": shift_payload["attendance"],
        "coverage": shift_payload["coverage"],
        "available_actions": shift_payload["available_actions"],
        "offer_result": offer_result,
        "schedule_lifecycle_state": next_state,
        "version_id": version_id,
    }


async def amend_schedule_shift_details(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    patch: dict,
    actor: str = "system",
) -> dict:
    shift = await queries.get_shift(db, shift_id)
    if shift is None:
        raise ValueError("Shift not found")
    schedule = await _assert_shift_schedule_mutable(db, shift)
    active_cascade = await queries.get_active_cascade_for_shift(db, shift_id)
    if active_cascade is not None:
        raise ValueError("Cannot edit shift while coverage workflow is active")
    if shift.get("status") != "scheduled":
        raise ValueError("Only scheduled shifts can be edited")
    if not patch:
        raise ValueError("At least one field is required")

    assignment = await queries.get_shift_assignment_with_worker(db, shift_id)
    assignment_status = assignment.get("assignment_status") if assignment else None
    assigned_worker_id = assignment.get("worker_id") if assignment else None

    if "role" in patch and not patch.get("role"):
        raise ValueError("Role is required")
    if "date" in patch and patch.get("date") is None:
        raise ValueError("Date is required")
    if "start_time" in patch and patch.get("start_time") is None:
        raise ValueError("Start time is required")
    if "end_time" in patch and patch.get("end_time") is None:
        raise ValueError("End time is required")
    if "pay_rate" in patch and patch.get("pay_rate") is None:
        raise ValueError("Pay rate is required")

    next_role = patch.get("role", shift.get("role"))
    next_date = patch.get("date", shift.get("date"))
    next_start_time = patch.get("start_time", shift.get("start_time"))
    next_end_time = patch.get("end_time", shift.get("end_time"))
    if str(next_end_time) == str(next_start_time):
        raise ValueError("Shift end time must differ from start time")

    if assigned_worker_id is not None and assignment_status in {"assigned", "claimed", "confirmed"}:
        worker = await queries.get_worker(db, int(assigned_worker_id))
        if worker is None:
            raise ValueError("Assigned worker not found")
        if next_role not in (worker.get("roles") or []):
            raise ValueError("Assigned worker is not eligible for updated role")

    updates: dict[str, object] = {}
    for field in ("role", "date", "start_time", "end_time", "pay_rate", "shift_label", "notes"):
        if field in patch:
            updates[field] = patch[field]
    if "requirements" in patch:
        updates["requirements"] = patch.get("requirements") or []
    if "spans_midnight" in patch:
        updates["spans_midnight"] = bool(patch["spans_midnight"])
    elif "start_time" in patch or "end_time" in patch:
        updates["spans_midnight"] = str(next_end_time) < str(next_start_time)

    core_fields_changed = any(field in patch for field in ("role", "date", "start_time", "end_time"))
    if core_fields_changed:
        updates.update(
            {
                "reminder_sent_at": None,
                "confirmation_requested_at": None,
                "worker_confirmed_at": None,
                "worker_declined_at": None,
                "confirmation_escalated_at": None,
                "check_in_requested_at": None,
                "checked_in_at": None,
                "late_reported_at": None,
                "late_eta_minutes": None,
                "check_in_escalated_at": None,
                "attendance_action_state": None,
                "attendance_action_updated_at": None,
            }
        )

    await queries.update_shift(db, shift_id, updates)

    schedule_state = None
    version_id = None
    if schedule is not None:
        schedule_state, version_id = await _apply_schedule_mutation(
            db,
            schedule=schedule,
            actor=actor,
            change_summary={
                "event": "shift_updated",
                "shift_id": shift_id,
                "fields": sorted(patch.keys()),
            },
        )
        if schedule_state == "amended":
            await queries.update_shift(db, shift_id, {"published_state": "amended"})
            await audit_svc.append(
                db,
                AuditAction.schedule_amended,
                actor=actor,
                entity_type="schedule",
                entity_id=int(schedule["id"]),
                details={"shift_id": shift_id, "version_id": version_id},
            )

    refreshed_shift = await queries.get_shift(db, shift_id)
    assert refreshed_shift is not None
    refreshed_assignment = await queries.get_shift_assignment_with_worker(db, shift_id)
    shift_payload = _serialize_schedule_shift_payload(
        shift=refreshed_shift,
        assignment=refreshed_assignment,
        active_cascade=None,
        pending_claim_worker=None,
    )
    await audit_svc.append(
        db,
        AuditAction.shift_updated,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={
            "fields": sorted(patch.keys()),
            "version_id": version_id,
            "role": next_role,
            "date": next_date,
            "start_time": next_start_time,
            "end_time": next_end_time,
        },
    )
    return {
        "shift_id": shift_id,
        "schedule_id": shift.get("schedule_id"),
        "shift": refreshed_shift,
        "assignment": shift_payload["assignment"],
        "confirmation": shift_payload["confirmation"],
        "attendance": shift_payload["attendance"],
        "coverage": shift_payload["coverage"],
        "available_actions": shift_payload["available_actions"],
        "updated_fields": sorted(patch.keys()),
        "schedule_lifecycle_state": schedule_state or "draft",
    }


async def delete_schedule_shift(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    actor: str = "system",
) -> dict:
    shift = await queries.get_shift(db, shift_id)
    if shift is None:
        raise ValueError("Shift not found")
    active_cascade = await queries.get_active_cascade_for_shift(db, shift_id)
    if active_cascade is not None:
        raise ValueError("Cannot delete a shift with an active coverage workflow")
    if shift.get("status") != "scheduled":
        raise ValueError("Only scheduled shifts can be deleted")

    schedule = await queries.get_schedule(db, int(shift["schedule_id"])) if shift.get("schedule_id") else None
    if schedule is not None and (schedule.get("lifecycle_state") or "draft") == "archived":
        raise ValueError("Archived schedules are read-only")

    await queries.delete_shift_assignment(db, shift_id)
    await queries.delete_shift(db, shift_id)

    next_state = None
    version_id = None
    if schedule is not None:
        next_state, version_id = await _apply_schedule_mutation(
            db,
            schedule=schedule,
            actor=actor,
            change_summary={"event": "shift_deleted", "shift_id": shift_id},
        )
    await audit_svc.append(
        db,
        AuditAction.shift_deleted,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={"schedule_id": shift.get("schedule_id"), "version_id": version_id},
    )
    return {
        "shift_id": shift_id,
        "schedule_id": shift.get("schedule_id"),
        "deleted": True,
        "schedule_lifecycle_state": next_state,
        "version_id": version_id,
    }


async def amend_shift_assignment(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    worker_id: Optional[int],
    assignment_status: str,
    notes: Optional[str],
    actor: str = "system",
) -> dict:
    shift = await queries.get_shift(db, shift_id)
    if shift is None:
        raise ValueError("Shift not found")
    await _assert_shift_schedule_mutable(db, shift)
    active_cascade = await queries.get_active_cascade_for_shift(db, shift_id)
    if active_cascade is not None:
        raise ValueError("Cannot change assignment while coverage workflow is active")

    current_assignment = await queries.get_shift_assignment(db, shift_id)
    current_assignment_status = current_assignment.get("assignment_status") if current_assignment else None
    if current_assignment_status == "closed":
        raise ValueError("Closed shifts must be reopened first")
    if worker_id is None and assignment_status in {"assigned", "claimed", "confirmed"}:
        raise ValueError("Assigned shifts require a worker")
    if worker_id is not None and assignment_status in {"open", "closed"}:
        raise ValueError("Open or closed shifts cannot keep a worker assigned")

    if worker_id is not None:
        worker = await queries.get_worker(db, worker_id)
        if worker is None:
            raise ValueError("Worker not found")
        if (worker.get("employment_status") or "active") != "active":
            raise ValueError("Worker is not active")
        if shift.get("location_id") is not None and worker.get("location_id") != shift.get("location_id"):
            raise ValueError("Worker does not belong to this location")
        if shift.get("role") not in (worker.get("roles") or []):
            raise ValueError("Worker is not eligible for this role")
    await queries.upsert_shift_assignment(
        db,
        {
            "shift_id": shift_id,
            "worker_id": worker_id,
            "assignment_status": assignment_status,
            "source": "manual",
        },
    )
    await queries.update_shift_status(
        db,
        shift_id=shift_id,
        status="scheduled",
        filled_by=None,
        fill_tier=None,
        called_out_by=shift.get("called_out_by"),
    )
    if notes is not None:
        await queries.update_shift(db, shift_id, {"notes": notes})

    schedule_state = None
    version_id = None
    if shift.get("schedule_id"):
        schedule = await queries.get_schedule(db, int(shift["schedule_id"]))
        if schedule is not None:
            schedule_state, version_id = await _apply_schedule_mutation(
                db,
                schedule=schedule,
                actor=actor,
                change_summary={"event": "assignment_updated", "shift_id": shift_id},
            )
            if schedule_state == "amended":
                await queries.update_shift(db, shift_id, {"published_state": "amended"})
                await audit_svc.append(
                    db,
                    AuditAction.schedule_amended,
                    actor=actor,
                    entity_type="schedule",
                    entity_id=int(schedule["id"]),
                    details={"shift_id": shift_id, "version_id": version_id},
                )

    assignment = await queries.get_shift_assignment_with_worker(db, shift_id)
    active_cascade = await queries.get_active_cascade_for_shift(db, shift_id)
    pending_claim_worker = await _get_pending_claim_worker(db, active_cascade)
    shift_payload = _serialize_schedule_shift_payload(
        shift=await queries.get_shift(db, shift_id),
        assignment=assignment,
        active_cascade=active_cascade,
        pending_claim_worker=pending_claim_worker,
    )
    await audit_svc.append(
        db,
        AuditAction.shift_assignment_updated,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={
            "worker_id": worker_id,
            "assignment_status": assignment_status,
            "version_id": version_id,
        },
    )
    return {
        "shift_id": shift_id,
        "schedule_id": shift.get("schedule_id"),
        "assignment": shift_payload["assignment"],
        "confirmation": shift_payload["confirmation"],
        "attendance": shift_payload["attendance"],
        "coverage": shift_payload["coverage"],
        "available_actions": shift_payload["available_actions"],
        "schedule_lifecycle_state": schedule_state or "draft",
    }


async def apply_schedule_shift_assignments(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    assignments: list[dict],
    actor: str = "manager_api",
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    if not assignments:
        raise ValueError("At least one assignment is required")

    schedule_shifts = await queries.list_shifts(db, schedule_id=schedule_id)
    shift_ids_in_schedule = {int(shift["id"]) for shift in schedule_shifts}
    results: list[dict] = []

    for item in assignments:
        shift_id = int(item.get("shift_id") or 0)
        worker_id = item.get("worker_id")
        result = {
            "shift_id": shift_id,
            "worker_id": worker_id,
        }
        if shift_id not in shift_ids_in_schedule:
            results.append(
                {
                    **result,
                    "status": "error",
                    "error": "shift_not_found",
                }
            )
            continue

        try:
            outcome = await amend_shift_assignment(
                db,
                shift_id=shift_id,
                worker_id=int(worker_id) if worker_id is not None else None,
                assignment_status="assigned" if worker_id is not None else "open",
                notes=item.get("notes"),
                actor=actor,
            )
        except ValueError as exc:
            results.append(
                {
                    **result,
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        results.append(
            {
                **result,
                "status": "ok",
                "result": outcome,
            }
        )

    refreshed_schedule_view = await get_schedule_view(
        db,
        location_id=int(schedule["location_id"]),
        week_start=str(schedule["week_start_date"]),
    )
    success_count = sum(1 for item in results if item.get("status") == "ok")
    return {
        "schedule_id": schedule_id,
        "processed_count": len(assignments),
        "success_count": success_count,
        "error_count": len(results) - success_count,
        "results": results,
        "schedule_view": refreshed_schedule_view,
    }


async def apply_schedule_shift_edits(
    db: aiosqlite.Connection,
    *,
    schedule_id: int,
    shift_ids: list[int],
    patch: dict,
    actor: str = "manager_api",
) -> dict:
    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        raise ValueError("Schedule not found")
    if not shift_ids:
        raise ValueError("At least one shift is required")
    if not patch:
        raise ValueError("At least one field is required")

    schedule_shifts = await queries.list_shifts(db, schedule_id=schedule_id)
    shift_ids_in_schedule = {int(shift["id"]) for shift in schedule_shifts}
    results: list[dict] = []

    for shift_id in [int(shift_id) for shift_id in shift_ids]:
        result = {
            "shift_id": shift_id,
        }
        if shift_id not in shift_ids_in_schedule:
            results.append(
                {
                    **result,
                    "status": "error",
                    "error": "shift_not_found",
                }
            )
            continue

        try:
            outcome = await amend_schedule_shift_details(
                db,
                shift_id=shift_id,
                patch=dict(patch),
                actor=actor,
            )
        except ValueError as exc:
            results.append(
                {
                    **result,
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        results.append(
            {
                **result,
                "status": "ok",
                "result": outcome,
            }
        )

    refreshed_schedule_view = await get_schedule_view(
        db,
        location_id=int(schedule["location_id"]),
        week_start=str(schedule["week_start_date"]),
    )
    success_count = sum(1 for item in results if item.get("status") == "ok")
    return {
        "schedule_id": schedule_id,
        "processed_count": len(shift_ids),
        "success_count": success_count,
        "error_count": len(results) - success_count,
        "results": results,
        "updated_fields": sorted(patch.keys()),
        "schedule_view": refreshed_schedule_view,
    }


async def get_coverage_view(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    week_start: Optional[str] = None,
) -> dict:
    if week_start:
        effective_start = date.fromisoformat(week_start)
    else:
        effective_start = _week_start_for(date.today())
    effective_end = _week_end_for(effective_start)

    shifts = await queries.list_shifts(db, location_id=location_id)
    at_risk_shifts = []
    for shift in shifts:
        shift_date = date.fromisoformat(shift["date"])
        if shift_date < effective_start or shift_date > effective_end:
            continue
        assignment = await queries.get_shift_assignment_with_worker(db, int(shift["id"]))
        if shift.get("status") not in {"vacant", "filling", "unfilled"} and (
            not assignment or assignment.get("assignment_status") != "open"
        ):
            continue
        cascade = await queries.get_active_cascade_for_shift(db, int(shift["id"]))
        at_risk_shifts.append(
            await _build_coverage_entry(
                db,
                shift=shift,
                assignment=assignment,
                cascade=cascade,
            )
        )
    return {
        "location_id": location_id,
        "at_risk_shifts": at_risk_shifts,
    }


async def get_manager_action_queue(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    week_start: Optional[str] = None,
) -> dict:
    location = await queries.get_location(db, location_id)
    coverage = await get_coverage_view(db, location_id=location_id, week_start=week_start)
    schedule_view = await get_schedule_view(db, location_id=location_id, week_start=week_start)
    pending_actions = []
    for entry in coverage["at_risk_shifts"]:
        if entry["coverage_status"] == "awaiting_manager_approval":
            pending_actions.append(
                {
                    "action_type": "approve_fill",
                    "cascade_id": entry["cascade_id"],
                    "shift_id": entry["shift_id"],
                    "role": entry["role"],
                    "date": entry["date"],
                    "start_time": entry["start_time"],
                    "coverage_status": entry["coverage_status"],
                    "requested_at": entry.get("claimed_at") or entry.get("last_response_at") or entry.get("last_outreach_at"),
                    "worker_id": entry.get("claimed_by_worker_id"),
                    "worker_name": entry.get("claimed_by_worker_name"),
                    "available_actions": ["approve_fill", "decline_fill"],
                }
            )
        elif entry["coverage_status"] == "awaiting_agency_approval":
            pending_actions.append(
                {
                    "action_type": "approve_agency",
                    "cascade_id": entry["cascade_id"],
                    "shift_id": entry["shift_id"],
                    "role": entry["role"],
                    "date": entry["date"],
                    "start_time": entry["start_time"],
                    "coverage_status": entry["coverage_status"],
                    "requested_at": entry.get("last_response_at") or entry.get("last_outreach_at"),
                    "worker_id": None,
                    "worker_name": None,
                    "available_actions": ["approve_agency"],
                }
            )

    late_policy = (location or {}).get("late_arrival_policy") or "wait"
    missed_policy = (location or {}).get("missed_check_in_policy") or "start_coverage"
    for shift in schedule_view.get("shifts") or []:
        attendance = shift.get("attendance") or {}
        assignment = shift.get("assignment") or {}
        if shift.get("status") != "scheduled":
            continue
        if attendance.get("action_state") == "waiting_for_worker":
            continue
        if attendance.get("status") == "late" and late_policy == "manager_action":
            pending_actions.append(
                {
                    "action_type": "review_late_arrival",
                    "cascade_id": None,
                    "shift_id": shift["id"],
                    "role": shift["role"],
                    "date": shift["date"],
                    "start_time": shift["start_time"],
                    "coverage_status": "none",
                    "requested_at": attendance.get("late_reported_at") or attendance.get("requested_at"),
                    "worker_id": assignment.get("worker_id"),
                    "worker_name": assignment.get("worker_name"),
                    "late_eta_minutes": attendance.get("late_eta_minutes"),
                    "attendance_status": attendance.get("status"),
                    "available_actions": ["wait_for_worker", "start_coverage"],
                }
            )
        elif attendance.get("status") == "escalated" and missed_policy == "manager_action":
            pending_actions.append(
                {
                    "action_type": "review_missed_check_in",
                    "cascade_id": None,
                    "shift_id": shift["id"],
                    "role": shift["role"],
                    "date": shift["date"],
                    "start_time": shift["start_time"],
                    "coverage_status": "none",
                    "requested_at": attendance.get("escalated_at") or attendance.get("requested_at"),
                    "worker_id": assignment.get("worker_id"),
                    "worker_name": assignment.get("worker_name"),
                    "late_eta_minutes": attendance.get("late_eta_minutes"),
                    "attendance_status": attendance.get("status"),
                    "available_actions": ["wait_for_worker", "start_coverage"],
                }
            )

    pending_actions.sort(
        key=lambda item: (
            str(item.get("requested_at") or ""),
            str(item.get("date") or ""),
            str(item.get("start_time") or ""),
            int(item.get("shift_id") or 0),
        ),
        reverse=True,
    )
    return {
        "location_id": location_id,
        "summary": {
            "pending_actions": len(pending_actions),
            "fill_approvals": sum(1 for item in pending_actions if item["action_type"] == "approve_fill"),
            "agency_approvals": sum(1 for item in pending_actions if item["action_type"] == "approve_agency"),
            "attendance_reviews": sum(
                1
                for item in pending_actions
                if item["action_type"] in {"review_late_arrival", "review_missed_check_in"}
            ),
        },
        "actions": pending_actions,
    }


async def _get_attendance_action_context(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
) -> tuple[dict, dict, dict, dict, dict, dict | None]:
    shift = await queries.get_shift(db, shift_id)
    if shift is None:
        raise ValueError("Shift not found")
    location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
    if location is None:
        raise ValueError("Location not found")
    if not _uses_backfill_shifts(location):
        raise ValueError("Location is not using Backfill Shifts")
    assignment = await queries.get_shift_assignment_with_worker(db, shift_id)
    if (
        assignment is None
        or assignment.get("worker_id") is None
        or assignment.get("assignment_status") not in {"assigned", "claimed", "confirmed"}
    ):
        raise ValueError("Shift is not currently assigned to a worker")
    worker = await queries.get_worker(db, int(assignment["worker_id"]))
    if worker is None:
        raise ValueError("Worker not found")
    attendance = _serialize_attendance_payload(shift, assignment)
    cascade = await queries.get_active_cascade_for_shift(db, shift_id)
    return shift, assignment, worker, location, attendance, cascade


def _resolve_attendance_review_issue(
    *,
    shift: dict,
    location: dict,
    attendance: dict,
) -> Optional[str]:
    if shift.get("status") != "scheduled":
        return None
    late_policy = location.get("late_arrival_policy") or "wait"
    missed_policy = location.get("missed_check_in_policy") or "start_coverage"
    if attendance.get("status") == "late" and late_policy == "manager_action":
        return "late_arrival"
    if attendance.get("status") == "escalated" and missed_policy == "manager_action":
        return "missed_check_in"
    return None


async def _start_coverage_for_attendance_issue(
    db: aiosqlite.Connection,
    *,
    shift: dict,
    worker: dict,
    location: dict,
    issue_type: str,
    actor: str,
    notify_manager: bool = False,
    eta_minutes: Optional[int] = None,
) -> dict:
    shift_id = int(shift["id"])
    active_cascade = await queries.get_active_cascade_for_shift(db, shift_id)
    if active_cascade is not None:
        refreshed_shift = await queries.get_shift(db, shift_id)
        return {
            "status": "coverage_active",
            "shift": refreshed_shift,
            "worker": worker,
            "location": location,
            "cascade": active_cascade,
            "idempotent": True,
        }

    now_iso = datetime.utcnow().isoformat()
    updates = {
        "check_in_escalated_at": shift.get("check_in_escalated_at") or now_iso,
        "attendance_action_state": None,
        "attendance_action_updated_at": now_iso,
        "escalated_from_worker_id": int(worker["id"]),
    }
    await queries.update_shift(db, shift_id, updates)

    if issue_type == "late_arrival" and not shift.get("check_in_escalated_at"):
        await audit_svc.append(
            db,
            AuditAction.shift_check_in_escalated,
            actor=actor,
            entity_type="shift",
            entity_id=shift_id,
            details={
                "worker_id": int(worker["id"]),
                "reason": "late_arrival_reported",
                "eta_minutes": eta_minutes,
            },
        )

    cascade = await shift_manager.create_vacancy(
        db,
        shift_id=shift_id,
        called_out_by_worker_id=None,
        actor=actor,
    )
    await cascade_svc.advance(db, int(cascade["id"]))
    refreshed_shift = await queries.get_shift(db, shift_id)

    if notify_manager and refreshed_shift is not None:
        if issue_type == "late_arrival":
            await notifications_svc.queue_manager_late_arrival_coverage_started_notification(
                db,
                location_id=int(location["id"]),
                shift_id=int(refreshed_shift["id"]),
                worker_id=int(worker["id"]),
                eta_minutes=int(eta_minutes or 0),
                cascade_id=int(cascade["id"]),
            )
        else:
            await notifications_svc.queue_manager_missed_check_in_escalated_notification(
                db,
                location_id=int(location["id"]),
                shift_id=int(refreshed_shift["id"]),
                worker_id=int(worker["id"]),
                cascade_id=int(cascade["id"]),
            )

    return {
        "status": "coverage_started",
        "shift": refreshed_shift,
        "worker": worker,
        "location": location,
        "cascade": cascade,
    }


async def wait_for_attendance_issue(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    actor: str = "manager_api",
) -> dict:
    shift, assignment, worker, location, attendance, cascade = await _get_attendance_action_context(
        db,
        shift_id=shift_id,
    )
    if cascade is not None or shift.get("status") != "scheduled":
        raise ValueError("Coverage is already active for this shift")
    issue_type = _resolve_attendance_review_issue(
        shift=shift,
        location=location,
        attendance=attendance,
    )
    if issue_type is None:
        raise ValueError("Shift does not require an attendance review action")

    updated_at = datetime.utcnow().isoformat()
    await queries.update_shift(
        db,
        shift_id,
        {
            "attendance_action_state": "waiting_for_worker",
            "attendance_action_updated_at": updated_at,
        },
    )
    await audit_svc.append(
        db,
        AuditAction.shift_attendance_actioned,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={
            "decision": "wait_for_worker",
            "issue_type": issue_type,
            "worker_id": int(worker["id"]),
            "location_id": int(location["id"]),
        },
    )
    refreshed_shift = await queries.get_shift(db, shift_id)
    refreshed_attendance = _serialize_attendance_payload(refreshed_shift, assignment) if refreshed_shift else attendance
    return {
        "status": "waiting_for_worker",
        "shift_id": shift_id,
        "issue_type": issue_type,
        "attendance_status": refreshed_attendance.get("status"),
        "action_state": "waiting_for_worker",
    }


async def start_coverage_for_attendance_issue(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    actor: str = "manager_api",
) -> dict:
    shift, assignment, worker, location, attendance, cascade = await _get_attendance_action_context(
        db,
        shift_id=shift_id,
    )
    if cascade is not None or shift.get("status") != "scheduled":
        refreshed_shift = await queries.get_shift(db, shift_id)
        return {
            "status": "coverage_active",
            "shift_id": shift_id,
            "issue_type": None,
            "cascade_id": int(cascade["id"]) if cascade is not None else None,
            "idempotent": True,
            "shift": refreshed_shift,
        }

    issue_type = _resolve_attendance_review_issue(
        shift=shift,
        location=location,
        attendance=attendance,
    )
    if issue_type is None:
        raise ValueError("Shift does not require an attendance review action")

    result = await _start_coverage_for_attendance_issue(
        db,
        shift=shift,
        worker=worker,
        location=location,
        issue_type=issue_type,
        actor=actor,
        notify_manager=False,
        eta_minutes=attendance.get("late_eta_minutes"),
    )
    await audit_svc.append(
        db,
        AuditAction.shift_attendance_actioned,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={
            "decision": "start_coverage",
            "issue_type": issue_type,
            "worker_id": int(worker["id"]),
            "location_id": int(location["id"]),
            "cascade_id": int(result["cascade"]["id"]),
        },
    )
    return {
        "status": result["status"],
        "shift_id": shift_id,
        "issue_type": issue_type,
        "cascade_id": int(result["cascade"]["id"]),
        "idempotent": bool(result.get("idempotent", False)),
    }


async def _get_pending_confirmation_context(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    worker_id: int,
) -> tuple[dict, dict, dict, dict | None]:
    shift = await queries.get_shift(db, shift_id)
    if shift is None:
        raise ValueError("Shift not found")
    assignment = await queries.get_shift_assignment(db, shift_id)
    if (
        assignment is None
        or assignment.get("worker_id") != worker_id
        or assignment.get("assignment_status") not in {"assigned", "claimed", "confirmed"}
    ):
        raise ValueError("Shift is no longer assigned to this worker")
    worker = await queries.get_worker(db, worker_id)
    if worker is None:
        raise ValueError("Worker not found")
    location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
    return shift, assignment, worker, location


async def confirm_worker_shift(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    worker_id: int,
    actor: str = "system",
) -> dict:
    shift, assignment, worker, location = await _get_pending_confirmation_context(
        db,
        shift_id=shift_id,
        worker_id=worker_id,
    )
    if shift.get("status") != "scheduled" or not shift.get("confirmation_requested_at"):
        return {"status": "not_pending", "shift_id": shift_id, "worker_id": worker_id}
    if shift.get("worker_confirmed_at"):
        return {"status": "confirmed", "shift_id": shift_id, "worker_id": worker_id, "idempotent": True}

    confirmed_at = datetime.utcnow().isoformat()
    await queries.update_shift(
        db,
        shift_id,
        {
            "worker_confirmed_at": confirmed_at,
            "worker_declined_at": None,
        },
    )
    refreshed_shift = await queries.get_shift(db, shift_id)
    await audit_svc.append(
        db,
        AuditAction.shift_confirmation_received,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={
            "worker_id": worker_id,
            "outcome": "confirmed",
            "location_id": location.get("id") if location else None,
        },
    )
    return {
        "status": "confirmed",
        "shift": refreshed_shift,
        "worker": worker,
        "assignment": assignment,
        "location": location,
    }


async def decline_worker_shift(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    worker_id: int,
    actor: str = "system",
) -> dict:
    shift, assignment, worker, location = await _get_pending_confirmation_context(
        db,
        shift_id=shift_id,
        worker_id=worker_id,
    )
    if shift.get("status") in {"vacant", "filling", "unfilled"}:
        active_cascade = await queries.get_active_cascade_for_shift(db, shift_id)
        return {
            "status": "coverage_started" if active_cascade else "not_pending",
            "shift": shift,
            "worker": worker,
            "location": location,
            "cascade": active_cascade,
            "idempotent": active_cascade is not None,
        }
    if shift.get("status") != "scheduled" or not shift.get("confirmation_requested_at"):
        return {"status": "not_pending", "shift_id": shift_id, "worker_id": worker_id}

    declined_at = datetime.utcnow().isoformat()
    await queries.update_shift(
        db,
        shift_id,
        {
            "worker_declined_at": declined_at,
            "worker_confirmed_at": None,
        },
    )
    await audit_svc.append(
        db,
        AuditAction.shift_confirmation_received,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={
            "worker_id": worker_id,
            "outcome": "declined",
            "location_id": location.get("id") if location else None,
        },
    )
    cascade = await shift_manager.create_vacancy(
        db,
        shift_id=shift_id,
        called_out_by_worker_id=worker_id,
        actor=actor,
    )
    await cascade_svc.advance(db, int(cascade["id"]))
    if location is not None:
        refreshed_shift = await queries.get_shift(db, shift_id)
        if refreshed_shift is not None:
            await notifications_svc.queue_manager_callout_received_notification(
                db,
                location_id=int(location["id"]),
                shift_id=int(refreshed_shift["id"]),
                worker_id=int(worker["id"]),
                cascade_id=int(cascade["id"]),
            )
    refreshed_shift = await queries.get_shift(db, shift_id)
    return {
        "status": "coverage_started",
        "shift": refreshed_shift,
        "worker": worker,
        "location": location,
        "cascade": cascade,
    }


async def _get_pending_check_in_context(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    worker_id: int,
) -> tuple[dict, dict, dict, dict | None]:
    shift = await queries.get_shift(db, shift_id)
    if shift is None:
        raise ValueError("Shift not found")
    assignment = await queries.get_shift_assignment(db, shift_id)
    if (
        assignment is None
        or assignment.get("worker_id") != worker_id
        or assignment.get("assignment_status") not in {"assigned", "claimed", "confirmed"}
    ):
        raise ValueError("Shift is no longer assigned to this worker")
    worker = await queries.get_worker(db, worker_id)
    if worker is None:
        raise ValueError("Worker not found")
    location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
    return shift, assignment, worker, location


async def record_worker_check_in(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    worker_id: int,
    actor: str = "system",
) -> dict:
    shift, assignment, worker, location = await _get_pending_check_in_context(
        db,
        shift_id=shift_id,
        worker_id=worker_id,
    )
    if shift.get("status") != "scheduled" or not shift.get("check_in_requested_at"):
        return {"status": "not_pending", "shift_id": shift_id, "worker_id": worker_id}
    if shift.get("checked_in_at"):
        return {"status": "checked_in", "shift_id": shift_id, "worker_id": worker_id, "idempotent": True}

    checked_in_at = datetime.utcnow().isoformat()
    await queries.update_shift(
        db,
        shift_id,
        {
            "checked_in_at": checked_in_at,
            "late_reported_at": None,
            "late_eta_minutes": None,
            "check_in_escalated_at": None,
            "attendance_action_state": None,
            "attendance_action_updated_at": checked_in_at,
        },
    )
    refreshed_shift = await queries.get_shift(db, shift_id)
    await audit_svc.append(
        db,
        AuditAction.shift_check_in_received,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={
            "worker_id": worker_id,
            "outcome": "checked_in",
            "location_id": location.get("id") if location else None,
        },
    )
    return {
        "status": "checked_in",
        "shift": refreshed_shift,
        "worker": worker,
        "assignment": assignment,
        "location": location,
    }


async def record_worker_late_arrival(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    worker_id: int,
    eta_minutes: int,
    actor: str = "system",
) -> dict:
    shift, assignment, worker, location = await _get_pending_check_in_context(
        db,
        shift_id=shift_id,
        worker_id=worker_id,
    )
    if shift.get("status") != "scheduled" or not shift.get("check_in_requested_at"):
        return {"status": "not_pending", "shift_id": shift_id, "worker_id": worker_id}

    late_reported_at = datetime.utcnow().isoformat()
    await queries.update_shift(
        db,
        shift_id,
        {
            "late_reported_at": late_reported_at,
            "late_eta_minutes": int(eta_minutes),
            "checked_in_at": None,
            "attendance_action_state": None,
            "attendance_action_updated_at": late_reported_at,
        },
    )
    refreshed_shift = await queries.get_shift(db, shift_id)
    await audit_svc.append(
        db,
        AuditAction.shift_check_in_received,
        actor=actor,
        entity_type="shift",
        entity_id=shift_id,
        details={
            "worker_id": worker_id,
            "outcome": "late",
            "eta_minutes": int(eta_minutes),
            "location_id": location.get("id") if location else None,
        },
    )
    late_policy = (location or {}).get("late_arrival_policy") or "wait"
    if location is not None and refreshed_shift is not None:
        if late_policy == "start_coverage":
            coverage_result = await _start_coverage_for_attendance_issue(
                db,
                shift=refreshed_shift,
                worker=worker,
                location=location,
                issue_type="late_arrival",
                actor=actor,
                notify_manager=True,
                eta_minutes=int(eta_minutes),
            )
            return {
                "status": coverage_result["status"],
                "shift": coverage_result["shift"],
                "worker": worker,
                "assignment": assignment,
                "location": location,
                "eta_minutes": int(eta_minutes),
                "cascade": coverage_result.get("cascade"),
            }
        await notifications_svc.queue_manager_late_arrival_reported_notification(
            db,
            location_id=int(location["id"]),
            shift_id=int(refreshed_shift["id"]),
            worker_id=int(worker["id"]),
            eta_minutes=int(eta_minutes),
        )
    return {
        "status": "late",
        "shift": refreshed_shift,
        "worker": worker,
        "assignment": assignment,
        "location": location,
        "eta_minutes": int(eta_minutes),
    }


async def send_shift_confirmation_requests(
    db: aiosqlite.Connection,
    *,
    within_minutes: int = 120,
    location_id: Optional[int] = None,
    actor: str = "system",
) -> dict:
    shifts = await queries.list_shifts_needing_confirmation_request(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )
    sent_shift_ids: list[int] = []
    skipped_shift_ids: list[int] = []
    failed_shift_ids: list[int] = []
    for shift in shifts:
        if not shift.get("assigned_worker_id") or not shift.get("assigned_worker_phone"):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
        if location is not None and not _uses_backfill_shifts(location):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        now_iso = datetime.utcnow().isoformat()
        try:
            message_sid = notifications_svc.notify_worker_shift_confirmation_request(
                str(shift["assigned_worker_phone"]),
                worker_name=str(shift.get("assigned_worker_name") or "there"),
                location_name=str(shift.get("location_name") or "your location"),
                role=str(shift["role"]),
                shift_date=str(shift["date"]),
                start_time=str(shift["start_time"]),
            )
        except Exception as exc:
            failed_shift_ids.append(int(shift["id"]))
            await audit_svc.append(
                db,
                AuditAction.shift_confirmation_requested,
                actor=actor,
                entity_type="shift",
                entity_id=int(shift["id"]),
                details={
                    "worker_id": int(shift["assigned_worker_id"]),
                    "status": "failed",
                    "error": str(exc),
                },
            )
            continue
        if not message_sid:
            failed_shift_ids.append(int(shift["id"]))
            await audit_svc.append(
                db,
                AuditAction.shift_confirmation_requested,
                actor=actor,
                entity_type="shift",
                entity_id=int(shift["id"]),
                details={
                    "worker_id": int(shift["assigned_worker_id"]),
                    "status": "failed",
                    "error": "delivery_unavailable",
                },
            )
            continue

        await queries.update_shift(
            db,
            int(shift["id"]),
            {
                "confirmation_requested_at": now_iso,
                "worker_confirmed_at": None,
                "worker_declined_at": None,
            },
        )
        sent_shift_ids.append(int(shift["id"]))
        await audit_svc.append(
            db,
            AuditAction.shift_confirmation_requested,
            actor=actor,
            entity_type="shift",
            entity_id=int(shift["id"]),
            details={
                "worker_id": int(shift["assigned_worker_id"]),
                "status": "sent",
                "message_sid": message_sid,
            },
        )

    return {
        "within_minutes": within_minutes,
        "sent_count": len(sent_shift_ids),
        "sent_shift_ids": sent_shift_ids,
        "skipped_shift_ids": skipped_shift_ids,
        "failed_shift_ids": failed_shift_ids,
    }


async def send_shift_check_in_requests(
    db: aiosqlite.Connection,
    *,
    within_minutes: int = 15,
    location_id: Optional[int] = None,
    actor: str = "system",
) -> dict:
    shifts = await queries.list_shifts_needing_check_in_request(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )
    sent_shift_ids: list[int] = []
    skipped_shift_ids: list[int] = []
    failed_shift_ids: list[int] = []
    for shift in shifts:
        if not shift.get("assigned_worker_id") or not shift.get("assigned_worker_phone"):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
        if location is not None and not _uses_backfill_shifts(location):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        now_iso = datetime.utcnow().isoformat()
        try:
            message_sid = notifications_svc.notify_worker_shift_check_in_request(
                str(shift["assigned_worker_phone"]),
                worker_name=str(shift.get("assigned_worker_name") or "there"),
                location_name=str(shift.get("location_name") or "your location"),
                role=str(shift["role"]),
                shift_date=str(shift["date"]),
                start_time=str(shift["start_time"]),
            )
        except Exception as exc:
            failed_shift_ids.append(int(shift["id"]))
            await audit_svc.append(
                db,
                AuditAction.shift_check_in_requested,
                actor=actor,
                entity_type="shift",
                entity_id=int(shift["id"]),
                details={
                    "worker_id": int(shift["assigned_worker_id"]),
                    "status": "failed",
                    "error": str(exc),
                },
            )
            continue
        if not message_sid:
            failed_shift_ids.append(int(shift["id"]))
            await audit_svc.append(
                db,
                AuditAction.shift_check_in_requested,
                actor=actor,
                entity_type="shift",
                entity_id=int(shift["id"]),
                details={
                    "worker_id": int(shift["assigned_worker_id"]),
                    "status": "failed",
                    "error": "delivery_unavailable",
                },
            )
            continue

        await queries.update_shift(
            db,
            int(shift["id"]),
            {
                "check_in_requested_at": now_iso,
                "checked_in_at": None,
                "late_reported_at": None,
                "late_eta_minutes": None,
                "check_in_escalated_at": None,
                "attendance_action_state": None,
                "attendance_action_updated_at": now_iso,
            },
        )
        sent_shift_ids.append(int(shift["id"]))
        await audit_svc.append(
            db,
            AuditAction.shift_check_in_requested,
            actor=actor,
            entity_type="shift",
            entity_id=int(shift["id"]),
            details={
                "worker_id": int(shift["assigned_worker_id"]),
                "status": "sent",
                "message_sid": message_sid,
            },
        )

    return {
        "within_minutes": within_minutes,
        "sent_count": len(sent_shift_ids),
        "sent_shift_ids": sent_shift_ids,
        "skipped_shift_ids": skipped_shift_ids,
        "failed_shift_ids": failed_shift_ids,
    }


def _should_escalate_missed_check_in(
    shift: dict,
    *,
    grace_minutes: int,
    now: datetime,
) -> bool:
    if shift.get("checked_in_at") or shift.get("check_in_escalated_at"):
        return False
    shift_start = _shift_start_datetime(shift)
    if shift_start is None:
        return False
    if shift.get("late_reported_at") and shift.get("late_eta_minutes") is not None:
        return now >= shift_start + timedelta(minutes=int(shift["late_eta_minutes"]))
    return now >= shift_start + timedelta(minutes=grace_minutes)


async def escalate_missed_check_ins(
    db: aiosqlite.Connection,
    *,
    grace_minutes: int = 10,
    location_id: Optional[int] = None,
    actor: str = "system",
) -> dict:
    now = datetime.utcnow()
    shifts = await queries.list_shifts_missing_check_in(
        db,
        location_id=location_id,
    )
    escalated_shift_ids: list[int] = []
    skipped_shift_ids: list[int] = []
    for shift in shifts:
        if not _should_escalate_missed_check_in(shift, grace_minutes=grace_minutes, now=now):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        if not shift.get("assigned_worker_id"):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
        if location is not None and not _uses_backfill_shifts(location):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        worker = await queries.get_worker(db, int(shift["assigned_worker_id"]))
        if worker is None:
            skipped_shift_ids.append(int(shift["id"]))
            continue

        escalated_at = datetime.utcnow().isoformat()
        await queries.update_shift(
            db,
            int(shift["id"]),
            {
                "check_in_escalated_at": escalated_at,
                "escalated_from_worker_id": int(worker["id"]),
                "attendance_action_state": None,
                "attendance_action_updated_at": escalated_at,
            },
        )
        await audit_svc.append(
            db,
            AuditAction.shift_check_in_escalated,
            actor=actor,
            entity_type="shift",
            entity_id=int(shift["id"]),
            details={
                "worker_id": int(worker["id"]),
                "reason": "missed_check_in_after_start",
                "grace_minutes": grace_minutes,
            },
        )
        refreshed_shift = await queries.get_shift(db, int(shift["id"]))
        missed_policy = (location or {}).get("missed_check_in_policy") or "start_coverage"
        if location is not None and refreshed_shift is not None and missed_policy == "manager_action":
            await notifications_svc.queue_manager_missed_check_in_action_required_notification(
                db,
                location_id=int(location["id"]),
                shift_id=int(refreshed_shift["id"]),
                worker_id=int(worker["id"]),
            )
            escalated_shift_ids.append(int(shift["id"]))
            continue

        coverage_result = await _start_coverage_for_attendance_issue(
            db,
            shift=refreshed_shift or shift,
            worker=worker,
            location=location or {},
            issue_type="missed_check_in",
            actor=actor,
            notify_manager=location is not None and refreshed_shift is not None,
        )
        escalated_shift_ids.append(int(shift["id"]))

    return {
        "grace_minutes": grace_minutes,
        "escalated_count": len(escalated_shift_ids),
        "escalated_shift_ids": escalated_shift_ids,
        "skipped_shift_ids": skipped_shift_ids,
    }


async def escalate_unconfirmed_shifts(
    db: aiosqlite.Connection,
    *,
    within_minutes: int = 15,
    location_id: Optional[int] = None,
    actor: str = "system",
) -> dict:
    shifts = await queries.list_unconfirmed_shifts_for_escalation(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )
    escalated_shift_ids: list[int] = []
    skipped_shift_ids: list[int] = []
    for shift in shifts:
        if not shift.get("assigned_worker_id"):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
        if location is not None and not _uses_backfill_shifts(location):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        worker = await queries.get_worker(db, int(shift["assigned_worker_id"]))
        if worker is None:
            skipped_shift_ids.append(int(shift["id"]))
            continue

        escalated_at = datetime.utcnow().isoformat()
        await queries.update_shift(
            db,
            int(shift["id"]),
            {
                "confirmation_escalated_at": escalated_at,
                "escalated_from_worker_id": int(worker["id"]),
            },
        )
        await audit_svc.append(
            db,
            AuditAction.shift_confirmation_escalated,
            actor=actor,
            entity_type="shift",
            entity_id=int(shift["id"]),
            details={
                "worker_id": int(worker["id"]),
                "reason": "unconfirmed_close_to_start",
            },
        )
        cascade = await shift_manager.create_vacancy(
            db,
            shift_id=int(shift["id"]),
            called_out_by_worker_id=None,
            actor=actor,
        )
        await cascade_svc.advance(db, int(cascade["id"]))
        refreshed_shift = await queries.get_shift(db, int(shift["id"]))
        if location is not None and refreshed_shift is not None:
            await notifications_svc.queue_manager_unconfirmed_shift_escalated_notification(
                db,
                location_id=int(location["id"]),
                shift_id=int(refreshed_shift["id"]),
                worker_id=int(worker["id"]),
                cascade_id=int(cascade["id"]),
            )
        escalated_shift_ids.append(int(shift["id"]))

    return {
        "within_minutes": within_minutes,
        "escalated_count": len(escalated_shift_ids),
        "escalated_shift_ids": escalated_shift_ids,
        "skipped_shift_ids": skipped_shift_ids,
    }


async def send_shift_reminders(
    db: aiosqlite.Connection,
    *,
    within_minutes: int = 30,
    location_id: Optional[int] = None,
    actor: str = "system",
) -> dict:
    from app.services.messaging import send_sms

    shifts = await queries.list_filled_shifts_needing_reminder(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )
    sent_shift_ids: list[int] = []
    skipped_shift_ids: list[int] = []
    for shift in shifts:
        worker_id = shift.get("reminder_worker_id") or shift.get("filled_by")
        if not worker_id:
            skipped_shift_ids.append(int(shift["id"]))
            continue
        worker = await queries.get_worker(db, int(worker_id))
        if worker is None or not worker.get("phone"):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        if worker.get("sms_consent_status") != "granted":
            skipped_shift_ids.append(int(shift["id"]))
            continue
        location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
        message_sid = send_sms(
            worker["phone"],
            outreach_svc.build_reminder_sms(worker, shift, location),
        )
        await queries.mark_reminder_sent(db, int(shift["id"]))
        await audit_svc.append(
            db,
            AuditAction.outreach_sent,
            actor=actor,
            entity_type="shift",
            entity_id=int(shift["id"]),
            details={
                "event": "shift_reminder_sent",
                "channel": "sms_reminder",
                "worker_id": int(worker_id),
                "message_sid": message_sid,
            },
        )
        sent_shift_ids.append(int(shift["id"]))
    return {
        "location_id": location_id,
        "within_minutes": within_minutes,
        "reminders_sent": len(sent_shift_ids),
        "shift_ids": sent_shift_ids,
        "skipped_shift_ids": skipped_shift_ids,
    }


async def send_manager_digest(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    lookahead_hours: int = 24,
    include_empty: bool = True,
    actor: str = "system",
) -> dict:
    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError("Location not found")
    if not location.get("manager_phone"):
        raise ValueError("Location manager phone is missing")

    now = datetime.utcnow()
    window_end = now + timedelta(hours=lookahead_hours)
    shifts = await queries.list_shifts(db, location_id=location_id)

    upcoming: list[tuple[dict, dict | None, dict | None]] = []
    for shift in shifts:
        assignment = await queries.get_shift_assignment_with_worker(db, int(shift["id"]))
        cascade = await queries.get_active_cascade_for_shift(db, int(shift["id"]))
        if not _should_include_in_manager_digest(
            shift,
            assignment=assignment,
            cascade=cascade,
            now=now,
            window_end=window_end,
        ):
            continue
        upcoming.append((shift, assignment, cascade))

    scheduled_shifts = len(upcoming)
    open_shifts = 0
    active_coverage = 0
    attendance_issues = 0
    late_arrivals = 0
    late_arrivals_awaiting_decision = 0
    missed_check_ins = 0
    missed_check_ins_awaiting_decision = 0
    missed_check_ins_escalated = 0
    pending_fill_approvals = 0
    pending_agency_approvals = 0
    pending_attendance_reviews = 0

    for shift, assignment, cascade in upcoming:
        assignment_payload = _serialize_assignment_payload(assignment, shift=shift)
        attendance_payload = _serialize_attendance_payload(shift, assignment)
        attendance_summary = _summarize_attendance_exception(
            attendance_payload,
            late_policy=(location.get("late_arrival_policy") or "wait"),
            missed_policy=(location.get("missed_check_in_policy") or "start_coverage"),
        )
        is_open = (
            shift.get("status") in {"vacant", "filling", "unfilled"}
            or assignment_payload.get("worker_id") is None
        )
        if is_open:
            open_shifts += 1
        attendance_issues += attendance_summary["attendance_issues"]
        late_arrivals += attendance_summary["late_arrivals"]
        late_arrivals_awaiting_decision += attendance_summary["late_arrivals_awaiting_decision"]
        missed_check_ins += attendance_summary["missed_check_ins"]
        missed_check_ins_awaiting_decision += attendance_summary["missed_check_ins_awaiting_decision"]
        missed_check_ins_escalated += attendance_summary["missed_check_ins_escalated"]
        pending_attendance_reviews += (
            attendance_summary["late_arrivals_awaiting_decision"]
            + attendance_summary["missed_check_ins_awaiting_decision"]
        )
        if cascade is not None:
            active_coverage += 1
            if cascade.get("pending_claim_worker_id") is not None:
                pending_fill_approvals += 1
            elif int(cascade.get("current_tier") or 1) >= 3 and not cascade.get("manager_approved_tier3"):
                pending_agency_approvals += 1

    pending_actions = pending_fill_approvals + pending_agency_approvals + pending_attendance_reviews
    if not include_empty and scheduled_shifts <= 0 and pending_actions <= 0 and active_coverage <= 0 and open_shifts <= 0:
        return {
            "location_id": location_id,
            "lookahead_hours": lookahead_hours,
            "status": "skipped_no_activity",
            "summary": {
                "scheduled_shifts": scheduled_shifts,
                "open_shifts": open_shifts,
                "active_coverage": active_coverage,
                "attendance_issues": attendance_issues,
                "late_arrivals": late_arrivals,
                "late_arrivals_awaiting_decision": late_arrivals_awaiting_decision,
                "missed_check_ins": missed_check_ins,
                "missed_check_ins_awaiting_decision": missed_check_ins_awaiting_decision,
                "missed_check_ins_escalated": missed_check_ins_escalated,
                "pending_actions": pending_actions,
                "pending_fill_approvals": pending_fill_approvals,
                "pending_agency_approvals": pending_agency_approvals,
                "pending_attendance_reviews": pending_attendance_reviews,
            },
            "review_link": None,
            "message_sid": None,
        }
    relevant_day = (
        min((_shift_start_datetime(shift) or now for shift, _, _ in upcoming), default=now).date()
    )
    review_tab = "coverage" if pending_actions or open_shifts or active_coverage else "schedule"
    review_link = notifications_svc.build_manager_dashboard_link(
        location_id,
        tab=review_tab,
        week_start=_week_start_for(relevant_day).isoformat(),
    )
    message_sid = notifications_svc.notify_manager_operational_digest(
        location["manager_phone"],
        location_name=location.get("name") or "your location",
        lookahead_hours=lookahead_hours,
        scheduled_shifts=scheduled_shifts,
        open_shifts=open_shifts,
        active_coverage=active_coverage,
        attendance_issues=attendance_issues,
        late_arrivals=late_arrivals,
        late_arrivals_awaiting_decision=late_arrivals_awaiting_decision,
        missed_check_ins=missed_check_ins,
        missed_check_ins_awaiting_decision=missed_check_ins_awaiting_decision,
        missed_check_ins_escalated=missed_check_ins_escalated,
        pending_actions=pending_actions,
        review_link=review_link,
    )
    summary = {
        "scheduled_shifts": scheduled_shifts,
        "open_shifts": open_shifts,
        "active_coverage": active_coverage,
        "attendance_issues": attendance_issues,
        "late_arrivals": late_arrivals,
        "late_arrivals_awaiting_decision": late_arrivals_awaiting_decision,
        "missed_check_ins": missed_check_ins,
        "missed_check_ins_awaiting_decision": missed_check_ins_awaiting_decision,
        "missed_check_ins_escalated": missed_check_ins_escalated,
        "pending_actions": pending_actions,
        "pending_fill_approvals": pending_fill_approvals,
        "pending_agency_approvals": pending_agency_approvals,
        "pending_attendance_reviews": pending_attendance_reviews,
    }
    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        actor=actor,
        entity_type="location",
        entity_id=location_id,
        details={
            "event": "manager_operational_digest",
            "lookahead_hours": lookahead_hours,
            "summary": summary,
            "review_link": review_link,
            "message_sid": message_sid,
        },
    )
    await queries.update_location(
        db,
        location_id,
        {"last_manager_digest_sent_at": datetime.utcnow().isoformat()},
    )
    return {
        "location_id": location_id,
        "lookahead_hours": lookahead_hours,
        "status": "sent",
        "summary": summary,
        "review_link": review_link,
        "message_sid": message_sid,
    }


def _uses_backfill_shifts(location: dict) -> bool:
    return (
        bool(location.get("backfill_shifts_enabled", True))
        and str(location.get("backfill_shifts_launch_state") or "enabled") != "disabled"
        and (
            location.get("operating_mode") == "backfill_shifts"
            or location.get("scheduling_platform") == "backfill_native"
        )
    )


async def get_location_backfill_shifts_metrics(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    days: int = 30,
) -> dict:
    from app.services import backfill_shifts_monitoring as monitoring_svc

    return await monitoring_svc.get_location_backfill_shifts_metrics(
        db,
        location_id=location_id,
        days=days,
    )


async def get_location_backfill_shifts_activity(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    days: int = 30,
    limit: int = 50,
) -> dict:
    from app.services import backfill_shifts_monitoring as monitoring_svc

    return await monitoring_svc.get_location_backfill_shifts_activity(
        db,
        location_id=location_id,
        days=days,
        limit=limit,
    )


async def get_backfill_shifts_webhook_health(
    db: aiosqlite.Connection,
    *,
    source: str = "twilio_sms",
    days: int = 30,
    limit: int = 50,
) -> dict:
    from app.services import backfill_shifts_monitoring as monitoring_svc

    return await monitoring_svc.get_backfill_shifts_webhook_health(
        db,
        source=source,
        days=days,
        limit=limit,
    )


async def send_due_manager_digests(
    db: aiosqlite.Connection,
    *,
    lookahead_hours: int = 24,
    cooldown_hours: int = 12,
    location_id: Optional[int] = None,
    include_empty: bool = False,
    actor: str = "system",
) -> dict:
    if location_id is not None:
        target = await queries.get_location(db, location_id)
        if target is None:
            raise ValueError("Location not found")
        locations = [target]
    else:
        locations = await queries.list_locations(db)

    now = datetime.utcnow()
    sent: list[int] = []
    skipped_recent: list[int] = []
    skipped_no_activity: list[int] = []
    skipped_ineligible: list[int] = []

    for location in locations:
        current_location_id = int(location["id"])
        if not _uses_backfill_shifts(location) or not location.get("manager_phone"):
            skipped_ineligible.append(current_location_id)
            continue
        last_digest_at = location.get("last_manager_digest_sent_at")
        if cooldown_hours > 0 and last_digest_at:
            try:
                last_sent = datetime.fromisoformat(str(last_digest_at))
                if now - last_sent < timedelta(hours=cooldown_hours):
                    skipped_recent.append(current_location_id)
                    continue
            except ValueError:
                pass

        result = await send_manager_digest(
            db,
            location_id=current_location_id,
            lookahead_hours=lookahead_hours,
            include_empty=include_empty,
            actor=actor,
        )
        if result.get("status") == "skipped_no_activity":
            skipped_no_activity.append(current_location_id)
            continue
        sent.append(current_location_id)

    return {
        "lookahead_hours": lookahead_hours,
        "cooldown_hours": cooldown_hours,
        "sent_count": len(sent),
        "sent_location_ids": sent,
        "skipped_recent_location_ids": skipped_recent,
        "skipped_no_activity_location_ids": skipped_no_activity,
        "skipped_ineligible_location_ids": skipped_ineligible,
    }


async def run_due_backfill_shifts_automation(
    db: aiosqlite.Connection,
    *,
    location_id: Optional[int] = None,
    confirmation_within_minutes: int = 120,
    unconfirmed_within_minutes: int = 15,
    check_in_within_minutes: int = 15,
    missed_check_in_grace_minutes: int = 10,
    reminder_within_minutes: int = 30,
    digest_lookahead_hours: int = 24,
    digest_cooldown_hours: int = 12,
    include_empty_digests: bool = False,
    run_confirmations: bool = True,
    run_unconfirmed_escalations: bool = True,
    run_check_ins: bool = True,
    run_missed_check_in_escalations: bool = True,
    run_reminders: bool = True,
    run_manager_digests: bool = True,
    actor: str = "system",
) -> dict:
    ran_at = datetime.utcnow().isoformat()
    steps: dict[str, dict] = {}

    async def _run_step(name: str, enabled: bool, func, **kwargs) -> None:
        if not enabled:
            steps[name] = {"status": "skipped"}
            return
        try:
            steps[name] = {
                "status": "completed",
                "result": await func(db, actor=actor, location_id=location_id, **kwargs),
            }
        except Exception as exc:
            steps[name] = {
                "status": "failed",
                "error": str(exc),
            }

    await _run_step(
        "unconfirmed_escalations",
        run_unconfirmed_escalations,
        escalate_unconfirmed_shifts,
        within_minutes=unconfirmed_within_minutes,
    )
    await _run_step(
        "missed_check_in_escalations",
        run_missed_check_in_escalations,
        escalate_missed_check_ins,
        grace_minutes=missed_check_in_grace_minutes,
    )
    await _run_step(
        "confirmation_requests",
        run_confirmations,
        send_shift_confirmation_requests,
        within_minutes=confirmation_within_minutes,
    )
    await _run_step(
        "check_in_requests",
        run_check_ins,
        send_shift_check_in_requests,
        within_minutes=check_in_within_minutes,
    )
    await _run_step(
        "shift_reminders",
        run_reminders,
        send_shift_reminders,
        within_minutes=reminder_within_minutes,
    )

    if run_manager_digests:
        try:
            steps["manager_digests"] = {
                "status": "completed",
                "result": await send_due_manager_digests(
                    db,
                    lookahead_hours=digest_lookahead_hours,
                    cooldown_hours=digest_cooldown_hours,
                    location_id=location_id,
                    include_empty=include_empty_digests,
                    actor=actor,
                ),
            }
        except Exception as exc:
            steps["manager_digests"] = {
                "status": "failed",
                "error": str(exc),
            }
    else:
        steps["manager_digests"] = {"status": "skipped"}

    return {
        "ran_at": ran_at,
        "location_id": location_id,
        "steps": steps,
        "summary": {
            "completed_steps": sum(1 for step in steps.values() if step.get("status") == "completed"),
            "failed_steps": sum(1 for step in steps.values() if step.get("status") == "failed"),
            "skipped_steps": sum(1 for step in steps.values() if step.get("status") == "skipped"),
        },
    }
