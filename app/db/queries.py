"""
CRUD helpers for every table. All functions accept an open aiosqlite.Connection
and return plain dicts (JSON-serializable lists are already decoded).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional
import aiosqlite

# ── helpers ──────────────────────────────────────────────────────────────────

_JSON_COLS: dict[str, list[str]] = {
    "locations":        ["preferred_agency_partners"],
    "workers":          ["roles", "certifications", "location_assignments", "locations_worked"],
    "shifts":           ["requirements"],
    "cascades":         ["standby_queue"],
    "retell_conversations": ["transcript_items", "analysis", "metadata", "raw_payload"],
    "onboarding_sessions": ["extracted_fields"],
    "agency_partners":  ["coverage_areas", "roles_supported", "certifications_supported"],
    "audit_log":        ["details"],
    "integration_events": ["payload"],
}

_BOOL_COLS: dict[str, list[str]] = {
    "locations": ["agency_supply_approved", "writeback_enabled"],
    "cascades":    ["manager_approved_tier3"],
    "agency_partners": ["active"],
}


def _normalize_write_aliases(data: dict) -> dict:
    return dict(data)


def _decode(table: str, row: aiosqlite.Row | dict) -> dict:
    import logging as _logging

    data = dict(row)
    for col in _JSON_COLS.get(table, []):
        if col in data and isinstance(data[col], str):
            try:
                data[col] = json.loads(data[col])
            except json.JSONDecodeError:
                _logging.getLogger(__name__).warning(
                    "Corrupt JSON in %s.%s — leaving as raw string", table, col
                )
    for col in _BOOL_COLS.get(table, []):
        if col in data and data[col] is not None:
            data[col] = bool(data[col])
    return data


def _encode_json(table: str, data: dict) -> dict:
    data = _normalize_write_aliases(data)
    for col in _JSON_COLS.get(table, []):
        if col in data and not isinstance(data[col], str):
            data[col] = json.dumps(data[col])
    return data


# ── locations ─────────────────────────────────────────────────────────────────

_LOCATION_TABLE = "locations"
_LOCATION_SELECT = f"""
    SELECT l.*, o.name AS organization_name
    FROM {_LOCATION_TABLE} l
    LEFT JOIN organizations o ON o.id = l.organization_id
