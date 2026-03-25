"""
Consent ledger — TCPA / FCC 2024 compliance.

Every outreach channel (SMS + voice) requires explicit opt-in.
Opt-out is honoured immediately and logged in the audit trail.

Disclosure text used in every first interaction:
  "Just so you know, I'm an AI assistant from Backfill. We'll use this number
   to text or call you about shift opportunities. You can opt out anytime by
   replying STOP or telling me. Is that ok?"
"""
from datetime import datetime
from typing import Literal
import aiosqlite

from app.db.queries import update_worker_consent, record_opt_out
from app.models.audit import AuditAction
from app.services import audit as audit_svc

CONSENT_VERSION = "v1.0"

ConsentChannel = Literal["inbound_call", "inbound_sms", "web", "csv_import"]
OptOutChannel = Literal["sms_reply", "voice", "web", "manual"]


async def grant(
    db: aiosqlite.Connection,
    worker_id: int,
    channel: ConsentChannel,
    actor: str = "system",
) -> None:
    """Record consent granted for both SMS and voice."""
    await update_worker_consent(
        db,
        worker_id=worker_id,
        sms_status="granted",
        voice_status="granted",
        version=CONSENT_VERSION,
        channel=channel,
    )
    await audit_svc.append(
        db,
        AuditAction.consent_granted,
        actor=actor,
        entity_type="worker",
        entity_id=worker_id,
        details={"channel": channel, "version": CONSENT_VERSION},
    )


async def revoke(
    db: aiosqlite.Connection,
    worker_id: int,
    channel: OptOutChannel,
    actor: str = "system",
) -> None:
    """Record opt-out. Must stop all outreach immediately."""
    await record_opt_out(db, worker_id=worker_id, channel=channel)
    await audit_svc.append(
        db,
        AuditAction.consent_revoked,
        actor=actor,
        entity_type="worker",
        entity_id=worker_id,
        details={"opt_out_channel": channel},
    )


async def has_sms_consent(db: aiosqlite.Connection, worker_id: int) -> bool:
    async with db.execute(
        "SELECT sms_consent_status FROM workers WHERE id=?", (worker_id,)
    ) as cur:
        row = await cur.fetchone()
    return row is not None and row[0] == "granted"


async def handle_stop_keyword(
    db: aiosqlite.Connection, phone: str
) -> bool:
    """
    Called when an inbound SMS contains STOP/UNSUBSCRIBE/QUIT/CANCEL/END.
    Returns True if a worker was found and opted out.
    """
    from app.db.queries import get_worker_by_phone
    worker = await get_worker_by_phone(db, phone)
    if not worker:
        return False
    await revoke(db, worker["id"], channel="sms_reply")
    return True
