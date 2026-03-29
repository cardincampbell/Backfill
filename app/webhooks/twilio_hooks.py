from __future__ import annotations

"""
Inbound SMS handling for worker replies.

This makes outbound SMS offers actionable:
- YES claims the shift if still open, otherwise enters standby
- NO declines the most recent offer
- CANCEL drops a worker from standby
- STOP revokes consent immediately
"""
from datetime import date, datetime, timedelta
from html import escape
import re

from fastapi import APIRouter, Depends, Form, Request, Response
import aiosqlite

from app.config import settings
from app.db.database import get_db
from app.db import queries
from app.services import backfill_shifts as backfill_shifts_svc
from app.services import cascade as cascade_svc
from app.services import consent as consent_svc
from app.services import notifications as notifications_svc
from app.services import agency_router as agency_router_svc
from app.services import outreach as outreach_svc
from app.services import rate_limit
from app.services import shift_manager

router = APIRouter(
    prefix="/webhooks/twilio",
    tags=["twilio-webhooks"],
    dependencies=[Depends(rate_limit.limit_by_request_key("twilio_webhook", limit=180, window_seconds=60))],
)
_MANAGER_SCHEDULE_COMMANDS = {
    "APPROVE",
    "PUBLISH",
    "REVIEW",
    "COPY LAST WEEK",
    "OPEN SHIFTS",
    "HOLD",
    "PAUSE",
    "HELP",
}
_WORKER_CHECK_IN_COMMANDS = {"YES", "Y", "HERE", "CHECK IN", "CHECK-IN", "ARRIVED", "ON SITE", "ONSITE"}
_WORKER_CONFIRM_COMMANDS = {"YES", "Y", "CONFIRM", "CONFIRMED", "HERE", "CHECK IN", "CHECK-IN"}
_WORKER_DECLINE_CONFIRM_COMMANDS = {"NO", "N"}
_CALL_OUT_PHRASES = (
    "CALL OUT",
    "CALLOUT",
    "CANT MAKE",
    "CAN'T MAKE",
    "CANNOT MAKE",
    "WONT MAKE",
    "WON'T MAKE",
    "NOT COMING",
    "OUT SICK",
    "SICK",
    "COVER MY SHIFT",
)
_WEEKDAY_ALIASES = {
    "MON": 0,
    "MONDAY": 0,
    "TUE": 1,
    "TUES": 1,
    "TUESDAY": 1,
    "WED": 2,
    "WEDNESDAY": 2,
    "THU": 3,
    "THUR": 3,
    "THURS": 3,
    "THURSDAY": 3,
    "FRI": 4,
    "FRIDAY": 4,
    "SAT": 5,
    "SATURDAY": 5,
    "SUN": 6,
    "SUNDAY": 6,
}


def _validate_twilio_signature(request: Request, params: dict) -> bool:
    """Return True if the X-Twilio-Signature header is valid, or if no auth token is configured."""
    try:
        from twilio.request_validator import RequestValidator

        if not settings.twilio_auth_token:
            # No credentials configured — skip validation in dev mode
            return True

        validator = RequestValidator(settings.twilio_auth_token)
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)
        return validator.validate(url, params, signature)
    except Exception:
        return False


