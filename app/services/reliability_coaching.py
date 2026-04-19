from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.business import Business
from app.models.common import (
    OutboxChannel,
    OutboxStatus,
    ReliabilityCoachingAttemptStatus,
    ReliabilityCoachingCaseStatus,
    ReliabilityCoachingDeliveryStatus,
)
from app.models.coverage import OutboxEvent
from app.models.integrations import RetellConversation
from app.models.reliability import ReliabilityEvent
from app.models.reliability_coaching import (
    ReliabilityCoachingAttempt,
    ReliabilityCoachingCase,
    ReliabilityCoachingOutcome,
    ReliabilityCoachingTrigger,
)
from app.models.scheduling import Shift
from app.models.workforce import Employee
from app.schemas.reliability_coaching import (
    ReliabilityCoachingAttemptRead,
    ReliabilityCoachingCaseDetailRead,
    ReliabilityCoachingCaseRead,
    ReliabilityCoachingOutcomeRead,
)
from app.services import llm_gateway, reliability_engine

RELIABILITY_COACHING_OUTBOX_TOPIC = "reliability.coaching.attempt.created"
RELIABILITY_COACHING_POLICY_VERSION = "v1"
RELIABILITY_COACHING_SCRIPT_TOOL = "render_reliability_coaching_script"
RELIABILITY_COACHING_ALLOWED_STYLES = {"supportive", "direct", "firm"}
RELIABILITY_COACHING_ACTIVE_CASE_STATUSES = {
    ReliabilityCoachingCaseStatus.open,
    ReliabilityCoachingCaseStatus.suppressed,
    ReliabilityCoachingCaseStatus.escalated,
}
RELIABILITY_COACHING_VOICE_BEHAVIORAL_SOURCES = {"retell_voice", "sms_automation"}


@dataclass(frozen=True)
class ReliabilityCoachingPolicy:
    style: str
    threshold_count: int
    window_days: int
    max_attempts: int
    no_answer_cooldown_hours: int
    quiet_hours_start_local_hour: int
    quiet_hours_end_local_hour: int
    policy_version: str = RELIABILITY_COACHING_POLICY_VERSION


def _normalized_style(style: str | None) -> str:
    normalized = str(style or "").strip().lower()
    if normalized in RELIABILITY_COACHING_ALLOWED_STYLES:
        return normalized
    return "supportive"


def coaching_policy_for_business(business: Business | None) -> ReliabilityCoachingPolicy:
    settings_payload = business.settings if business is not None and isinstance(business.settings, dict) else {}
    coaching_settings = (
        dict(settings_payload.get("reliability_coaching"))
        if isinstance(settings_payload.get("reliability_coaching"), dict)
        else {}
    )
    return ReliabilityCoachingPolicy(
        style=_normalized_style(coaching_settings.get("style")),
        threshold_count=max(1, settings.reliability_coaching_callout_threshold_count),
        window_days=max(1, settings.reliability_coaching_window_days),
        max_attempts=max(1, settings.reliability_coaching_max_attempts),
        no_answer_cooldown_hours=max(1, settings.reliability_coaching_no_answer_cooldown_hours),
        quiet_hours_start_local_hour=max(0, min(23, settings.reliability_coaching_quiet_hours_start_local_hour)),
        quiet_hours_end_local_hour=max(0, min(23, settings.reliability_coaching_quiet_hours_end_local_hour)),
    )


def employee_has_reliability_coaching_opt_out(employee: Employee | None) -> bool:
    metadata = employee.employee_metadata if employee is not None and isinstance(employee.employee_metadata, dict) else {}
    coaching = metadata.get("reliability_coaching")
    if not isinstance(coaching, dict):
        return False
    return bool(coaching.get("opted_out"))


def _set_employee_reliability_coaching_opt_out(
    employee: Employee,
    *,
    opted_out: bool,
    occurred_at: datetime,
    reason: str,
) -> None:
    metadata = dict(employee.employee_metadata or {})
    coaching = dict(metadata.get("reliability_coaching") or {})
    coaching["opted_out"] = opted_out
    coaching["opted_out_at"] = occurred_at.isoformat() if opted_out else None
    coaching["opt_out_reason"] = reason if opted_out else None
    metadata["reliability_coaching"] = coaching
    employee.employee_metadata = metadata


def _normalize_timezone_name(value: str | None) -> str:
    candidate = str(value or "").strip()
    return candidate or "UTC"


