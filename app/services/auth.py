from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import hashlib
import re
import secrets
from typing import Optional
from urllib.parse import quote

import aiosqlite
from fastapi import Depends, HTTPException, Request

from app.config import settings
from app.db import queries
from app.db.database import get_db
from app.services import messaging

_PUBLIC_API_PATTERNS = (
    re.compile(r"^/api/auth/request-access$"),
    re.compile(r"^/api/auth/exchange$"),
    re.compile(r"^/api/onboarding/sessions/[^/]+$"),
    re.compile(r"^/api/onboarding/sessions/[^/]+/complete$"),
)

_INTERNAL_ONLY_PATTERNS = (
    re.compile(r"^/api/internal/"),
    re.compile(r"^/api/retell/reconcile$"),
    re.compile(r"^/api/organizations($|/)"),
    re.compile(r"^/api/cascades($|/)"),
    re.compile(r"^/api/outreach-attempts$"),
    re.compile(r"^/api/agency-requests$"),
    re.compile(r"^/api/audit-log$"),
    re.compile(r"^/api/shifts/backfill$"),
    re.compile(r"^/api/manager/shifts$"),
    re.compile(r"^/api/exports/"),
)

_DASHBOARD_PROTECTED_PATTERNS = (
    re.compile(r"^/api/onboarding/link$"),
    re.compile(r"^/api/auth/(me|logout)$"),
    re.compile(r"^/api/locations$"),
    re.compile(r"^/api/locations/\d+$"),
    re.compile(r"^/api/locations/\d+/(connect-sync|sync-roster|sync-schedule)$"),
    re.compile(r"^/api/locations/\d+/(settings|status|roster|eligible-workers|enrollment-invite-preview|enrollment-invites)$"),
    re.compile(r"^/api/locations/\d+/backfill-shifts-(metrics|activity)$"),
    re.compile(r"^/api/locations/\d+/import-jobs$"),
    re.compile(r"^/api/import-jobs/\d+/(upload|mapping|rows|error-csv|commit)$"),
    re.compile(r"^/api/import-rows/\d+$"),
    re.compile(r"^/api/locations/\d+/(schedules/current|schedule-exceptions|schedule-draft-options|schedule-templates|coverage|manager-actions|manager-digest)$"),
    re.compile(r"^/api/locations/\d+/schedule-exceptions/actions$"),
    re.compile(r"^/api/locations/\d+/schedules/(copy-last-week|create-from-template|ai-draft)$"),
    re.compile(r"^/api/schedules/\d+/"),
    re.compile(r"^/api/schedule-templates/\d+"),
    re.compile(r"^/api/schedule-template-shifts/\d+"),
    re.compile(r"^/api/workers$"),
    re.compile(r"^/api/workers/import-csv$"),
    re.compile(r"^/api/workers/\d+$"),
    re.compile(r"^/api/shifts$"),
    re.compile(r"^/api/cascades/\d+/(approve-fill|decline-fill|approve-agency)$"),
    re.compile(r"^/api/shifts/\d+(/status)?$"),
    re.compile(r"^/api/shifts/\d+/(assignment|coverage/start|coverage/cancel|open-shift/close|open-shift/reopen|attendance/wait|attendance/start-coverage)$"),
    re.compile(r"^/api/workers/\d+/(deactivate|reactivate|transfer)$"),
)


@dataclass
class AuthPrincipal:
    principal_type: str
    organization_id: Optional[int] = None
    location_ids: list[int] = field(default_factory=list)
    session_id: Optional[int] = None
    subject_phone: Optional[str] = None

    @property
    def is_internal(self) -> bool:
        return self.principal_type == "internal"

    @property
    def is_session(self) -> bool:
        return self.principal_type == "session"

    @property
    def is_setup(self) -> bool:
        return self.principal_type == "setup"


def _trim_text(value: object | None) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_phone(value: object | None) -> Optional[str]:
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


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _new_raw_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(24)}"


def _mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 4:
        return phone
    return f"***-***-{digits[-4:]}"


def _expires_at(minutes: int = 0, hours: int = 0) -> str:
    return (datetime.utcnow() + timedelta(minutes=minutes, hours=hours)).isoformat()


