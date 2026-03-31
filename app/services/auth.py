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
    re.compile(r"^/api/location-manager-invites/[^/]+$"),
    re.compile(r"^/api/location-manager-invites/[^/]+/request-access$"),
    re.compile(r"^/api/onboarding/sessions/[^/]+$"),
    re.compile(r"^/api/onboarding/sessions/[^/]+/complete$"),
    re.compile(r"^/api/places/autocomplete$"),
    re.compile(r"^/api/places/details$"),
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
    re.compile(r"^/api/auth/(me|logout|complete-onboarding)$"),
    re.compile(r"^/api/locations$"),
    re.compile(r"^/api/locations/\d+$"),
    re.compile(r"^/api/locations/\d+/preview-bootstrap$"),
    re.compile(r"^/api/locations/\d+/(connect-sync|sync-roster|sync-schedule)$"),
    re.compile(r"^/api/locations/\d+/(settings|status|roster|eligible-workers|enrollment-invite-preview|enrollment-invites)$"),
    re.compile(r"^/api/locations/\d+/manager-memberships$"),
    re.compile(r"^/api/locations/\d+/manager-memberships/\d+$"),
    re.compile(r"^/api/locations/\d+/manager-invites/\d+$"),
    re.compile(r"^/api/locations/\d+/backfill-shifts-(metrics|activity)$"),
    re.compile(r"^/api/locations/\d+/(ai-action-history|ai-action-attention|ai-runtime-stats|ai-capabilities|ai-active-sessions)$"),
    re.compile(r"^/api/locations/\d+/import-jobs$"),
    re.compile(r"^/api/ai-actions($|/)"),
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


def _is_valid_otp_code(value: object | None) -> bool:
    text = _trim_text(value)
    return bool(text and text.isdigit() and 4 <= len(text) <= 10)


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


async def _resolve_phone_access(
    db: aiosqlite.Connection,
    phone: str,
) -> tuple[Optional[int], list[int]]:
    locations = await queries.list_locations_by_contact_phone(db, phone)
    memberships = await queries.list_location_memberships_for_phone(db, phone)
    organizations = await queries.list_organizations_by_contact_phone(db, phone)

    location_ids = sorted({int(location["id"]) for location in locations})
    location_ids.extend(
        int(item["location_id"])
        for item in memberships
        if item.get("location_id") is not None
    )
    organization_ids = {int(item["id"]) for item in organizations}
    organization_id = next(iter(organization_ids)) if len(organization_ids) == 1 else None
    return organization_id, sorted(set(location_ids))


def filter_locations_for_principal(
    locations: list[dict],
    principal: AuthPrincipal,
) -> list[dict]:
    if principal.is_internal:
        return list(locations)

    allowed_location_ids = set(int(value) for value in principal.location_ids)
    accessible: list[dict] = []
    for location in locations:
        location_id = int(location["id"])
        if location_id in allowed_location_ids:
            accessible.append(location)
            continue
        if (
            principal.organization_id is not None
            and location.get("organization_id") == principal.organization_id
        ):
            accessible.append(location)
    return accessible


