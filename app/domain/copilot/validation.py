from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.copilot.registry import get_tool
from app.models.common import MembershipRole
from app.schemas.copilot import CopilotValidationResultRead
from app.services.auth import AuthContext, has_business_access, has_location_access

READ_ROLES = {
    MembershipRole.owner,
    MembershipRole.admin,
    MembershipRole.manager,
    MembershipRole.viewer,
}

DAY_NAME_TO_INDEX = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


@dataclass(frozen=True)
class ValidatedToolCall:
    validation_result: CopilotValidationResultRead
    normalized_arguments: dict[str, Any]


def _ok(arguments: dict[str, Any] | None = None) -> ValidatedToolCall:
    return ValidatedToolCall(
        validation_result=CopilotValidationResultRead(
            ok=True,
            code="ok",
            message="Tool call validated.",
        ),
        normalized_arguments=arguments or {},
    )


def _error(code: str, message: str) -> ValidatedToolCall:
    return ValidatedToolCall(
        validation_result=CopilotValidationResultRead(
            ok=False,
            code=code,
            message=message,
        ),
        normalized_arguments={},
    )


def _normalize_day_of_week(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("day_of_week_must_be_weekday_index")
    if isinstance(value, int):
        day_of_week = value
    elif isinstance(value, str):
        normalized = value.strip().lower()
        if normalized.isdigit():
            day_of_week = int(normalized)
        elif normalized in DAY_NAME_TO_INDEX:
            day_of_week = DAY_NAME_TO_INDEX[normalized]
        else:
            raise ValueError("day_of_week_must_be_weekday_index")
    else:
        raise ValueError("day_of_week_must_be_weekday_index")
    if day_of_week < 0 or day_of_week > 6:
        raise ValueError("day_of_week_must_be_weekday_index")
    return day_of_week


def _normalize_local_time(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        if value < 0 or value > 23:
            raise ValueError("time_must_be_local_clock_value")
        return f"{value:02d}:00:00"
    if not isinstance(value, str):
        raise ValueError("time_must_be_local_clock_value")
    raw = value.strip()
    if not raw:
        raise ValueError("time_must_be_local_clock_value")
    candidates = (
        "%H:%M:%S",
        "%H:%M",
        "%H",
        "%I:%M %p",
        "%I %p",
        "%I:%M%p",
        "%I%p",
    )
    normalized = raw.upper().replace(".", "")
    for pattern in candidates:
        try:
            parsed = datetime.strptime(normalized, pattern)
            return parsed.strftime("%H:%M:%S")
        except ValueError:
            continue
    raise ValueError("time_must_be_local_clock_value")


def _normalize_availability_arguments(
    *,
    tool_arguments: dict[str, Any] | None,
    default_timezone: str | None,
) -> ValidatedToolCall:
    arguments = tool_arguments or {}
    if not isinstance(arguments, dict):
        return _error(
            "invalid_arguments",
            "Availability updates require a structured rules payload.",
        )
    if "rules" not in arguments:
        return _error(
            "invalid_arguments",
            "Availability updates require an explicit rules field.",
        )
    raw_rules = arguments.get("rules")
    if not isinstance(raw_rules, list):
        return _error(
            "invalid_arguments",
            "Availability updates require rules to be sent as a list.",
        )
    clear_requested = bool(arguments.get("clear_requested"))
    top_level_timezone = arguments.get("timezone")
    effective_timezone = top_level_timezone if isinstance(top_level_timezone, str) and top_level_timezone.strip() else default_timezone
    if len(raw_rules) == 0:
        if not clear_requested:
            return _error(
                "invalid_arguments",
                "Availability updates need at least one rule unless the operator explicitly asked to clear availability.",
            )
        return _ok(
            {
                "timezone": effective_timezone or "UTC",
                "clear_requested": True,
                "rules": [],
            }
        )
    normalized_rules: list[dict[str, Any]] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            return _error(
                "invalid_arguments",
                "Each availability rule must be an object with day and time values.",
            )
        try:
            day_of_week = _normalize_day_of_week(raw_rule.get("day_of_week"))
            start_local_time = _normalize_local_time(raw_rule.get("start_local_time"))
            end_local_time = _normalize_local_time(raw_rule.get("end_local_time"))
        except ValueError:
            return _error(
                "invalid_arguments",
                "Availability rules must use a valid weekday index and local start/end times.",
            )
        if end_local_time <= start_local_time:
            return _error(
                "invalid_arguments",
                "Availability rule end times must be later than start times.",
            )
        rule_timezone = raw_rule.get("timezone")
        normalized_timezone = (
            rule_timezone.strip()
            if isinstance(rule_timezone, str) and rule_timezone.strip()
            else effective_timezone
        )
        if not normalized_timezone:
            return _error(
                "invalid_arguments",
                "Availability updates need a timezone so local hours can be saved correctly.",
            )
        normalized_rules.append(
            {
                "day_of_week": day_of_week,
                "start_local_time": start_local_time,
                "end_local_time": end_local_time,
                "timezone": normalized_timezone,
                "availability_type": "available",
                "priority": 0,
                "availability_metadata": {"source": "copilot"},
            }
        )
    return _ok(
        {
            "timezone": effective_timezone or (normalized_rules[0]["timezone"] if normalized_rules else default_timezone or "UTC"),
            "clear_requested": False,
            "rules": normalized_rules,
        }
    )


def validate_and_normalize_tool_call(
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    location_id: UUID | None,
    tool_name: str,
    tool_arguments: dict[str, Any] | None = None,
    default_timezone: str | None = None,
) -> ValidatedToolCall:
    tool_definition = get_tool(tool_name)

    if not has_business_access(auth_ctx, business_id, allowed_roles=READ_ROLES):
        return _error(
            code="business_access_denied",
            message="You do not have access to this business context.",
        )

    if location_id is not None and not has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=READ_ROLES,
    ):
        return _error(
            code="location_access_denied",
            message="You do not have access to this location context.",
        )

    if tool_name == "coverage.start_campaign":
        return _error(
            code="tool_not_available",
            message="Campaign-starting tools are not available in this Copilot scaffold yet.",
        )
    if tool_definition is None:
        return _error(
            code="tool_not_available",
            message="That Copilot tool is not available in this scaffold.",
        )
    if tool_definition.availability != "available":
        return _error(
            code="tool_not_available",
            message=f"{tool_definition.title} is planned but not enabled in this Copilot scaffold yet.",
        )
    if tool_name == "roster.update_availability":
        return _normalize_availability_arguments(
            tool_arguments=tool_arguments,
            default_timezone=default_timezone,
        )
    return _ok()


def validate_tool_call(
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    location_id: UUID | None,
    tool_name: str,
    tool_arguments: dict[str, Any] | None = None,
    default_timezone: str | None = None,
) -> CopilotValidationResultRead:
    return validate_and_normalize_tool_call(
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=location_id,
        tool_name=tool_name,
        tool_arguments=tool_arguments,
        default_timezone=default_timezone,
    ).validation_result
