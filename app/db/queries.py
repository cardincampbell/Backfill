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
    "locations":        [
        "preferred_agency_partners",
        "place_types",
        "place_address_components",
        "place_regular_opening_hours",
        "place_plus_code",
        "place_metadata",
    ],
    "workers":          ["roles", "certifications", "location_assignments", "locations_worked"],
    "shifts":           ["requirements"],
    "cascades":         ["standby_queue"],
    "schedule_versions": ["snapshot_json", "change_summary_json"],
    "schedule_template_shifts": ["requirements"],
    "import_jobs":      ["mapping_json", "summary_json", "columns_json"],
    "import_row_results": ["raw_payload", "normalized_payload"],
    "retell_conversations": ["transcript_items", "analysis", "metadata", "raw_payload"],
    "onboarding_sessions": ["extracted_fields"],
    "agency_partners":  ["coverage_areas", "roles_supported", "certifications_supported"],
    "audit_log":        ["details"],
    "integration_events": ["payload"],
    "webhook_receipts": ["request_payload"],
    "dashboard_access_requests": ["location_ids_json"],
    "dashboard_sessions": ["location_ids_json"],
    "ops_jobs": ["payload_json"],
    "ai_action_requests": ["action_plan_json", "result_summary_json"],
    "ai_action_entities": ["candidate_payload_json"],
    "ai_action_events": ["payload_json"],
    "action_sessions": ["pending_payload_json"],
}

