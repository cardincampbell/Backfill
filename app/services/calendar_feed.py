from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.business import Location, Role
from app.models.common import ShiftLifecycleStatus
from app.models.scheduling import Shift

# ---------------------------------------------------------------------------
# Scope: this service produces a *location-level* rolling ICS feed showing the
# published schedule for a single location.  It is NOT a per-employee/assignee
# feed — every subscriber sees the same full set of non-draft shifts for that
# location regardless of who they are assigned to.  A per-employee feed would
# require joining ShiftAssignment and filtering by employee_id.
# ---------------------------------------------------------------------------

FEED_TOKEN_SETTINGS_KEY = "calendar_feed_token"
FEED_TOKEN_ROTATED_AT_KEY = "calendar_feed_token_rotated_at"

# Lifecycle statuses that are publishable (non-draft).
# Cancelled shifts are included so subscriber clients receive STATUS:CANCELLED
# and can cleanly remove the event without a missing-event ambiguity.
_PUBLISHABLE_LIFECYCLE_STATUSES = [
    ShiftLifecycleStatus.scheduled,
    ShiftLifecycleStatus.in_progress,
    ShiftLifecycleStatus.completed,
    ShiftLifecycleStatus.cancelled,
]


def generate_feed_token() -> str:
    return secrets.token_urlsafe(32)


def feed_url_for_token(token: str) -> str:
    return f"{settings.api_base_url}{settings.api_prefix}/calendar-feeds/{token}.ics"


def get_feed_info(location: Location) -> tuple[str | None, datetime | None]:
    """Return (token, rotated_at) from location.settings."""
    token: str | None = None
    rotated_at: datetime | None = None
    if isinstance(location.settings, dict):
        raw_token = location.settings.get(FEED_TOKEN_SETTINGS_KEY)
        token = raw_token if isinstance(raw_token, str) and raw_token else None
        raw_ts = location.settings.get(FEED_TOKEN_ROTATED_AT_KEY)
        if isinstance(raw_ts, str):
            try:
                rotated_at = datetime.fromisoformat(raw_ts)
            except ValueError:
                pass
    return token, rotated_at


async def get_or_create_feed_token(
    session: AsyncSession, location: Location
) -> tuple[str, datetime | None, bool]:
    """Return (token, rotated_at, created).

    ``created`` is True when a new token was written and flush() was called;
    the caller is responsible for commit() when created=True.
    """
    token, rotated_at = get_feed_info(location)
    if token:
        return token, rotated_at, False
    token = generate_feed_token()
    now = datetime.now(timezone.utc)
    location.settings = {
        **(location.settings or {}),
        FEED_TOKEN_SETTINGS_KEY: token,
        FEED_TOKEN_ROTATED_AT_KEY: now.isoformat(),
    }
    await session.flush()
    return token, now, True


async def rotate_feed_token(
    session: AsyncSession, location: Location
) -> tuple[str, datetime]:
    """Generate a new token, flush, return (new_token, rotated_at).

    The caller must call commit() after this returns.
    """
    token = generate_feed_token()
    now = datetime.now(timezone.utc)
    location.settings = {
        **(location.settings or {}),
        FEED_TOKEN_SETTINGS_KEY: token,
        FEED_TOKEN_ROTATED_AT_KEY: now.isoformat(),
    }
    await session.flush()
    return token, now


async def get_location_by_feed_token(
    session: AsyncSession, feed_token: str
) -> Location | None:
    """Look up a Location by its calendar feed token stored in settings JSONB."""
    result = await session.execute(
        select(Location).where(
            Location.settings[FEED_TOKEN_SETTINGS_KEY].astext == feed_token
        )
    )
    return result.scalar_one_or_none()


def _fmt_dt(dt: datetime) -> str:
    """Format a datetime as an ICS UTC timestamp (YYYYMMDDTHHMMSSZ)."""
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    """Fold an ICS line at 75 characters per RFC 5545 §3.1."""
    if len(line) <= 75:
        return line
    chunks = [line[:75]]
    line = line[75:]
    while line:
        chunks.append(" " + line[:74])
        line = line[74:]
    return "\r\n".join(chunks)


def _escape(value: str) -> str:
    """Escape special characters for ICS text values per RFC 5545 §3.3.11."""
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_ics_text(
    location: Location,
    shifts: list[Shift],
    role_name_by_id: dict[UUID, str],
    now: datetime,
) -> str:
    """Build a complete ICS calendar text for the given pre-filtered shifts.

    Shifts must already have lifecycle_status != draft before being passed in;
    this function does not re-filter.  Cancelled shifts are rendered with
    STATUS:CANCELLED so subscriber clients can cleanly remove the event.
    UIDs are stable: ``{shift.id}@backfill`` — never regenerated.
    """
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Backfill//Calendar Feed//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(location.location_display_name)} \u2013 Backfill Schedule",
        f"X-WR-TIMEZONE:{location.timezone}",
    ]

    dtstamp = _fmt_dt(now)

    for shift in shifts:
        role_name = role_name_by_id.get(shift.role_id, "Shift")
        is_cancelled = shift.lifecycle_status == ShiftLifecycleStatus.cancelled

        summary = role_name
        if shift.seats_requested > 1:
            summary = f"{role_name} ({shift.seats_requested} seats)"

        location_parts = [
            p
            for p in [
                location.location_display_name,
                location.address_line_1,
                location.locality,
                location.region,
            ]
            if p
        ]
        location_str = ", ".join(location_parts)

        event_lines = [
            "BEGIN:VEVENT",
            f"UID:{shift.id}@backfill",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{_fmt_dt(shift.starts_at)}",
            f"DTEND:{_fmt_dt(shift.ends_at)}",
            f"SUMMARY:{_escape(summary)}",
            f"STATUS:{'CANCELLED' if is_cancelled else 'CONFIRMED'}",
        ]
        if location_str:
            event_lines.append(f"LOCATION:{_escape(location_str)}")
        if shift.notes:
            event_lines.append(f"DESCRIPTION:{_escape(shift.notes)}")
        event_lines.append("END:VEVENT")
        lines.extend(event_lines)

    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


async def build_location_ics(session: AsyncSession, location: Location) -> str:
    """Build the full rolling ICS feed text for a location.

    Window: past 7 days through next 49 days (rolling, not week-anchored).
    Drafts are excluded by querying lifecycle_status != draft directly.
    Cancelled shifts are included so subscribers can remove the event.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=7)
    window_end = now + timedelta(days=49)

    shifts_result = await session.execute(
        select(Shift)
        .where(
            Shift.location_id == location.id,
            Shift.lifecycle_status.in_(_PUBLISHABLE_LIFECYCLE_STATUSES),
            Shift.ends_at >= window_start,
            Shift.starts_at <= window_end,
        )
        .order_by(Shift.starts_at.asc())
    )
    shifts = list(shifts_result.scalars().all())

    role_ids = list({shift.role_id for shift in shifts})
    role_name_by_id: dict[UUID, str] = {}
    if role_ids:
        roles_result = await session.execute(select(Role).where(Role.id.in_(role_ids)))
        for role in roles_result.scalars().all():
            role_name_by_id[role.id] = role.name

    return build_ics_text(location, shifts, role_name_by_id, now)
