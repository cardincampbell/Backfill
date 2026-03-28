"""
Helpers for manager onboarding handoff.

The phone call captures intent and basics. Structured setup happens on the web.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlencode

import aiosqlite

from app.config import settings
from app.db import queries
from app.services.messaging import send_sms

_logger = logging.getLogger(__name__)


def _normalize_platform(platform: Optional[str]) -> str:
    value = (platform or "").strip().lower().replace(" ", "_")
    aliases = {
        "7shifts": "7shifts",
        "seven_shifts": "7shifts",
        "deputy": "deputy",
        "when_i_work": "wheniwork",
        "wheniwork": "wheniwork",
        "homebase": "homebase",
        "backfill_native": "backfill_native",
    }
    return aliases.get(value, "")


def _normalize_kind(kind: Optional[str]) -> str:
    route_kind = (kind or "manual_form").strip().lower()
    if route_kind in {"integration", "csv_upload", "manual_form"}:
        return route_kind
    return "manual_form"


def build_onboarding_path(kind: str, platform: Optional[str] = None) -> str:
    route_kind = _normalize_kind(kind)
    normalized_platform = _normalize_platform(platform)

    if route_kind == "integration":
        if normalized_platform and normalized_platform != "backfill_native":
            return f"/setup/connect?platform={normalized_platform}"
        return "/setup/connect"
    if route_kind == "csv_upload":
        return "/setup/upload"
    if route_kind == "manual_form":
        return "/setup/add"
    raise ValueError(f"Unsupported onboarding link kind: {kind!r}")


def build_setup_resume_path(
    *,
    kind: str,
    location_id: int,
    platform: Optional[str],
) -> str:
    path = build_onboarding_path(kind, platform=platform)
    params = {"location_id": location_id, "from_signup": "1"}
    normalized_platform = _normalize_platform(platform)
    if normalized_platform and kind == "integration":
        params["platform"] = normalized_platform
    return f"{path}?{urlencode(params)}"


def build_onboarding_url(kind: str, platform: Optional[str] = None) -> str:
    return f"{settings.backfill_web_base_url}{build_onboarding_path(kind, platform=platform)}"


def send_onboarding_link(phone: str, kind: str, platform: Optional[str] = None) -> dict:
    path = build_onboarding_path(kind, platform=platform)
    url = f"{settings.backfill_web_base_url}{path}"
    message = (
        f"Backfill setup: use this link to continue onboarding: {url} "
        "Reply here if you need help."
    )
    message_sid = send_sms(phone, message)
    return {
        "kind": _normalize_kind(kind),
        "platform": _normalize_platform(platform) or None,
        "path": path,
        "url": url,
        "message_sid": message_sid,
    }


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(24)
    return token, _token_hash(token)


def _pick_value(*mappings: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        for key in keys:
            value = mapping.get(key)
            if value not in (None, ""):
                return value
    return None


def _coerce_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _combined_text(*values: Any) -> str:
    parts = [str(value).strip() for value in values if isinstance(value, str) and value.strip()]
    return " ".join(parts)


def _normalize_phone_e164(value: Any) -> Optional[str]:
    text = _coerce_str(value)
    if text is None:
        return None
    if text.startswith("+"):
        digits = re.sub(r"\D", "", text)
        return f"+{digits}" if digits else None

    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    return None


def _signup_sms_dynamic_variables(
    *,
    session: Optional[dict] = None,
    lead: Optional[dict[str, Any]] = None,
    signup_url: str,
) -> dict[str, str]:
    source = lead or session or {}
    contact_name = _coerce_str(source.get("contact_name"))
    first_name = None
    if contact_name:
        first_name = contact_name.split()[0]

    variables = {
        "customer_name": contact_name,
        "first_name": first_name,
        "business_name": _coerce_str(source.get("business_name")),
        "role_name": _coerce_str(source.get("role_name")),
        "signup_url": signup_url,
        "from_number": _normalize_phone_e164(settings.retell_from_number or settings.backfill_phone_number),
        "agent_name": "Backfill",
        "submission_status": _coerce_str(source.get("submission_status")) or "captured_for_team",
    }
    return {key: value for key, value in variables.items() if value}


def _conversation_direction(conversation: dict) -> Optional[str]:
    direction = _coerce_str(conversation.get("direction"))
    if direction:
        return direction.lower()

    phone_from = _normalize_phone_e164(conversation.get("phone_from"))
    phone_to = _normalize_phone_e164(conversation.get("phone_to"))
    retell_number = _normalize_phone_e164(settings.retell_from_number)
    if retell_number:
        if phone_to == retell_number:
            return "inbound"
        if phone_from == retell_number:
            return "outbound"
    return None


def _analysis_sources(conversation: dict) -> list[dict[str, Any]]:
    analysis = conversation.get("analysis") or {}
    raw_payload = conversation.get("raw_payload") or {}
    raw_call = raw_payload.get("call") if isinstance(raw_payload.get("call"), dict) else {}
    metadata = conversation.get("metadata") or {}

    nested = []
    for mapping in (analysis, raw_call, raw_payload):
        if not isinstance(mapping, dict):
            continue
        for key in ("custom_analysis_data", "structured_data", "extracted_data", "output_fields"):
            value = mapping.get(key)
            if isinstance(value, dict):
                nested.append(value)

    return [analysis, raw_call, raw_payload, metadata, *nested]


def extract_lead_fields_from_conversation(conversation: dict) -> dict[str, Any]:
    sources = _analysis_sources(conversation)
    direction = _conversation_direction(conversation)
    summary_text = _coerce_str(
        _pick_value(*sources, keys=("call_summary", "summary", "conversation_summary"))
    )
    transcript_text = _coerce_str(conversation.get("transcript_text") or conversation.get("transcript"))
    phone = _normalize_phone_e164(
        conversation.get("phone_from") if direction == "inbound" else conversation.get("phone_to")
    )
    callback_phone = _normalize_phone_e164(
        _pick_value(*sources, keys=("callback_number", "contact_phone"))
    )
    platform = _normalize_platform(
        _pick_value(*sources, keys=("platform", "scheduling_platform", "scheduler", "integration_platform"))
    )
    call_type = _coerce_str(_pick_value(*sources, keys=("call_type", "intent", "lead_type", "branch")))
    role_name = _coerce_str(_pick_value(*sources, keys=("role_name", "job_title", "title")))
    business_name = _coerce_str(_pick_value(*sources, keys=("business_name", "company_name", "organization_name")))
    location_name = _coerce_str(_pick_value(*sources, keys=("location_name", "site_name", "store_name")))
    vertical = _coerce_str(_pick_value(*sources, keys=("vertical", "business_vertical")))
    notes = _coerce_str(_pick_value(*sources, keys=("notes", "note", "freeform_notes"))) or summary_text
    urgency = _coerce_str(_pick_value(*sources, keys=("urgency", "priority")))
    pain_point_summary = _coerce_str(
        _pick_value(*sources, keys=("pain_point_summary", "pain_points", "use_case", "problem_summary", "call_summary", "summary"))
    )
    if pain_point_summary is None and transcript_text:
        pain_point_summary = transcript_text

    setup_kind = "manual_form"
    if platform and platform != "backfill_native":
        setup_kind = "integration"
    elif _coerce_str(_pick_value(*sources, keys=("setup_kind", "onboarding_kind", "kind"))) == "csv_upload":
        setup_kind = "csv_upload"

    return {
        "call_type": call_type,
        "contact_name": _coerce_str(_pick_value(*sources, keys=("caller_name", "contact_name", "reported_by_name"))),
        "contact_phone": callback_phone or phone,
        "contact_email": _coerce_str(_pick_value(*sources, keys=("business_email", "contact_email", "email"))),
        "role_name": role_name,
        "business_name": business_name,
        "location_name": location_name,
        "vertical": vertical or "other",
        "location_count": _coerce_int(_pick_value(*sources, keys=("location_count", "num_locations"))),
        "pain_point_summary": pain_point_summary,
        "urgency": urgency,
        "notes": notes,
        "setup_kind": setup_kind,
        "scheduling_platform": platform or "backfill_native",
        "extracted_fields": {
            "call_type": call_type,
            "caller_name": _coerce_str(_pick_value(*sources, keys=("caller_name", "contact_name", "reported_by_name"))),
            "callback_number": _coerce_str(_pick_value(*sources, keys=("callback_number", "contact_phone"))),
            "normalized_callback_number": callback_phone,
            "business_name": business_name,
            "location_name": location_name,
            "role_name": role_name,
            "business_email": _coerce_str(_pick_value(*sources, keys=("business_email", "contact_email", "email"))),
            "location_count": _coerce_int(_pick_value(*sources, keys=("location_count", "num_locations"))),
            "pain_point_summary": pain_point_summary,
            "urgency": urgency,
            "notes": notes,
            "summary_text": summary_text,
        },
    }


def _is_business_signup_candidate(conversation: dict, lead: dict[str, Any]) -> bool:
    if conversation.get("conversation_type") != "call":
        return False
    if _conversation_direction(conversation) != "inbound":
        return False
    if conversation.get("shift_id") or conversation.get("cascade_id"):
        return False

    normalized_call_type = (lead.get("call_type") or "").strip().lower()
    denylist = {
        "callout_request",
        "worker_callout",
        "support",
        "current_customer_support",
        "partnership",
        "business_development",
    }
    allowlist = {
        "business_inquiry",
        "new_business_inquiry",
        "signup",
        "demo",
        "pricing",
        "sales",
    }

    if normalized_call_type in denylist:
        return False
    if normalized_call_type in allowlist:
        return True

    search_text = _combined_text(
        lead.get("pain_point_summary"),
        lead.get("notes"),
        (conversation.get("analysis") or {}).get("call_summary"),
        conversation.get("transcript_text"),
        conversation.get("transcript"),
    ).lower()

    support_markers = (
        "already use backfill",
        "need support",
        "support team",
        "existing customer",
    )
    business_markers = (
        "for business",
        "using backfill",
        "using the service",
        "pricing",
        "demo",
        "covering shifts when someone calls out",
        "last-minute shift gaps",
        "handle call-outs",
    )

    if any(marker in search_text for marker in support_markers):
        return False
    if any(marker in search_text for marker in business_markers):
        return bool(lead.get("contact_phone"))

    return bool(
        lead.get("contact_phone")
        and (
            lead.get("business_name")
            or lead.get("contact_email")
            or lead.get("pain_point_summary")
            or lead.get("location_count")
        )
    )


async def _resolve_organization_id(
    db: aiosqlite.Connection,
    *,
    session: dict | None,
    business_name: Optional[str],
    vertical: Optional[str],
    contact_name: Optional[str],
    contact_phone: Optional[str],
    contact_email: Optional[str],
    location_count: Optional[int],
) -> Optional[int]:
    existing_id = session.get("organization_id") if session else None
    if existing_id:
        await queries.update_organization(
            db,
            int(existing_id),
            {
                "vertical": vertical,
                "contact_name": contact_name,
                "contact_phone": contact_phone,
                "contact_email": contact_email,
                "location_count_estimate": location_count,
            },
        )
        return int(existing_id)

    normalized_name = (business_name or "").strip()
    if not normalized_name:
        return None

    existing = await queries.get_organization_by_name(db, normalized_name)
    if existing is not None:
        await queries.update_organization(
            db,
            int(existing["id"]),
            {
                "vertical": vertical,
                "contact_name": contact_name,
                "contact_phone": contact_phone,
                "contact_email": contact_email,
                "location_count_estimate": location_count,
            },
        )
        return int(existing["id"])

    return await queries.insert_organization(
        db,
        {
            "name": normalized_name,
            "vertical": vertical,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "contact_email": contact_email,
            "location_count_estimate": location_count,
        },
    )


async def maybe_send_post_call_signup(db: aiosqlite.Connection, conversation: dict) -> Optional[dict]:
    existing = await queries.get_onboarding_session_by_source_external_id(
        db,
        conversation["external_id"],
    )
    if existing is not None:
        if not existing.get("sent_message_sid") and existing.get("status") == "pending":
            return await _retry_pending_signup_session(db, existing)
        return existing

    lead = extract_lead_fields_from_conversation(conversation)
    if not _is_business_signup_candidate(conversation, lead):
        return None

    organization_id = await _resolve_organization_id(
        db,
        session=None,
        business_name=lead.get("business_name"),
        vertical=lead.get("vertical"),
        contact_name=lead.get("contact_name"),
        contact_phone=lead.get("contact_phone"),
        contact_email=lead.get("contact_email"),
        location_count=lead.get("location_count"),
    )
    token, token_hash = _new_session_token()
    session_id = await queries.insert_onboarding_session(
        db,
        {
            "token_hash": token_hash,
            "source_conversation_id": conversation.get("id"),
            "source_external_id": conversation["external_id"],
            "organization_id": organization_id,
            "status": "pending",
            **lead,
        },
    )

    url = f"{settings.backfill_web_base_url}/signup/{token}"
    message = (
        "Thanks for calling Backfill. We’d love to help your team cover call-outs faster. "
        f"Review what we captured and finish setup here: {url} "
        "Reply here if you want help."
    )
    await _try_send_signup_session_sms(
        db,
        session_id=session_id,
        phone=str(lead["contact_phone"]),
        message=message,
        dynamic_variables=_signup_sms_dynamic_variables(lead=lead, signup_url=url),
    )
    session = await queries.get_onboarding_session(db, session_id)
    assert session is not None
    session["signup_url"] = url
    return session


async def _try_send_signup_session_sms(
    db: aiosqlite.Connection,
    *,
    session_id: int,
    phone: str,
    message: str,
    dynamic_variables: Optional[dict[str, str]] = None,
) -> None:
    normalized_phone = _normalize_phone_e164(phone)
    if normalized_phone is None:
        _logger.warning(
            "Skipping onboarding SMS for session %s: could not normalize phone %r to E.164",
            session_id,
            phone,
        )
        return
    try:
        message_sid = send_sms(
            normalized_phone,
            message,
            dynamic_variables=dynamic_variables,
        )
    except Exception:
        _logger.exception(
            "Failed to send onboarding SMS to %s for session %s",
            normalized_phone,
            session_id,
        )
        return
    await queries.update_onboarding_session(
        db,
        session_id,
        {
            "contact_phone": normalized_phone,
            "sent_message_sid": message_sid,
            "sent_at": datetime.utcnow().isoformat(),
        },
    )


async def _retry_pending_signup_session(
    db: aiosqlite.Connection,
    session: dict,
) -> dict:
    phone = _normalize_phone_e164(session.get("contact_phone"))
    if phone is None:
        return session
    token, token_hash = _new_session_token()
    url = f"{settings.backfill_web_base_url}/signup/{token}"
    await queries.update_onboarding_session(
        db,
        int(session["id"]),
        {
            "token_hash": token_hash,
            "contact_phone": phone,
        },
    )
    message = (
        "Thanks for calling Backfill. We’d love to help your team cover call-outs faster. "
        f"Review what we captured and finish setup here: {url} "
        "Reply here if you want help."
    )
    await _try_send_signup_session_sms(
        db,
        session_id=int(session["id"]),
        phone=phone,
        message=message,
        dynamic_variables=_signup_sms_dynamic_variables(session=session, signup_url=url),
    )
    refreshed = await queries.get_onboarding_session(db, int(session["id"]))
    assert refreshed is not None
    refreshed["signup_url"] = url
    return refreshed


async def get_signup_session_by_token(
    db: aiosqlite.Connection,
    token: str,
) -> Optional[dict]:
    session = await queries.get_onboarding_session_by_token_hash(db, _token_hash(token))
    if session is None:
        return None
    if session.get("organization_id"):
        session["organization"] = await queries.get_organization(db, int(session["organization_id"]))
    if session.get("location_id"):
        session["location"] = await queries.get_location(db, int(session["location_id"]))
    return session


async def complete_signup_session(
    db: aiosqlite.Connection,
    token: str,
    data: dict,
) -> dict:
    session = await get_signup_session_by_token(db, token)
    if session is None:
        raise ValueError("Onboarding session not found")

    business_name = _coerce_str(data.get("business_name")) or session.get("business_name")
    location_name = _coerce_str(data.get("location_name")) or session.get("location_name")
    contact_name = _coerce_str(data.get("contact_name")) or session.get("contact_name")
    contact_phone = _coerce_str(data.get("contact_phone")) or session.get("contact_phone")
    contact_email = _coerce_str(data.get("contact_email")) or session.get("contact_email")
    vertical = _coerce_str(data.get("vertical")) or session.get("vertical") or "other"
    address = _coerce_str(data.get("address"))
    if not location_name:
        raise ValueError("Location name is required")
    if not contact_phone:
        raise ValueError("Primary contact phone is required")

    location_count = _coerce_int(data.get("location_count")) or session.get("location_count")
    employee_count = _coerce_int(data.get("employee_count"))
    scheduling_platform = _normalize_platform(data.get("scheduling_platform")) or "backfill_native"
    setup_kind = _normalize_kind(data.get("setup_kind"))
    notes = _coerce_str(data.get("notes")) or session.get("notes")
    pain_point_summary = _coerce_str(data.get("pain_point_summary")) or session.get("pain_point_summary")
    urgency = _coerce_str(data.get("urgency")) or session.get("urgency")

    organization_id = await _resolve_organization_id(
        db,
        session=session,
        business_name=business_name,
        vertical=vertical,
        contact_name=contact_name,
        contact_phone=contact_phone,
        contact_email=contact_email,
        location_count=location_count,
    )

    onboarding_notes = "\n".join(
        part for part in [pain_point_summary, notes] if isinstance(part, str) and part.strip()
    ) or None
    location_payload = {
        "name": location_name,
        "organization_id": organization_id,
        "vertical": vertical,
        "address": address,
        "employee_count": employee_count,
        "manager_name": contact_name,
        "manager_phone": contact_phone,
        "manager_email": contact_email,
        "scheduling_platform": scheduling_platform,
        "integration_status": "pending_setup" if scheduling_platform != "backfill_native" else "native_lite",
        "onboarding_info": onboarding_notes,
    }

    if session.get("location_id"):
        location_id = int(session["location_id"])
        await queries.update_location(db, location_id, location_payload)
    else:
        location_id = await queries.insert_location(db, location_payload)

    extracted_fields = dict(session.get("extracted_fields") or {})
    extracted_fields.update(
        {
            "business_name": business_name,
            "location_name": location_name,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "contact_email": contact_email,
            "vertical": vertical,
            "location_count": location_count,
            "employee_count": employee_count,
            "address": address,
            "pain_point_summary": pain_point_summary,
            "urgency": urgency,
            "notes": notes,
            "setup_kind": setup_kind,
            "scheduling_platform": scheduling_platform,
        }
    )
    await queries.update_onboarding_session(
        db,
        int(session["id"]),
        {
            "organization_id": organization_id,
            "location_id": location_id,
            "status": "completed",
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "contact_email": contact_email,
            "business_name": business_name,
            "location_name": location_name,
            "vertical": vertical,
            "location_count": location_count,
            "employee_count": employee_count,
            "address": address,
            "pain_point_summary": pain_point_summary,
            "urgency": urgency,
            "notes": notes,
            "setup_kind": setup_kind,
            "scheduling_platform": scheduling_platform,
            "extracted_fields": extracted_fields,
            "completed_at": datetime.utcnow().isoformat(),
        },
    )
    location = await queries.get_location(db, location_id)
    assert location is not None
    organization = await queries.get_organization(db, organization_id) if organization_id else None
    next_path = build_setup_resume_path(
        kind=setup_kind,
        location_id=location_id,
        platform=scheduling_platform,
    )
    return {
        "status": "completed",
        "organization": organization,
        "location": location,
        "next_path": next_path,
    }