_BOOL_COLS: dict[str, list[str]] = {
    "locations": [
        "agency_supply_approved",
        "writeback_enabled",
        "backfill_shifts_enabled",
        "backfill_shifts_beta_eligible",
        "coverage_requires_manager_approval",
    ],
    "shifts": ["spans_midnight"],
    "schedule_template_shifts": ["spans_midnight"],
    "cascades":    ["manager_approved_tier3"],
    "agency_partners": ["active"],
    "ai_action_requests": ["requires_confirmation"],
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


def _split_name_parts(full_name: str | None) -> tuple[Optional[str], Optional[str]]:
    text = (full_name or "").strip()
    if not text:
        return None, None
    parts = text.split()
    first_name = parts[0]
    last_name = " ".join(parts[1:]) or None
    return first_name, last_name


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


async def list_organizations_by_contact_phone(
    db: aiosqlite.Connection,
    phone: str,
) -> list[dict]:
    async with db.execute(
        "SELECT * FROM organizations WHERE contact_phone=? ORDER BY id DESC",
        (phone,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def insert_organization(db: aiosqlite.Connection, data: dict) -> int:
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """INSERT INTO organizations
           (name, vertical, contact_name, contact_phone, contact_email, location_count_estimate, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            data["name"],
            data.get("vertical"),
            data.get("contact_name"),
            data.get("contact_phone"),
            data.get("contact_email"),
            data.get("location_count_estimate"),
            data.get("created_at", now),
            data.get("updated_at", now),
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
    updates["updated_at"] = datetime.utcnow().isoformat()
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


async def list_locations_by_contact_phone(db: aiosqlite.Connection, phone: str) -> list[dict]:
    async with db.execute(
        f"{_LOCATION_SELECT} WHERE l.manager_phone=? ORDER BY l.id DESC",
        (phone,),
    ) as cur:
        rows = await cur.fetchall()
    return [_decode("locations", row) for row in rows]


async def get_location_membership_by_phone(
    db: aiosqlite.Connection,
    location_id: int,
    phone: str,
    *,
    include_revoked: bool = True,
) -> Optional[dict]:
    query = """
        SELECT *
        FROM location_memberships
        WHERE location_id=? AND phone=?
    """
    params: list[Any] = [location_id, phone]
    if not include_revoked:
        query += " AND (invite_status IS NULL OR invite_status != 'revoked')"
    async with db.execute(query, params) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def list_location_memberships_for_phone(
    db: aiosqlite.Connection,
    phone: str,
    *,
    include_revoked: bool = False,
) -> list[dict]:
    query = """
        SELECT *
        FROM location_memberships
        WHERE phone=?
        ORDER BY location_id ASC, id ASC
    """
    params: list[Any] = [phone]
    if not include_revoked:
        query = """
        SELECT *
        FROM location_memberships
        WHERE phone=? AND (invite_status IS NULL OR invite_status != 'revoked')
        ORDER BY location_id ASC, id ASC
        """
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def list_location_memberships_for_location(
    db: aiosqlite.Connection,
    location_id: int,
    *,
    include_revoked: bool = False,
) -> list[dict]:
    query = """
        SELECT *
        FROM location_memberships
        WHERE location_id=?
    """
    params: list[Any] = [location_id]
    if not include_revoked:
        query += """
        AND (invite_status IS NULL OR invite_status != 'revoked')
        """
    query += """
        ORDER BY
            CASE WHEN role='owner' THEN 0 ELSE 1 END,
            CASE
                WHEN invite_status='pending' THEN 0
                WHEN invite_status='active' THEN 1
                ELSE 2
            END,
            COALESCE(manager_name, phone) ASC,
            id ASC
        """
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_location_membership(
    db: aiosqlite.Connection,
    membership_id: int,
) -> Optional[dict]:
    async with db.execute(
        """
        SELECT *
        FROM location_memberships
        WHERE id=?
        """,
        (membership_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_location_membership(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    phone: str,
    manager_name: Optional[str] = None,
    manager_email: Optional[str] = None,
    role: str = "manager",
    invite_status: Optional[str] = None,
    invited_by_phone: Optional[str] = None,
    accepted_at: Optional[str] = None,
    revoked_at: Optional[str] = None,
) -> dict:
    now = datetime.utcnow().isoformat()
    if invite_status is None:
        invite_status = "active" if role == "owner" else "pending"
    if role == "owner" and accepted_at is None:
        accepted_at = now
    await db.execute(
        """
        INSERT INTO location_memberships (
            location_id,
            phone,
            manager_name,
            manager_email,
            role,
            invite_status,
            invited_by_phone,
            accepted_at,
            revoked_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(location_id, phone) DO UPDATE SET
            manager_name=COALESCE(excluded.manager_name, location_memberships.manager_name),
            manager_email=COALESCE(excluded.manager_email, location_memberships.manager_email),
            role=excluded.role,
            invite_status=COALESCE(excluded.invite_status, location_memberships.invite_status),
            invited_by_phone=COALESCE(excluded.invited_by_phone, location_memberships.invited_by_phone),
            accepted_at=COALESCE(excluded.accepted_at, location_memberships.accepted_at),
            revoked_at=excluded.revoked_at,
            updated_at=excluded.updated_at
        """,
        (
            location_id,
            phone,
            manager_name,
            manager_email,
            role,
            invite_status,
            invited_by_phone,
            accepted_at,
            revoked_at,
            now,
            now,
        ),
    )
    await db.commit()
    membership = await get_location_membership_by_phone(db, location_id, phone)
    assert membership is not None
    return membership


async def complete_location_memberships_for_phone(
    db: aiosqlite.Connection,
    *,
    phone: str,
    manager_name: str,
    manager_email: str,
) -> int:
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """
        UPDATE location_memberships
        SET
            manager_name=?,
            manager_email=?,
            invite_status='active',
            accepted_at=COALESCE(accepted_at, ?),
            revoked_at=NULL,
            updated_at=?
        WHERE phone=? AND role!='owner' AND (invite_status IS NULL OR invite_status != 'revoked')
        """,
        (manager_name, manager_email, now, now, phone),
    )
    await db.commit()
    return int(cur.rowcount or 0)


async def revoke_location_membership(
    db: aiosqlite.Connection,
    membership_id: int,
) -> None:
    now = datetime.utcnow().isoformat()
    await db.execute(
        """
        UPDATE location_memberships
        SET invite_status='revoked', revoked_at=?, updated_at=?
        WHERE id=?
        """,
        (now, now, membership_id),
    )
    await db.commit()


async def list_incomplete_location_memberships_for_phone(
    db: aiosqlite.Connection,
    phone: str,
) -> list[dict]:
    async with db.execute(
        """
        SELECT *
        FROM location_memberships
        WHERE
            phone=?
            AND role!='owner'
            AND (invite_status IS NULL OR invite_status != 'revoked')
            AND (
                invite_status='pending'
                OR manager_name IS NULL
                OR TRIM(manager_name)=''
                OR manager_email IS NULL
                OR TRIM(manager_email)=''
            )
        ORDER BY location_id ASC, id ASC
        """,
        (phone,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_location_manager_invite_by_email(
    db: aiosqlite.Connection,
    location_id: int,
    invite_email: str,
    *,
    include_revoked: bool = True,
) -> Optional[dict]:
    query = """
        SELECT *
        FROM location_manager_invites
        WHERE location_id=? AND LOWER(invite_email)=LOWER(?)
    """
    params: list[Any] = [location_id, invite_email]
    if not include_revoked:
        query += " AND status != 'revoked'"
    async with db.execute(query, params) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_location_manager_invite(
    db: aiosqlite.Connection,
    invite_id: int,
) -> Optional[dict]:
    async with db.execute(
        """
        SELECT *
        FROM location_manager_invites
        WHERE id=?
        """,
        (invite_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_location_manager_invite_by_token_hash(
    db: aiosqlite.Connection,
    token_hash: str,
) -> Optional[dict]:
    async with db.execute(
        """
        SELECT *
        FROM location_manager_invites
        WHERE token_hash=?
        """,
        (token_hash,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def list_location_manager_invites_for_location(
    db: aiosqlite.Connection,
    location_id: int,
    *,
    include_terminal: bool = False,
) -> list[dict]:
    query = """
        SELECT *
        FROM location_manager_invites
        WHERE location_id=?
    """
    params: list[Any] = [location_id]
    if not include_terminal:
        query += " AND status='pending'"
    query += """
        ORDER BY COALESCE(claimed_name, manager_name, invite_email) ASC, id ASC
    """
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def upsert_location_manager_invite(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    invite_email: str,
    manager_name: Optional[str] = None,
    role: str = "manager",
    token_hash: str,
    invited_by_phone: Optional[str] = None,
    expires_at: str,
) -> dict:
    now = datetime.utcnow().isoformat()
    await db.execute(
        """
        INSERT INTO location_manager_invites (
            location_id,
            invite_email,
            manager_name,
            role,
            token_hash,
            status,
            invited_by_phone,
            claimed_phone,
            claimed_name,
            accepted_phone,
            accepted_at,
            revoked_at,
            expires_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?)
        ON CONFLICT(location_id, invite_email) DO UPDATE SET
            manager_name=COALESCE(excluded.manager_name, location_manager_invites.manager_name),
            role=excluded.role,
            token_hash=excluded.token_hash,
            status='pending',
            invited_by_phone=COALESCE(excluded.invited_by_phone, location_manager_invites.invited_by_phone),
            claimed_phone=NULL,
            claimed_name=NULL,
            accepted_phone=NULL,
            accepted_at=NULL,
            revoked_at=NULL,
            expires_at=excluded.expires_at,
            updated_at=excluded.updated_at
        """,
        (
            location_id,
            invite_email,
            manager_name,
            role,
            token_hash,
            invited_by_phone,
            expires_at,
            now,
            now,
        ),
    )
    await db.commit()
    invite = await get_location_manager_invite_by_email(
        db,
        location_id,
        invite_email,
        include_revoked=True,
    )
    assert invite is not None
    return invite


async def claim_location_manager_invite(
    db: aiosqlite.Connection,
    invite_id: int,
    *,
    claimed_phone: str,
    claimed_name: Optional[str] = None,
) -> None:
    now = datetime.utcnow().isoformat()
    await db.execute(
        """
        UPDATE location_manager_invites
        SET claimed_phone=?, claimed_name=COALESCE(?, claimed_name), updated_at=?
        WHERE id=?
        """,
        (claimed_phone, claimed_name, now, invite_id),
    )
    await db.commit()


async def accept_location_manager_invite(
    db: aiosqlite.Connection,
    invite_id: int,
    *,
    accepted_phone: str,
) -> None:
    now = datetime.utcnow().isoformat()
    await db.execute(
        """
        UPDATE location_manager_invites
        SET
            status='accepted',
            accepted_phone=?,
            accepted_at=COALESCE(accepted_at, ?),
            updated_at=?
        WHERE id=?
        """,
        (accepted_phone, now, now, invite_id),
    )
    await db.commit()


async def revoke_location_manager_invite(
    db: aiosqlite.Connection,
    invite_id: int,
) -> None:
    now = datetime.utcnow().isoformat()
    await db.execute(
        """
        UPDATE location_manager_invites
        SET status='revoked', revoked_at=?, updated_at=?
        WHERE id=?
        """,
        (now, now, invite_id),
    )
    await db.commit()


async def insert_location(db: aiosqlite.Connection, data: dict) -> int:
    d = _encode_json("locations", data)
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        f"""INSERT INTO {_LOCATION_TABLE}
           (name, organization_id, vertical, address, place_inferred_vertical,
            place_provider, place_id, place_resource_name, place_display_name, place_brand_name, place_location_label,
           place_formatted_address, place_primary_type, place_primary_type_display_name, place_business_status,
            place_latitude, place_longitude, place_google_maps_uri, place_website_uri,
            place_national_phone_number, place_international_phone_number, place_utc_offset_minutes,
            place_rating, place_user_rating_count, place_city, place_state_region, place_postal_code,
            place_country_code, place_neighborhood, place_sublocality, place_types, place_address_components,
            place_regular_opening_hours, place_plus_code, place_metadata,
            employee_count, manager_name, manager_phone, manager_email,
           scheduling_platform, scheduling_platform_id, integration_status,
            last_roster_sync_at, last_roster_sync_status,
            last_schedule_sync_at, last_schedule_sync_status, last_sync_error,
            integration_state, last_event_sync_at, last_rolling_sync_at, last_daily_sync_at, last_writeback_at,
           last_manager_digest_sent_at,
            writeback_enabled, writeback_subscription_tier, backfill_shifts_enabled,
            backfill_shifts_launch_state, backfill_shifts_beta_eligible,
            coverage_requires_manager_approval,
            late_arrival_policy, missed_check_in_policy, timezone, operating_mode,
            onboarding_info,
            agency_supply_approved, preferred_agency_partners, created_at, updated_at)
           VALUES (:name,:organization_id,:vertical,:address,:place_inferred_vertical,
                   :place_provider,:place_id,:place_resource_name,:place_display_name,:place_brand_name,:place_location_label,
                   :place_formatted_address,:place_primary_type,:place_primary_type_display_name,:place_business_status,
                   :place_latitude,:place_longitude,:place_google_maps_uri,:place_website_uri,
                   :place_national_phone_number,:place_international_phone_number,:place_utc_offset_minutes,
                   :place_rating,:place_user_rating_count,:place_city,:place_state_region,:place_postal_code,
                   :place_country_code,:place_neighborhood,:place_sublocality,:place_types,:place_address_components,
                   :place_regular_opening_hours,:place_plus_code,:place_metadata,
                   :employee_count,:manager_name,:manager_phone,:manager_email,
                   :scheduling_platform,:scheduling_platform_id,:integration_status,
                   :last_roster_sync_at,:last_roster_sync_status,
                   :last_schedule_sync_at,:last_schedule_sync_status,:last_sync_error,
                   :integration_state,:last_event_sync_at,:last_rolling_sync_at,:last_daily_sync_at,:last_writeback_at,
                   :last_manager_digest_sent_at,
                   :writeback_enabled,:writeback_subscription_tier,:backfill_shifts_enabled,
                   :backfill_shifts_launch_state,:backfill_shifts_beta_eligible,:coverage_requires_manager_approval,
                   :late_arrival_policy,:missed_check_in_policy,:timezone,:operating_mode,
                   :onboarding_info,
                   :agency_supply_approved,:preferred_agency_partners,:created_at,:updated_at)""",
        {
            "name": d.get("name"),
            "organization_id": d.get("organization_id"),
            "vertical": d.get("vertical", "restaurant"),
            "address": d.get("address"),
            "place_inferred_vertical": d.get("place_inferred_vertical"),
            "place_provider": d.get("place_provider"),
            "place_id": d.get("place_id"),
            "place_resource_name": d.get("place_resource_name"),
            "place_display_name": d.get("place_display_name"),
            "place_brand_name": d.get("place_brand_name"),
            "place_location_label": d.get("place_location_label"),
            "place_formatted_address": d.get("place_formatted_address"),
            "place_primary_type": d.get("place_primary_type"),
            "place_primary_type_display_name": d.get("place_primary_type_display_name"),
            "place_business_status": d.get("place_business_status"),
            "place_latitude": d.get("place_latitude"),
            "place_longitude": d.get("place_longitude"),
            "place_google_maps_uri": d.get("place_google_maps_uri"),
            "place_website_uri": d.get("place_website_uri"),
            "place_national_phone_number": d.get("place_national_phone_number"),
            "place_international_phone_number": d.get("place_international_phone_number"),
            "place_utc_offset_minutes": d.get("place_utc_offset_minutes"),
            "place_rating": d.get("place_rating"),
            "place_user_rating_count": d.get("place_user_rating_count"),
            "place_city": d.get("place_city"),
            "place_state_region": d.get("place_state_region"),
            "place_postal_code": d.get("place_postal_code"),
            "place_country_code": d.get("place_country_code"),
            "place_neighborhood": d.get("place_neighborhood"),
            "place_sublocality": d.get("place_sublocality"),
            "place_types": d.get("place_types", "[]"),
            "place_address_components": d.get("place_address_components", "[]"),
            "place_regular_opening_hours": d.get("place_regular_opening_hours", "{}"),
            "place_plus_code": d.get("place_plus_code", "{}"),
            "place_metadata": d.get("place_metadata", "{}"),
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
            "last_manager_digest_sent_at": d.get("last_manager_digest_sent_at"),
            "writeback_enabled": int(d.get("writeback_enabled", False)),
            "writeback_subscription_tier": d.get("writeback_subscription_tier", "core"),
            "backfill_shifts_enabled": int(d.get("backfill_shifts_enabled", True)),
            "backfill_shifts_launch_state": d.get("backfill_shifts_launch_state", "enabled"),
            "backfill_shifts_beta_eligible": int(d.get("backfill_shifts_beta_eligible", False)),
            "coverage_requires_manager_approval": int(d.get("coverage_requires_manager_approval", False)),
            "late_arrival_policy": d.get("late_arrival_policy", "wait"),
            "missed_check_in_policy": d.get("missed_check_in_policy", "start_coverage"),
            "timezone": d.get("timezone"),
            "operating_mode": d.get("operating_mode"),
            "onboarding_info": d.get("onboarding_info"),
            "agency_supply_approved": int(d.get("agency_supply_approved", False)),
            "preferred_agency_partners": d.get("preferred_agency_partners", "[]"),
            "created_at": d.get("created_at", now),
            "updated_at": d.get("updated_at", now),
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
        "place_inferred_vertical",
        "place_provider",
        "place_id",
        "place_resource_name",
        "place_display_name",
        "place_brand_name",
        "place_location_label",
        "place_formatted_address",
        "place_primary_type",
        "place_primary_type_display_name",
        "place_business_status",
        "place_latitude",
        "place_longitude",
        "place_google_maps_uri",
        "place_website_uri",
        "place_national_phone_number",
        "place_international_phone_number",
        "place_utc_offset_minutes",
        "place_rating",
        "place_user_rating_count",
        "place_city",
        "place_state_region",
        "place_postal_code",
        "place_country_code",
        "place_neighborhood",
        "place_sublocality",
        "place_types",
        "place_address_components",
        "place_regular_opening_hours",
        "place_plus_code",
        "place_metadata",
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
        "last_manager_digest_sent_at",
        "writeback_enabled",
        "writeback_subscription_tier",
        "backfill_shifts_enabled",
        "backfill_shifts_launch_state",
        "backfill_shifts_beta_eligible",
        "coverage_requires_manager_approval",
        "late_arrival_policy",
        "missed_check_in_policy",
        "timezone",
        "operating_mode",
        "onboarding_info",
        "agency_supply_approved",
        "preferred_agency_partners",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("locations", updates)
    encoded["updated_at"] = datetime.utcnow().isoformat()
    if "agency_supply_approved" in encoded:
        encoded["agency_supply_approved"] = int(bool(encoded["agency_supply_approved"]))
    if "writeback_enabled" in encoded:
        encoded["writeback_enabled"] = int(bool(encoded["writeback_enabled"]))
    if "backfill_shifts_enabled" in encoded:
        encoded["backfill_shifts_enabled"] = int(bool(encoded["backfill_shifts_enabled"]))
    if "backfill_shifts_beta_eligible" in encoded:
        encoded["backfill_shifts_beta_eligible"] = int(bool(encoded["backfill_shifts_beta_eligible"]))
    if "coverage_requires_manager_approval" in encoded:
        encoded["coverage_requires_manager_approval"] = int(bool(encoded["coverage_requires_manager_approval"]))
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE {_LOCATION_TABLE} SET {cols} WHERE id=?",
        (*encoded.values(), location_id),
    )
    await db.commit()


async def delete_location(db: aiosqlite.Connection, location_id: int) -> None:
    await db.execute(f"DELETE FROM {_LOCATION_TABLE} WHERE id=?", (location_id,))
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
    query = (
        "SELECT * FROM workers WHERE location_id=? "
        "AND (employment_status IS NULL OR employment_status='active')"
    )
    if active_consent_only:
        query += " AND (sms_consent_status='granted' OR voice_consent_status='granted')"
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
        if worker.get("employment_status") in {"inactive", "terminated"}:
            continue
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
    now = datetime.utcnow().isoformat()
    name = d["name"]
    first_name = d.get("first_name")
    last_name = d.get("last_name")
    if not first_name and not last_name:
        first_name, last_name = _split_name_parts(name)
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
           (name, first_name, last_name, phone, email, worker_type, preferred_channel, roles, certifications,
            priority_rank, location_id, location_assignments, locations_worked, source,
            source_id, employment_status, max_hours_per_week,
            sms_consent_status, voice_consent_status, consent_text_version,
            consent_timestamp, consent_channel, created_at, updated_at)
           VALUES (:name,:first_name,:last_name,:phone,:email,:worker_type,:preferred_channel,:roles,:certifications,
                   :priority_rank,:location_id,:location_assignments,:locations_worked,:source,
                   :source_id,:employment_status,:max_hours_per_week,
                   :sms_consent_status,:voice_consent_status,:consent_text_version,
                   :consent_timestamp,:consent_channel,:created_at,:updated_at)""",
        {
            "name": name,
            "first_name": first_name,
            "last_name": last_name,
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
            "employment_status": d.get("employment_status") or "active",
            "max_hours_per_week": d.get("max_hours_per_week"),
            "sms_consent_status": d.get("sms_consent_status", "pending"),
            "voice_consent_status": d.get("voice_consent_status", "pending"),
            "consent_text_version": d.get("consent_text_version"),
            "consent_timestamp": d.get("consent_timestamp"),
            "consent_channel": d.get("consent_channel"),
            "created_at": d.get("created_at", now),
            "updated_at": d.get("updated_at", now),
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
        "first_name",
        "last_name",
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
        "employment_status",
        "max_hours_per_week",
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
    encoded["updated_at"] = datetime.utcnow().isoformat()
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
            SUM(CASE WHEN outcome IN ('claimed_pending_manager', 'confirmed', 'standby', 'declined', 'manager_declined', 'no_response', 'promoted', 'standby_expired', 'too_late') THEN 1 ELSE 0 END) AS total_responses,
            SUM(CASE WHEN outcome IN ('claimed_pending_manager', 'confirmed', 'standby', 'manager_declined', 'promoted') THEN 1 ELSE 0 END) AS total_acceptances
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
           consent_text_version=?, consent_timestamp=?, consent_channel=?, updated_at=?
           WHERE id=?""",
        (
            sms_status,
            voice_status,
            version,
            datetime.utcnow().isoformat(),
            channel,
            datetime.utcnow().isoformat(),
            worker_id,
        ),
    )
    await db.commit()


async def record_opt_out(
    db: aiosqlite.Connection, worker_id: int, channel: str
) -> None:
    await db.execute(
        """UPDATE workers SET
           sms_consent_status='revoked', voice_consent_status='revoked',
           opt_out_timestamp=?, opt_out_channel=?, updated_at=?
           WHERE id=?""",
        (datetime.utcnow().isoformat(), channel, datetime.utcnow().isoformat(), worker_id),
    )
    await db.commit()


# ── shifts ────────────────────────────────────────────────────────────────────

async def get_shift(db: aiosqlite.Connection, shift_id: int) -> Optional[dict]:
    async with db.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)) as cur:
        row = await cur.fetchone()
    return _decode("shifts", row) if row else None


async def insert_shift(db: aiosqlite.Connection, data: dict) -> int:
    d = _encode_json("shifts", data)
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """INSERT INTO shifts
           (location_id, schedule_id, scheduling_platform_id, role, date, start_time, end_time, spans_midnight, pay_rate,
            requirements, status, source_platform, shift_label, notes, published_state, escalated_from_worker_id, reminder_sent_at,
            confirmation_requested_at, worker_confirmed_at, worker_declined_at, confirmation_escalated_at,
            check_in_requested_at, checked_in_at, late_reported_at, late_eta_minutes, check_in_escalated_at,
            attendance_action_state, attendance_action_updated_at, created_at, updated_at)
           VALUES (:location_id,:schedule_id,:scheduling_platform_id,:role,:date,:start_time,:end_time,:spans_midnight,:pay_rate,
                   :requirements,:status,:source_platform,:shift_label,:notes,:published_state,:escalated_from_worker_id,:reminder_sent_at,
                   :confirmation_requested_at,:worker_confirmed_at,:worker_declined_at,:confirmation_escalated_at,
                   :check_in_requested_at,:checked_in_at,:late_reported_at,:late_eta_minutes,:check_in_escalated_at,
                   :attendance_action_state,:attendance_action_updated_at,:created_at,:updated_at)""",
        {
            "location_id": d.get("location_id"),
            "schedule_id": d.get("schedule_id"),
            "scheduling_platform_id": d.get("scheduling_platform_id"),
            "role": d["role"],
            "date": str(d["date"]),
            "start_time": str(d["start_time"]),
            "end_time": str(d["end_time"]),
            "spans_midnight": int(bool(d.get("spans_midnight", False))),
            "pay_rate": d.get("pay_rate", 0.0),
            "requirements": d.get("requirements", "[]"),
            "status": d.get("status", "scheduled"),
            "source_platform": d.get("source_platform", "backfill_native"),
            "shift_label": d.get("shift_label"),
            "notes": d.get("notes"),
            "published_state": d.get("published_state"),
            "escalated_from_worker_id": d.get("escalated_from_worker_id"),
            "reminder_sent_at": d.get("reminder_sent_at"),
            "confirmation_requested_at": d.get("confirmation_requested_at"),
            "worker_confirmed_at": d.get("worker_confirmed_at"),
            "worker_declined_at": d.get("worker_declined_at"),
            "confirmation_escalated_at": d.get("confirmation_escalated_at"),
            "check_in_requested_at": d.get("check_in_requested_at"),
            "checked_in_at": d.get("checked_in_at"),
            "late_reported_at": d.get("late_reported_at"),
            "late_eta_minutes": d.get("late_eta_minutes"),
            "check_in_escalated_at": d.get("check_in_escalated_at"),
            "attendance_action_state": d.get("attendance_action_state"),
            "attendance_action_updated_at": d.get("attendance_action_updated_at"),
            "created_at": d.get("created_at", now),
            "updated_at": d.get("updated_at", now),
        },
    )
    await db.commit()
    return cur.lastrowid


async def list_shifts(
    db: aiosqlite.Connection,
    location_id: Optional[int] = None,
    status: Optional[str] = None,
    schedule_id: Optional[int] = None,
) -> list[dict]:
    query = "SELECT * FROM shifts"
    clauses: list[str] = []
    params: list[Any] = []
    if location_id is not None:
        clauses.append("location_id=?")
        params.append(location_id)
    if schedule_id is not None:
        clauses.append("schedule_id=?")
        params.append(schedule_id)
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
        "schedule_id",
        "scheduling_platform_id",
        "role",
        "date",
        "start_time",
        "end_time",
        "spans_midnight",
        "pay_rate",
        "requirements",
        "status",
        "called_out_by",
        "filled_by",
        "fill_tier",
        "escalated_from_worker_id",
        "source_platform",
        "shift_label",
        "notes",
        "published_state",
        "reminder_sent_at",
        "confirmation_requested_at",
        "worker_confirmed_at",
        "worker_declined_at",
        "confirmation_escalated_at",
        "check_in_requested_at",
        "checked_in_at",
        "late_reported_at",
        "late_eta_minutes",
        "check_in_escalated_at",
        "attendance_action_state",
        "attendance_action_updated_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("shifts", updates)
    normalized = {
        key: str(value) if key in {"date", "start_time", "end_time"} and value is not None else value
        for key, value in encoded.items()
    }
    normalized["updated_at"] = datetime.utcnow().isoformat()
    if "spans_midnight" in normalized:
        normalized["spans_midnight"] = int(bool(normalized["spans_midnight"]))
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
           , updated_at=?
           WHERE id=?""",
        (status, filled_by, fill_tier, called_out_by, datetime.utcnow().isoformat(), shift_id),
    )
    await db.commit()


async def delete_shift(db: aiosqlite.Connection, shift_id: int) -> None:
    await db.execute("DELETE FROM shifts WHERE id=?", (shift_id,))
    await db.commit()


# ── schedules ─────────────────────────────────────────────────────────────────

async def get_schedule(db: aiosqlite.Connection, schedule_id: int) -> Optional[dict]:
    async with db.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_schedule_by_location_week(
    db: aiosqlite.Connection,
    location_id: int,
    week_start_date: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM schedules WHERE location_id=? AND week_start_date=?",
        (location_id, week_start_date),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_latest_schedule_for_location(
    db: aiosqlite.Connection,
    location_id: int,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM schedules WHERE location_id=? ORDER BY week_start_date DESC, id DESC LIMIT 1",
        (location_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def list_schedules_for_location(
    db: aiosqlite.Connection,
    location_id: int,
) -> list[dict]:
    async with db.execute(
        """
        SELECT *
        FROM schedules
        WHERE location_id=?
        ORDER BY week_start_date DESC, id DESC
        """,
        (location_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def insert_schedule(db: aiosqlite.Connection, data: dict) -> int:
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """INSERT INTO schedules
           (location_id, week_start_date, week_end_date, lifecycle_state, current_version_id,
            derived_from_schedule_id, created_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            data["location_id"],
            data["week_start_date"],
            data["week_end_date"],
            data.get("lifecycle_state", "draft"),
            data.get("current_version_id"),
            data.get("derived_from_schedule_id"),
            data.get("created_by"),
            data.get("created_at", now),
            data.get("updated_at", now),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_schedule(db: aiosqlite.Connection, schedule_id: int, data: dict) -> None:
    allowed = {
        "week_start_date",
        "week_end_date",
        "lifecycle_state",
        "current_version_id",
        "derived_from_schedule_id",
        "created_by",
        "created_at",
        "updated_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    if "updated_at" not in updates:
        updates["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{key}=?" for key in updates)
    await db.execute(
        f"UPDATE schedules SET {cols} WHERE id=?",
        (*updates.values(), schedule_id),
    )
    await db.commit()


async def insert_schedule_version(db: aiosqlite.Connection, data: dict) -> int:
    encoded = _encode_json("schedule_versions", data)
    cur = await db.execute(
        """INSERT INTO schedule_versions
           (schedule_id, version_number, version_type, snapshot_json, change_summary_json,
            published_at, published_by, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            encoded["schedule_id"],
            encoded["version_number"],
            encoded["version_type"],
            encoded.get("snapshot_json", "{}"),
            encoded.get("change_summary_json", "{}"),
            encoded.get("published_at"),
            encoded.get("published_by"),
            encoded.get("created_at", datetime.utcnow().isoformat()),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def list_schedule_versions(
    db: aiosqlite.Connection,
    schedule_id: int,
) -> list[dict]:
    async with db.execute(
        "SELECT * FROM schedule_versions WHERE schedule_id=? ORDER BY version_number ASC, id ASC",
        (schedule_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [_decode("schedule_versions", row) for row in rows]


async def get_schedule_version(
    db: aiosqlite.Connection,
    version_id: int,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM schedule_versions WHERE id=?",
        (version_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("schedule_versions", row) if row else None


async def get_next_schedule_version_number(
    db: aiosqlite.Connection,
    schedule_id: int,
) -> int:
    async with db.execute(
        "SELECT COALESCE(MAX(version_number), 0) AS max_version FROM schedule_versions WHERE schedule_id=?",
        (schedule_id,),
    ) as cur:
        row = await cur.fetchone()
    return int((row["max_version"] if row else 0) or 0) + 1


# ── schedule templates ────────────────────────────────────────────────────────

async def get_schedule_template(
    db: aiosqlite.Connection,
    template_id: int,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM schedule_templates WHERE id=?",
        (template_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_schedule_template_shift(
    db: aiosqlite.Connection,
    template_shift_id: int,
) -> Optional[dict]:
    async with db.execute(
        """
        SELECT sts.*, w.name AS worker_name, w.phone AS worker_phone
        FROM schedule_template_shifts sts
        LEFT JOIN workers w ON w.id = sts.worker_id
        WHERE sts.id=?
        """,
        (template_shift_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("schedule_template_shifts", row) if row else None


async def list_schedule_templates_for_location(
    db: aiosqlite.Connection,
    location_id: int,
) -> list[dict]:
    async with db.execute(
        """
        SELECT *
        FROM schedule_templates
        WHERE location_id=?
        ORDER BY updated_at DESC, id DESC
        """,
        (location_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def insert_schedule_template(db: aiosqlite.Connection, data: dict) -> int:
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """
        INSERT INTO schedule_templates
        (location_id, name, description, source_schedule_id, created_by, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            data["location_id"],
            data["name"],
            data.get("description"),
            data.get("source_schedule_id"),
            data.get("created_by"),
            data.get("created_at", now),
            data.get("updated_at", now),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_schedule_template(db: aiosqlite.Connection, template_id: int, data: dict) -> None:
    allowed = {
        "name",
        "description",
        "source_schedule_id",
        "created_by",
        "created_at",
        "updated_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    if "updated_at" not in updates:
        updates["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{key}=?" for key in updates)
    await db.execute(
        f"UPDATE schedule_templates SET {cols} WHERE id=?",
        (*updates.values(), template_id),
    )
    await db.commit()


async def delete_schedule_template(
    db: aiosqlite.Connection,
    template_id: int,
) -> None:
    await db.execute("DELETE FROM schedule_templates WHERE id=?", (template_id,))
    await db.commit()


async def delete_schedule_template_shifts(
    db: aiosqlite.Connection,
    template_id: int,
) -> None:
    await db.execute(
        "DELETE FROM schedule_template_shifts WHERE template_id=?",
        (template_id,),
    )
    await db.commit()


async def insert_schedule_template_shift(db: aiosqlite.Connection, data: dict) -> int:
    encoded = _encode_json("schedule_template_shifts", data)
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """
        INSERT INTO schedule_template_shifts
        (template_id, day_of_week, role, start_time, end_time, spans_midnight, pay_rate,
         requirements, shift_label, notes, worker_id, assignment_status, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            encoded["template_id"],
            encoded["day_of_week"],
            encoded["role"],
            str(encoded["start_time"]),
            str(encoded["end_time"]),
            int(bool(encoded.get("spans_midnight", False))),
            encoded.get("pay_rate", 0.0),
            encoded.get("requirements", "[]"),
            encoded.get("shift_label"),
            encoded.get("notes"),
            encoded.get("worker_id"),
            encoded.get("assignment_status", "open"),
            encoded.get("created_at", now),
            encoded.get("updated_at", now),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_schedule_template_shift(
    db: aiosqlite.Connection,
    template_shift_id: int,
    data: dict,
) -> None:
    allowed = {
        "day_of_week",
        "role",
        "start_time",
        "end_time",
        "spans_midnight",
        "pay_rate",
        "requirements",
        "shift_label",
        "notes",
        "worker_id",
        "assignment_status",
        "created_at",
        "updated_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    if "updated_at" not in updates:
        updates["updated_at"] = datetime.utcnow().isoformat()
    encoded = _encode_json("schedule_template_shifts", updates)
    normalized = {}
    for key, value in encoded.items():
        if key in {"start_time", "end_time"} and value is not None:
            normalized[key] = str(value)
        elif key == "spans_midnight":
            normalized[key] = int(bool(value))
        else:
            normalized[key] = value
    cols = ", ".join(f"{key}=?" for key in normalized)
    await db.execute(
        f"UPDATE schedule_template_shifts SET {cols} WHERE id=?",
        (*normalized.values(), template_shift_id),
    )
    await db.commit()


async def list_schedule_template_shifts(
    db: aiosqlite.Connection,
    template_id: int,
) -> list[dict]:
    async with db.execute(
        """
        SELECT sts.*, w.name AS worker_name, w.phone AS worker_phone
        FROM schedule_template_shifts sts
        LEFT JOIN workers w ON w.id = sts.worker_id
        WHERE sts.template_id=?
        ORDER BY sts.day_of_week ASC, sts.start_time ASC, sts.id ASC
        """,
        (template_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [_decode("schedule_template_shifts", row) for row in rows]


async def delete_schedule_template_shift_by_id(
    db: aiosqlite.Connection,
    template_shift_id: int,
) -> None:
    await db.execute("DELETE FROM schedule_template_shifts WHERE id=?", (template_shift_id,))
    await db.commit()


# ── shift assignments ────────────────────────────────────────────────────────

async def get_shift_assignment(
    db: aiosqlite.Connection,
    shift_id: int,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM shift_assignments WHERE shift_id=?",
        (shift_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_shift_assignment_with_worker(
    db: aiosqlite.Connection,
    shift_id: int,
) -> Optional[dict]:
    async with db.execute(
        """
        SELECT sa.*, w.name AS worker_name, w.phone AS worker_phone
        FROM shift_assignments sa
        LEFT JOIN workers w ON w.id = sa.worker_id
        WHERE sa.shift_id=?
        """,
        (shift_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def list_shift_assignments_for_schedule(
    db: aiosqlite.Connection,
    schedule_id: int,
) -> list[dict]:
    async with db.execute(
        """
        SELECT sa.*, s.schedule_id, w.name AS worker_name, w.phone AS worker_phone
        FROM shift_assignments sa
        JOIN shifts s ON s.id = sa.shift_id
        LEFT JOIN workers w ON w.id = sa.worker_id
        WHERE s.schedule_id=?
        ORDER BY sa.shift_id ASC
        """,
        (schedule_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def list_assigned_schedule_shifts_for_worker(
    db: aiosqlite.Connection,
    worker_id: int,
    *,
    published_only: bool = False,
) -> list[dict]:
    query = """
        SELECT
            s.*,
            sa.assignment_status,
            sc.week_start_date,
            sc.lifecycle_state,
            l.name AS location_name,
            o.name AS organization_name
        FROM shift_assignments sa
        JOIN shifts s ON s.id = sa.shift_id
        LEFT JOIN schedules sc ON sc.id = s.schedule_id
        LEFT JOIN locations l ON l.id = s.location_id
        LEFT JOIN organizations o ON o.id = l.organization_id
        WHERE sa.worker_id=?
          AND sa.assignment_status IN ('assigned', 'claimed', 'confirmed')
    """
    params: list[object] = [worker_id]
    if published_only:
        query += " AND s.published_state IN ('published', 'amended')"
    query += " ORDER BY s.date ASC, s.start_time ASC, s.id ASC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("shifts", row) for row in rows]


async def upsert_shift_assignment(db: aiosqlite.Connection, data: dict) -> int:
    existing = await get_shift_assignment(db, data["shift_id"])
    now = datetime.utcnow().isoformat()
    if existing is None:
        cur = await db.execute(
            """INSERT INTO shift_assignments
               (shift_id, worker_id, assignment_status, source, created_at, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (
                data["shift_id"],
                data.get("worker_id"),
                data.get("assignment_status", "open"),
                data.get("source", "manual"),
                data.get("created_at", now),
                data.get("updated_at", now),
            ),
        )
        await db.commit()
        return cur.lastrowid

    assignment_changed = (
        existing.get("worker_id") != data.get("worker_id")
        or existing.get("assignment_status") != data.get("assignment_status", existing.get("assignment_status", "open"))
    )
    await db.execute(
        """UPDATE shift_assignments
           SET worker_id=?, assignment_status=?, source=?, updated_at=?
           WHERE shift_id=?""",
        (
            data.get("worker_id"),
            data.get("assignment_status", existing.get("assignment_status", "open")),
            data.get("source", existing.get("source", "manual")),
            data.get("updated_at", now),
            data["shift_id"],
        ),
    )
    if assignment_changed:
        await db.execute(
            """UPDATE shifts
               SET confirmation_requested_at=NULL,
                   worker_confirmed_at=NULL,
                   worker_declined_at=NULL,
                   check_in_requested_at=NULL,
                   checked_in_at=NULL,
                   late_reported_at=NULL,
                   late_eta_minutes=NULL,
                   attendance_action_state=NULL,
                   attendance_action_updated_at=NULL
               WHERE id=?""",
            (data["shift_id"],),
        )
    await db.commit()
    return int(existing["id"])


async def delete_shift_assignment(db: aiosqlite.Connection, shift_id: int) -> None:
    await db.execute("DELETE FROM shift_assignments WHERE shift_id=?", (shift_id,))
    await db.commit()


# ── import jobs ───────────────────────────────────────────────────────────────

async def insert_import_job(db: aiosqlite.Connection, data: dict) -> int:
    encoded = _encode_json("import_jobs", data)
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """INSERT INTO import_jobs
           (location_id, import_type, filename, status, mapping_json, summary_json, columns_json,
            uploaded_csv, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            encoded["location_id"],
            encoded["import_type"],
            encoded.get("filename"),
            encoded.get("status", "uploaded"),
            encoded.get("mapping_json", "{}"),
            encoded.get("summary_json", "{}"),
            encoded.get("columns_json", "[]"),
            encoded.get("uploaded_csv"),
            encoded.get("created_at", now),
            encoded.get("updated_at", now),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def get_import_job(db: aiosqlite.Connection, job_id: int) -> Optional[dict]:
    async with db.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)) as cur:
        row = await cur.fetchone()
    return _decode("import_jobs", row) if row else None


async def get_latest_import_job_for_location(
    db: aiosqlite.Connection,
    location_id: int,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM import_jobs WHERE location_id=? ORDER BY updated_at DESC, id DESC LIMIT 1",
        (location_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("import_jobs", row) if row else None


async def get_import_row_result(
    db: aiosqlite.Connection,
    row_id: int,
) -> Optional[dict]:
    async with db.execute("SELECT * FROM import_row_results WHERE id=?", (row_id,)) as cur:
        row = await cur.fetchone()
    return _decode("import_row_results", row) if row else None


async def update_import_job(db: aiosqlite.Connection, job_id: int, data: dict) -> None:
    allowed = {
        "filename",
        "status",
        "mapping_json",
        "summary_json",
        "columns_json",
        "uploaded_csv",
        "updated_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    if "updated_at" not in updates:
        updates["updated_at"] = datetime.utcnow().isoformat()
    encoded = _encode_json("import_jobs", updates)
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE import_jobs SET {cols} WHERE id=?",
        (*encoded.values(), job_id),
    )
    await db.commit()


async def clear_import_row_results(db: aiosqlite.Connection, job_id: int) -> None:
    await db.execute("DELETE FROM import_row_results WHERE import_job_id=?", (job_id,))
    await db.commit()


async def insert_import_row_result(db: aiosqlite.Connection, data: dict) -> int:
    encoded = _encode_json("import_row_results", data)
    cur = await db.execute(
        """INSERT INTO import_row_results
           (import_job_id, row_number, entity_type, outcome, error_code, error_message,
            raw_payload, normalized_payload, resolution_action, resolved_at, resolved_by,
            committed_at, committed_entity_id, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            encoded["import_job_id"],
            encoded["row_number"],
            encoded["entity_type"],
            encoded["outcome"],
            encoded.get("error_code"),
            encoded.get("error_message"),
            encoded.get("raw_payload", "{}"),
            encoded.get("normalized_payload"),
            encoded.get("resolution_action"),
            encoded.get("resolved_at"),
            encoded.get("resolved_by"),
            encoded.get("committed_at"),
            encoded.get("committed_entity_id"),
            encoded.get("created_at", datetime.utcnow().isoformat()),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_import_row_result(db: aiosqlite.Connection, row_id: int, data: dict) -> None:
    allowed = {
        "entity_type",
        "outcome",
        "error_code",
        "error_message",
        "raw_payload",
        "normalized_payload",
        "resolution_action",
        "resolved_at",
        "resolved_by",
        "committed_at",
        "committed_entity_id",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("import_row_results", updates)
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE import_row_results SET {cols} WHERE id=?",
        (*encoded.values(), row_id),
    )
    await db.commit()


async def list_import_row_results(
    db: aiosqlite.Connection,
    job_id: int,
) -> list[dict]:
    async with db.execute(
        """
        SELECT * FROM import_row_results
        WHERE import_job_id=?
        ORDER BY row_number ASC, id ASC
        """,
        (job_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [_decode("import_row_results", row) for row in rows]


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
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        "INSERT INTO cascades (shift_id, outreach_mode, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (shift_id, outreach_mode, now, now),
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
        "pending_claim_worker_id",
        "pending_claim_at",
        "standby_queue",
        "manager_approved_tier3",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("cascades", updates)
    encoded["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{k}=?" for k in encoded)
    await db.execute(
        f"UPDATE cascades SET {cols} WHERE id=?", (*encoded.values(), cascade_id)
    )
    await db.commit()


async def reserve_cascade_confirmation(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
) -> bool:
    cur = await db.execute(
        """UPDATE cascades
           SET confirmed_worker_id=?
           WHERE id=?
             AND status='active'
             AND confirmed_worker_id IS NULL""",
        (worker_id, cascade_id),
    )
    await db.commit()
    return int(cur.rowcount or 0) > 0


async def reserve_cascade_pending_claim(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
    *,
    pending_claim_at: str,
    standby_queue: Optional[list[int]] = None,
) -> bool:
    if standby_queue is None:
        cur = await db.execute(
            """UPDATE cascades
               SET pending_claim_worker_id=?, pending_claim_at=?
               WHERE id=?
                 AND status='active'
                 AND confirmed_worker_id IS NULL
                 AND pending_claim_worker_id IS NULL""",
            (worker_id, pending_claim_at, cascade_id),
        )
    else:
        cur = await db.execute(
            """UPDATE cascades
               SET pending_claim_worker_id=?, pending_claim_at=?, standby_queue=?
               WHERE id=?
                 AND status='active'
                 AND confirmed_worker_id IS NULL
                 AND pending_claim_worker_id IS NULL""",
            (worker_id, pending_claim_at, json.dumps(standby_queue), cascade_id),
        )
    await db.commit()
    return int(cur.rowcount or 0) > 0


async def approve_cascade_pending_claim(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
) -> bool:
    cur = await db.execute(
        """UPDATE cascades
           SET confirmed_worker_id=?, pending_claim_worker_id=NULL, pending_claim_at=NULL
           WHERE id=?
             AND status='active'
             AND confirmed_worker_id IS NULL
             AND pending_claim_worker_id=?""",
        (worker_id, cascade_id, worker_id),
    )
    await db.commit()
    return int(cur.rowcount or 0) > 0


async def clear_cascade_pending_claim(
    db: aiosqlite.Connection,
    cascade_id: int,
    *,
    worker_id: Optional[int] = None,
) -> bool:
    if worker_id is None:
        cur = await db.execute(
            """UPDATE cascades
               SET pending_claim_worker_id=NULL, pending_claim_at=NULL
               WHERE id=?
                 AND pending_claim_worker_id IS NOT NULL""",
            (cascade_id,),
        )
    else:
        cur = await db.execute(
            """UPDATE cascades
               SET pending_claim_worker_id=NULL, pending_claim_at=NULL
               WHERE id=?
                 AND pending_claim_worker_id=?""",
            (cascade_id, worker_id),
        )
    await db.commit()
    return int(cur.rowcount or 0) > 0


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

async def get_outreach_attempt(db: aiosqlite.Connection, attempt_id: int) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM outreach_attempts WHERE id=?",
        (attempt_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def insert_outreach_attempt(db: aiosqlite.Connection, data: dict) -> int:
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """INSERT INTO outreach_attempts
           (cascade_id, worker_id, tier, channel, status, outcome, standby_position,
            promoted_at, sent_at, responded_at, conversation_summary, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["cascade_id"],
            data["worker_id"],
            data["tier"],
            data.get("channel", "sms"),
            data.get("status", "sent"),
            data.get("outcome"),
            data.get("standby_position"),
            data.get("promoted_at"),
            data.get("sent_at", now),
            data.get("responded_at"),
            data.get("conversation_summary"),
            data.get("created_at", now),
            data.get("updated_at", now),
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
    updates["updated_at"] = datetime.utcnow().isoformat()
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


# ── dashboard auth ────────────────────────────────────────────────────────────

async def insert_dashboard_access_request(db: aiosqlite.Connection, data: dict) -> int:
    encoded = _encode_json("dashboard_access_requests", data)
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """
        INSERT INTO dashboard_access_requests
        (phone, organization_id, location_ids_json, purpose, token_hash, session_id, verification_sid, channel, status,
         expires_at, used_at, verified_at, check_count, last_check_at, requested_at, created_at, updated_at,
         location_manager_invite_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            encoded["phone"],
            encoded.get("organization_id"),
            encoded.get("location_ids_json", "[]"),
            encoded.get("purpose", "login"),
            encoded["token_hash"],
            encoded.get("session_id"),
            encoded.get("verification_sid"),
            encoded.get("channel", "sms"),
            encoded.get("status", "pending"),
            encoded["expires_at"],
            encoded.get("used_at"),
            encoded.get("verified_at"),
            encoded.get("check_count", 0),
            encoded.get("last_check_at"),
            encoded.get("requested_at", now),
            encoded.get("created_at", now),
            encoded.get("updated_at", now),
            encoded.get("location_manager_invite_id"),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def get_dashboard_access_request_by_token_hash(
    db: aiosqlite.Connection,
    token_hash: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM dashboard_access_requests WHERE token_hash=?",
        (token_hash,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("dashboard_access_requests", row) if row else None


async def get_dashboard_access_request(
    db: aiosqlite.Connection,
    request_id: int,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM dashboard_access_requests WHERE id=?",
        (request_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("dashboard_access_requests", row) if row else None


async def get_latest_dashboard_access_request_for_phone(
    db: aiosqlite.Connection,
    phone: str,
    *,
    status: Optional[str] = None,
    purpose: Optional[str] = None,
) -> Optional[dict]:
    query = "SELECT * FROM dashboard_access_requests WHERE phone=?"
    params: list[Any] = [phone]
    if status is not None:
        query += " AND status=?"
        params.append(status)
    if purpose is not None:
        query += " AND purpose=?"
        params.append(purpose)
    query += " ORDER BY id DESC LIMIT 1"
    async with db.execute(query, params) as cur:
        row = await cur.fetchone()
    return _decode("dashboard_access_requests", row) if row else None


async def supersede_pending_dashboard_access_requests_for_phone(
    db: aiosqlite.Connection,
    phone: str,
) -> None:
    now = datetime.utcnow().isoformat()
    await db.execute(
        """
        UPDATE dashboard_access_requests
        SET status='superseded', updated_at=?
        WHERE phone=? AND status='pending'
        """,
        (now, phone),
    )
    await db.commit()


async def update_dashboard_access_request(
    db: aiosqlite.Connection,
    request_id: int,
    data: dict,
) -> None:
    allowed = {
        "phone",
        "organization_id",
        "location_ids_json",
        "purpose",
        "token_hash",
        "session_id",
        "location_manager_invite_id",
        "verification_sid",
        "channel",
        "status",
        "expires_at",
        "used_at",
        "verified_at",
        "check_count",
        "last_check_at",
        "requested_at",
        "created_at",
        "updated_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("dashboard_access_requests", updates)
    encoded["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE dashboard_access_requests SET {cols} WHERE id=?",
        (*encoded.values(), request_id),
    )
    await db.commit()


async def insert_dashboard_session(db: aiosqlite.Connection, data: dict) -> int:
    encoded = _encode_json("dashboard_sessions", data)
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """
        INSERT INTO dashboard_sessions
        (organization_id, location_ids_json, subject_phone, session_token_hash, access_request_id,
         status, verified_at, step_up_verified_at, expires_at, last_seen_at, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            encoded.get("organization_id"),
            encoded.get("location_ids_json", "[]"),
            encoded["subject_phone"],
            encoded["session_token_hash"],
            encoded.get("access_request_id"),
            encoded.get("status", "active"),
            encoded.get("verified_at"),
            encoded.get("step_up_verified_at"),
            encoded["expires_at"],
            encoded.get("last_seen_at"),
            encoded.get("created_at", now),
            encoded.get("updated_at", now),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def get_dashboard_session_by_token_hash(
    db: aiosqlite.Connection,
    token_hash: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM dashboard_sessions WHERE session_token_hash=?",
        (token_hash,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("dashboard_sessions", row) if row else None


async def get_dashboard_session(
    db: aiosqlite.Connection,
    session_id: int,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM dashboard_sessions WHERE id=?",
        (session_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("dashboard_sessions", row) if row else None


async def update_dashboard_session(
    db: aiosqlite.Connection,
    session_id: int,
    data: dict,
) -> None:
    allowed = {
        "organization_id",
        "location_ids_json",
        "subject_phone",
        "session_token_hash",
        "access_request_id",
        "status",
        "verified_at",
        "step_up_verified_at",
        "expires_at",
        "last_seen_at",
        "created_at",
        "updated_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("dashboard_sessions", updates)
    encoded["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE dashboard_sessions SET {cols} WHERE id=?",
        (*encoded.values(), session_id),
    )
    await db.commit()


async def insert_setup_access_token(db: aiosqlite.Connection, data: dict) -> int:
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """
        INSERT INTO setup_access_tokens
        (location_id, token_hash, status, source, expires_at, last_seen_at, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            data["location_id"],
            data["token_hash"],
            data.get("status", "active"),
            data.get("source"),
            data["expires_at"],
            data.get("last_seen_at"),
            data.get("created_at", now),
            data.get("updated_at", now),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def get_setup_access_token_by_token_hash(
    db: aiosqlite.Connection,
    token_hash: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM setup_access_tokens WHERE token_hash=?",
        (token_hash,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def update_setup_access_token(
    db: aiosqlite.Connection,
    token_id: int,
    data: dict,
) -> None:
    allowed = {
        "location_id",
        "token_hash",
        "status",
        "source",
        "expires_at",
        "last_seen_at",
        "created_at",
        "updated_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{key}=?" for key in updates)
    await db.execute(
        f"UPDATE setup_access_tokens SET {cols} WHERE id=?",
        (*updates.values(), token_id),
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


# ── ops jobs ──────────────────────────────────────────────────────────────────

async def get_ops_job(db: aiosqlite.Connection, job_id: int) -> Optional[dict]:
    async with db.execute("SELECT * FROM ops_jobs WHERE id=?", (job_id,)) as cur:
        row = await cur.fetchone()
    return _decode("ops_jobs", row) if row else None


async def get_ops_job_by_idempotency_key(
    db: aiosqlite.Connection,
    idempotency_key: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM ops_jobs WHERE idempotency_key=?",
        (idempotency_key,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("ops_jobs", row) if row else None


async def insert_ops_job(db: aiosqlite.Connection, data: dict) -> int:
    idempotency_key = data.get("idempotency_key")
    if idempotency_key:
        existing = await get_ops_job_by_idempotency_key(db, idempotency_key)
        if existing is not None:
            return int(existing["id"])

    encoded = _encode_json("ops_jobs", data)
    now = datetime.utcnow().isoformat()
    cur = await db.execute(
        """
        INSERT INTO ops_jobs
        (job_type, location_id, priority, payload_json, status, attempt_count, max_attempts,
         next_run_at, started_at, completed_at, last_error, idempotency_key, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            encoded["job_type"],
            encoded.get("location_id"),
            encoded.get("priority", 50),
            encoded.get("payload_json", "{}"),
            encoded.get("status", "queued"),
            encoded.get("attempt_count", 0),
            encoded.get("max_attempts", 3),
            encoded.get("next_run_at", now),
            encoded.get("started_at"),
            encoded.get("completed_at"),
            encoded.get("last_error"),
            idempotency_key,
            encoded.get("created_at", now),
            encoded.get("updated_at", now),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_ops_job(db: aiosqlite.Connection, job_id: int, data: dict) -> None:
    allowed = {
        "status",
        "priority",
        "payload_json",
        "attempt_count",
        "max_attempts",
        "next_run_at",
        "started_at",
        "completed_at",
        "last_error",
        "idempotency_key",
        "created_at",
        "updated_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("ops_jobs", updates)
    encoded["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE ops_jobs SET {cols} WHERE id=?",
        (*encoded.values(), job_id),
    )
    await db.commit()


async def list_ops_jobs(
    db: aiosqlite.Connection,
    *,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    location_id: Optional[int] = None,
    limit: int = 100,
) -> list[dict]:
    query = "SELECT * FROM ops_jobs"
    clauses: list[str] = []
    params: list[Any] = []
    if status is not None:
        clauses.append("status=?")
        params.append(status)
    if job_type is not None:
        clauses.append("job_type=?")
        params.append(job_type)
    if location_id is not None:
        clauses.append("location_id=?")
        params.append(location_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY priority ASC, next_run_at ASC, id ASC LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("ops_jobs", row) for row in rows]


# ── ai action requests ───────────────────────────────────────────────────────

async def get_ai_action_request(
    db: aiosqlite.Connection,
    action_request_id: int,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM ai_action_requests WHERE id=?",
        (action_request_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("ai_action_requests", row) if row else None


async def insert_ai_action_request(db: aiosqlite.Connection, data: dict) -> int:
    encoded = _encode_json("ai_action_requests", data)
    cur = await db.execute(
        """INSERT INTO ai_action_requests
           (channel, actor_type, actor_id, organization_id, location_id, original_text,
            intent_type, status, risk_class, requires_confirmation, redirect_reason,
            action_plan_json, result_summary_json, error_code, error_message, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            encoded["channel"],
            encoded["actor_type"],
            encoded.get("actor_id"),
            encoded.get("organization_id"),
            encoded["location_id"],
            encoded["original_text"],
            encoded.get("intent_type"),
            encoded.get("status", "received"),
            encoded.get("risk_class"),
            int(bool(encoded.get("requires_confirmation", False))),
            encoded.get("redirect_reason"),
            encoded.get("action_plan_json", "{}"),
            encoded.get("result_summary_json", "{}"),
            encoded.get("error_code"),
            encoded.get("error_message"),
            encoded.get("created_at", datetime.utcnow().isoformat()),
            encoded.get("updated_at", datetime.utcnow().isoformat()),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_ai_action_request(
    db: aiosqlite.Connection,
    action_request_id: int,
    data: dict,
) -> None:
    allowed = {
        "intent_type",
        "status",
        "risk_class",
        "requires_confirmation",
        "redirect_reason",
        "action_plan_json",
        "result_summary_json",
        "error_code",
        "error_message",
        "updated_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("ai_action_requests", updates)
    if "requires_confirmation" in encoded:
        encoded["requires_confirmation"] = int(bool(encoded["requires_confirmation"]))
    if "updated_at" not in encoded:
        encoded["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE ai_action_requests SET {cols} WHERE id=?",
        (*encoded.values(), action_request_id),
    )
    await db.commit()


async def list_ai_action_requests_for_location(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    status: str | None = None,
    channel: str | None = None,
    created_after: str | None = None,
    limit: int = 20,
) -> list[dict]:
    where_clauses = ["location_id=?"]
    params: list[Any] = [location_id]
    if status:
        where_clauses.append("status=?")
        params.append(status)
    if channel:
        where_clauses.append("channel=?")
        params.append(channel)
    if created_after:
        where_clauses.append("created_at>=?")
        params.append(created_after)
    sql = f"""
        SELECT *
        FROM ai_action_requests
        WHERE {' AND '.join(where_clauses)}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
    """
    params.append(limit)
    async with db.execute(sql, tuple(params)) as cur:
        rows = await cur.fetchall()
    return [_decode("ai_action_requests", row) for row in rows]


async def insert_ai_action_entity(db: aiosqlite.Connection, data: dict) -> int:
    encoded = _encode_json("ai_action_entities", data)
    cur = await db.execute(
        """INSERT INTO ai_action_entities
           (ai_action_request_id, entity_type, entity_id, raw_reference, normalized_reference,
            confidence_score, resolution_status, candidate_payload_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            encoded["ai_action_request_id"],
            encoded["entity_type"],
            encoded.get("entity_id"),
            encoded.get("raw_reference"),
            encoded.get("normalized_reference"),
            encoded.get("confidence_score"),
            encoded["resolution_status"],
            encoded.get("candidate_payload_json", "[]"),
            encoded.get("created_at", datetime.utcnow().isoformat()),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def list_ai_action_entities(
    db: aiosqlite.Connection,
    ai_action_request_id: int,
) -> list[dict]:
    async with db.execute(
        "SELECT * FROM ai_action_entities WHERE ai_action_request_id=? ORDER BY id ASC",
        (ai_action_request_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [_decode("ai_action_entities", row) for row in rows]


async def insert_ai_action_event(db: aiosqlite.Connection, data: dict) -> int:
    encoded = _encode_json("ai_action_events", data)
    cur = await db.execute(
        """INSERT INTO ai_action_events
           (ai_action_request_id, event_type, payload_json, created_at)
           VALUES (?,?,?,?)""",
        (
            encoded["ai_action_request_id"],
            encoded["event_type"],
            encoded.get("payload_json", "{}"),
            encoded.get("created_at", datetime.utcnow().isoformat()),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def list_ai_action_events(
    db: aiosqlite.Connection,
    ai_action_request_id: int,
) -> list[dict]:
    async with db.execute(
        "SELECT * FROM ai_action_events WHERE ai_action_request_id=? ORDER BY id ASC",
        (ai_action_request_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [_decode("ai_action_events", row) for row in rows]


async def list_ai_action_events_for_request_ids(
    db: aiosqlite.Connection,
    request_ids: list[int],
    *,
    event_type: str | None = None,
) -> list[dict]:
    normalized_ids = [int(value) for value in request_ids if int(value) > 0]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    params: list[Any] = list(normalized_ids)
    where = [f"ai_action_request_id IN ({placeholders})"]
    if event_type:
        where.append("event_type=?")
        params.append(event_type)
    sql = f"""
        SELECT *
        FROM ai_action_events
        WHERE {' AND '.join(where)}
        ORDER BY ai_action_request_id ASC, id ASC
    """
    async with db.execute(sql, tuple(params)) as cur:
        rows = await cur.fetchall()
    return [_decode("ai_action_events", row) for row in rows]


async def list_recent_ai_action_requests(
    db: aiosqlite.Connection,
    *,
    location_id: int | None = None,
    organization_id: int | None = None,
    status: str | None = None,
    channel: str | None = None,
    limit: int = 50,
) -> list[dict]:
    where_clauses = ["1=1"]
    params: list[Any] = []
    if location_id is not None:
        where_clauses.append("r.location_id=?")
        params.append(location_id)
    if organization_id is not None:
        where_clauses.append("r.organization_id=?")
        params.append(organization_id)
    if status:
        where_clauses.append("r.status=?")
        params.append(status)
    if channel:
        where_clauses.append("r.channel=?")
        params.append(channel)
    sql = f"""
        SELECT r.*, l.name AS location_name
        FROM ai_action_requests r
        LEFT JOIN locations l ON l.id = r.location_id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT ?
    """
    params.append(limit)
    async with db.execute(sql, tuple(params)) as cur:
        rows = await cur.fetchall()
    return [_decode("ai_action_requests", row) for row in rows]


async def get_action_session_by_request_id(
    db: aiosqlite.Connection,
    ai_action_request_id: int,
) -> Optional[dict]:
    async with db.execute(
        """
        SELECT *
        FROM action_sessions
        WHERE ai_action_request_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (ai_action_request_id,),
    ) as cur:
        row = await cur.fetchone()
    return _decode("action_sessions", row) if row else None


async def get_latest_active_action_session_for_location(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    channel: str,
    actor_type: str,
) -> Optional[dict]:
    async with db.execute(
        """
        SELECT *
        FROM action_sessions
        WHERE location_id=?
          AND channel=?
          AND actor_type=?
          AND status='active'
        ORDER BY id DESC
        LIMIT 1
        """,
        (location_id, channel, actor_type),
    ) as cur:
        row = await cur.fetchone()
    return _decode("action_sessions", row) if row else None


async def insert_action_session(db: aiosqlite.Connection, data: dict) -> int:
    encoded = _encode_json("action_sessions", data)
    cur = await db.execute(
        """INSERT INTO action_sessions
           (ai_action_request_id, channel, actor_type, actor_id, organization_id, location_id,
            status, pending_prompt_type, pending_payload_json, expires_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            encoded["ai_action_request_id"],
            encoded["channel"],
            encoded["actor_type"],
            encoded.get("actor_id"),
            encoded.get("organization_id"),
            encoded["location_id"],
            encoded.get("status", "active"),
            encoded.get("pending_prompt_type"),
            encoded.get("pending_payload_json", "{}"),
            encoded.get("expires_at"),
            encoded.get("created_at", datetime.utcnow().isoformat()),
            encoded.get("updated_at", datetime.utcnow().isoformat()),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_action_session(
    db: aiosqlite.Connection,
    session_id: int,
    data: dict,
) -> None:
    allowed = {
        "status",
        "pending_prompt_type",
        "pending_payload_json",
        "expires_at",
        "updated_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return
    encoded = _encode_json("action_sessions", updates)
    if "updated_at" not in encoded:
        encoded["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{key}=?" for key in encoded)
    await db.execute(
        f"UPDATE action_sessions SET {cols} WHERE id=?",
        (*encoded.values(), session_id),
    )
    await db.commit()


async def list_action_sessions(
    db: aiosqlite.Connection,
    *,
    location_id: int | None = None,
    organization_id: int | None = None,
    status: str | None = None,
    channel: str | None = None,
    expired_before: str | None = None,
    limit: int = 50,
) -> list[dict]:
    where_clauses = ["1=1"]
    params: list[Any] = []
    if location_id is not None:
        where_clauses.append("s.location_id=?")
        params.append(location_id)
    if organization_id is not None:
        where_clauses.append("s.organization_id=?")
        params.append(organization_id)
    if status:
        where_clauses.append("s.status=?")
        params.append(status)
    if channel:
        where_clauses.append("s.channel=?")
        params.append(channel)
    if expired_before:
        where_clauses.append("s.expires_at IS NOT NULL")
        where_clauses.append("s.expires_at<=?")
        params.append(expired_before)
    sql = f"""
        SELECT
            s.*,
            r.status AS request_status,
            r.original_text AS request_text,
            r.action_plan_json AS request_action_plan_json,
            r.result_summary_json AS request_result_summary_json,
            l.name AS location_name
        FROM action_sessions s
        JOIN ai_action_requests r ON r.id = s.ai_action_request_id
        LEFT JOIN locations l ON l.id = s.location_id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY s.updated_at DESC, s.id DESC
        LIMIT ?
    """
    params.append(limit)
    async with db.execute(sql, tuple(params)) as cur:
        rows = await cur.fetchall()
    return [_decode("action_sessions", row) for row in rows]


async def claim_due_ops_jobs(
    db: aiosqlite.Connection,
    *,
    limit: int = 10,
    now_iso: Optional[str] = None,
) -> list[dict]:
    now = now_iso or datetime.utcnow().isoformat()
    async with db.execute(
        """
        SELECT id
        FROM ops_jobs
        WHERE status='queued' AND next_run_at<=?
        ORDER BY priority ASC, next_run_at ASC, id ASC
        LIMIT ?
        """,
        (now, limit),
    ) as cur:
        rows = await cur.fetchall()
    job_ids = [int(row["id"]) for row in rows]

    claimed: list[dict] = []
    for job_id in job_ids:
        await db.execute(
            """
            UPDATE ops_jobs
            SET status='running', started_at=?, attempt_count=attempt_count+1
            WHERE id=? AND status='queued'
            """,
            (now, job_id),
        )
        await db.commit()
        refreshed = await get_ops_job(db, job_id)
        if refreshed and refreshed["status"] == "running":
            claimed.append(refreshed)
    return claimed


async def claim_ops_job(
    db: aiosqlite.Connection,
    job_id: int,
    *,
    now_iso: Optional[str] = None,
) -> Optional[dict]:
    now = now_iso or datetime.utcnow().isoformat()
    await db.execute(
        """
        UPDATE ops_jobs
        SET status='running', started_at=?, attempt_count=attempt_count+1
        WHERE id=? AND status='queued'
        """,
        (now, job_id),
    )
    await db.commit()
    job = await get_ops_job(db, job_id)
    if job and job["status"] == "running":
        return job
    return None


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


async def get_webhook_receipt(
    db: aiosqlite.Connection,
    *,
    source: str,
    external_id: str,
) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM webhook_receipts WHERE source=? AND external_id=?",
        (source, external_id),
    ) as cur:
        row = await cur.fetchone()
    return _decode("webhook_receipts", row) if row else None


async def claim_webhook_receipt(
    db: aiosqlite.Connection,
    *,
    source: str,
    external_id: str,
    request_payload: Optional[dict] = None,
) -> dict:
    now = datetime.utcnow().isoformat()
    payload = _encode_json(
        "webhook_receipts",
        {
            "source": source,
            "external_id": external_id,
            "status": "processing",
            "duplicate_count": 0,
            "request_payload": request_payload or {},
            "last_seen_at": now,
            "created_at": now,
            "updated_at": now,
        },
    )
    try:
        cur = await db.execute(
            """INSERT INTO webhook_receipts
               (source, external_id, status, duplicate_count, request_payload, last_seen_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                payload["source"],
                payload["external_id"],
                payload["status"],
                payload["duplicate_count"],
                payload["request_payload"],
                payload["last_seen_at"],
                payload["created_at"],
                payload["updated_at"],
            ),
        )
        await db.commit()
        receipt_id = cur.lastrowid
        async with db.execute("SELECT * FROM webhook_receipts WHERE id=?", (receipt_id,)) as fetch_cur:
            row = await fetch_cur.fetchone()
        return {"status": "claimed", "receipt": _decode("webhook_receipts", row) if row else None}
    except aiosqlite.IntegrityError:
        await db.execute(
            """UPDATE webhook_receipts
               SET duplicate_count=COALESCE(duplicate_count, 0) + 1,
                   last_seen_at=?,
                   updated_at=?
               WHERE source=? AND external_id=?""",
            (
                now,
                now,
                source,
                external_id,
            ),
        )
        await db.commit()
        existing = await get_webhook_receipt(db, source=source, external_id=external_id)
        return {"status": "existing", "receipt": existing}


async def finalize_webhook_receipt(
    db: aiosqlite.Connection,
    receipt_id: int,
    *,
    response_body: str,
    response_status_code: int,
    status: str = "completed",
) -> Optional[dict]:
    updated_at = datetime.utcnow().isoformat()
    await db.execute(
        """UPDATE webhook_receipts
           SET status=?, response_body=?, response_status_code=?, updated_at=?
           WHERE id=?""",
        (
            status,
            response_body,
            response_status_code,
            updated_at,
            receipt_id,
        ),
    )
    await db.commit()
    async with db.execute("SELECT * FROM webhook_receipts WHERE id=?", (receipt_id,)) as cur:
        row = await cur.fetchone()
    return _decode("webhook_receipts", row) if row else None


async def delete_webhook_receipt(
    db: aiosqlite.Connection,
    receipt_id: int,
) -> None:
    await db.execute("DELETE FROM webhook_receipts WHERE id=?", (receipt_id,))
    await db.commit()


async def list_webhook_receipts(
    db: aiosqlite.Connection,
    *,
    source: Optional[str] = None,
    status: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    query = "SELECT * FROM webhook_receipts"
    clauses: list[str] = []
    params: list[Any] = []
    if source is not None:
        clauses.append("source=?")
        params.append(source)
    if status is not None:
        clauses.append("status=?")
        params.append(status)
    if since is not None:
        clauses.append("created_at>=?")
        params.append(since)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY COALESCE(last_seen_at, created_at) DESC, id DESC LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("webhook_receipts", row) for row in rows]


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


async def list_audit_log_for_location(
    db: aiosqlite.Connection,
    location_id: int,
    *,
    limit: int = 5000,
    since: Optional[str] = None,
) -> list[dict]:
    query = """
        SELECT al.*
        FROM audit_log al
        LEFT JOIN schedules sc
            ON al.entity_type='schedule' AND al.entity_id=sc.id
        LEFT JOIN shifts sh
            ON al.entity_type='shift' AND al.entity_id=sh.id
        LEFT JOIN workers w
            ON al.entity_type='worker' AND al.entity_id=w.id
        LEFT JOIN locations loc
            ON al.entity_type='location' AND al.entity_id=loc.id
        WHERE COALESCE(sc.location_id, sh.location_id, w.location_id, loc.id)=?
    """
    params: list[Any] = [location_id]
    if since is not None:
        query += " AND al.timestamp>=?"
        params.append(since)
    query += " ORDER BY al.id DESC LIMIT ?"
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
    location_id: Optional[int] = None,
) -> list[dict]:
    """Return schedule-assigned or filled shifts due for worker reminder delivery."""
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    cutoff = now + timedelta(minutes=within_minutes)
    query = """
        SELECT
            s.*,
            COALESCE(sa.worker_id, s.filled_by) AS reminder_worker_id
        FROM shifts s
        LEFT JOIN shift_assignments sa
          ON sa.shift_id = s.id
         AND sa.assignment_status IN ('assigned', 'claimed', 'confirmed')
        WHERE s.reminder_sent_at IS NULL
          AND datetime(s.date || ' ' || s.start_time) BETWEEN ? AND ?
          AND (
                (s.published_state IN ('published', 'amended') AND sa.worker_id IS NOT NULL)
                OR (s.status='filled' AND s.filled_by IS NOT NULL)
          )
    """
    params: list[object] = [
        now.strftime("%Y-%m-%d %H:%M:%S"),
        cutoff.strftime("%Y-%m-%d %H:%M:%S"),
    ]
    if location_id is not None:
        query += " AND s.location_id=?"
        params.append(location_id)
    query += " ORDER BY s.date ASC, s.start_time ASC, s.id ASC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("shifts", row) for row in rows]


async def mark_reminder_sent(db: aiosqlite.Connection, shift_id: int) -> None:
    from datetime import datetime

    await db.execute(
        "UPDATE shifts SET reminder_sent_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), shift_id),
    )
    await db.commit()


async def list_shifts_needing_confirmation_request(
    db: aiosqlite.Connection,
    within_minutes: int = 120,
    location_id: Optional[int] = None,
) -> list[dict]:
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    cutoff = now + timedelta(minutes=within_minutes)
    query = """
        SELECT
            s.*,
            sa.worker_id AS assigned_worker_id,
            sa.assignment_status,
            sa.source AS assignment_source,
            w.name AS assigned_worker_name,
            w.phone AS assigned_worker_phone,
            l.name AS location_name
        FROM shifts s
        JOIN shift_assignments sa
          ON sa.shift_id = s.id
         AND sa.assignment_status IN ('assigned', 'claimed', 'confirmed')
         AND sa.worker_id IS NOT NULL
        JOIN workers w
          ON w.id = sa.worker_id
        LEFT JOIN locations l
          ON l.id = s.location_id
        LEFT JOIN cascades c
          ON c.shift_id = s.id
         AND c.status = 'active'
        WHERE s.status = 'scheduled'
          AND s.published_state IN ('published', 'amended')
          AND s.confirmation_requested_at IS NULL
          AND s.worker_confirmed_at IS NULL
          AND w.sms_consent_status = 'granted'
          AND datetime(s.date || ' ' || s.start_time) BETWEEN ? AND ?
          AND c.id IS NULL
    """
    params: list[object] = [
        now.strftime("%Y-%m-%d %H:%M:%S"),
        cutoff.strftime("%Y-%m-%d %H:%M:%S"),
    ]
    if location_id is not None:
        query += " AND s.location_id=?"
        params.append(location_id)
    query += " ORDER BY s.date ASC, s.start_time ASC, s.id ASC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("shifts", row) for row in rows]


async def list_unconfirmed_shifts_for_escalation(
    db: aiosqlite.Connection,
    within_minutes: int = 15,
    location_id: Optional[int] = None,
) -> list[dict]:
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    cutoff = now + timedelta(minutes=within_minutes)
    query = """
        SELECT
            s.*,
            sa.worker_id AS assigned_worker_id,
            sa.assignment_status,
            sa.source AS assignment_source,
            w.name AS assigned_worker_name,
            w.phone AS assigned_worker_phone,
            l.name AS location_name
        FROM shifts s
        JOIN shift_assignments sa
          ON sa.shift_id = s.id
         AND sa.assignment_status IN ('assigned', 'claimed', 'confirmed')
         AND sa.worker_id IS NOT NULL
        JOIN workers w
          ON w.id = sa.worker_id
        LEFT JOIN locations l
          ON l.id = s.location_id
        LEFT JOIN cascades c
          ON c.shift_id = s.id
         AND c.status = 'active'
        WHERE s.status = 'scheduled'
          AND s.published_state IN ('published', 'amended')
          AND s.confirmation_requested_at IS NOT NULL
          AND s.worker_confirmed_at IS NULL
          AND s.worker_declined_at IS NULL
          AND s.confirmation_escalated_at IS NULL
          AND w.sms_consent_status = 'granted'
          AND datetime(s.date || ' ' || s.start_time) BETWEEN ? AND ?
          AND c.id IS NULL
    """
    params: list[object] = [
        now.strftime("%Y-%m-%d %H:%M:%S"),
        cutoff.strftime("%Y-%m-%d %H:%M:%S"),
    ]
    if location_id is not None:
        query += " AND s.location_id=?"
        params.append(location_id)
    query += " ORDER BY s.date ASC, s.start_time ASC, s.id ASC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("shifts", row) for row in rows]


async def list_shifts_needing_check_in_request(
    db: aiosqlite.Connection,
    within_minutes: int = 15,
    location_id: Optional[int] = None,
) -> list[dict]:
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    cutoff = now + timedelta(minutes=within_minutes)
    query = """
        SELECT
            s.*,
            sa.worker_id AS assigned_worker_id,
            sa.assignment_status,
            sa.source AS assignment_source,
            w.name AS assigned_worker_name,
            w.phone AS assigned_worker_phone,
            l.name AS location_name
        FROM shifts s
        JOIN shift_assignments sa
          ON sa.shift_id = s.id
         AND sa.assignment_status IN ('assigned', 'claimed', 'confirmed')
         AND sa.worker_id IS NOT NULL
        JOIN workers w
          ON w.id = sa.worker_id
        LEFT JOIN locations l
          ON l.id = s.location_id
        LEFT JOIN cascades c
          ON c.shift_id = s.id
         AND c.status = 'active'
        WHERE s.status = 'scheduled'
          AND s.published_state IN ('published', 'amended')
          AND s.check_in_requested_at IS NULL
          AND s.checked_in_at IS NULL
          AND s.check_in_escalated_at IS NULL
          AND w.sms_consent_status = 'granted'
          AND datetime(s.date || ' ' || s.start_time) BETWEEN ? AND ?
          AND c.id IS NULL
    """
    params: list[object] = [
        now.strftime("%Y-%m-%d %H:%M:%S"),
        cutoff.strftime("%Y-%m-%d %H:%M:%S"),
    ]
    if location_id is not None:
        query += " AND s.location_id=?"
        params.append(location_id)
    query += " ORDER BY s.date ASC, s.start_time ASC, s.id ASC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("shifts", row) for row in rows]


async def list_shifts_missing_check_in(
    db: aiosqlite.Connection,
    lookback_hours: int = 12,
    location_id: Optional[int] = None,
) -> list[dict]:
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    earliest = now - timedelta(hours=lookback_hours)
    query = """
        SELECT
            s.*,
            sa.worker_id AS assigned_worker_id,
            sa.assignment_status,
            sa.source AS assignment_source,
            w.name AS assigned_worker_name,
            w.phone AS assigned_worker_phone,
            l.name AS location_name
        FROM shifts s
        JOIN shift_assignments sa
          ON sa.shift_id = s.id
         AND sa.assignment_status IN ('assigned', 'claimed', 'confirmed')
         AND sa.worker_id IS NOT NULL
        JOIN workers w
          ON w.id = sa.worker_id
        LEFT JOIN locations l
          ON l.id = s.location_id
        LEFT JOIN cascades c
          ON c.shift_id = s.id
         AND c.status = 'active'
        WHERE s.status = 'scheduled'
          AND s.published_state IN ('published', 'amended')
          AND s.check_in_requested_at IS NOT NULL
          AND s.checked_in_at IS NULL
          AND s.check_in_escalated_at IS NULL
          AND datetime(s.date || ' ' || s.start_time) BETWEEN ? AND ?
          AND c.id IS NULL
    """
    params: list[object] = [
        earliest.strftime("%Y-%m-%d %H:%M:%S"),
        now.strftime("%Y-%m-%d %H:%M:%S"),
    ]
    if location_id is not None:
        query += " AND s.location_id=?"
        params.append(location_id)
    query += " ORDER BY s.date ASC, s.start_time ASC, s.id ASC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_decode("shifts", row) for row in rows]


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
