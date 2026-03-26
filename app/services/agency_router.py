"""
Agency partner routing.

This is the Tier 3 fallback once internal staff and alumni are exhausted and
the location has approved external supply.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import aiosqlite

from app.db.queries import (
    get_location,
    get_shift,
    insert_agency_request,
    list_agency_requests,
    list_agency_partners,
)
from app.models.audit import AuditAction
from app.services import audit as audit_svc
from app.services.messaging import send_sms


def _match_score(shift: dict, location: dict, partner: dict) -> tuple:
    required_certs = set(shift.get("requirements") or [])
    supported_certs = set(partner.get("certifications_supported") or [])
    cert_match = 1 if required_certs.issubset(supported_certs) else 0

    supported_roles = set(partner.get("roles_supported") or [])
    role_match = 1 if shift["role"] in supported_roles else 0

    address = (location.get("address") or "").lower()
    coverage_match = 1 if any(area.lower() in address for area in partner.get("coverage_areas") or []) else 0

    preferred_partners = set(location.get("preferred_agency_partners") or [])
    preferred = 1 if partner["id"] in preferred_partners else 0
    priority_sla = 1 if partner.get("sla_tier") == "priority" else 0
    fill_rate = float(partner.get("fill_rate") or 0)
    acceptance_rate = float(partner.get("acceptance_rate") or 0)

    return (
        preferred,
        role_match,
        cert_match,
        coverage_match,
        priority_sla,
        fill_rate,
        acceptance_rate,
    )


def _build_request_message(shift: dict, location: dict) -> str:
    requirements = ", ".join(shift.get("requirements") or []) or "none"
    notes = location.get("onboarding_info") or "none"
    return (
        f"Backfill request for {location['name']}: "
        f"{shift['role']} on {shift['date']} {shift['start_time']}-{shift['end_time']} "
        f"@ ${shift['pay_rate']}/hr. Requirements: {requirements}. "
        f"Notes: {notes}. Reply with accepted / declined / unavailable."
    )


def _send_request(partner: dict, body: str) -> str:
    if partner.get("contact_channel") == "sms" and partner.get("contact_info"):
        send_sms(partner["contact_info"], body)
        return "sms"
    # Email and other channels remain operational placeholders until a
    # dedicated email/API transport is added.
    print(f"[AGENCY REQUEST → {partner.get('contact_channel')}:{partner.get('contact_info')}] {body}")
    return partner.get("contact_channel") or "email"


async def route_to_agencies(
    db: aiosqlite.Connection,
    cascade_id: int,
    shift_id: int,
) -> dict:
    existing = await list_agency_requests(db, cascade_id=cascade_id)
    if existing:
        return {"status": "agency_routed", "requests": existing}

    shift = await get_shift(db, shift_id)
    if shift is None:
        raise ValueError(f"Shift {shift_id} not found")
    location = await get_location(db, shift["location_id"])
    if location is None:
        raise ValueError(f"Location {shift['location_id']} not found")

    partners = await list_agency_partners(db)
    ranked = sorted(partners, key=lambda partner: _match_score(shift, location, partner), reverse=True)

    body = _build_request_message(shift, location)
    requests: list[dict] = []
    for partner in ranked[:3]:
        deadline = datetime.utcnow() + timedelta(minutes=int(partner.get("avg_response_time_minutes") or 30))
        channel = _send_request(partner, body)
        agency_request_id = await insert_agency_request(
            db,
            {
                "shift_id": shift_id,
                "cascade_id": cascade_id,
                "agency_partner_id": partner["id"],
                "status": "sent",
                "request_timestamp": datetime.utcnow().isoformat(),
                "response_deadline": deadline.isoformat(),
                "notes": f"transport={channel}",
            },
        )
        await audit_svc.append(
            db,
            AuditAction.agency_request_sent,
            entity_type="agency_request",
            entity_id=agency_request_id,
            details={
                "cascade_id": cascade_id,
                "shift_id": shift_id,
                "agency_partner_id": partner["id"],
                "channel": channel,
            },
        )
        requests.append(
            {
                "agency_request_id": agency_request_id,
                "agency_partner_id": partner["id"],
                "channel": channel,
                "response_deadline": deadline.isoformat(),
            }
        )

    return {"status": "agency_routed", "requests": requests}