def _zoneinfo(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(_normalize_timezone_name(timezone_name))
    except Exception:
        return ZoneInfo("UTC")


def employee_timezone_name(
    *,
    employee: Employee | None = None,
    shift: Shift | None = None,
    business: Business | None = None,
) -> str:
    employee_metadata = employee.employee_metadata if employee is not None and isinstance(employee.employee_metadata, dict) else {}
    employee_timezone = employee_metadata.get("timezone")
    if isinstance(employee_timezone, str) and employee_timezone.strip():
        return employee_timezone.strip()
    if shift is not None and str(getattr(shift, "timezone", "") or "").strip():
        return str(shift.timezone).strip()
    if business is not None and str(getattr(business, "timezone", "") or "").strip():
        return str(business.timezone).strip()
    return "UTC"


def coaching_window_bounds(
    *,
    occurred_at: datetime,
    timezone_name: str,
    window_days: int,
) -> tuple[datetime, datetime]:
    zone = _zoneinfo(timezone_name)
    local_occurred = occurred_at.astimezone(zone)
    local_start = local_occurred - timedelta(days=max(1, window_days))
    return local_start.astimezone(timezone.utc), occurred_at


def next_delivery_available_at(
    *,
    now: datetime,
    timezone_name: str,
    policy: ReliabilityCoachingPolicy,
    earliest_allowed_at: datetime | None = None,
) -> tuple[datetime, bool]:
    zone = _zoneinfo(timezone_name)
    local_now = now.astimezone(zone)
    quiet_start = time(policy.quiet_hours_start_local_hour, 0)
    quiet_end = time(policy.quiet_hours_end_local_hour, 0)
    blocked = False

    if local_now.time() >= quiet_start or local_now.time() < quiet_end:
        blocked = True
        if local_now.time() >= quiet_start:
            next_local = datetime.combine(local_now.date() + timedelta(days=1), quiet_end, tzinfo=zone)
        else:
            next_local = datetime.combine(local_now.date(), quiet_end, tzinfo=zone)
        candidate = next_local.astimezone(timezone.utc)
    else:
        candidate = now

    if earliest_allowed_at is not None and earliest_allowed_at > candidate:
        blocked = True
        candidate = earliest_allowed_at
    return candidate, blocked


def _callout_event_key(
    *,
    shift_id: UUID,
    employee_id: UUID,
    source: str,
    reason_code: str,
) -> str:
    return f"{shift_id}:{employee_id}:{reason_code}:{source}"


async def _find_existing_callout_event(
    session: AsyncSession,
    *,
    business_id: UUID,
    employee_id: UUID,
    callout_key: str,
) -> ReliabilityEvent | None:
    result = await session.execute(
        select(ReliabilityEvent).where(
            ReliabilityEvent.business_id == business_id,
            ReliabilityEvent.employee_id == employee_id,
            ReliabilityEvent.event_type == "callout_submitted",
            ReliabilityEvent.event_payload["callout_key"].astext == callout_key,
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _count_qualifying_callouts(
    session: AsyncSession,
    *,
    business_id: UUID,
    employee_id: UUID,
    window_start: datetime,
    window_end: datetime,
) -> int:
    result = await session.execute(
        select(func.count(ReliabilityEvent.id)).where(
            ReliabilityEvent.business_id == business_id,
            ReliabilityEvent.employee_id == employee_id,
            ReliabilityEvent.event_type == "callout_submitted",
            ReliabilityEvent.occurred_at >= window_start,
            ReliabilityEvent.occurred_at <= window_end,
            ReliabilityEvent.event_payload["behavioral"].astext == "true",
        )
    )
    return int(result.scalar_one() or 0)


async def _load_active_case_for_update(
    session: AsyncSession,
    *,
    business_id: UUID,
    employee_id: UUID,
    now: datetime | None = None,
) -> ReliabilityCoachingCase | None:
    reference_time = now or datetime.now(timezone.utc)
    result = await session.execute(
        select(ReliabilityCoachingCase)
        .where(
            ReliabilityCoachingCase.business_id == business_id,
            ReliabilityCoachingCase.employee_id == employee_id,
            ReliabilityCoachingCase.case_status.in_(list(RELIABILITY_COACHING_ACTIVE_CASE_STATUSES)),
        )
        .order_by(ReliabilityCoachingCase.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    coaching_case = result.scalar_one_or_none()
    if (
        coaching_case is not None
        and coaching_case.case_status == ReliabilityCoachingCaseStatus.suppressed
        and coaching_case.suppression_expires_at is not None
        and coaching_case.suppression_expires_at <= reference_time
    ):
        coaching_case.case_status = ReliabilityCoachingCaseStatus.open
        coaching_case.suppressed_at = None
        coaching_case.suppressed_by_user_id = None
        coaching_case.suppression_reason_code = None
        coaching_case.suppression_note = None
        coaching_case.suppression_expires_at = None
    return coaching_case


async def _load_attempt_count(
    session: AsyncSession,
    *,
    coaching_case_id: UUID,
) -> int:
    result = await session.execute(
        select(func.count(ReliabilityCoachingAttempt.id)).where(
            ReliabilityCoachingAttempt.coaching_case_id == coaching_case_id
        )
    )
    return int(result.scalar_one() or 0)


async def _has_active_delivery(
    session: AsyncSession,
    *,
    coaching_case_id: UUID,
) -> bool:
    result = await session.execute(
        select(ReliabilityCoachingAttempt.id)
        .where(
            ReliabilityCoachingAttempt.coaching_case_id == coaching_case_id,
            ReliabilityCoachingAttempt.status.in_(
                [
                    ReliabilityCoachingAttemptStatus.queued,
                    ReliabilityCoachingAttemptStatus.in_flight,
                ]
            ),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _cancel_pending_case_delivery(
    session: AsyncSession,
    *,
    coaching_case_id: UUID,
    now: datetime,
    reason: str,
) -> None:
    result = await session.execute(
        select(ReliabilityCoachingAttempt).where(
            ReliabilityCoachingAttempt.coaching_case_id == coaching_case_id,
            ReliabilityCoachingAttempt.status == ReliabilityCoachingAttemptStatus.queued,
        )
    )
    queued_attempts = list(result.scalars().all())
    for attempt in queued_attempts:
        attempt.status = ReliabilityCoachingAttemptStatus.cancelled
        attempt.completed_at = now
        attempt.attempt_metadata = {
            **(attempt.attempt_metadata or {}),
            "cancel_reason": reason,
        }
        if attempt.outbox_event_id is None:
            continue
        outbox_event = await session.get(OutboxEvent, attempt.outbox_event_id)
        if outbox_event is None:
            continue
        if outbox_event.status in {OutboxStatus.pending, OutboxStatus.failed, OutboxStatus.processing}:
            outbox_event.status = OutboxStatus.cancelled
            outbox_event.processed_at = now
            outbox_event.locked_at = None
            outbox_event.error_message = reason
            outbox_event.result_payload = {
                **(outbox_event.result_payload or {}),
                "cancel_reason": reason,
            }


async def _build_script_payload(
    session: AsyncSession,
    *,
    business: Business,
    employee: Employee,
    shift: Shift | None,
    policy: ReliabilityCoachingPolicy,
    qualifying_callout_count: int,
) -> dict[str, Any]:
    employee_first_name = str(employee.preferred_name or employee.full_name or "").strip().split(" ")[0] or "there"
    role_name = (
        str(getattr(getattr(shift, "role", None), "name", "") or "").strip()
        if shift is not None
        else str(employee.primary_role_name or "").strip()
    )
    location_name = (
        str(getattr(getattr(shift, "location", None), "display_name", "") or "").strip()
        if shift is not None
        else str(employee.primary_location_name or "").strip()
    )
    fallback = _fallback_script_payload(
        employee_first_name=employee_first_name,
        style=policy.style,
        qualifying_callout_count=qualifying_callout_count,
        role_name=role_name,
        location_name=location_name,
    )
    if not settings.reliability_coaching_model or not llm_gateway.provider_is_configured(llm_gateway.LlmProvider.OPENAI):
        return fallback

    tool = llm_gateway.LlmToolDefinition(
        name=RELIABILITY_COACHING_SCRIPT_TOOL,
        description="Render a bounded reliability coaching script for a voice agent.",
        input_schema={
            "type": "object",
            "properties": {
                "coaching_summary": {"type": "string"},
                "opening_line": {"type": "string"},
                "support_line": {"type": "string"},
                "closing_line": {"type": "string"},
            },
            "required": ["coaching_summary", "opening_line", "support_line", "closing_line"],
        },
    )
    prompt_payload = {
        "employee_first_name": employee_first_name,
        "style": policy.style,
        "qualifying_callout_count": qualifying_callout_count,
        "window_days": policy.window_days,
        "role_name": role_name,
        "location_name": location_name,
        "instructions": [
            "Be supportive and non-punitive.",
            "Do not threaten discipline, payroll impact, or job status.",
            "Do not ask for medical details.",
            "The goal is to coach attendance reliability and offer manager/availability follow-up help.",
        ],
    }
    try:
        result = await llm_gateway.generate(
            session,
            request=llm_gateway.LlmGenerationRequest(
                purpose="reliability_coaching_script",
                business_id=business.id,
                provider=llm_gateway.LlmProvider.OPENAI,
                model=settings.reliability_coaching_model,
                prompt_version=settings.reliability_coaching_prompt_version,
                messages=[
                    llm_gateway.LlmMessage(
                        role="system",
                        content=(
                            "You generate bounded employee reliability coaching copy for a voice assistant. "
                            "Use the tool exactly once."
                        ),
                    ),
                    llm_gateway.LlmMessage(
                        role="user",
                        content=json.dumps(prompt_payload, ensure_ascii=True),
                    ),
                ],
                tools=[tool],
                tool_choice=RELIABILITY_COACHING_SCRIPT_TOOL,
                temperature=0.2,
                max_output_tokens=600,
                metadata={
                    "feature": "reliability_coaching_script",
                    "business_id": str(business.id),
                    "employee_id": str(employee.id),
                },
            ),
        )
        tool_call = next(
            (call for call in result.tool_calls if call.name == RELIABILITY_COACHING_SCRIPT_TOOL),
            None,
        )
        if tool_call is None:
            return fallback
        arguments = dict(tool_call.arguments or {})
        if not all(str(arguments.get(key) or "").strip() for key in ("coaching_summary", "opening_line", "support_line", "closing_line")):
            return fallback
        return {
            "employee_first_name": employee_first_name,
            "style": policy.style,
            "qualifying_callout_count": qualifying_callout_count,
            "window_days": policy.window_days,
            "role_name": role_name,
            "location_name": location_name,
            "coaching_summary": str(arguments["coaching_summary"]).strip(),
            "opening_line": str(arguments["opening_line"]).strip(),
            "support_line": str(arguments["support_line"]).strip(),
            "closing_line": str(arguments["closing_line"]).strip(),
            "script_source": "llm",
        }
    except Exception:
        return fallback


def _fallback_script_payload(
    *,
    employee_first_name: str,
    style: str,
    qualifying_callout_count: int,
    role_name: str,
    location_name: str,
) -> dict[str, Any]:
    if style == "firm":
        summary = (
            f"{employee_first_name}, Backfill noticed {qualifying_callout_count} callouts in the last week. "
            "This pattern is making schedule coverage harder, and we want to help stabilize it."
        )
    elif style == "direct":
        summary = (
            f"{employee_first_name}, Backfill noticed {qualifying_callout_count} callouts in the last week. "
            "We want to address the pattern early and help reduce future disruptions."
        )
    else:
        summary = (
            f"{employee_first_name}, Backfill noticed {qualifying_callout_count} callouts in the last week. "
            "We want to help you keep your schedule more stable."
        )
    support_line = "If your availability has changed or you need manager follow-up, tell me and Backfill will record it."
    context = " ".join(part for part in [role_name, location_name] if part).strip()
    return {
        "employee_first_name": employee_first_name,
        "style": style,
        "qualifying_callout_count": qualifying_callout_count,
        "window_days": 7,
        "role_name": role_name,
        "location_name": location_name,
        "coaching_summary": summary,
        "opening_line": summary,
        "support_line": support_line,
        "closing_line": f"This is a quick coaching check-in for your {context or 'schedule'} reliability, not a disciplinary action.",
        "script_source": "fallback",
    }


async def _create_attempt_and_outbox(
    session: AsyncSession,
    *,
    coaching_case: ReliabilityCoachingCase,
    business: Business,
    employee: Employee,
    shift: Shift | None,
    qualifying_callout_count: int,
    policy: ReliabilityCoachingPolicy,
    now: datetime,
    earliest_allowed_at: datetime | None = None,
) -> ReliabilityCoachingAttempt | None:
    if employee_has_reliability_coaching_opt_out(employee):
        coaching_case.delivery_status = ReliabilityCoachingDeliveryStatus.exhausted
        coaching_case.case_status = ReliabilityCoachingCaseStatus.closed
        coaching_case.closed_at = now
        return None
    if not employee.phone_e164:
        coaching_case.delivery_status = ReliabilityCoachingDeliveryStatus.exhausted
        coaching_case.case_status = ReliabilityCoachingCaseStatus.closed
        coaching_case.closed_at = now
        return None
    if await _has_active_delivery(session, coaching_case_id=coaching_case.id):
        return None

    existing_attempt_count = await _load_attempt_count(session, coaching_case_id=coaching_case.id)
    attempt_no = existing_attempt_count + 1
    if attempt_no > policy.max_attempts:
        coaching_case.delivery_status = ReliabilityCoachingDeliveryStatus.exhausted
        coaching_case.case_status = ReliabilityCoachingCaseStatus.closed
        coaching_case.closed_at = now
        return None

    timezone_name = employee_timezone_name(employee=employee, shift=shift, business=business)
    available_at, blocked = next_delivery_available_at(
        now=now,
        timezone_name=timezone_name,
        policy=policy,
        earliest_allowed_at=earliest_allowed_at,
    )
    prompt_payload = await _build_script_payload(
        session,
        business=business,
        employee=employee,
        shift=shift,
        policy=policy,
        qualifying_callout_count=qualifying_callout_count,
    )
    attempt = ReliabilityCoachingAttempt(
        coaching_case_id=coaching_case.id,
        channel=OutboxChannel.voice,
        status=ReliabilityCoachingAttemptStatus.queued,
        attempt_no=attempt_no,
        queued_at=now,
        next_eligible_at=available_at if blocked else None,
        prompt_payload=prompt_payload,
        attempt_metadata={
            "timezone": timezone_name,
            "available_at": available_at.isoformat(),
            "qualifying_callout_count": qualifying_callout_count,
        },
    )
    session.add(attempt)
    await session.flush()
    outbox_event = OutboxEvent(
        aggregate_type="reliability_coaching_attempt",
        aggregate_id=attempt.id,
        topic=RELIABILITY_COACHING_OUTBOX_TOPIC,
        channel=OutboxChannel.voice,
        status=OutboxStatus.pending,
        available_at=available_at,
        payload={
            "coaching_case_id": str(coaching_case.id),
            "coaching_attempt_id": str(attempt.id),
            "business_id": str(coaching_case.business_id),
            "employee_id": str(coaching_case.employee_id),
            "phone_e164": employee.phone_e164,
            "prompt_payload": prompt_payload,
            "policy_version": policy.policy_version,
            "prompt_version": coaching_case.prompt_version,
        },
    )
    session.add(outbox_event)
    await session.flush()
    attempt.outbox_event_id = outbox_event.id
    coaching_case.delivery_status = (
        ReliabilityCoachingDeliveryStatus.cooldown_blocked
        if blocked
        else ReliabilityCoachingDeliveryStatus.queued
    )
    coaching_case.case_metadata = {
        **(coaching_case.case_metadata or {}),
        "next_delivery_at": available_at.isoformat(),
        "latest_attempt_id": str(attempt.id),
    }
    return attempt


async def record_behavioral_callout_and_maybe_trigger_coaching(
    session: AsyncSession,
    *,
    business: Business,
    employee: Employee,
    shift: Shift,
    source: str,
    reason_code: str,
    occurred_at: datetime | None = None,
    event_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reference_time = occurred_at or datetime.now(timezone.utc)
    normalized_source = str(source or "").strip() or "retell_voice"
    if normalized_source not in RELIABILITY_COACHING_VOICE_BEHAVIORAL_SOURCES:
        return {"status": "ignored_non_behavioral_source"}

    callout_key = _callout_event_key(
        shift_id=shift.id,
        employee_id=employee.id,
        source=normalized_source,
        reason_code=reason_code,
    )
    event = await _find_existing_callout_event(
        session,
        business_id=business.id,
        employee_id=employee.id,
        callout_key=callout_key,
    )
    if event is None:
        event = await reliability_engine.record_reliability_event(
            session,
            business_id=business.id,
            employee_id=employee.id,
            shift_id=shift.id,
            location_id=shift.location_id,
            role_id=shift.role_id,
            event_type="callout_submitted",
            occurred_at=reference_time,
            source=normalized_source,
            event_payload={
                "behavioral": True,
                "reason_code": reason_code,
                "callout_key": callout_key,
                **dict(event_payload or {}),
            },
        )
    await reliability_engine.refresh_employee_reliability_snapshot(
        session,
        employee.id,
        snapshot_at=reference_time,
    )

    if not settings.reliability_coaching_global_enabled:
        return {"status": "global_pause", "reliability_event_id": str(event.id)}
    if employee_has_reliability_coaching_opt_out(employee):
        return {"status": "employee_opted_out", "reliability_event_id": str(event.id)}

    policy = coaching_policy_for_business(business)
    timezone_name = employee_timezone_name(employee=employee, shift=shift, business=business)
    window_start, window_end = coaching_window_bounds(
        occurred_at=reference_time,
        timezone_name=timezone_name,
        window_days=policy.window_days,
    )
    qualifying_callout_count = await _count_qualifying_callouts(
        session,
        business_id=business.id,
        employee_id=employee.id,
        window_start=window_start,
        window_end=window_end,
    )
    active_case = await _load_active_case_for_update(
        session,
        business_id=business.id,
        employee_id=employee.id,
        now=reference_time,
    )
    if active_case is None and qualifying_callout_count < policy.threshold_count:
        return {
            "status": "threshold_not_met",
            "reliability_event_id": str(event.id),
            "qualifying_callout_count": qualifying_callout_count,
        }

    coaching_case = active_case
    if coaching_case is None:
        coaching_case = ReliabilityCoachingCase(
            business_id=business.id,
            employee_id=employee.id,
            case_status=ReliabilityCoachingCaseStatus.open,
            delivery_status=ReliabilityCoachingDeliveryStatus.pending,
            coaching_style=policy.style,
            policy_version=policy.policy_version,
            prompt_version=settings.reliability_coaching_prompt_version,
            trigger_metric="callout_count_rolling_7d",
            trigger_threshold=policy.threshold_count,
            trigger_window_days=policy.window_days,
            trigger_count=0,
            opened_at=reference_time,
            case_metadata={
                "latest_shift_id": str(shift.id),
                "latest_location_id": str(shift.location_id),
                "latest_role_id": str(shift.role_id),
                "latest_source": normalized_source,
            },
        )
        session.add(coaching_case)
        await session.flush()

    existing_trigger = await session.scalar(
        select(ReliabilityCoachingTrigger).where(
            ReliabilityCoachingTrigger.reliability_event_id == event.id
        )
    )
    if existing_trigger is None:
        session.add(
            ReliabilityCoachingTrigger(
                coaching_case_id=coaching_case.id,
                reliability_event_id=event.id,
                shift_id=shift.id,
                location_id=shift.location_id,
                role_id=shift.role_id,
                trigger_source=normalized_source,
                occurred_at=reference_time,
                window_start=window_start,
                window_end=window_end,
                qualifying_callout_count=qualifying_callout_count,
                trigger_payload={
                    "reason_code": reason_code,
                    "callout_key": callout_key,
                },
            )
        )
        coaching_case.trigger_count = int(coaching_case.trigger_count or 0) + 1
        coaching_case.last_triggered_at = reference_time

    coaching_case.case_metadata = {
        **(coaching_case.case_metadata or {}),
        "latest_shift_id": str(shift.id),
        "latest_location_id": str(shift.location_id),
        "latest_role_id": str(shift.role_id),
        "latest_source": normalized_source,
        "latest_qualifying_callout_count": qualifying_callout_count,
        "latest_window_start": window_start.isoformat(),
        "latest_window_end": window_end.isoformat(),
    }

    attempt = None
    if coaching_case.case_status == ReliabilityCoachingCaseStatus.open and existing_trigger is None:
        attempt = await _create_attempt_and_outbox(
            session,
            coaching_case=coaching_case,
            business=business,
            employee=employee,
            shift=shift,
            qualifying_callout_count=qualifying_callout_count,
            policy=policy,
            now=reference_time,
        )

    return {
        "status": "case_created" if active_case is None else "case_appended",
        "reliability_event_id": str(event.id),
        "coaching_case_id": str(coaching_case.id),
        "coaching_attempt_id": str(attempt.id) if attempt is not None else None,
        "qualifying_callout_count": qualifying_callout_count,
    }


def coaching_attempt_read(attempt: ReliabilityCoachingAttempt) -> ReliabilityCoachingAttemptRead:
    return ReliabilityCoachingAttemptRead(
        id=attempt.id,
        coaching_case_id=attempt.coaching_case_id,
        outbox_event_id=attempt.outbox_event_id,
        channel=attempt.channel.value if hasattr(attempt.channel, "value") else str(attempt.channel),
        status=attempt.status.value if hasattr(attempt.status, "value") else str(attempt.status),
        attempt_no=attempt.attempt_no,
        provider=attempt.provider,
        provider_conversation_id=attempt.provider_conversation_id,
        queued_at=attempt.queued_at,
        sent_at=attempt.sent_at,
        delivered_at=attempt.delivered_at,
        completed_at=attempt.completed_at,
        next_eligible_at=attempt.next_eligible_at,
        prompt_payload=attempt.prompt_payload or {},
        attempt_metadata=attempt.attempt_metadata or {},
    )


def coaching_outcome_read(outcome: ReliabilityCoachingOutcome) -> ReliabilityCoachingOutcomeRead:
    return ReliabilityCoachingOutcomeRead(
        id=outcome.id,
        coaching_case_id=outcome.coaching_case_id,
        attempt_id=outcome.attempt_id,
        outcome_code=outcome.outcome_code,
        barrier_code=outcome.barrier_code,
        availability_update_requested=bool(outcome.availability_update_requested),
        manager_followup_requested=bool(outcome.manager_followup_requested),
        coaching_acknowledged=bool(outcome.coaching_acknowledged),
        opt_out=bool(outcome.opt_out),
        recorded_at=outcome.recorded_at,
        outcome_payload=outcome.outcome_payload or {},
    )


def coaching_case_read(coaching_case: ReliabilityCoachingCase) -> ReliabilityCoachingCaseRead:
    return ReliabilityCoachingCaseRead(
        id=coaching_case.id,
        business_id=coaching_case.business_id,
        employee_id=coaching_case.employee_id,
        case_status=coaching_case.case_status.value if hasattr(coaching_case.case_status, "value") else str(coaching_case.case_status),
        delivery_status=coaching_case.delivery_status.value if hasattr(coaching_case.delivery_status, "value") else str(coaching_case.delivery_status),
        coaching_style=coaching_case.coaching_style,
        trigger_metric=coaching_case.trigger_metric,
        trigger_threshold=coaching_case.trigger_threshold,
        trigger_window_days=coaching_case.trigger_window_days,
        trigger_count=coaching_case.trigger_count,
        opened_at=coaching_case.opened_at,
        last_triggered_at=coaching_case.last_triggered_at,
        closed_at=coaching_case.closed_at,
        escalated_at=coaching_case.escalated_at,
        suppressed_at=coaching_case.suppressed_at,
        suppression_reason_code=coaching_case.suppression_reason_code,
        suppression_note=coaching_case.suppression_note,
        suppression_expires_at=coaching_case.suppression_expires_at,
        case_metadata=coaching_case.case_metadata or {},
    )


def coaching_case_detail_read(coaching_case: ReliabilityCoachingCase) -> ReliabilityCoachingCaseDetailRead:
    base = coaching_case_read(coaching_case)
    return ReliabilityCoachingCaseDetailRead(
        **base.model_dump(),
        attempts=[coaching_attempt_read(attempt) for attempt in coaching_case.attempts or []],
        outcomes=[coaching_outcome_read(outcome) for outcome in coaching_case.outcomes or []],
    )


async def list_business_coaching_cases(
    session: AsyncSession,
    *,
    business_id: UUID,
    employee_id: UUID | None = None,
    limit: int = 50,
) -> list[ReliabilityCoachingCase]:
    stmt = (
        select(ReliabilityCoachingCase)
        .options(
            selectinload(ReliabilityCoachingCase.attempts),
            selectinload(ReliabilityCoachingCase.outcomes),
        )
        .where(ReliabilityCoachingCase.business_id == business_id)
        .order_by(ReliabilityCoachingCase.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    if employee_id is not None:
        stmt = stmt.where(ReliabilityCoachingCase.employee_id == employee_id)
    result = await session.execute(stmt)
    return list(result.scalars().unique().all())


async def get_business_coaching_case(
    session: AsyncSession,
    *,
    business_id: UUID,
    coaching_case_id: UUID,
) -> ReliabilityCoachingCase | None:
    result = await session.execute(
        select(ReliabilityCoachingCase)
        .options(
            selectinload(ReliabilityCoachingCase.attempts).selectinload(ReliabilityCoachingAttempt.outcome),
            selectinload(ReliabilityCoachingCase.outcomes),
            selectinload(ReliabilityCoachingCase.employee),
        )
        .where(
            ReliabilityCoachingCase.id == coaching_case_id,
            ReliabilityCoachingCase.business_id == business_id,
        )
    )
    return result.scalars().unique().first()


async def suppress_coaching_case(
    session: AsyncSession,
    *,
    business_id: UUID,
    coaching_case_id: UUID,
    actor_user_id: UUID,
    reason_code: str,
    note: str | None,
    expires_at: datetime | None,
    now: datetime | None = None,
) -> ReliabilityCoachingCase:
    reference_time = now or datetime.now(timezone.utc)
    coaching_case = await get_business_coaching_case(
        session,
        business_id=business_id,
        coaching_case_id=coaching_case_id,
    )
    if coaching_case is None:
        raise LookupError("reliability_coaching_case_not_found")
    await _cancel_pending_case_delivery(
        session,
        coaching_case_id=coaching_case.id,
        now=reference_time,
        reason="case_suppressed",
    )
    coaching_case.case_status = ReliabilityCoachingCaseStatus.suppressed
    coaching_case.delivery_status = ReliabilityCoachingDeliveryStatus.exhausted
    coaching_case.suppressed_at = reference_time
    coaching_case.suppressed_by_user_id = actor_user_id
    coaching_case.suppression_reason_code = reason_code
    coaching_case.suppression_note = note
    coaching_case.suppression_expires_at = expires_at
    coaching_case.case_metadata = {
        **(coaching_case.case_metadata or {}),
        "suppressed_reason_code": reason_code,
        "suppressed_note": note,
    }
    return coaching_case


async def close_coaching_case(
    session: AsyncSession,
    *,
    business_id: UUID,
    coaching_case_id: UUID,
    reason_code: str,
    note: str | None,
    now: datetime | None = None,
) -> ReliabilityCoachingCase:
    reference_time = now or datetime.now(timezone.utc)
    coaching_case = await get_business_coaching_case(
        session,
        business_id=business_id,
        coaching_case_id=coaching_case_id,
    )
    if coaching_case is None:
        raise LookupError("reliability_coaching_case_not_found")
    await _cancel_pending_case_delivery(
        session,
        coaching_case_id=coaching_case.id,
        now=reference_time,
        reason="case_closed",
    )
    coaching_case.case_status = ReliabilityCoachingCaseStatus.closed
    coaching_case.delivery_status = ReliabilityCoachingDeliveryStatus.exhausted
    coaching_case.closed_at = reference_time
    coaching_case.case_metadata = {
        **(coaching_case.case_metadata or {}),
        "closed_reason_code": reason_code,
        "closed_note": note,
    }
    return coaching_case


async def load_coaching_attempt_for_outbox(
    session: AsyncSession,
    *,
    attempt_id: UUID,
) -> ReliabilityCoachingAttempt | None:
    result = await session.execute(
        select(ReliabilityCoachingAttempt)
        .options(
            selectinload(ReliabilityCoachingAttempt.coaching_case).selectinload(ReliabilityCoachingCase.employee),
        )
        .where(ReliabilityCoachingAttempt.id == attempt_id)
    )
    return result.scalars().unique().first()


def build_retell_coaching_metadata(
    *,
    coaching_case: ReliabilityCoachingCase,
    attempt: ReliabilityCoachingAttempt,
    employee: Employee,
) -> dict[str, Any]:
    return {
        "business_id": str(coaching_case.business_id),
        "employee_id": str(coaching_case.employee_id),
        "reliability_coaching_case_id": str(coaching_case.id),
        "reliability_coaching_attempt_id": str(attempt.id),
        "reliability_coaching_policy_version": coaching_case.policy_version,
        "reliability_coaching_prompt_version": coaching_case.prompt_version,
        "backfill_linkage": {
            "reliability_coaching_case_id": str(coaching_case.id),
            "reliability_coaching_attempt_id": str(attempt.id),
            "employee_id": str(employee.id),
            "contract_version": "backfill_reliability_coaching_callback_v1",
        },
    }


def build_retell_coaching_dynamic_variables(
    *,
    coaching_case: ReliabilityCoachingCase,
    attempt: ReliabilityCoachingAttempt,
    employee: Employee,
) -> dict[str, Any]:
    prompt_payload = dict(attempt.prompt_payload or {})
    return {
        "employee_first_name": prompt_payload.get("employee_first_name") or str(employee.preferred_name or employee.full_name or "").strip().split(" ")[0],
        "coaching_style": coaching_case.coaching_style,
        "recent_callout_count": str(prompt_payload.get("qualifying_callout_count") or coaching_case.case_metadata.get("latest_qualifying_callout_count") or coaching_case.trigger_count),
        "window_days": str(prompt_payload.get("window_days") or coaching_case.trigger_window_days),
        "coaching_summary": prompt_payload.get("coaching_summary") or "",
        "opening_line": prompt_payload.get("opening_line") or "",
        "support_line": prompt_payload.get("support_line") or "",
        "closing_line": prompt_payload.get("closing_line") or "",
        "role_name": prompt_payload.get("role_name") or "",
        "location_name": prompt_payload.get("location_name") or "",
    }


def conversation_is_reliability_coaching(conversation: RetellConversation | None) -> bool:
    if conversation is None:
        return False
    metadata = conversation.metadata_json if isinstance(conversation.metadata_json, dict) else {}
    return any(
        value not in (None, "")
        for value in (
            metadata.get("reliability_coaching_case_id"),
            metadata.get("reliability_coaching_attempt_id"),
            (metadata.get("backfill_linkage") or {}).get("reliability_coaching_case_id")
            if isinstance(metadata.get("backfill_linkage"), dict)
            else None,
        )
    )


def _normalized_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _metadata_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def coaching_outcome_signal(conversation: RetellConversation) -> dict[str, Any]:
    payload = conversation.raw_payload if isinstance(conversation.raw_payload, dict) else {}
    analysis = conversation.analysis if isinstance(conversation.analysis, dict) else {}
    custom = payload.get("custom_analysis_data")
    custom_mapping = custom if isinstance(custom, dict) else {}
    transcript_text = str(conversation.transcript_text or "").strip().lower()
    disconnection_reason = str(conversation.disconnection_reason or "").strip().lower()

    outcome_code = (
        _metadata_value(custom_mapping, "coaching_result", "Coaching Result", "Outcome Code")
        or _metadata_value(analysis, "coaching_result")
    )
    barrier_code = _metadata_value(custom_mapping, "barrier_code", "Barrier Code")
    availability_update_requested = _normalized_bool(
        _metadata_value(custom_mapping, "availability_update_requested", "Availability Update Requested")
    )
    manager_followup_requested = _normalized_bool(
        _metadata_value(custom_mapping, "manager_followup_requested", "Manager Followup Requested", "Manager Follow-up Requested")
    )
    coaching_acknowledged = _normalized_bool(
        _metadata_value(custom_mapping, "coaching_acknowledged", "Coaching Acknowledged")
    )
    opt_out = _normalized_bool(_metadata_value(custom_mapping, "opt_out", "Opt Out"))

    if outcome_code is None:
        if any(token in disconnection_reason for token in ("voicemail", "no_answer", "unanswered")):
            outcome_code = "no_answer"
        elif "stop calling" in transcript_text or "stop texting" in transcript_text or "opt out" in transcript_text:
            outcome_code = "opt_out"
        elif "manager" in transcript_text or "supervisor" in transcript_text:
            outcome_code = "manager_followup_requested"
        elif "availability" in transcript_text or "schedule changed" in transcript_text:
            outcome_code = "availability_update_requested"
        else:
            outcome_code = "acknowledged"

    normalized_outcome_code = str(outcome_code).strip().lower().replace(" ", "_")
    return {
        "outcome_code": normalized_outcome_code,
        "barrier_code": str(barrier_code).strip().lower().replace(" ", "_") if barrier_code not in (None, "") else None,
        "availability_update_requested": bool(
            availability_update_requested if availability_update_requested is not None else normalized_outcome_code == "availability_update_requested"
        ),
        "manager_followup_requested": bool(
            manager_followup_requested if manager_followup_requested is not None else normalized_outcome_code == "manager_followup_requested"
        ),
        "coaching_acknowledged": bool(
            coaching_acknowledged if coaching_acknowledged is not None else normalized_outcome_code in {"acknowledged", "availability_update_requested", "manager_followup_requested"}
        ),
        "opt_out": bool(opt_out if opt_out is not None else normalized_outcome_code == "opt_out"),
    }


async def process_coaching_conversation_completion(
    session: AsyncSession,
    conversation: RetellConversation,
) -> dict[str, Any]:
    metadata = conversation.metadata_json if isinstance(conversation.metadata_json, dict) else {}
    linkage = metadata.get("backfill_linkage") if isinstance(metadata.get("backfill_linkage"), dict) else {}
    raw_attempt_id = (
        metadata.get("reliability_coaching_attempt_id")
        or linkage.get("reliability_coaching_attempt_id")
    )
    raw_case_id = (
        metadata.get("reliability_coaching_case_id")
        or linkage.get("reliability_coaching_case_id")
    )
    attempt_id = UUID(str(raw_attempt_id)) if raw_attempt_id not in (None, "") else None
    case_id = UUID(str(raw_case_id)) if raw_case_id not in (None, "") else None
    if attempt_id is None and conversation.external_id:
        attempt = await session.scalar(
            select(ReliabilityCoachingAttempt).where(
                ReliabilityCoachingAttempt.provider_conversation_id == conversation.external_id
            )
        )
    elif attempt_id is not None:
        attempt = await session.get(ReliabilityCoachingAttempt, attempt_id)
    else:
        attempt = None
    if attempt is None:
        return {"status": "coaching_attempt_not_found"}
    coaching_case = await session.get(ReliabilityCoachingCase, attempt.coaching_case_id)
    if coaching_case is None:
        return {"status": "coaching_case_not_found"}
    if case_id is not None and case_id != coaching_case.id:
        return {"status": "coaching_case_mismatch"}
    existing_outcome = await session.scalar(
        select(ReliabilityCoachingOutcome).where(
            ReliabilityCoachingOutcome.attempt_id == attempt.id
        )
    )
    if existing_outcome is not None:
        return {
            "status": "already_processed",
            "coaching_case_id": str(coaching_case.id),
            "coaching_attempt_id": str(attempt.id),
            "outcome_code": existing_outcome.outcome_code,
        }

    signal = coaching_outcome_signal(conversation)
    now = datetime.now(timezone.utc)
    attempt.delivered_at = attempt.delivered_at or conversation.ended_at or now
    attempt.completed_at = now
    outcome_code = signal["outcome_code"]
    if outcome_code == "no_answer":
        attempt.status = ReliabilityCoachingAttemptStatus.no_answer
    else:
        attempt.status = ReliabilityCoachingAttemptStatus.completed

    outcome = ReliabilityCoachingOutcome(
        coaching_case_id=coaching_case.id,
        attempt_id=attempt.id,
        outcome_code=outcome_code,
        barrier_code=signal["barrier_code"],
        availability_update_requested=signal["availability_update_requested"],
        manager_followup_requested=signal["manager_followup_requested"],
        coaching_acknowledged=signal["coaching_acknowledged"],
        opt_out=signal["opt_out"],
        recorded_at=now,
        outcome_payload={
            "conversation_id": str(conversation.id),
            "conversation_external_id": conversation.external_id,
            "summary": conversation.conversation_summary,
        },
    )
    session.add(outcome)

    employee = await session.get(Employee, coaching_case.employee_id)
    if signal["opt_out"] and employee is not None:
        _set_employee_reliability_coaching_opt_out(
            employee,
            opted_out=True,
            occurred_at=now,
            reason="retell_coaching_opt_out",
        )

    if outcome_code == "no_answer":
        business = await session.get(Business, coaching_case.business_id)
        employee = employee or await session.get(Employee, coaching_case.employee_id)
        if business is not None and employee is not None:
            policy = coaching_policy_for_business(business)
            attempt_count = await _load_attempt_count(session, coaching_case_id=coaching_case.id)
            if attempt_count < policy.max_attempts and coaching_case.case_status == ReliabilityCoachingCaseStatus.open:
                earliest_allowed_at = now + timedelta(hours=policy.no_answer_cooldown_hours)
                latest_trigger_count = int(
                    (coaching_case.case_metadata or {}).get("latest_qualifying_callout_count")
                    or coaching_case.trigger_count
                    or policy.threshold_count
                )
                await _create_attempt_and_outbox(
                    session,
                    coaching_case=coaching_case,
                    business=business,
                    employee=employee,
                    shift=None,
                    qualifying_callout_count=latest_trigger_count,
                    policy=policy,
                    now=now,
                    earliest_allowed_at=earliest_allowed_at,
                )
            else:
                coaching_case.delivery_status = ReliabilityCoachingDeliveryStatus.exhausted
                coaching_case.case_status = ReliabilityCoachingCaseStatus.closed
                coaching_case.closed_at = now
        return {
            "status": "processed",
            "coaching_case_id": str(coaching_case.id),
            "coaching_attempt_id": str(attempt.id),
            "outcome_code": outcome_code,
        }

    coaching_case.delivery_status = ReliabilityCoachingDeliveryStatus.delivered
    if signal["manager_followup_requested"]:
        coaching_case.case_status = ReliabilityCoachingCaseStatus.escalated
        coaching_case.escalated_at = now
    else:
        coaching_case.case_status = ReliabilityCoachingCaseStatus.closed
        coaching_case.closed_at = now

    return {
        "status": "processed",
        "coaching_case_id": str(coaching_case.id),
        "coaching_attempt_id": str(attempt.id),
        "outcome_code": outcome_code,
    }