def _is_expired(value: str | None) -> bool:
    if not value:
        return True
    try:
        return datetime.fromisoformat(value) <= datetime.utcnow()
    except ValueError:
        return True


def _is_public_api_path(path: str) -> bool:
    return any(pattern.match(path) for pattern in _PUBLIC_API_PATTERNS)


def _is_internal_only_path(path: str) -> bool:
    return any(pattern.match(path) for pattern in _INTERNAL_ONLY_PATTERNS)


def _is_dashboard_protected_path(request: Request) -> bool:
    path = request.url.path
    method = request.method.upper()
    if path in {"/api/dashboard", "/api/locations"} and method == "GET":
        return True
    if path in {"/api/workers", "/api/shifts"} and method == "GET":
        return True
    if any(pattern.match(path) for pattern in _DASHBOARD_PROTECTED_PATTERNS):
        return True
    if path in {"/api/workers", "/api/shifts"} and request.query_params.get("location_id"):
        return True
    return False


def _build_access_link(raw_token: str) -> str:
    return f"{settings.backfill_web_base_url}/auth/verify?token={quote(raw_token)}"


def _build_access_sms_body(*, raw_token: str) -> str:
    link = _build_access_link(raw_token)
    return (
        "Backfill: your dashboard access link is ready. "
        f"Open {link} within {settings.backfill_dashboard_access_request_ttl_minutes} minutes."
    )


def _request_principal(request: Request) -> Optional[AuthPrincipal]:
    principal = getattr(request.state, "backfill_principal", None)
    return principal if isinstance(principal, AuthPrincipal) else None


def request_rate_limit_key(request: Request) -> str:
    principal = _request_principal(request)
    if principal is not None:
        if principal.is_internal:
            return "internal"
        if principal.session_id is not None:
            return f"session:{principal.session_id}"
        if principal.organization_id is not None:
            return f"organization:{principal.organization_id}"
        if principal.location_ids:
            return f"locations:{','.join(str(value) for value in sorted(principal.location_ids))}"

    forwarded_for = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    if forwarded_for:
        return f"ip:{forwarded_for}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


async def _authenticate_request(
    request: Request,
    db: aiosqlite.Connection,
) -> Optional[AuthPrincipal]:
    internal_key = _trim_text(request.headers.get("x-backfill-internal-key"))
    if internal_key and settings.backfill_internal_api_key and internal_key == settings.backfill_internal_api_key:
        return AuthPrincipal(principal_type="internal")

    authorization = _trim_text(request.headers.get("authorization"))
    if authorization and authorization.lower().startswith("bearer "):
        session_token = authorization.split(" ", 1)[1].strip()
        if session_token:
            session = await queries.get_dashboard_session_by_token_hash(db, _hash_token(session_token))
            if session is not None and session.get("status") == "active" and not _is_expired(session.get("expires_at")):
                await queries.update_dashboard_session(
                    db,
                    int(session["id"]),
                    {"last_seen_at": datetime.utcnow().isoformat()},
                )
                return AuthPrincipal(
                    principal_type="session",
                    organization_id=session.get("organization_id"),
                    location_ids=[int(value) for value in session.get("location_ids_json") or []],
                    session_id=int(session["id"]),
                    subject_phone=session.get("subject_phone"),
                )

    setup_token = _trim_text(request.headers.get("x-backfill-setup-token"))
    if setup_token:
        token_row = await queries.get_setup_access_token_by_token_hash(db, _hash_token(setup_token))
        if token_row is not None and token_row.get("status") == "active" and not _is_expired(token_row.get("expires_at")):
            await queries.update_setup_access_token(
                db,
                int(token_row["id"]),
                {"last_seen_at": datetime.utcnow().isoformat()},
            )
            return AuthPrincipal(
                principal_type="setup",
                location_ids=[int(token_row["location_id"])],
            )

    return None