@router.post("/sms")
async def inbound_sms(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    form = await request.form()
    form_params = {
        key: value if isinstance(value, str) else str(value)
        for key, value in form.multi_items()
    }
    if not _validate_twilio_signature(request, form_params):
        return Response(content="Forbidden", status_code=403)

    body = _normalize_body(Body)
    message_sid = str(form_params.get("MessageSid") or form_params.get("SmsMessageSid") or "").strip()
    receipt: dict | None = None
    if message_sid:
        claim = await queries.claim_webhook_receipt(
            db,
            source="twilio_sms",
            external_id=message_sid,
            request_payload=form_params,
        )
        receipt = claim.get("receipt")
        if claim.get("status") == "existing" and receipt is not None:
            if receipt.get("status") == "completed" and receipt.get("response_body"):
                return Response(
                    content=str(receipt["response_body"]),
                    status_code=int(receipt.get("response_status_code") or 200),
                    media_type="application/xml",
                )
            return _twiml("We already received your message and are processing it.")

    try:
        response = await _handle_inbound_sms_request(db, From, body)
    except Exception:
        if receipt is not None and receipt.get("id") is not None:
            await queries.delete_webhook_receipt(db, int(receipt["id"]))
        raise

    if receipt is not None and receipt.get("id") is not None:
        response_body = response.body.decode("utf-8") if isinstance(response.body, bytes) else str(response.body)
        await queries.finalize_webhook_receipt(
            db,
            int(receipt["id"]),
            response_body=response_body,
            response_status_code=int(response.status_code),
        )
    return response


async def _handle_inbound_sms_request(
    db: aiosqlite.Connection,
    phone: str,
    body: str,
) -> Response:
    if body in {"STOP", "UNSUBSCRIBE", "QUIT", "END"}:
        handled = await consent_svc.handle_stop_keyword(db, phone)
        message = (
            "You've been unsubscribed from Backfill shift texts."
            if handled else
            "You're unsubscribed from Backfill messages."
        )
        return _twiml(message)

    if body in {"JOIN", "START", "UNSTOP"}:
        enrollment_message = await _handle_worker_enrollment_keyword(db, phone)
        if enrollment_message:
            return _twiml(enrollment_message)

    manager_context = await _find_manager_context(db, phone)
    manager_pending_claim = await _find_latest_manager_pending_claim(db, phone) if manager_context else None
    if body in {"AGENCY", "STATUS"}:
        manager_cascade = await _find_latest_manager_cascade(db, phone)
        if manager_cascade:
            if body == "AGENCY":
                await queries.update_cascade(
                    db,
                    manager_cascade["cascade"]["id"],
                    manager_approved_tier3=True,
                    current_tier=3,
                    status="active",
                )
                result = await agency_router_svc.route_to_agencies(
                    db,
                    cascade_id=manager_cascade["cascade"]["id"],
                    shift_id=manager_cascade["shift"]["id"],
                )
                requests_sent = len(result.get("requests") or [])
                return _twiml(
                    f"Agency routing approved. We sent {requests_sent} partner request"
                    f"{'' if requests_sent == 1 else 's'} for this shift."
                )
            shift = manager_cascade["shift"]
            status = shift["status"].upper()
            tier = manager_cascade["cascade"]["current_tier"]
            return _twiml(
                f"Shift status: {status} for {shift['role']} on {shift['date']} at "
                f"{shift['start_time']}. Current cascade tier: {tier}."
            )
        if manager_context:
            return _twiml("No active coverage approval is waiting right now. Reply HELP for schedule commands.")

    if manager_pending_claim and body in {"YES", "NO"}:
        return _twiml(await _handle_manager_claim_command(db, manager_pending_claim, body))

    if body in _MANAGER_SCHEDULE_COMMANDS and manager_context:
        return _twiml(await _handle_manager_schedule_command(db, manager_context, body))

    callout_message = await _handle_worker_callout(db, phone, body, manager_context=manager_context)
    if callout_message:
        return _twiml(callout_message)

    attempt = await _find_latest_sms_attempt(db, phone)
    if attempt is None:
        pending_check_in = await _find_latest_pending_check_in_shift(db, phone)
        late_eta_minutes = _extract_late_eta_minutes(body)
        if pending_check_in and body in _WORKER_CHECK_IN_COMMANDS:
            result = await backfill_shifts_svc.record_worker_check_in(
                db,
                shift_id=int(pending_check_in["shift"]["id"]),
                worker_id=int(pending_check_in["worker"]["id"]),
                actor=f"worker_sms:{phone}",
            )
            if result["status"] == "checked_in":
                return _twiml("Thanks, you're checked in. Have a good shift.")
            return _twiml("That shift doesn't need a check-in anymore.")
        if pending_check_in and late_eta_minutes is not None:
            result = await backfill_shifts_svc.record_worker_late_arrival(
                db,
                shift_id=int(pending_check_in["shift"]["id"]),
                worker_id=int(pending_check_in["worker"]["id"]),
                eta_minutes=late_eta_minutes,
                actor=f"worker_sms:{phone}",
            )
            if result["status"] == "late":
                return _twiml(
                    f"Got it. We told your manager you're about {late_eta_minutes} "
                    f"{'minute' if late_eta_minutes == 1 else 'minutes'} late."
                )
            if result["status"] == "coverage_started":
                return _twiml(
                    f"Got it. We told your manager and started coverage because you're about "
                    f"{late_eta_minutes} {'minute' if late_eta_minutes == 1 else 'minutes'} late."
                )
            return _twiml("That shift doesn't need a check-in anymore.")

        pending_confirmation = await _find_latest_pending_confirmation_shift(db, phone)
        if pending_confirmation and body in _WORKER_CONFIRM_COMMANDS:
            result = await backfill_shifts_svc.confirm_worker_shift(
                db,
                shift_id=int(pending_confirmation["shift"]["id"]),
                worker_id=int(pending_confirmation["worker"]["id"]),
                actor=f"worker_sms:{phone}",
            )
            if result["status"] == "confirmed":
                await notifications_svc.queue_worker_shift_confirmed_notification(
                    db,
                    shift_id=int(pending_confirmation["shift"]["id"]),
                    worker_id=int(pending_confirmation["worker"]["id"]),
                    location_id=int(pending_confirmation["location"]["id"]),
                )
                return _twiml("Thanks, you're confirmed. We'll keep this shift on your schedule.")
            return _twiml("That shift doesn't need confirmation anymore.")
        if pending_confirmation and body in _WORKER_DECLINE_CONFIRM_COMMANDS:
            result = await backfill_shifts_svc.decline_worker_shift(
                db,
                shift_id=int(pending_confirmation["shift"]["id"]),
                worker_id=int(pending_confirmation["worker"]["id"]),
                actor=f"worker_sms:{phone}",
            )
            if result["status"] == "coverage_started":
                return _twiml("Got it. We recorded that you can't make it and started finding coverage now.")
            return _twiml("That shift doesn't need confirmation anymore.")

        if manager_context:
            return _twiml(_manager_help_text())
        return _twiml("Thanks for the message. Call 1-800-BACKFILL if you need help.")

    if body == "YES":
        vacancy_kind = _vacancy_kind_from_attempt(attempt)
        result = await cascade_svc.claim_shift(
            db,
            cascade_id=attempt["cascade_id"],
            worker_id=attempt["worker_id"],
            summary="Accepted by SMS",
        )
        if result["status"] == "confirmed":
            await notifications_svc.queue_manager_notification(
                db,
                cascade_id=int(attempt["cascade_id"]),
                worker_id=int(attempt["worker_id"]),
                filled=True,
            )
            if vacancy_kind == "open_shift":
                return _twiml("You're confirmed for the open shift. We'll text any final details shortly.")
            return _twiml("You're confirmed. We'll text any final details shortly.")
        if result["status"] == "awaiting_manager_approval":
            if vacancy_kind == "open_shift":
                return _twiml("Got it. We sent your open shift claim to the manager for approval.")
            return _twiml("Got it. We sent your claim to the manager for approval.")
        if result["status"] == "standby":
            shift_label = "That open shift" if vacancy_kind == "open_shift" else "That shift"
            return _twiml(
                f"{shift_label} just got claimed, but you're on standby as #{result['standby_position']}. "
                "Reply CANCEL anytime to drop off standby."
            )
        if result["status"] == "manager_declined":
            return _twiml("The manager already passed on your claim for that shift.")
        return _twiml("We already have your response recorded for this shift.")

    if body == "NO":
        await cascade_svc.decline_shift(
            db,
            cascade_id=attempt["cascade_id"],
            worker_id=attempt["worker_id"],
            summary="Declined by SMS",
        )
        return _twiml("No problem. Thanks for the quick reply.")

    if body == "CANCEL":
        result = await cascade_svc.cancel_standby(
            db,
            cascade_id=attempt["cascade_id"],
            worker_id=attempt["worker_id"],
            summary="Standby cancelled by SMS",
        )
        if result["status"] == "standby_cancelled":
            return _twiml("Got it. You're off standby for that shift.")
        return _twiml("You're not currently on standby for an active Backfill shift.")

    return _twiml("Reply YES to take the shift, NO to pass, CANCEL to leave standby, or STOP to opt out.")


async def _find_latest_sms_attempt(db: aiosqlite.Connection, phone: str):
    async with db.execute(
        """SELECT oa.cascade_id, oa.worker_id, oa.outcome,
                  s.id AS shift_id,
                  s.called_out_by,
                  s.confirmation_escalated_at,
                  s.check_in_escalated_at,
                  s.escalated_from_worker_id
           FROM outreach_attempts oa
           JOIN workers w ON w.id = oa.worker_id
           JOIN cascades c ON c.id = oa.cascade_id
           JOIN shifts s ON s.id = c.shift_id
           WHERE w.phone=? AND oa.channel='sms'
             AND (c.status IN ('active', 'completed') OR oa.outcome='standby')
           ORDER BY oa.id DESC
           LIMIT 1""",
        (phone,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def _find_latest_manager_cascade(db: aiosqlite.Connection, phone: str):
    async with db.execute(
        """SELECT c.id AS cascade_id, s.id AS shift_id
           FROM cascades c
           JOIN shifts s ON s.id = c.shift_id
           JOIN locations r ON r.id = s.location_id
           WHERE r.manager_phone=? AND c.status='active'
           ORDER BY c.id DESC
           LIMIT 1""",
        (phone,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    cascade = await queries.get_cascade(db, row["cascade_id"])
    shift = await queries.get_shift(db, row["shift_id"])
    if not cascade or not shift:
        return None
    return {"cascade": cascade, "shift": shift}


async def _find_latest_manager_pending_claim(db: aiosqlite.Connection, phone: str):
    async with db.execute(
        """SELECT c.id AS cascade_id, s.id AS shift_id, c.pending_claim_worker_id
           FROM cascades c
           JOIN shifts s ON s.id = c.shift_id
           JOIN locations r ON r.id = s.location_id
           WHERE r.manager_phone=? AND c.status='active' AND c.pending_claim_worker_id IS NOT NULL
           ORDER BY c.pending_claim_at DESC, c.id DESC
           LIMIT 1""",
        (phone,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    cascade = await queries.get_cascade(db, row["cascade_id"])
    shift = await queries.get_shift(db, row["shift_id"])
    worker = await queries.get_worker(db, int(row["pending_claim_worker_id"]))
    if not cascade or not shift or not worker:
        return None
    location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
    if not location:
        return None
    return {
        "cascade": cascade,
        "shift": shift,
        "worker": worker,
        "location": location,
    }


def _normalize_body(body: str) -> str:
    return " ".join((body or "").strip().upper().split())


def _manager_help_text() -> str:
    return (
        "Reply APPROVE or PUBLISH to publish the latest draft, REVIEW for the dashboard link, "
        "COPY LAST WEEK to clone the latest schedule, OPEN SHIFTS to start offering unassigned shifts, "
        "HOLD to leave it unchanged, "
        "STATUS for live coverage, YES/NO to approve a pending claim, or AGENCY to approve partner outreach."
    )


def _vacancy_kind_from_attempt(attempt: dict) -> str:
    return outreach_svc.vacancy_kind(attempt)


async def _handle_manager_claim_command(
    db: aiosqlite.Connection,
    pending_claim: dict,
    command: str,
) -> str:
    cascade = pending_claim["cascade"]
    shift = pending_claim["shift"]
    worker = pending_claim["worker"]
    vacancy_kind = outreach_svc.vacancy_kind(shift)
    shift_phrase = (
        f"the open {shift['role']} shift on {shift['date']} at {shift['start_time']}"
        if vacancy_kind == "open_shift"
        else f"the {shift['role']} shift on {shift['date']} at {shift['start_time']}"
    )

    if command == "YES":
        result = await cascade_svc.approve_pending_claim(
            db,
            int(cascade["id"]),
            summary=f"Approved by manager via SMS from {pending_claim['location'].get('manager_phone')}",
        )
        if result["status"] == "confirmed":
            return f"Approved. {worker['name']} is confirmed for {shift_phrase}."
        if result["status"] == "awaiting_manager_approval":
            return "That claim is still pending. Reply YES again in a moment if you want to approve it."
        return "That claim is no longer pending. Reply STATUS for the latest coverage state."

    result = await cascade_svc.decline_pending_claim(
        db,
        int(cascade["id"]),
        summary=f"Declined by manager via SMS from {pending_claim['location'].get('manager_phone')}",
    )
    if result["status"] == "declined_by_manager":
        next_result = result.get("next_result") or {}
        if next_result.get("status") == "awaiting_manager_approval":
            return (
                f"Passed on {worker['name']}. "
                "Another worker is now waiting for approval. Reply YES to approve or NO to keep looking."
            )
        return f"Passed on {worker['name']}. We kept coverage running."
    if result["status"] == "confirmed":
        return "That shift is already covered."
    return "That claim is no longer pending. Reply STATUS for the latest coverage state."


def _normalize_match_text(body: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9:/ ]+", " ", body.upper())
    return " ".join(cleaned.split())


def _looks_like_worker_callout(body: str) -> bool:
    normalized = _normalize_match_text(body)
    if any(phrase in normalized for phrase in _CALL_OUT_PHRASES):
        return True
    if "OUT" in normalized and any(token in normalized for token in {"TODAY", "TONIGHT", "TOMORROW"}):
        return True
    return False


def _extract_callout_date(body: str, *, reference_date: date) -> date | None:
    normalized = _normalize_match_text(body)
    if any(token in normalized for token in {"TODAY", "TONIGHT", "THIS MORNING", "THIS AFTERNOON", "THIS EVENING"}):
        return reference_date
    if "TOMORROW" in normalized:
        return reference_date + timedelta(days=1)

    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", normalized)
    if iso_match:
        return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))

    slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", normalized)
    if slash_match:
        month = int(slash_match.group(1))
        day = int(slash_match.group(2))
        year_token = slash_match.group(3)
        if year_token:
            year = int(year_token)
            if year < 100:
                year += 2000
        else:
            year = reference_date.year
            if (month, day) < (reference_date.month, reference_date.day):
                year += 1
        try:
            return date(year, month, day)
        except ValueError:
            return None

    for label, weekday in _WEEKDAY_ALIASES.items():
        if re.search(rf"\b{label}\b", normalized):
            delta = (weekday - reference_date.weekday()) % 7
            return reference_date + timedelta(days=delta)
    return None


def _extract_callout_minutes(body: str) -> int | None:
    normalized = _normalize_match_text(body)
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?\b", normalized)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    if meridiem:
        if hour == 12:
            hour = 0
        if meridiem == "PM":
            hour += 12
    elif hour > 23:
        return None
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _extract_late_eta_minutes(body: str) -> int | None:
    normalized = _normalize_match_text(body)
    if "LATE" not in normalized and "ETA" not in normalized and "BE THERE IN" not in normalized:
        return None
    match = re.search(r"\b(\d{1,3})\b", normalized)
    if match:
        return max(1, min(int(match.group(1)), 240))
    if "LATE" in normalized:
        return 15
    return None


def _format_shift_clock(value: str) -> str:
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return value


def _shift_start_minutes(shift: dict) -> int | None:
    raw = str(shift.get("start_time") or "")
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.hour * 60 + parsed.minute
        except ValueError:
            continue
    return None


def _format_worker_shift_label(shift: dict) -> str:
    shift_day = date.fromisoformat(str(shift["date"]))
    return (
        f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} "
        f"{_format_shift_clock(str(shift['start_time']))}-"
        f"{_format_shift_clock(str(shift['end_time']))} "
        f"at {(shift.get('location_name') or 'your location')}"
    )


def _select_callout_shift(
    shifts: list[dict],
    *,
    body: str,
    reference_date: date,
) -> tuple[dict | None, str | None]:
    candidates = [
        shift
        for shift in shifts
        if shift.get("date")
        and shift["date"] >= reference_date.isoformat()
        and not (shift.get("status") == "filled" and shift.get("filled_by"))
    ]
    if not candidates:
        return None, "none"

    target_date = _extract_callout_date(body, reference_date=reference_date)
    target_minutes = _extract_callout_minutes(body)
    if target_date:
        candidates = [shift for shift in candidates if shift.get("date") == target_date.isoformat()]
        if not candidates:
            return None, "none"

    if target_minutes is not None and candidates:
        scored = [
            (abs((_shift_start_minutes(shift) or 0) - target_minutes), shift)
            for shift in candidates
            if _shift_start_minutes(shift) is not None
        ]
        if len(scored) == 1:
            return scored[0][1], None
        if scored:
            scored.sort(key=lambda item: (item[0], str(item[1]["date"]), str(item[1]["start_time"])))
            if len(scored) > 1 and scored[0][0] == scored[1][0]:
                return None, "ambiguous"
            return scored[0][1], None

    if len(candidates) == 1:
        return candidates[0], None

    same_day = [shift for shift in candidates if shift.get("date") == reference_date.isoformat()]
    if len(same_day) == 1:
        return same_day[0], None

    near_term = [
        shift
        for shift in candidates
        if date.fromisoformat(str(shift["date"])) <= reference_date + timedelta(days=1)
    ]
    if len(near_term) == 1:
        return near_term[0], None

    return None, "ambiguous"


async def _handle_worker_callout(
    db: aiosqlite.Connection,
    phone: str,
    body: str,
    *,
    manager_context: dict | None,
) -> str | None:
    if not _looks_like_worker_callout(body):
        return None

    worker = await queries.get_worker_by_phone(db, phone)
    if not worker:
        if manager_context:
            return None
        return (
            "I couldn't match this number to a scheduled Backfill shift yet. "
            "Ask your manager to invite you from the roster or call 1-800-BACKFILL for help."
        )

    if manager_context and int(worker["location_id"]) != int(manager_context["location"]["id"]):
        return None

    shifts = await queries.list_assigned_schedule_shifts_for_worker(
        db,
        int(worker["id"]),
        published_only=True,
    )
    shift, match_state = _select_callout_shift(shifts, body=body, reference_date=date.today())
    if shift is None:
        if match_state == "ambiguous":
            return (
                "I found more than one upcoming scheduled shift for you. "
                "Reply with the day or time, like 'call out tomorrow 9am'."
            )
        return (
            "I couldn't match that to one of your published shifts right now. "
            "Reply with the day or time, or contact your manager if this is urgent."
        )

    active_cascade = await queries.get_active_cascade_for_shift(db, int(shift["id"]))
    if active_cascade or shift.get("status") in {"vacant", "filling", "unfilled"}:
        return (
            f"We already recorded that callout for {_format_worker_shift_label(shift)}. "
            "Coverage is already in progress."
        )

    cascade = await shift_manager.create_vacancy(
        db,
        shift_id=int(shift["id"]),
        called_out_by_worker_id=int(worker["id"]),
        actor=f"worker_sms:{phone}",
    )
    await cascade_svc.advance(db, int(cascade["id"]))

    location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
    if location is not None:
        await notifications_svc.queue_manager_callout_received_notification(
            db,
            location_id=int(location["id"]),
            shift_id=int(shift["id"]),
            worker_id=int(worker["id"]),
            cascade_id=int(cascade["id"]),
        )

    return (
        f"Got it. We recorded your callout for {_format_worker_shift_label(shift)} "
        "and started finding coverage now."
    )


async def _find_manager_context(db: aiosqlite.Connection, phone: str):
    locations = await queries.list_locations_by_contact_phone(db, phone)
    if not locations:
        return None

    preferred: list[dict] = [
        location
        for location in locations
        if location.get("operating_mode") == "backfill_shifts"
        or location.get("scheduling_platform") == "backfill_native"
    ]
    candidates = preferred or locations
    best_context = None
    best_score: tuple[int, int, str, str, int] | None = None

    for location in candidates:
        location_id = int(location["id"])
        schedule = await queries.get_latest_schedule_for_location(db, location_id)
        import_job = await queries.get_latest_import_job_for_location(db, location_id)
        review_row = await _get_review_row(db, import_job) if import_job else None

        score = (
            1 if review_row else 0,
            1 if schedule and schedule.get("lifecycle_state") in {"draft", "amended", "recalled"} else 0,
            import_job.get("updated_at", "") if import_job else "",
            schedule.get("updated_at", "") if schedule else "",
            location_id,
        )
        if best_score is None or score > best_score:
            best_score = score
            best_context = {
                "location": location,
                "schedule": schedule,
                "import_job": import_job,
                "review_row": review_row,
            }

    return best_context


async def _get_worker_schedule_context(db: aiosqlite.Connection, worker: dict) -> tuple[dict | None, list[dict], str | None]:
    shifts = await queries.list_assigned_schedule_shifts_for_worker(
        db,
        int(worker["id"]),
        published_only=True,
    )
    if not shifts:
        location = await queries.get_location(db, int(worker["location_id"])) if worker.get("location_id") else None
        return location, [], None

    today_iso = date.today().isoformat()
    target_shift = next(
        (shift for shift in shifts if shift.get("date") and shift["date"] >= today_iso),
        shifts[0],
    )
    target_schedule_id = target_shift.get("schedule_id")
    target_week_start = target_shift.get("week_start_date")
    location = await queries.get_location(db, int(target_shift["location_id"])) if target_shift.get("location_id") else None
    selected_shifts = [
        shift
        for shift in shifts
        if shift.get("schedule_id") == target_schedule_id and shift.get("week_start_date") == target_week_start
    ]
    return location, selected_shifts, target_week_start


async def _find_latest_pending_confirmation_shift(
    db: aiosqlite.Connection,
    phone: str,
) -> dict | None:
    worker = await queries.get_worker_by_phone(db, phone)
    if worker is None:
        return None
    shifts = await queries.list_assigned_schedule_shifts_for_worker(
        db,
        int(worker["id"]),
        published_only=True,
    )
    pending = [
        shift
        for shift in shifts
        if shift.get("status") == "scheduled"
        and shift.get("confirmation_requested_at")
        and not shift.get("worker_confirmed_at")
        and not shift.get("worker_declined_at")
    ]
    if not pending:
        return None
    pending.sort(
        key=lambda shift: (
            str(shift.get("date") or ""),
            str(shift.get("start_time") or ""),
            int(shift.get("id") or 0),
        )
    )
    shift = pending[0]
    location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
    return {
        "worker": worker,
        "shift": shift,
        "location": location or {"name": "your location"},
    }


async def _find_latest_pending_check_in_shift(
    db: aiosqlite.Connection,
    phone: str,
) -> dict | None:
    worker = await queries.get_worker_by_phone(db, phone)
    if worker is None:
        return None
    shifts = await queries.list_assigned_schedule_shifts_for_worker(
        db,
        int(worker["id"]),
        published_only=True,
    )
    pending = [
        shift
        for shift in shifts
        if shift.get("status") == "scheduled"
        and shift.get("check_in_requested_at")
        and not shift.get("checked_in_at")
    ]
    if not pending:
        return None
    pending.sort(
        key=lambda shift: (
            str(shift.get("date") or ""),
            str(shift.get("start_time") or ""),
            int(shift.get("id") or 0),
        )
    )
    shift = pending[0]
    location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
    return {
        "worker": worker,
        "shift": shift,
        "location": location or {"name": "your location"},
    }


async def _handle_worker_enrollment_keyword(db: aiosqlite.Connection, phone: str) -> str | None:
    worker = await queries.get_worker_by_phone(db, phone)
    if not worker:
        return "We couldn't match this number to a Backfill worker yet. Ask your manager to invite you from the roster."

    if worker.get("sms_consent_status") != "granted":
        await consent_svc.grant(
            db,
            int(worker["id"]),
            channel="inbound_sms",
            actor=f"worker_sms:{phone}",
        )

    location, shifts, week_start_date = await _get_worker_schedule_context(db, worker)
    location_name = (location or {}).get("name") or "your location"
    organization_name = (location or {}).get("organization_name")
    return notifications_svc.build_worker_enrollment_confirmation_text(
        location_name=location_name,
        organization_name=organization_name,
        week_start_date=week_start_date,
        shifts=shifts,
    )


async def _get_review_row(db: aiosqlite.Connection, import_job: dict | None):
    if not import_job:
        return None
    rows = await queries.list_import_row_results(db, int(import_job["id"]))
    return next(
        (
            row
            for row in rows
            if row.get("committed_at") is None and row.get("outcome") in {"failed", "warning"}
        ),
        None,
    )


async def _handle_manager_schedule_command(
    db: aiosqlite.Connection,
    manager_context: dict,
    command: str,
) -> str:
    location = manager_context["location"]
    schedule = manager_context.get("schedule")
    import_job = manager_context.get("import_job")
    review_row = manager_context.get("review_row")
    location_id = int(location["id"])
    actor = f"manager_sms:{location.get('manager_phone') or location_id}"

    if command == "HELP":
        return _manager_help_text()

    if command == "REVIEW":
        if import_job and review_row:
            link = notifications_svc.build_manager_dashboard_link(
                location_id,
                tab="imports",
                job_id=int(import_job["id"]),
                row_number=int(review_row["row_number"]),
            )
            return f"Open import review for {location['name']}: {link}"
        if schedule:
            link = notifications_svc.build_manager_dashboard_link(
                location_id,
                tab="schedule",
                week_start=str(schedule["week_start_date"]),
            )
            return (
                f"Open schedule review for {location['name']} and the week of "
                f"{schedule['week_start_date']}: {link}"
            )
        return (
            f"I couldn't find a schedule draft for {location['name']} yet. "
            "Upload your CSV first, then reply REVIEW again."
        )

    if command in {"HOLD", "PAUSE"}:
        if schedule:
            return (
                f"No changes made. {location['name']} stays on the current "
                f"{schedule['lifecycle_state']} schedule for the week of {schedule['week_start_date']}."
            )
        return f"No schedule changes made for {location['name']}."

    if command in {"APPROVE", "PUBLISH"}:
        if import_job and review_row and schedule is None:
            link = notifications_svc.build_manager_dashboard_link(
                location_id,
                tab="imports",
                job_id=int(import_job["id"]),
                row_number=int(review_row["row_number"]),
            )
            return f"Finish your import review first for {location['name']}: {link}"
        if schedule is None:
            return f"I couldn't find a schedule draft to publish for {location['name']}."
        try:
            result = await backfill_shifts_svc.publish_schedule(
                db,
                schedule_id=int(schedule["id"]),
                actor=actor,
            )
        except ValueError as exc:
            link = notifications_svc.build_manager_dashboard_link(
                location_id,
                tab="schedule",
                week_start=str(schedule["week_start_date"]),
            )
            return f"{exc}. Review it here: {link}"
        link = notifications_svc.build_manager_dashboard_link(
            location_id,
            tab="schedule",
            week_start=str(schedule["week_start_date"]),
        )
        delivery = result.get("delivery_summary") or {}
        message = (
            f"Published {location['name']} for the week of {schedule['week_start_date']}. "
            f"{delivery.get('sms_sent', 0)} employee schedule text"
            f"{'' if delivery.get('sms_sent', 0) == 1 else 's'} sent, "
        )
        if delivery.get("sms_failed", 0):
            failure_label = "delivery failed" if delivery.get("sms_failed", 0) == 1 else "deliveries failed"
            message += (
                f"{delivery.get('sms_failed', 0)} {failure_label}, "
            )
        message += f"{delivery.get('not_enrolled', 0)} not enrolled. Review: {link}"
        return message

    if command == "OPEN SHIFTS":
        if schedule is None:
            return f"I couldn't find a published schedule with open shifts for {location['name']}."
        try:
            result = await backfill_shifts_svc.offer_open_shifts_for_schedule(
                db,
                schedule_id=int(schedule["id"]),
                actor=actor,
            )
        except ValueError as exc:
            link = notifications_svc.build_manager_dashboard_link(
                location_id,
                tab="schedule",
                week_start=str(schedule["week_start_date"]),
            )
            return f"{exc}. Review it here: {link}"
        summary = result.get("summary") or {}
        if int(summary.get("requested", 0) or 0) <= 0:
            return f"No open shifts are ready to offer for {location['name']} right now."
        return (
            f"Started offering {summary.get('started', 0)} open shift"
            f"{'' if summary.get('started', 0) == 1 else 's'} for {location['name']}. "
            f"{summary.get('already_active', 0)} already active, "
            f"{summary.get('skipped_assigned', 0)} assigned, "
            f"{summary.get('skipped_not_open', 0)} skipped. "
            f"Review: {result['review_link']}"
        )

    if command == "COPY LAST WEEK":
        if schedule is None:
            return f"I couldn't find a schedule to copy for {location['name']} yet."
        target_week_start = (date.fromisoformat(str(schedule["week_start_date"])) + timedelta(days=7)).isoformat()
        existing_target = await queries.get_schedule_by_location_week(db, location_id, target_week_start)
        if existing_target is not None:
            link = notifications_svc.build_manager_dashboard_link(
                location_id,
                tab="schedule",
                week_start=target_week_start,
            )
            return (
                f"A schedule already exists for {location['name']} and the week of "
                f"{target_week_start}. Review it here: {link}"
            )
        result = await backfill_shifts_svc.copy_schedule_week(
            db,
            location_id=location_id,
            source_schedule_id=int(schedule["id"]),
            target_week_start_date=target_week_start,
            actor=actor,
        )
        link = notifications_svc.build_manager_dashboard_link(
            location_id,
            tab="schedule",
            week_start=result["week_start_date"],
        )
        return (
            f"Copied the latest schedule into a new draft for {location['name']} and the week of "
            f"{result['week_start_date']}. Review: {link}"
        )

    return _manager_help_text()


def _twiml(message: str) -> Response:
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{escape(message)}</Message></Response>"
    )
    return Response(content=body, media_type="application/xml")
