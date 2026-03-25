"""
CRUD helpers for every table. All functions accept an open aiosqlite.Connection
and return plain dicts (JSON-serializable lists are already decoded).
"""
import json
from datetime import datetime
from typing import Any, Optional
import aiosqlite

# ── helpers ──────────────────────────────────────────────────────────────────

_JSON_COLS: dict[str, list[str]] = {
    "restaurants":      ["preferred_agency_partners"],
    "workers":          ["roles", "certifications", "restaurant_assignments", "restaurants_worked"],
    "shifts":           ["requirements"],
    "agency_partners":  ["coverage_areas", "roles_supported", "certifications_supported"],
    "audit_log":        ["details"],
}

_BOOL_COLS: dict[str, list[str]] = {
    "restaurants": ["agency_supply_approved"],
    "cascades":    ["manager_approved_tier3"],
    "agency_partners": ["active"],
}


def _decode(table: str, row: aiosqlite.Row) -> dict:
    data = dict(row)
    for col in _JSON_COLS.get(table, []):
        if col in data and isinstance(data[col], str):
            data[col] = json.loads(data[col])
    for col in _BOOL_COLS.get(table, []):
        if col in data and data[col] is not None:
            data[col] = bool(data[col])
    return data


def _encode_json(table: str, data: dict) -> dict:
    data = dict(data)
    for col in _JSON_COLS.get(table, []):
        if col in data and not isinstance(data[col], str):
            data[col] = json.dumps(data[col])
    return data


# ── restaurants ───────────────────────────────────────────────────────────────

async def get_restaurant(db: aiosqlite.Connection, restaurant_id: int) -> Optional[dict]:
    async with db.execute("SELECT * FROM restaurants WHERE id=?", (restaurant_id,)) as cur:
        row = await cur.fetchone()
    return _decode("restaurants", row) if row else None


async def get_restaurant_by_name(db: aiosqlite.Connection, name: str) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM restaurants WHERE LOWER(name)=LOWER(?)", (name,)
    ) as cur:
        row = await cur.fetchone()
    return _decode("restaurants", row) if row else None


async def insert_restaurant(db: aiosqlite.Connection, data: dict) -> int:
    d = _encode_json("restaurants", data)
    cur = await db.execute(
        """INSERT INTO restaurants
           (name, address, manager_name, manager_phone, manager_email,
            scheduling_platform, scheduling_platform_id, onboarding_info,
            agency_supply_approved, preferred_agency_partners)
           VALUES (:name,:address,:manager_name,:manager_phone,:manager_email,
                   :scheduling_platform,:scheduling_platform_id,:onboarding_info,
                   :agency_supply_approved,:preferred_agency_partners)""",
        {
            "name": d.get("name"),
            "address": d.get("address"),
            "manager_name": d.get("manager_name"),
            "manager_phone": d.get("manager_phone"),
            "manager_email": d.get("manager_email"),
            "scheduling_platform": d.get("scheduling_platform", "backfill_native"),
            "scheduling_platform_id": d.get("scheduling_platform_id"),
            "onboarding_info": d.get("onboarding_info"),
            "agency_supply_approved": int(d.get("agency_supply_approved", False)),
            "preferred_agency_partners": d.get("preferred_agency_partners", "[]"),
        },
    )
    await db.commit()
    return cur.lastrowid