async def _resolve_location_id_from_request(
    request: Request,
    db: aiosqlite.Connection,
) -> Optional[int]:
    path_params = request.path_params
    if "location_id" in path_params:
        return int(path_params["location_id"])
    if "schedule_id" in path_params:
        schedule = await queries.get_schedule(db, int(path_params["schedule_id"]))
        return int(schedule["location_id"]) if schedule else None
    if "template_id" in path_params:
        template = await queries.get_schedule_template(db, int(path_params["template_id"]))
        return int(template["location_id"]) if template else None
    if "template_shift_id" in path_params:
        template_shift = await queries.get_schedule_template_shift(db, int(path_params["template_shift_id"]))
        if template_shift is None:
            return None
        template = await queries.get_schedule_template(db, int(template_shift["template_id"]))
        return int(template["location_id"]) if template else None
    if "job_id" in path_params:
        job = await queries.get_import_job(db, int(path_params["job_id"]))
        return int(job["location_id"]) if job else None
    if "row_id" in path_params:
        row = await queries.get_import_row_result(db, int(path_params["row_id"]))
        if row is None:
            return None
        job = await queries.get_import_job(db, int(row["import_job_id"]))
        return int(job["location_id"]) if job else None
    if "shift_id" in path_params:
        shift = await queries.get_shift(db, int(path_params["shift_id"]))
        return int(shift["location_id"]) if shift else None
    if "cascade_id" in path_params:
        cascade = await queries.get_cascade(db, int(path_params["cascade_id"]))
        if cascade is None:
            return None
        shift = await queries.get_shift(db, int(cascade["shift_id"]))
        return int(shift["location_id"]) if shift else None
    if "worker_id" in path_params:
        worker = await queries.get_worker(db, int(path_params["worker_id"]))
        return int(worker["location_id"]) if worker and worker.get("location_id") is not None else None
    location_query = request.query_params.get("location_id")
    if location_query:
        try:
            return int(location_query)
        except ValueError:
            return None
    return None