async def principal_requires_onboarding(
    db: aiosqlite.Connection,
    principal: AuthPrincipal,
    accessible_locations: list[dict],
) -> bool:
    if not accessible_locations:
        return True
    if not principal.subject_phone:
        return False
    incomplete_memberships = await queries.list_incomplete_location_memberships_for_phone(
        db,
        principal.subject_phone,
    )
    return bool(incomplete_memberships)


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
                organization_id = session.get("organization_id")
                location_ids = [int(value) for value in session.get("location_ids_json") or []]
                subject_phone = session.get("subject_phone")
                refresh_updates: dict[str, object] = {
                    "last_seen_at": datetime.utcnow().isoformat(),
                }

                if subject_phone:
                    refreshed_org_id, refreshed_location_ids = await _resolve_phone_access(
                        db,
                        subject_phone,
                    )
                    if refreshed_org_id != organization_id or refreshed_location_ids != location_ids:
                        organization_id = refreshed_org_id
                        location_ids = refreshed_location_ids
                        refresh_updates["organization_id"] = organization_id
                        refresh_updates["location_ids_json"] = location_ids

                refresh_updates["expires_at"] = _expires_at(
                    hours=settings.backfill_dashboard_session_ttl_hours
                )
                await queries.update_dashboard_session(
                    db,
                    int(session["id"]),
                    refresh_updates,
                )
                return AuthPrincipal(
                    principal_type="session",
                    organization_id=organization_id,
                    location_ids=location_ids,
                    session_id=int(session["id"]),
                    subject_phone=subject_phone,
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
        if needs_internal or (needs_dashboard_auth and settings.backfill_dashboard_auth_required):
            raise HTTPException(status_code=401, detail="Authentication required")
        return None
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
    if principal is not None and principal.is_session:
        return principal
    if not settings.backfill_dashboard_auth_required:
        return AuthPrincipal(principal_type="internal")
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


async def refresh_dashboard_session_access(
    db: aiosqlite.Connection,
    principal: AuthPrincipal,
) -> AuthPrincipal:
    if not principal.is_session or principal.session_id is None or not principal.subject_phone:
        return principal

    organization_id, location_ids = await _resolve_phone_access(db, principal.subject_phone)
    if organization_id == principal.organization_id and location_ids == principal.location_ids:
        return principal

    await queries.update_dashboard_session(
        db,
        principal.session_id,
        {
            "organization_id": organization_id,
            "location_ids_json": location_ids,
        },
    )
    principal.organization_id = organization_id
    principal.location_ids = location_ids
    return principal


async def _create_dashboard_session(
    db: aiosqlite.Connection,
    *,
    phone: str,
    organization_id: Optional[int],
    location_ids: list[int],
    access_request_id: Optional[int],
) -> tuple[str, AuthPrincipal]:
    session_token = _new_raw_token("bfsess")
    session_id = await queries.insert_dashboard_session(
        db,
        {
            "organization_id": organization_id,
            "location_ids_json": location_ids,
            "subject_phone": phone,
            "session_token_hash": _hash_token(session_token),
            "access_request_id": access_request_id,
            "expires_at": _expires_at(hours=settings.backfill_dashboard_session_ttl_hours),
            "last_seen_at": datetime.utcnow().isoformat(),
        },
    )
    principal = AuthPrincipal(
        principal_type="session",
        organization_id=organization_id,
        location_ids=location_ids,
        session_id=session_id,
        subject_phone=phone,
    )
    return session_token, principal


async def request_dashboard_access(
    db: aiosqlite.Connection,
    *,
    phone: str,
) -> dict:
    normalized_phone = normalize_phone(phone)
    if normalized_phone is None:
        raise ValueError("Phone number must be a valid mobile number")

    organization_id, location_ids = await _resolve_phone_access(db, normalized_phone)
    await queries.supersede_pending_dashboard_access_requests_for_phone(db, normalized_phone)

    try:
        verification = messaging.send_sms_verification(normalized_phone)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("Could not send verification code") from exc
    request_id = await queries.insert_dashboard_access_request(
        db,
        {
            "phone": normalized_phone,
            "organization_id": organization_id,
            "location_ids_json": location_ids,
            "token_hash": _hash_token(_new_raw_token("bfreq")),
            "verification_sid": verification.get("sid"),
            "channel": verification.get("channel") or "sms",
            "expires_at": _expires_at(minutes=settings.backfill_dashboard_access_request_ttl_minutes),
            "requested_at": datetime.utcnow().isoformat(),
        },
    )
    return {
        "request_id": request_id,
        "destination": _mask_phone(normalized_phone),
        "expires_at": _expires_at(minutes=settings.backfill_dashboard_access_request_ttl_minutes),
        "message_sid": verification.get("sid"),
        "organization_id": None,
        "location_ids": [],
        "channel": verification.get("channel") or "sms",
    }


async def request_dashboard_access_for_location_invite(
    db: aiosqlite.Connection,
    *,
    invite_token: str,
    manager_name: str,
    phone: str,
) -> dict:
    normalized_phone = normalize_phone(phone)
    normalized_name = _trim_text(manager_name)
    raw_token = _trim_text(invite_token)
    if normalized_name is None:
        raise ValueError("Manager name is required")
    if normalized_phone is None:
        raise ValueError("Phone number must be a valid mobile number")
    if raw_token is None:
        raise ValueError("Invite token is required")

    invite = await queries.get_location_manager_invite_by_token_hash(
        db,
        _hash_token(raw_token),
    )
    if invite is None:
        raise ValueError("Invite not found")
    if invite.get("status") != "pending" or _is_expired(invite.get("expires_at")):
        raise ValueError("Invite has expired")

    location = await queries.get_location(db, int(invite["location_id"]))
    if location is None:
        raise ValueError("Location not found")

    await queries.supersede_pending_dashboard_access_requests_for_phone(db, normalized_phone)

    try:
        verification = messaging.send_sms_verification(normalized_phone)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("Could not send verification code") from exc

    await queries.claim_location_manager_invite(
        db,
        int(invite["id"]),
        claimed_phone=normalized_phone,
        claimed_name=normalized_name,
    )

    request_id = await queries.insert_dashboard_access_request(
        db,
        {
            "phone": normalized_phone,
            "organization_id": location.get("organization_id"),
            "location_ids_json": [int(invite["location_id"])],
            "location_manager_invite_id": int(invite["id"]),
            "token_hash": _hash_token(_new_raw_token("bfreq")),
            "verification_sid": verification.get("sid"),
            "channel": verification.get("channel") or "sms",
            "expires_at": _expires_at(
                minutes=settings.backfill_dashboard_access_request_ttl_minutes
            ),
            "requested_at": datetime.utcnow().isoformat(),
        },
    )
    return {
        "request_id": request_id,
        "destination": _mask_phone(normalized_phone),
        "expires_at": _expires_at(
            minutes=settings.backfill_dashboard_access_request_ttl_minutes
        ),
        "message_sid": verification.get("sid"),
        "organization_id": location.get("organization_id"),
        "location_ids": [int(invite["location_id"])],
        "channel": verification.get("channel") or "sms",
    }


async def verify_dashboard_access_code(
    db: aiosqlite.Connection,
    *,
    request_id: int,
    code: str,
) -> tuple[str, AuthPrincipal]:
    if not _is_valid_otp_code(code):
        raise ValueError("Verification code must be 4 to 10 digits")

    access_request = await queries.get_dashboard_access_request(db, request_id)
    if access_request is None:
        raise ValueError("Verification request not found")
    if access_request.get("status") != "pending" or _is_expired(access_request.get("expires_at")):
        raise ValueError("Verification code has expired")
    if int(access_request.get("check_count") or 0) >= settings.backfill_dashboard_access_max_attempts:
        await queries.update_dashboard_access_request(
            db,
            request_id,
            {
                "status": "blocked",
                "last_check_at": datetime.utcnow().isoformat(),
            },
        )
        raise ValueError("Too many verification attempts. Request a new code.")

    try:
        verification_check = messaging.check_sms_verification(
            access_request["phone"],
            code,
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("Could not verify code") from exc
    status = str(verification_check.get("status") or "").lower()
    approved = bool(verification_check.get("valid")) or status == "approved"

    if not approved:
        check_count = int(access_request.get("check_count") or 0) + 1
        update_payload: dict[str, object] = {
            "check_count": check_count,
            "last_check_at": datetime.utcnow().isoformat(),
        }
        if check_count >= settings.backfill_dashboard_access_max_attempts:
            update_payload["status"] = "blocked"
        await queries.update_dashboard_access_request(
            db,
            request_id,
            update_payload,
        )
        if check_count >= settings.backfill_dashboard_access_max_attempts:
            raise ValueError("Too many verification attempts. Request a new code.")
        raise ValueError("Invalid verification code")

    invite_id = access_request.get("location_manager_invite_id")
    if invite_id is not None:
        invite = await queries.get_location_manager_invite(db, int(invite_id))
        if invite is None:
            raise ValueError("Invite not found")
        if invite.get("status") == "revoked" or _is_expired(invite.get("expires_at")):
            raise ValueError("Invite has expired")
        if invite.get("status") == "accepted" and invite.get("accepted_phone") != access_request["phone"]:
            raise ValueError("Invite has already been accepted")
        await queries.upsert_location_membership(
            db,
            location_id=int(invite["location_id"]),
            phone=access_request["phone"],
            manager_name=invite.get("claimed_name") or invite.get("manager_name"),
            manager_email=invite.get("invite_email"),
            role=invite.get("role") or "manager",
            invite_status="active",
            invited_by_phone=invite.get("invited_by_phone"),
            accepted_at=datetime.utcnow().isoformat(),
            revoked_at=None,
        )
        await queries.accept_location_manager_invite(
            db,
            int(invite_id),
            accepted_phone=access_request["phone"],
        )

    organization_id, location_ids = await _resolve_phone_access(db, access_request["phone"])
    session_token, principal = await _create_dashboard_session(
        db,
        phone=access_request["phone"],
        organization_id=organization_id,
        location_ids=location_ids,
        access_request_id=int(access_request["id"]),
    )
    await queries.update_dashboard_access_request(
        db,
        int(access_request["id"]),
        {
            "organization_id": organization_id,
            "location_ids_json": location_ids,
            "status": "used",
            "used_at": datetime.utcnow().isoformat(),
            "verified_at": datetime.utcnow().isoformat(),
            "last_check_at": datetime.utcnow().isoformat(),
            "check_count": int(access_request.get("check_count") or 0) + 1,
        },
    )
    return session_token, principal


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

    session_token, principal = await _create_dashboard_session(
        db,
        phone=access_request["phone"],
        organization_id=access_request.get("organization_id"),
        location_ids=[int(value) for value in access_request.get("location_ids_json") or []],
        access_request_id=int(access_request["id"]),
    )
    await queries.update_dashboard_access_request(
        db,
        int(access_request["id"]),
        {
            "status": "used",
            "used_at": datetime.utcnow().isoformat(),
            "verified_at": datetime.utcnow().isoformat(),
        },
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
    principal = await refresh_dashboard_session_access(db, principal)
    organization = (
        await queries.get_organization(db, principal.organization_id)
        if principal.organization_id is not None
        else None
    )
    accessible_locations = filter_locations_for_principal(
        await queries.list_locations(db),
        principal,
    )
    accessible_locations.sort(key=lambda item: (item.get("name") or "", int(item["id"])))
    onboarding_required = await principal_requires_onboarding(
        db,
        principal,
        accessible_locations,
    )
    return {
        "principal_type": principal.principal_type,
        "session_id": principal.session_id,
        "subject_phone": principal.subject_phone,
        "session_expires_at": _expires_at(hours=settings.backfill_dashboard_session_ttl_hours)
        if principal.is_session
        else None,
        "onboarding_required": onboarding_required,
        "organization": organization,
        "location_ids": principal.location_ids,
        "locations": accessible_locations,
    }


def principal_to_dict(principal: AuthPrincipal) -> dict:
    return asdict(principal)


def get_request_principal(request: Request) -> Optional[AuthPrincipal]:
    return _request_principal(request)