"""


# ── organizations ─────────────────────────────────────────────────────────────

async def get_organization(db: aiosqlite.Connection, organization_id: int) -> Optional[dict]:
    async with db.execute("SELECT * FROM organizations WHERE id=?", (organization_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_organization_by_name(db: aiosqlite.Connection, name: str) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM organizations WHERE LOWER(name)=LOWER(?)",
        (name,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def insert_organization(db: aiosqlite.Connection, data: dict) -> int:
    cur = await db.execute(
        """INSERT INTO organizations
           (name, vertical, contact_name, contact_phone, contact_email, location_count_estimate)
           VALUES (?,?,?,?,?,?)""",
        (
            data["name"],
            data.get("vertical"),
            data.get("contact_name"),
            data.get("contact_phone"),
            data.get("contact_email"),
            data.get("location_count_estimate"),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def list_organizations(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute("SELECT * FROM organizations ORDER BY name ASC, id ASC") as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def update_organization(db: aiosqlite.Connection, organization_id: int, data: dict) -> None:
    allowed = {
        "name",
        "vertical",
        "contact_name",
        "contact_phone",
        "contact_email",
        "location_count_estimate",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    cols = ", ".join(f"{key}=?" for key in updates)
    await db.execute(
        f"UPDATE organizations SET {cols} WHERE id=?",
        (*updates.values(), organization_id),
    )
    await db.commit()


async def get_location(db: aiosqlite.Connection, location_id: int) -> Optional[dict]:
    async with db.execute(f"{_LOCATION_SELECT} WHERE l.id=?", (location_id,)) as cur:
        row = await cur.fetchone()
    return _decode("locations", row) if row else None


async def get_location_by_name(db: aiosqlite.Connection, name: str) -> Optional[dict]:
    async with db.execute(
        f"{_LOCATION_SELECT} WHERE LOWER(l.name)=LOWER(?)", (name,)
    ) as cur:
        row = await cur.fetchone()
    return _decode("locations", row) if row else None


async def get_location_by_contact_phone(db: aiosqlite.Connection, phone: str) -> Optional[dict]:
    async with db.execute(f"{_LOCATION_SELECT} WHERE l.manager_phone=?", (phone,)) as cur:
        row = await cur.fetchone()
    return _decode("locations", row) if row else None


async def insert_location(db: aiosqlite.Connection, data: dict) -> int:
    d = _encode_json("locations", data)
    cur = await db.execute(
        f"""INSERT INTO {_LOCATION_TABLE}
           (name, organization_id, vertical, address, employee_count, manager_name, manager_phone, manager_email,
           scheduling_platform, scheduling_platform_id, integration_status,
            last_roster_sync_at, last_roster_sync_status,
            last_schedule_sync_at, last_schedule_sync_status, last_sync_error,
            integration_state, last_event_sync_at, last_rolling_sync_at, last_daily_sync_at, last_writeback_at,
            writeback_enabled, writeback_subscription_tier,
            onboarding_info,
            agency_supply_approved, preferred_agency_partners)
           VALUES (:name,:organization_id,:vertical,:address,:employee_count,:manager_name,:manager_phone,:manager_email,
                   :scheduling_platform,:scheduling_platform_id,:integration_status,
                   :last_roster_sync_at,:last_roster_sync_status,
                   :last_schedule_sync_at,:last_schedule_sync_status,:last_sync_error,
                   :integration_state,:last_event_sync_at,:last_rolling_sync_at,:last_daily_sync_at,:last_writeback_at,
                   :writeback_enabled,:writeback_subscription_tier,
                   :onboarding_info,
                   :agency_supply_approved,:preferred_agency_partners)""",
        {
            "name": d.get("name"),
            "organization_id": d.get("organization_id"),
            "vertical": d.get("vertical", "restaurant"),
            "address": d.get("address"),
            "employee_count": d.get("employee_count"),
            "manager_name": d.get("manager_name"),
            "manager_phone": d.get("manager_phone"),
            "manager_email": d.get("manager_email"),
            "scheduling_platform": d.get("scheduling_platform", "backfill_native"),
            "scheduling_platform_id": d.get("scheduling_platform_id"),
            "integration_status": d.get("integration_status"),
            "last_roster_sync_at": d.get("last_roster_sync_at"),
            "last_roster_sync_status": d.get("last_roster_sync_status"),
            "last_schedule_sync_at": d.get("last_schedule_sync_at"),
            "last_schedule_sync_status": d.get("last_schedule_sync_status"),
            "last_sync_error": d.get("last_sync_error"),
            "integration_state": d.get("integration_state"),
            "last_event_sync_at": d.get("last_event_sync_at"),
            "last_rolling_sync_at": d.get("last_rolling_sync_at"),
            "last_daily_sync_at": d.get("last_daily_sync_at"),
            "last_writeback_at": d.get("last_writeback_at"),
            "writeback_enabled": int(d.get("writeback_enabled", False)),
            "writeback_subscription_tier": d.get("writeback_subscription_tier", "core"),
            "onboarding_info": d.get("onboarding_info"),
            "agency_supply_approved": int(d.get("agency_supply_approved", False)),
            "preferred_agency_partners": d.get("preferred_agency_partners", "[]"),
        },
    )
    await db.commit()
    return cur.lastrowid


async def list_locations(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute(f"{_LOCATION_SELECT} ORDER BY l.id ASC") as cur:
        rows = await cur.fetchall()
    return [_decode("locations", row) for row in rows]


async def update_location(db: aiosqlite.Connection, location_id: int, data: dict) -> None:
    allowed = {
        "name",
        "organization_id",
        "vertical",
        "address",
        "employee_count",
        "manager_name",
        "manager_phone",
        "manager_email",
        "scheduling_platform",
        "scheduling_platform_id",
        "integration_status",
        "last_roster_sync_at",
        "last_roster_sync_status",
        "last_schedule_sync_at",
        "last_schedule_sync_status",
        "last_sync_error",
        "integration_state",
        "last_event_sync_at",
        "last_rolling_sync_at",
        "last_daily_sync_at",
        "last_writeback_at",
        "writeback_enabled",
        "writeback_subscription_tier",
        "onboarding_info",
        "agency_supply_approved",
        "preferred_agency_partners",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("locations", updates)
    if "agency_supply_approved" in encoded:
        encoded["agency_supply_approved"] = int(bool(encoded["agency_supply_approved"]))
    if "writeback_enabled" in encoded:
        encoded["writeback_enabled"] = int(bool(encoded["writeback_enabled"]))
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE {_LOCATION_TABLE} SET {cols} WHERE id=?",
        (*encoded.values(), location_id),
    )
    await db.commit()


# ── workers ───────────────────────────────────────────────────────────────────

async def get_worker(db: aiosqlite.Connection, worker_id: int) -> Optional[dict]:
    async with db.execute("SELECT * FROM workers WHERE id=?", (worker_id,)) as cur:
        row = await cur.fetchone()
    return _decode("workers", row) if row else None


async def get_worker_by_phone(db: aiosqlite.Connection, phone: str) -> Optional[dict]:
    async with db.execute("SELECT * FROM workers WHERE phone=?", (phone,)) as cur:
        row = await cur.fetchone()
    return _decode("workers", row) if row else None


async def get_worker_by_source_id(
    db: aiosqlite.Connection,
    source_id: str,
    location_id: Optional[int] = None,
) -> Optional[dict]:
    query = "SELECT * FROM workers WHERE source_id=?"
    params: list[Any] = [source_id]
    if location_id is not None:
        query += " AND location_id=?"
        params.append(location_id)
    async with db.execute(query, params) as cur:
        row = await cur.fetchone()
    return _decode("workers", row) if row else None


async def list_workers_for_location(
    db: aiosqlite.Connection, location_id: int, active_consent_only: bool = True
) -> list[dict]:
    query = "SELECT * FROM workers WHERE location_id=?"
    if active_consent_only:
        query += " AND sms_consent_status='granted'"
    query += " ORDER BY priority_rank ASC"
    async with db.execute(query, (location_id,)) as cur:
        rows = await cur.fetchall()
    return [_decode("workers", r) for r in rows]


async def list_workers_by_locations_worked(
    db: aiosqlite.Connection, location_id: int
) -> list[dict]:
    """Return all workers whose locations_worked JSON list contains the location id."""
    async with db.execute("SELECT * FROM workers ORDER BY priority_rank ASC, id ASC") as cur:
        rows = await cur.fetchall()
    result = []
    for row in rows:
        worker = _decode("workers", row)
        if location_id in (worker.get("locations_worked") or []):
            result.append(worker)
    return result


async def list_workers(db: aiosqlite.Connection, location_id: Optional[int] = None) -> list[dict]:
    query = "SELECT * FROM workers"
    params: list[Any] = []
    if location_id is not None:
        query += " WHERE location_id=?"
        params.append(location_id)
    query += " ORDER BY priority_rank ASC, id ASC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("workers", row) for row in rows]


async def insert_worker(db: aiosqlite.Connection, data: dict) -> int:
    d = _encode_json("workers", data)
    location_id = d.get("location_id")
    assignments = d.get("location_assignments")
    locations_worked = d.get("locations_worked")

    if assignments is None:
        assignments = json.dumps([
            {
                "location_id": location_id,
                "priority_rank": d.get("priority_rank", 1),
                "is_active": True,
                "roles": json.loads(d.get("roles", "[]")),
            }
        ]) if location_id else "[]"

    if locations_worked is None:
        locations_worked = json.dumps([location_id]) if location_id else "[]"

    cur = await db.execute(
        """INSERT INTO workers
           (name, phone, email, worker_type, preferred_channel, roles, certifications,
            priority_rank, location_id, location_assignments, locations_worked, source,
            source_id,
            sms_consent_status, voice_consent_status, consent_text_version,
            consent_timestamp, consent_channel)
           VALUES (:name,:phone,:email,:worker_type,:preferred_channel,:roles,:certifications,
                   :priority_rank,:location_id,:location_assignments,:locations_worked,:source,
                   :source_id,
                   :sms_consent_status,:voice_consent_status,:consent_text_version,
                   :consent_timestamp,:consent_channel)""",
        {
            "name": d["name"],
            "phone": d["phone"],
            "email": d.get("email"),
            "worker_type": d.get("worker_type", "internal"),
            "preferred_channel": d.get("preferred_channel", "sms"),
            "roles": d.get("roles", "[]"),
            "certifications": d.get("certifications", "[]"),
            "priority_rank": d.get("priority_rank", 1),
            "location_id": location_id,
            "location_assignments": assignments,
            "locations_worked": locations_worked,
            "source": d.get("source", "csv_import"),
            "source_id": d.get("source_id"),
            "sms_consent_status": d.get("sms_consent_status", "pending"),
            "voice_consent_status": d.get("voice_consent_status", "pending"),
            "consent_text_version": d.get("consent_text_version"),
            "consent_timestamp": d.get("consent_timestamp"),
            "consent_channel": d.get("consent_channel"),
        },
    )
    await db.commit()
    return cur.lastrowid


async def get_location_manager_by_shift(db: aiosqlite.Connection, shift_id: int) -> Optional[dict]:
    async with db.execute(
        f"""SELECT r.* FROM {_LOCATION_TABLE} r
           JOIN shifts s ON s.location_id = r.id
           WHERE s.id=?""",
        (shift_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("locations", row) if row else None


async def get_location_contact_by_shift(db: aiosqlite.Connection, shift_id: int) -> Optional[dict]:
    return await get_location_manager_by_shift(db, shift_id)


async def update_worker(db: aiosqlite.Connection, worker_id: int, data: dict) -> None:
    allowed = {
        "name",
        "phone",
        "email",
        "worker_type",
        "preferred_channel",
        "roles",
        "certifications",
        "priority_rank",
        "location_id",
        "location_assignments",
        "locations_worked",
        "source",
        "source_id",
        "sms_consent_status",
        "voice_consent_status",
        "consent_text_version",
        "consent_timestamp",
        "consent_channel",
        "opt_out_timestamp",
        "opt_out_channel",
        "response_rate",
        "acceptance_rate",
        "show_up_rate",
        "rating",
        "total_shifts_filled",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("workers", updates)
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE workers SET {cols} WHERE id=?",
        (*encoded.values(), worker_id),
    )
    await db.commit()


async def get_worker_outreach_metrics(
    db: aiosqlite.Connection,
    worker_id: int,
) -> dict[str, int]:
    async with db.execute(
        """
        SELECT
            COUNT(*) AS total_attempts,
            SUM(CASE WHEN outcome IN ('confirmed', 'standby', 'declined', 'no_response', 'promoted', 'standby_expired', 'too_late') THEN 1 ELSE 0 END) AS total_responses,
            SUM(CASE WHEN outcome IN ('confirmed', 'standby', 'promoted') THEN 1 ELSE 0 END) AS total_acceptances
        FROM outreach_attempts
        WHERE worker_id=?
        """,
        (worker_id,),
    ) as cur:
        row = await cur.fetchone()
    return {
        "total_attempts": int(row["total_attempts"] or 0),
        "total_responses": int(row["total_responses"] or 0),
        "total_acceptances": int(row["total_acceptances"] or 0),
    }


async def update_worker_consent(
    db: aiosqlite.Connection,
    worker_id: int,
    sms_status: str,
    voice_status: str,
    version: str,
    channel: str,
) -> None:
    await db.execute(
        """UPDATE workers SET
           sms_consent_status=?, voice_consent_status=?,
           consent_text_version=?, consent_timestamp=?, consent_channel=?
           WHERE id=?""",
        (sms_status, voice_status, version, datetime.utcnow().isoformat(), channel, worker_id),
    )
    await db.commit()


async def record_opt_out(
    db: aiosqlite.Connection, worker_id: int, channel: str
) -> None:
    await db.execute(
        """UPDATE workers SET
           sms_consent_status='revoked', voice_consent_status='revoked',
           opt_out_timestamp=?, opt_out_channel=?
           WHERE id=?""",
        (datetime.utcnow().isoformat(), channel, worker_id),
    )
    await db.commit()


# ── shifts ────────────────────────────────────────────────────────────────────

async def get_shift(db: aiosqlite.Connection, shift_id: int) -> Optional[dict]:
    async with db.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)) as cur:
        row = await cur.fetchone()
    return _decode("shifts", row) if row else None


async def insert_shift(db: aiosqlite.Connection, data: dict) -> int:
    d = _encode_json("shifts", data)
    cur = await db.execute(
        """INSERT INTO shifts
           (location_id, scheduling_platform_id, role, date, start_time, end_time, pay_rate,
            requirements, status, source_platform)
           VALUES (:location_id,:scheduling_platform_id,:role,:date,:start_time,:end_time,:pay_rate,
                   :requirements,:status,:source_platform)""",
        {
            "location_id": d.get("location_id"),
            "scheduling_platform_id": d.get("scheduling_platform_id"),
            "role": d["role"],
            "date": str(d["date"]),
            "start_time": str(d["start_time"]),
            "end_time": str(d["end_time"]),
            "pay_rate": d["pay_rate"],
            "requirements": d.get("requirements", "[]"),
            "status": d.get("status", "scheduled"),
            "source_platform": d.get("source_platform", "backfill_native"),
        },
    )
    await db.commit()
    return cur.lastrowid


async def list_shifts(
    db: aiosqlite.Connection,
    location_id: Optional[int] = None,
    status: Optional[str] = None,
) -> list[dict]:
    query = "SELECT * FROM shifts"
    clauses: list[str] = []
    params: list[Any] = []
    if location_id is not None:
        clauses.append("location_id=?")
        params.append(location_id)
    if status is not None:
        clauses.append("status=?")
        params.append(status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY date ASC, start_time ASC, id ASC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("shifts", row) for row in rows]


async def get_shift_by_platform_id(
    db: aiosqlite.Connection,
    source_platform: str,
    scheduling_platform_id: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM shifts WHERE source_platform=? AND scheduling_platform_id=?",
        (source_platform, scheduling_platform_id),
    ) as cur:
        row = await cur.fetchone()
    return _decode("shifts", row) if row else None


async def update_shift(db: aiosqlite.Connection, shift_id: int, data: dict) -> None:
    allowed = {
        "location_id",
        "scheduling_platform_id",
        "role",
        "date",
        "start_time",
        "end_time",
        "pay_rate",
        "requirements",
        "status",
        "called_out_by",
        "filled_by",
        "fill_tier",
        "source_platform",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("shifts", updates)
    normalized = {
        key: str(value) if key in {"date", "start_time", "end_time"} and value is not None else value
        for key, value in encoded.items()
    }
    cols = ", ".join(f"{key}=?" for key in normalized)
    await db.execute(
        f"UPDATE shifts SET {cols} WHERE id=?",
        (*normalized.values(), shift_id),
    )
    await db.commit()


async def update_shift_status(
    db: aiosqlite.Connection,
    shift_id: int,
    status: str,
    filled_by: Optional[int] = None,
    fill_tier: Optional[str] = None,
    called_out_by: Optional[int] = None,
) -> None:
    await db.execute(
        """UPDATE shifts SET status=?, filled_by=?, fill_tier=?, called_out_by=?
           WHERE id=?""",
        (status, filled_by, fill_tier, called_out_by, shift_id),
    )
    await db.commit()


# ── cascades ──────────────────────────────────────────────────────────────────

async def get_cascade(db: aiosqlite.Connection, cascade_id: int) -> Optional[dict]:
    async with db.execute("SELECT * FROM cascades WHERE id=?", (cascade_id,)) as cur:
        row = await cur.fetchone()
    return _decode("cascades", row) if row else None


async def get_active_cascade_for_shift(
    db: aiosqlite.Connection, shift_id: int
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM cascades WHERE shift_id=? AND status='active'", (shift_id,)
    ) as cur:
        row = await cur.fetchone()
    return _decode("cascades", row) if row else None


async def insert_cascade(
    db: aiosqlite.Connection,
    shift_id: int,
    outreach_mode: str = "cascade",
) -> int:
    cur = await db.execute(
        "INSERT INTO cascades (shift_id, outreach_mode) VALUES (?, ?)",
        (shift_id, outreach_mode),
    )
    await db.commit()
    return cur.lastrowid


async def update_cascade(db: aiosqlite.Connection, cascade_id: int, **kwargs: Any) -> None:
    allowed = {
        "status",
        "outreach_mode",
        "current_tier",
        "current_batch",
        "current_position",
        "confirmed_worker_id",
        "standby_queue",
        "manager_approved_tier3",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("cascades", updates)
    cols = ", ".join(f"{k}=?" for k in encoded)
    await db.execute(
        f"UPDATE cascades SET {cols} WHERE id=?", (*encoded.values(), cascade_id)
    )
    await db.commit()


async def list_cascades(
    db: aiosqlite.Connection,
    shift_id: Optional[int] = None,
    status: Optional[str] = None,
) -> list[dict]:
    query = "SELECT * FROM cascades"
    clauses: list[str] = []
    params: list[Any] = []
    if shift_id is not None:
        clauses.append("shift_id=?")
        params.append(shift_id)
    if status is not None:
        clauses.append("status=?")
        params.append(status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("cascades", row) for row in rows]


# ── outreach attempts ─────────────────────────────────────────────────────────

async def insert_outreach_attempt(db: aiosqlite.Connection, data: dict) -> int:
    cur = await db.execute(
        """INSERT INTO outreach_attempts
           (cascade_id, worker_id, tier, channel, status, outcome, standby_position,
            promoted_at, sent_at, responded_at, conversation_summary)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["cascade_id"],
            data["worker_id"],
            data["tier"],
            data.get("channel", "sms"),
            data.get("status", "sent"),
            data.get("outcome"),
            data.get("standby_position"),
            data.get("promoted_at"),
            data.get("sent_at", datetime.utcnow().isoformat()),
            data.get("responded_at"),
            data.get("conversation_summary"),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_outreach_attempt(
    db: aiosqlite.Connection,
    attempt_id: int,
    **kwargs: Any,
) -> None:
    allowed = {
        "status",
        "outcome",
        "standby_position",
        "promoted_at",
        "sent_at",
        "responded_at",
        "conversation_summary",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    cols = ", ".join(f"{key}=?" for key in updates)
    await db.execute(
        f"UPDATE outreach_attempts SET {cols} WHERE id=?",
        (*updates.values(), attempt_id),
    )
    await db.commit()


async def update_outreach_outcome(
    db: aiosqlite.Connection,
    attempt_id: int,
    outcome: str,
    conversation_summary: Optional[str] = None,
) -> None:
    await update_outreach_attempt(
        db,
        attempt_id,
        outcome=outcome,
        status="responded",
        responded_at=datetime.utcnow().isoformat(),
        conversation_summary=conversation_summary,
    )


async def list_outreach_attempts(
    db: aiosqlite.Connection,
    cascade_id: Optional[int] = None,
    shift_id: Optional[int] = None,
) -> list[dict]:
    query = """
        SELECT oa.*
        FROM outreach_attempts oa
        JOIN cascades c ON c.id = oa.cascade_id
    """
    clauses: list[str] = []
    params: list[Any] = []
    if cascade_id is not None:
        clauses.append("oa.cascade_id=?")
        params.append(cascade_id)
    if shift_id is not None:
        clauses.append("c.shift_id=?")
        params.append(shift_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY oa.id DESC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


# ── retell conversations ──────────────────────────────────────────────────────

async def get_retell_conversation_by_external_id(
    db: aiosqlite.Connection,
    external_id: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM retell_conversations WHERE external_id=?",
        (external_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("retell_conversations", row) if row else None


async def get_retell_conversation(
    db: aiosqlite.Connection,
    conversation_id: int,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM retell_conversations WHERE id=?",
        (conversation_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("retell_conversations", row) if row else None


async def upsert_retell_conversation(
    db: aiosqlite.Connection,
    data: dict,
) -> int:
    encoded = _encode_json("retell_conversations", data)
    external_id = encoded["external_id"]
    existing = await get_retell_conversation_by_external_id(db, external_id)
    now = datetime.utcnow().isoformat()

    if existing is None:
        cur = await db.execute(
            """INSERT INTO retell_conversations
               (external_id, conversation_type, event_type, direction, status, agent_id,
                location_id, shift_id, cascade_id, worker_id, phone_from, phone_to,
                disconnection_reason, conversation_summary, transcript_text, transcript_items,
                analysis, metadata, raw_payload, started_at, ended_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                external_id,
                encoded["conversation_type"],
                encoded.get("event_type"),
                encoded.get("direction"),
                encoded.get("status"),
                encoded.get("agent_id"),
                encoded.get("location_id"),
                encoded.get("shift_id"),
                encoded.get("cascade_id"),
                encoded.get("worker_id"),
                encoded.get("phone_from"),
                encoded.get("phone_to"),
                encoded.get("disconnection_reason"),
                encoded.get("conversation_summary"),
                encoded.get("transcript_text"),
                encoded.get("transcript_items", "[]"),
                encoded.get("analysis", "{}"),
                encoded.get("metadata", "{}"),
                encoded.get("raw_payload", "{}"),
                encoded.get("started_at"),
                encoded.get("ended_at"),
                encoded.get("created_at", now),
                encoded.get("updated_at", now),
            ),
        )
        await db.commit()
        return cur.lastrowid

    allowed = {
        "conversation_type",
        "event_type",
        "direction",
        "status",
        "agent_id",
        "location_id",
        "shift_id",
        "cascade_id",
        "worker_id",
        "phone_from",
        "phone_to",
        "disconnection_reason",
        "conversation_summary",
        "transcript_text",
        "transcript_items",
        "analysis",
        "metadata",
        "raw_payload",
        "started_at",
        "ended_at",
    }
    updates = {k: v for k, v in encoded.items() if k in allowed and v is not None}
    updates["updated_at"] = now
    cols = ", ".join(f"{key}=?" for key in updates)
    await db.execute(
        f"UPDATE retell_conversations SET {cols} WHERE external_id=?",
        (*updates.values(), external_id),
    )
    await db.commit()
    return int(existing["id"])


async def list_retell_conversations(
    db: aiosqlite.Connection,
    shift_id: Optional[int] = None,
    cascade_id: Optional[int] = None,
    worker_id: Optional[int] = None,
    limit: int = 50,
) -> list[dict]:
    query = "SELECT * FROM retell_conversations"
    clauses: list[str] = []
    params: list[Any] = []
    if shift_id is not None:
        clauses.append("shift_id=?")
        params.append(shift_id)
    if cascade_id is not None:
        clauses.append("cascade_id=?")
        params.append(cascade_id)
    if worker_id is not None:
        clauses.append("worker_id=?")
        params.append(worker_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("retell_conversations", row) for row in rows]


# ── onboarding sessions ───────────────────────────────────────────────────────

async def get_onboarding_session(db: aiosqlite.Connection, session_id: int) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM onboarding_sessions WHERE id=?",
        (session_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("onboarding_sessions", row) if row else None


async def get_onboarding_session_by_source_external_id(
    db: aiosqlite.Connection,
    source_external_id: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM onboarding_sessions WHERE source_external_id=?",
        (source_external_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("onboarding_sessions", row) if row else None


async def get_onboarding_session_by_token_hash(
    db: aiosqlite.Connection,
    token_hash: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM onboarding_sessions WHERE token_hash=?",
        (token_hash,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("onboarding_sessions", row) if row else None


async def insert_onboarding_session(db: aiosqlite.Connection, data: dict) -> int:
    encoded = _encode_json("onboarding_sessions", data)
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """INSERT INTO onboarding_sessions
           (token_hash, source_conversation_id, source_external_id, organization_id, location_id,
            status, call_type, contact_name, contact_phone, contact_email, role_name,
            business_name, location_name, vertical, location_count, lead_source, employee_count, address,
            pain_point_summary, urgency, notes, setup_kind, scheduling_platform, extracted_fields,
            sent_message_sid, sent_at, completed_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            encoded["token_hash"],
            encoded.get("source_conversation_id"),
            encoded.get("source_external_id"),
            encoded.get("organization_id"),
            encoded.get("location_id"),
            encoded.get("status", "pending"),
            encoded.get("call_type"),
            encoded.get("contact_name"),
            encoded.get("contact_phone"),
            encoded.get("contact_email"),
            encoded.get("role_name"),
            encoded.get("business_name"),
            encoded.get("location_name"),
            encoded.get("vertical"),
            encoded.get("location_count"),
            encoded.get("lead_source"),
            encoded.get("employee_count"),
            encoded.get("address"),
            encoded.get("pain_point_summary"),
            encoded.get("urgency"),
            encoded.get("notes"),
            encoded.get("setup_kind"),
            encoded.get("scheduling_platform"),
            encoded.get("extracted_fields", "{}"),
            encoded.get("sent_message_sid"),
            encoded.get("sent_at"),
            encoded.get("completed_at"),
            encoded.get("created_at", now),
            encoded.get("updated_at", now),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_onboarding_session(
    db: aiosqlite.Connection,
    session_id: int,
    data: dict,
) -> None:
    allowed = {
        "token_hash",
        "source_conversation_id",
        "source_external_id",
        "organization_id",
        "location_id",
        "status",
        "call_type",
        "contact_name",
        "contact_phone",
        "contact_email",
        "role_name",
        "business_name",
        "location_name",
        "vertical",
        "location_count",
        "lead_source",
        "employee_count",
        "address",
        "pain_point_summary",
        "urgency",
        "notes",
        "setup_kind",
        "scheduling_platform",
        "extracted_fields",
        "sent_message_sid",
        "sent_at",
        "completed_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("onboarding_sessions", updates)
    encoded["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE onboarding_sessions SET {cols} WHERE id=?",
        (*encoded.values(), session_id),
    )
    await db.commit()


# ── app state + repair helpers ────────────────────────────────────────────────

async def get_app_state(db: aiosqlite.Connection, key: str) -> Optional[str]:
    async with db.execute("SELECT value FROM app_state WHERE key=?", (key,)) as cur:
        row = await cur.fetchone()
    return str(row["value"]) if row and row["value"] is not None else None


async def set_app_state(db: aiosqlite.Connection, key: str, value: str) -> None:
    now = datetime.utcnow().isoformat()
    await db.execute(
        """
        INSERT INTO app_state (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, now),
    )
    await db.commit()


async def list_recent_outreach_audit_entries(
    db: aiosqlite.Connection,
    *,
    since: str,
    shift_ids: Optional[set[int]] = None,
    limit: int = 250,
) -> list[dict]:
    async with db.execute(
        """
        SELECT *
        FROM audit_log
        WHERE action=?
          AND timestamp >= ?
        ORDER BY id DESC
        LIMIT ?
        """,
        ("outreach_sent", since, limit),
    ) as cur:
        rows = await cur.fetchall()

    entries: list[dict] = []
    for row in rows:
        decoded = _decode("audit_log", row)
        details = decoded.get("details") or {}
        shift_id = details.get("shift_id")
        if shift_ids and shift_id not in shift_ids:
            continue
        entries.append(decoded)
    return entries


# ── integration events + sync jobs ───────────────────────────────────────────

async def get_integration_event(db: aiosqlite.Connection, event_id: int) -> Optional[dict]:
    async with db.execute("SELECT * FROM integration_events WHERE id=?", (event_id,)) as cur:
        row = await cur.fetchone()
    return _decode("integration_events", row) if row else None


async def get_integration_event_by_source(
    db: aiosqlite.Connection,
    platform: str,
    source_event_id: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM integration_events WHERE platform=? AND source_event_id=?",
        (platform, source_event_id),
    ) as cur:
        row = await cur.fetchone()
    return _decode("integration_events", row) if row else None


async def insert_integration_event(db: aiosqlite.Connection, data: dict) -> int:
    platform = data["platform"]
    source_event_id = data.get("source_event_id")
    if source_event_id:
        existing = await get_integration_event_by_source(db, platform, source_event_id)
        if existing is not None:
            return int(existing["id"])

    encoded = _encode_json("integration_events", data)
    cur = await db.execute(
        """INSERT INTO integration_events
           (platform, location_id, source_event_id, event_type, event_scope, payload,
            received_at, processed_at, status, error)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            encoded["platform"],
            encoded.get("location_id"),
            encoded.get("source_event_id"),
            encoded.get("event_type"),
            encoded.get("event_scope"),
            encoded.get("payload", "{}"),
            encoded.get("received_at", datetime.utcnow().isoformat()),
            encoded.get("processed_at"),
            encoded.get("status", "received"),
            encoded.get("error"),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_integration_event(db: aiosqlite.Connection, event_id: int, data: dict) -> None:
    allowed = {"location_id", "processed_at", "status", "error", "event_type", "event_scope", "payload"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("integration_events", updates)
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE integration_events SET {cols} WHERE id=?",
        (*encoded.values(), event_id),
    )
    await db.commit()


async def get_sync_job(db: aiosqlite.Connection, job_id: int) -> Optional[dict]:
    async with db.execute("SELECT * FROM sync_jobs WHERE id=?", (job_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_sync_job_by_idempotency_key(
    db: aiosqlite.Connection,
    idempotency_key: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM sync_jobs WHERE idempotency_key=?",
        (idempotency_key,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def insert_sync_job(db: aiosqlite.Connection, data: dict) -> int:
    idempotency_key = data.get("idempotency_key")
    if idempotency_key:
        existing = await get_sync_job_by_idempotency_key(db, idempotency_key)
        if existing is not None:
            return int(existing["id"])

    normalized = _normalize_write_aliases(data)
    cur = await db.execute(
        """INSERT INTO sync_jobs
           (platform, location_id, integration_event_id, job_type, priority, scope, scope_ref,
            window_start, window_end, status, attempt_count, max_attempts, next_run_at,
            started_at, completed_at, last_error, idempotency_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            normalized["platform"],
            normalized.get("location_id"),
            normalized.get("integration_event_id"),
            normalized["job_type"],
            normalized.get("priority", 50),
            normalized.get("scope"),
            normalized.get("scope_ref"),
            normalized.get("window_start"),
            normalized.get("window_end"),
            normalized.get("status", "queued"),
            normalized.get("attempt_count", 0),
            normalized.get("max_attempts", 3),
            normalized.get("next_run_at", datetime.utcnow().isoformat()),
            normalized.get("started_at"),
            normalized.get("completed_at"),
            normalized.get("last_error"),
            idempotency_key,
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_sync_job(db: aiosqlite.Connection, job_id: int, data: dict) -> None:
    allowed = {
        "status",
        "attempt_count",
        "max_attempts",
        "next_run_at",
        "started_at",
        "completed_at",
        "last_error",
        "priority",
        "window_start",
        "window_end",
        "scope",
        "scope_ref",
        "integration_event_id",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    cols = ", ".join(f"{key}=?" for key in updates)
    await db.execute(
        f"UPDATE sync_jobs SET {cols} WHERE id=?",
        (*updates.values(), job_id),
    )
    await db.commit()


async def list_sync_jobs(
    db: aiosqlite.Connection,
    *,
    status: Optional[str] = None,
    platform: Optional[str] = None,
    location_id: Optional[int] = None,
    limit: int = 100,
) -> list[dict]:
    query = "SELECT * FROM sync_jobs"
    clauses: list[str] = []
    params: list[Any] = []
    if status is not None:
        clauses.append("status=?")
        params.append(status)
    if platform is not None:
        clauses.append("platform=?")
        params.append(platform)
    if location_id is not None:
        clauses.append("location_id=?")
        params.append(location_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY priority ASC, next_run_at ASC, id ASC LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def claim_due_sync_jobs(
    db: aiosqlite.Connection,
    *,
    platform: Optional[str] = None,
    limit: int = 10,
    now_iso: Optional[str] = None,
) -> list[dict]:
    now = now_iso or datetime.utcnow().isoformat()
    query = """
        SELECT id
        FROM sync_jobs
        WHERE status='queued' AND next_run_at<=?
    """
    params: list[Any] = [now]
    if platform is not None:
        query += " AND platform=?"
        params.append(platform)
    query += " ORDER BY priority ASC, next_run_at ASC, id ASC LIMIT ?"
    params.append(limit)

    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    job_ids = [int(row["id"]) for row in rows]

    claimed: list[dict] = []
    for job_id in job_ids:
        job = await get_sync_job(db, job_id)
        if job is None or job["status"] != "queued":
            continue
        await db.execute(
            """UPDATE sync_jobs
               SET status='running', started_at=?, attempt_count=attempt_count+1
               WHERE id=? AND status='queued'""",
            (now, job_id),
        )
        await db.commit()
        refreshed = await get_sync_job(db, job_id)
        if refreshed and refreshed["status"] == "running":
            claimed.append(refreshed)
    return claimed


async def claim_sync_job(
    db: aiosqlite.Connection,
    job_id: int,
    *,
    now_iso: Optional[str] = None,
) -> Optional[dict]:
    now = now_iso or datetime.utcnow().isoformat()
    await db.execute(
        """UPDATE sync_jobs
           SET status='running', started_at=?, attempt_count=attempt_count+1
           WHERE id=? AND status='queued'""",
        (now, job_id),
    )
    await db.commit()
    job = await get_sync_job(db, job_id)
    if job and job["status"] == "running":
        return job
    return None


async def insert_sync_run(db: aiosqlite.Connection, data: dict) -> int:
    cur = await db.execute(
        """INSERT INTO sync_runs
           (sync_job_id, attempt_number, started_at, completed_at, status,
            created_count, updated_count, skipped_count, latency_ms, error)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            data["sync_job_id"],
            data["attempt_number"],
            data["started_at"],
            data.get("completed_at"),
            data["status"],
            data.get("created_count", 0),
            data.get("updated_count", 0),
            data.get("skipped_count", 0),
            data.get("latency_ms"),
            data.get("error"),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def list_sync_runs(db: aiosqlite.Connection, sync_job_id: int) -> list[dict]:
    async with db.execute(
        "SELECT * FROM sync_runs WHERE sync_job_id=? ORDER BY id DESC",
        (sync_job_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def find_pending_sync_job_for_scope(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    job_type: str,
    scope_ref: str,
) -> Optional[dict]:
    async with db.execute(
        """SELECT *
           FROM sync_jobs
           WHERE location_id=?
             AND job_type=?
             AND scope_ref=?
             AND status IN ('queued', 'running')
           ORDER BY priority ASC, next_run_at ASC, id ASC
           LIMIT 1""",
        (location_id, job_type, scope_ref),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


# ── audit log ─────────────────────────────────────────────────────────────────

async def insert_audit(db: aiosqlite.Connection, data: dict) -> int:
    cur = await db.execute(
        """INSERT INTO audit_log (timestamp, actor, action, entity_type, entity_id, details)
           VALUES (?,?,?,?,?,?)""",
        (
            data.get("timestamp", datetime.utcnow().isoformat()),
            data["actor"],
            data["action"],
            data.get("entity_type"),
            data.get("entity_id"),
            json.dumps(data.get("details", {})),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def list_audit_log(
    db: aiosqlite.Connection,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    limit: int = 100,
) -> list[dict]:
    query = "SELECT * FROM audit_log"
    clauses: list[str] = []
    params: list[Any] = []
    if entity_type is not None:
        clauses.append("entity_type=?")
        params.append(entity_type)
    if entity_id is not None:
        clauses.append("entity_id=?")
        params.append(entity_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("audit_log", row) for row in rows]


async def get_shift_status(db: aiosqlite.Connection, shift_id: int) -> Optional[dict]:
    shift = await get_shift(db, shift_id)
    if shift is None:
        return None

    location = await get_location(db, shift["location_id"]) if shift.get("location_id") else None
    cascade = await get_active_cascade_for_shift(db, shift_id)
    if cascade is None:
        async with db.execute(
            "SELECT * FROM cascades WHERE shift_id=? ORDER BY id DESC LIMIT 1",
            (shift_id,),
        ) as cur:
            row = await cur.fetchone()
        cascade = _decode("cascades", row) if row else None
    filled_worker = await get_worker(db, shift["filled_by"]) if shift.get("filled_by") else None
    attempts = await list_outreach_attempts(db, shift_id=shift_id)
    conversations = await list_retell_conversations(db, shift_id=shift_id)

    return {
        "shift": shift,
        "location": location,
        "cascade": cascade,
        "filled_worker": filled_worker,
        "outreach_attempts": attempts,
        "retell_conversations": conversations,
    }


async def get_location_status(
    db: aiosqlite.Connection,
    location_id: int,
    audit_limit: int = 12,
) -> Optional[dict]:
    location = await get_location(db, location_id)
    if location is None:
        return None

    workers = await list_workers(db, location_id=location_id)
    shifts = await list_shifts(db, location_id=location_id)
    shift_ids = {shift["id"] for shift in shifts}
    shift_by_id = {shift["id"]: shift for shift in shifts}
    worker_by_id = {worker["id"]: worker for worker in workers}

    cascades = [
        cascade
        for cascade in await list_cascades(db)
        if cascade["shift_id"] in shift_ids
    ]
    relevant_cascades = [
        cascade
        for cascade in cascades
        if cascade["status"] == "active"
        or cascade.get("confirmed_worker_id")
        or (cascade.get("standby_queue") or [])
    ]

    recent_shifts = sorted(
        shifts,
        key=lambda shift: (shift.get("date") or "", shift.get("start_time") or "", shift.get("id") or 0),
        reverse=True,
    )[:8]

    active_cascades = []
    for cascade in relevant_cascades:
        shift = shift_by_id.get(cascade["shift_id"])
        if shift is None:
            continue
        confirmed_worker_id = cascade.get("confirmed_worker_id")
        confirmed_worker = worker_by_id.get(confirmed_worker_id) if confirmed_worker_id else None
        active_cascades.append(
            {
                "id": cascade["id"],
                "shift_id": shift["id"],
                "shift_role": shift["role"],
                "shift_date": shift["date"],
                "shift_start_time": shift["start_time"],
                "shift_status": shift["status"],
                "status": cascade["status"],
                "outreach_mode": cascade.get("outreach_mode"),
                "current_tier": cascade.get("current_tier"),
                "confirmed_worker_id": confirmed_worker_id,
                "confirmed_worker_name": (
                    confirmed_worker["name"] if confirmed_worker else (
                        f"Worker #{confirmed_worker_id}" if confirmed_worker_id else None
                    )
                ),
                "standby_depth": len(cascade.get("standby_queue") or []),
            }
        )

    active_cascades.sort(
        key=lambda cascade: (
            cascade.get("shift_date") or "",
            cascade.get("shift_start_time") or "",
            cascade.get("id") or 0,
        ),
        reverse=True,
    )

    today = datetime.utcnow().date().isoformat()
    worker_preview = workers[:8]
    location_audit = await list_audit_log(
        db,
        entity_type="location",
        entity_id=location_id,
        limit=audit_limit,
    )
    audit_rows = sorted(
        location_audit,
        key=lambda row: (row.get("timestamp") or "", row.get("id") or 0),
        reverse=True,
    )[:audit_limit]
    recent_sync_jobs = await list_sync_jobs(
        db,
        location_id=location_id,
        limit=8,
    )

    return {
        "location": location,
        "metrics": {
            "workers_total": len(workers),
            "workers_sms_ready": sum(1 for worker in workers if worker.get("sms_consent_status") == "granted"),
            "workers_voice_ready": sum(1 for worker in workers if worker.get("voice_consent_status") == "granted"),
            "upcoming_shifts": sum(1 for shift in shifts if (shift.get("date") or "") >= today),
            "shifts_vacant": sum(1 for shift in shifts if shift["status"] == "vacant"),
            "shifts_filled": sum(1 for shift in shifts if shift["status"] == "filled"),
            "active_cascades": sum(1 for cascade in cascades if cascade["status"] == "active"),
            "workers_on_standby": sum(len(cascade.get("standby_queue") or []) for cascade in cascades),
        },
        "worker_preview": worker_preview,
        "recent_shifts": recent_shifts,
        "active_cascades": active_cascades[:8],
        "recent_sync_jobs": recent_sync_jobs,
        "recent_audit": audit_rows,
    }


async def get_dashboard_summary(db: aiosqlite.Connection, location_id: Optional[int] = None) -> dict:
    shifts = await list_shifts(db, location_id=location_id)
    cascades = await list_cascades(db)
    if location_id is not None:
        cascades = [
            cascade for cascade in cascades
            if any(shift["id"] == cascade["shift_id"] for shift in shifts)
        ]
    workers = await list_workers(db, location_id=location_id)
    total_locations = len(await list_locations(db)) if location_id is None else 1

    active_shift_ids = {cascade["shift_id"] for cascade in cascades if cascade["status"] == "active"}
    broadcast_cascades_active = sum(
        1
        for cascade in cascades
        if cascade["status"] == "active" and cascade.get("outreach_mode") == "broadcast"
    )
    workers_on_standby = sum(len(cascade.get("standby_queue") or []) for cascade in cascades)
    return {
        "location_id": location_id,
        "locations": total_locations,
        "workers": len(workers),
        "shifts_total": len(shifts),
        "shifts_vacant": sum(1 for shift in shifts if shift["status"] == "vacant"),
        "shifts_filled": sum(1 for shift in shifts if shift["status"] == "filled"),
        "cascades_active": sum(1 for cascade in cascades if cascade["status"] == "active"),
        "broadcast_cascades_active": broadcast_cascades_active,
        "workers_on_standby": workers_on_standby,
        "active_shift_ids": sorted(active_shift_ids),
        "recent_shifts": shifts[:10],
    }


async def list_filled_shifts_needing_reminder(
    db: aiosqlite.Connection,
    within_minutes: int = 30,
) -> list[dict]:
    """Return filled shifts whose start time is within `within_minutes` and no reminder sent yet."""
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    cutoff = now + timedelta(minutes=within_minutes)
    async with db.execute(
        """SELECT * FROM shifts
           WHERE status='filled'
             AND filled_by IS NOT NULL
             AND reminder_sent_at IS NULL
             AND datetime(date || ' ' || start_time) BETWEEN ? AND ?""",
        (now.strftime("%Y-%m-%d %H:%M:%S"), cutoff.strftime("%Y-%m-%d %H:%M:%S")),
    ) as cur:
        rows = await cur.fetchall()
    return [_decode("shifts", row) for row in rows]


async def mark_reminder_sent(db: aiosqlite.Connection, shift_id: int) -> None:
    from datetime import datetime

    await db.execute(
        "UPDATE shifts SET reminder_sent_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), shift_id),
    )
    await db.commit()


# ── agency partners ───────────────────────────────────────────────────────────

async def list_agency_partners(
    db: aiosqlite.Connection, active_only: bool = True
) -> list[dict]:
    query = "SELECT * FROM agency_partners"
    if active_only:
        query += " WHERE active=1"
    async with db.execute(query) as cur:
        rows = await cur.fetchall()
    return [_decode("agency_partners", r) for r in rows]


async def insert_agency_partner(db: aiosqlite.Connection, data: dict) -> int:
    d = _encode_json("agency_partners", data)
    cur = await db.execute(
        """INSERT INTO agency_partners
           (name, coverage_areas, roles_supported, certifications_supported,
            contact_channel, contact_info, avg_response_time_minutes,
            acceptance_rate, fill_rate, billing_model, sla_tier, active)
           VALUES (:name,:coverage_areas,:roles_supported,:certifications_supported,
                   :contact_channel,:contact_info,:avg_response_time_minutes,
                   :acceptance_rate,:fill_rate,:billing_model,:sla_tier,:active)""",
        {
            "name": d["name"],
            "coverage_areas": d.get("coverage_areas", "[]"),
            "roles_supported": d.get("roles_supported", "[]"),
            "certifications_supported": d.get("certifications_supported", "[]"),
            "contact_channel": d.get("contact_channel", "email"),
            "contact_info": d.get("contact_info"),
            "avg_response_time_minutes": d.get("avg_response_time_minutes"),
            "acceptance_rate": d.get("acceptance_rate"),
            "fill_rate": d.get("fill_rate"),
            "billing_model": d.get("billing_model", "referral_fee"),
            "sla_tier": d.get("sla_tier", "standard"),
            "active": int(d.get("active", True)),
        },
    )
    await db.commit()
    return cur.lastrowid


async def insert_agency_request(db: aiosqlite.Connection, data: dict) -> int:
    cur = await db.execute(
        """INSERT INTO agency_requests
           (shift_id, cascade_id, agency_partner_id, status, request_timestamp,
            response_deadline, confirmed_worker_name, confirmed_worker_eta,
            agency_reference_id, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            data["shift_id"],
            data["cascade_id"],
            data["agency_partner_id"],
            data.get("status", "sent"),
            data.get("request_timestamp", datetime.utcnow().isoformat()),
            data.get("response_deadline"),
            data.get("confirmed_worker_name"),
            data.get("confirmed_worker_eta"),
            data.get("agency_reference_id"),
            data.get("notes"),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_agency_request(
    db: aiosqlite.Connection,
    agency_request_id: int,
    **kwargs: Any,
) -> None:
    allowed = {
        "status",
        "request_timestamp",
        "response_deadline",
        "confirmed_worker_name",
        "confirmed_worker_eta",
        "agency_reference_id",
        "notes",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    cols = ", ".join(f"{key}=?" for key in updates)
    await db.execute(
        f"UPDATE agency_requests SET {cols} WHERE id=?",
        (*updates.values(), agency_request_id),
    )
    await db.commit()


async def list_agency_requests(
    db: aiosqlite.Connection,
    cascade_id: Optional[int] = None,
    shift_id: Optional[int] = None,
) -> list[dict]:
    query = "SELECT * FROM agency_requests"
    clauses: list[str] = []
    params: list[Any] = []
    if cascade_id is not None:
        clauses.append("cascade_id=?")
        params.append(cascade_id)
    if shift_id is not None:
        clauses.append("shift_id=?")
        params.append(shift_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]