async def list_restaurants(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute("SELECT * FROM restaurants ORDER BY id ASC") as cur:
        rows = await cur.fetchall()
    return [_decode("restaurants", row) for row in rows]


async def update_restaurant(db: aiosqlite.Connection, restaurant_id: int, data: dict) -> None:
    allowed = {
        "name",
        "address",
        "manager_name",
        "manager_phone",
        "manager_email",
        "scheduling_platform",
        "scheduling_platform_id",
        "onboarding_info",
        "agency_supply_approved",
        "preferred_agency_partners",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("restaurants", updates)
    if "agency_supply_approved" in encoded:
        encoded["agency_supply_approved"] = int(bool(encoded["agency_supply_approved"]))
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE restaurants SET {cols} WHERE id=?",
        (*encoded.values(), restaurant_id),
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
    restaurant_id: Optional[int] = None,
) -> Optional[dict]:
    query = "SELECT * FROM workers WHERE source_id=?"
    params: list[Any] = [source_id]
    if restaurant_id is not None:
        query += " AND restaurant_id=?"
        params.append(restaurant_id)
    async with db.execute(query, params) as cur:
        row = await cur.fetchone()
    return _decode("workers", row) if row else None


async def list_workers_for_restaurant(
    db: aiosqlite.Connection, restaurant_id: int, active_consent_only: bool = True
) -> list[dict]:
    query = "SELECT * FROM workers WHERE restaurant_id=?"
    if active_consent_only:
        query += " AND sms_consent_status='granted'"
    query += " ORDER BY priority_rank ASC"
    async with db.execute(query, (restaurant_id,)) as cur:
        rows = await cur.fetchall()
    return [_decode("workers", r) for r in rows]


async def list_workers_by_restaurants_worked(
    db: aiosqlite.Connection, restaurant_id: int
) -> list[dict]:
    """Return all workers whose restaurants_worked JSON list contains restaurant_id."""
    async with db.execute("SELECT * FROM workers ORDER BY priority_rank ASC, id ASC") as cur:
        rows = await cur.fetchall()
    result = []
    for row in rows:
        worker = _decode("workers", row)
        if restaurant_id in (worker.get("restaurants_worked") or []):
            result.append(worker)
    return result


async def list_workers(db: aiosqlite.Connection, restaurant_id: Optional[int] = None) -> list[dict]:
    query = "SELECT * FROM workers"
    params: list[Any] = []
    if restaurant_id is not None:
        query += " WHERE restaurant_id=?"
        params.append(restaurant_id)
    query += " ORDER BY priority_rank ASC, id ASC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("workers", row) for row in rows]


async def insert_worker(db: aiosqlite.Connection, data: dict) -> int:
    d = _encode_json("workers", data)
    restaurant_id = d.get("restaurant_id")
    assignments = d.get("restaurant_assignments")
    restaurants_worked = d.get("restaurants_worked")

    if assignments is None:
        assignments = json.dumps([
            {
                "restaurant_id": restaurant_id,
                "priority_rank": d.get("priority_rank", 1),
                "is_active": True,
                "roles": json.loads(d.get("roles", "[]")),
            }
        ]) if restaurant_id else "[]"

    if restaurants_worked is None:
        restaurants_worked = json.dumps([restaurant_id]) if restaurant_id else "[]"

    cur = await db.execute(
        """INSERT INTO workers
           (name, phone, email, worker_type, preferred_channel, roles, certifications,
            priority_rank, restaurant_id, restaurant_assignments, restaurants_worked, source,
            source_id,
            sms_consent_status, voice_consent_status, consent_text_version,
            consent_timestamp, consent_channel)
           VALUES (:name,:phone,:email,:worker_type,:preferred_channel,:roles,:certifications,
                   :priority_rank,:restaurant_id,:restaurant_assignments,:restaurants_worked,:source,
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
            "restaurant_id": restaurant_id,
            "restaurant_assignments": assignments,
            "restaurants_worked": restaurants_worked,
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


async def get_restaurant_manager_by_shift(db: aiosqlite.Connection, shift_id: int) -> Optional[dict]:
    async with db.execute(
        """SELECT r.* FROM restaurants r
           JOIN shifts s ON s.restaurant_id = r.id
           WHERE s.id=?""",
        (shift_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("restaurants", row) if row else None


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
        "restaurant_id",
        "restaurant_assignments",
        "restaurants_worked",
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
            SUM(CASE WHEN outcome IN ('accepted', 'declined', 'negotiating') THEN 1 ELSE 0 END) AS total_responses,
            SUM(CASE WHEN outcome = 'accepted' THEN 1 ELSE 0 END) AS total_acceptances
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
           (restaurant_id, scheduling_platform_id, role, date, start_time, end_time, pay_rate,
            requirements, status, source_platform)
           VALUES (:restaurant_id,:scheduling_platform_id,:role,:date,:start_time,:end_time,:pay_rate,
                   :requirements,:status,:source_platform)""",
        {
            "restaurant_id": d.get("restaurant_id"),
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
    restaurant_id: Optional[int] = None,
    status: Optional[str] = None,
) -> list[dict]:
    query = "SELECT * FROM shifts"
    clauses: list[str] = []
    params: list[Any] = []
    if restaurant_id is not None:
        clauses.append("restaurant_id=?")
        params.append(restaurant_id)
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
        "restaurant_id",
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


async def insert_cascade(db: aiosqlite.Connection, shift_id: int) -> int:
    cur = await db.execute(
        "INSERT INTO cascades (shift_id) VALUES (?)", (shift_id,)
    )
    await db.commit()
    return cur.lastrowid


async def update_cascade(db: aiosqlite.Connection, cascade_id: int, **kwargs: Any) -> None:
    allowed = {"status", "current_tier", "current_position", "manager_approved_tier3"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    cols = ", ".join(f"{k}=?" for k in updates)
    await db.execute(
        f"UPDATE cascades SET {cols} WHERE id=?", (*updates.values(), cascade_id)
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
           (cascade_id, worker_id, tier, channel, status, sent_at)
           VALUES (?,?,?,?,?,?)""",
        (
            data["cascade_id"],
            data["worker_id"],
            data["tier"],
            data.get("channel", "sms"),
            data.get("status", "sent"),
            data.get("sent_at", datetime.utcnow().isoformat()),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_outreach_outcome(
    db: aiosqlite.Connection,
    attempt_id: int,
    outcome: str,
    conversation_summary: Optional[str] = None,
) -> None:
    await db.execute(
        """UPDATE outreach_attempts
           SET outcome=?, status='responded', responded_at=?, conversation_summary=?
           WHERE id=?""",
        (outcome, datetime.utcnow().isoformat(), conversation_summary, attempt_id),
    )
    await db.commit()


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

    restaurant = await get_restaurant(db, shift["restaurant_id"]) if shift.get("restaurant_id") else None
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

    return {
        "shift": shift,
        "restaurant": restaurant,
        "cascade": cascade,
        "filled_worker": filled_worker,
        "outreach_attempts": attempts,
    }


async def get_dashboard_summary(db: aiosqlite.Connection, restaurant_id: Optional[int] = None) -> dict:
    shifts = await list_shifts(db, restaurant_id=restaurant_id)
    cascades = await list_cascades(db)
    if restaurant_id is not None:
        cascades = [
            cascade for cascade in cascades
            if any(shift["id"] == cascade["shift_id"] for shift in shifts)
        ]
    workers = await list_workers(db, restaurant_id=restaurant_id)

    active_shift_ids = {cascade["shift_id"] for cascade in cascades if cascade["status"] == "active"}
    return {
        "restaurant_id": restaurant_id,
        "restaurants": len(await list_restaurants(db)) if restaurant_id is None else 1,
        "workers": len(workers),
        "shifts_total": len(shifts),
        "shifts_vacant": sum(1 for shift in shifts if shift["status"] == "vacant"),
        "shifts_filled": sum(1 for shift in shifts if shift["status"] == "filled"),
        "cascades_active": sum(1 for cascade in cascades if cascade["status"] == "active"),
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