async def _ensure_organization_access(
    db: aiosqlite.Connection,
    principal: AuthPrincipal,
    organization_id: int,
) -> None:
    if principal.is_internal:
        return
    organization = await queries.get_organization(db, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if principal.organization_id is not None and principal.organization_id == organization_id:
        return
    raise HTTPException(status_code=403, detail="Forbidden for this organization")


async def _ensure_location_access(
    db: aiosqlite.Connection,
    principal: AuthPrincipal,
    location_id: int,
) -> None:
    if principal.is_internal:
        return
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    if location_id in principal.location_ids:
        return
    if principal.organization_id is not None and location.get("organization_id") == principal.organization_id:
        return
    raise HTTPException(status_code=403, detail="Forbidden for this location")


async def require_api_request_access(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
) -> Optional[AuthPrincipal]:
    path = request.url.path
    if not path.startswith("/api/"):
        return None
    if _is_public_api_path(path):
        return None
    needs_internal = _is_internal_only_path(path)
    needs_dashboard_auth = _is_dashboard_protected_path(request)
    if not needs_internal and not needs_dashboard_auth:
        return None

    principal = await _authenticate_request(request, db)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if needs_internal and not principal.is_internal:
        raise HTTPException(status_code=403, detail="Internal API key required")

    if not principal.is_internal:
        if "organization_id" in request.path_params:
            await _ensure_organization_access(db, principal, int(request.path_params["organization_id"]))
        location_id = await _resolve_location_id_from_request(request, db)
        if location_id is not None:
            await _ensure_location_access(db, principal, location_id)

    request.state.backfill_principal = principal
    return principal


async def require_dashboard_session(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
) -> AuthPrincipal:
    principal = _request_principal(request)
    if principal is None:
        principal = await _authenticate_request(request, db)
        if principal is not None:
            request.state.backfill_principal = principal
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not principal.is_session:
        raise HTTPException(status_code=403, detail="Dashboard session required")
    return principal


async def ensure_location_access(
    db: aiosqlite.Connection,
    principal: AuthPrincipal,
    location_id: int,
) -> None:
    await _ensure_location_access(db, principal, location_id)


async def request_dashboard_access(
    db: aiosqlite.Connection,
    *,
    phone: str,
) -> dict:
    normalized_phone = normalize_phone(phone)
    if normalized_phone is None:
        raise ValueError("Phone number must be a valid mobile number")

    locations = await queries.list_locations_by_contact_phone(db, normalized_phone)
    organizations = await queries.list_organizations_by_contact_phone(db, normalized_phone)
    if not locations and not organizations:
        raise ValueError("No dashboard access is configured for that phone number")

    location_ids = sorted({int(location["id"]) for location in locations})
    organization_ids = {
        int(location["organization_id"])
        for location in locations
        if location.get("organization_id") is not None
    }
    organization_ids.update(int(item["id"]) for item in organizations)
    if len(organization_ids) > 1:
        raise ValueError("Phone number is linked to multiple organizations; contact support to finish setup")
    organization_id = next(iter(organization_ids)) if organization_ids else None

    raw_token = _new_raw_token("bflink")
    request_id = await queries.insert_dashboard_access_request(
        db,
        {
            "phone": normalized_phone,
            "organization_id": organization_id,
            "location_ids_json": location_ids,
            "token_hash": _hash_token(raw_token),
            "expires_at": _expires_at(minutes=settings.backfill_dashboard_access_request_ttl_minutes),
            "requested_at": datetime.utcnow().isoformat(),
        },
    )
    message_sid = messaging.send_sms(
        normalized_phone,
        _build_access_sms_body(raw_token=raw_token),
    )
    return {
        "request_id": request_id,
        "destination": _mask_phone(normalized_phone),
        "expires_at": _expires_at(minutes=settings.backfill_dashboard_access_request_ttl_minutes),
        "message_sid": message_sid,
        "organization_id": organization_id,
        "location_ids": location_ids,
    }


async def exchange_dashboard_access_token(
    db: aiosqlite.Connection,
    *,
    token: str,
) -> tuple[str, AuthPrincipal]:
    raw_token = _trim_text(token)
    if not raw_token:
        raise ValueError("Access token is required")
    access_request = await queries.get_dashboard_access_request_by_token_hash(db, _hash_token(raw_token))
    if access_request is None:
        raise ValueError("Access request not found")
    if access_request.get("status") != "pending" or _is_expired(access_request.get("expires_at")):
        raise ValueError("Access link has expired")

    session_token = _new_raw_token("bfsess")
    session_id = await queries.insert_dashboard_session(
        db,
        {
            "organization_id": access_request.get("organization_id"),
            "location_ids_json": access_request.get("location_ids_json") or [],
            "subject_phone": access_request["phone"],
            "session_token_hash": _hash_token(session_token),
            "access_request_id": access_request["id"],
            "expires_at": _expires_at(hours=settings.backfill_dashboard_session_ttl_hours),
            "last_seen_at": datetime.utcnow().isoformat(),
        },
    )
    await queries.update_dashboard_access_request(
        db,
        int(access_request["id"]),
        {
            "status": "used",
            "used_at": datetime.utcnow().isoformat(),
        },
    )
    principal = AuthPrincipal(
        principal_type="session",
        organization_id=access_request.get("organization_id"),
        location_ids=[int(value) for value in access_request.get("location_ids_json") or []],
        session_id=session_id,
        subject_phone=access_request.get("phone"),
    )
    return session_token, principal


async def revoke_dashboard_session(
    db: aiosqlite.Connection,
    principal: AuthPrincipal,
) -> None:
    if principal.session_id is None:
        return
    await queries.update_dashboard_session(
        db,
        principal.session_id,
        {"status": "revoked"},
    )


async def build_auth_response_payload(
    db: aiosqlite.Connection,
    principal: AuthPrincipal,
) -> dict:
    organization = (
        await queries.get_organization(db, principal.organization_id)
        if principal.organization_id is not None
        else None
    )
    accessible_locations: list[dict] = []
    if principal.organization_id is not None:
        locations = await queries.list_locations(db)
        accessible_locations = [
            location
            for location in locations
            if location.get("organization_id") == principal.organization_id
        ]
    elif principal.location_ids:
        for location_id in principal.location_ids:
            location = await queries.get_location(db, location_id)
            if location is not None:
                accessible_locations.append(location)
    accessible_locations.sort(key=lambda item: (item.get("name") or "", int(item["id"])))
    return {
        "principal_type": principal.principal_type,
        "session_id": principal.session_id,
        "subject_phone": principal.subject_phone,
        "organization": organization,
        "location_ids": principal.location_ids,
        "locations": accessible_locations,
    }


def principal_to_dict(principal: AuthPrincipal) -> dict:
    return asdict(principal)


def get_request_principal(request: Request) -> Optional[AuthPrincipal]:
    return _request_principal(request)
