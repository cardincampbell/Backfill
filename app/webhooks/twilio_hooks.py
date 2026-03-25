"""
Inbound SMS handling for worker replies.

This makes outbound SMS offers actionable:
- YES claims the shift if still open, otherwise enters standby
- NO declines the most recent offer
- CANCEL drops a worker from standby
- STOP revokes consent immediately
"""
from fastapi import APIRouter, Depends, Form, Request, Response
import aiosqlite

from app.config import settings
from app.db.database import get_db
from app.db import queries
from app.services import cascade as cascade_svc
from app.services import consent as consent_svc
from app.services import notifications as notifications_svc
from app.services import agency_router as agency_router_svc

router = APIRouter(prefix="/webhooks/twilio", tags=["twilio-webhooks"])


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

    body = Body.strip().upper()

    if body in {"STOP", "UNSUBSCRIBE", "QUIT", "END"}:
        handled = await consent_svc.handle_stop_keyword(db, From)
        message = (
            "You've been unsubscribed from Backfill shift texts."
            if handled else
            "You're unsubscribed from Backfill messages."
        )
        return _twiml(message)

    manager_cascade = await _find_latest_manager_cascade(db, From)
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
        if body == "STATUS":
            shift = manager_cascade["shift"]
            status = shift["status"].upper()
            tier = manager_cascade["cascade"]["current_tier"]
            return _twiml(
                f"Shift status: {status} for {shift['role']} on {shift['date']} at "
                f"{shift['start_time']}. Current cascade tier: {tier}."
            )

    attempt = await _find_latest_sms_attempt(db, From)
    if attempt is None:
        return _twiml("Thanks for the message. Call 1-800-BACKFILL if you need help.")

    if body == "YES":
        result = await cascade_svc.claim_shift(
            db,
            cascade_id=attempt["cascade_id"],
            worker_id=attempt["worker_id"],
            summary="Accepted by SMS",
        )
        if result["status"] == "confirmed":
            await notifications_svc.fire_manager_notification(db, attempt["cascade_id"], attempt["worker_id"], filled=True)
            return _twiml("You're confirmed. We'll text any final details shortly.")
        if result["status"] == "standby":
            return _twiml(
                f"That shift just got claimed, but you're on standby as #{result['standby_position']}. "
                "Reply CANCEL anytime to drop off standby."
            )
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
        """SELECT oa.cascade_id, oa.worker_id, oa.outcome
           FROM outreach_attempts oa
           JOIN workers w ON w.id = oa.worker_id
           JOIN cascades c ON c.id = oa.cascade_id
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
           JOIN restaurants r ON r.id = s.restaurant_id
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


def _twiml(message: str) -> Response:
    body = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{message}</Message></Response>'
    return Response(content=body, media_type="application/xml")
