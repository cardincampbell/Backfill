#!/usr/bin/env python3
"""
Import or update a Twilio-backed phone number inside Retell.

This script handles the Retell side of a custom telephony setup. It does not
configure Twilio webhooks for SMS; Backfill still expects inbound SMS to hit
/webhooks/twilio/sms directly on your backend.

Required env vars:
  RETELL_API_KEY
  RETELL_FROM_NUMBER
  RETELL_TWILIO_TERMINATION_URI

Optional env vars:
  RETELL_AGENT_ID_INBOUND
  RETELL_AGENT_ID_OUTBOUND
  RETELL_CHAT_AGENT_ID
  RETELL_CHAT_AGENT_ID_INBOUND
  RETELL_CHAT_AGENT_ID_OUTBOUND
  RETELL_TWILIO_AUTH_USERNAME
  RETELL_TWILIO_AUTH_PASSWORD
  RETELL_TWILIO_TRANSPORT=TLS
  RETELL_PHONE_NICKNAME=Backfill Primary
  RETELL_ALLOWED_INBOUND_COUNTRIES=US,CA
  RETELL_ALLOWED_OUTBOUND_COUNTRIES=US,CA
"""
from __future__ import annotations

import os
import sys
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.retellai.com"


def _require(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        sys.exit(f"ERROR: {key} is not set in .env")
    return value


def _split_csv_env(key: str, default: str) -> list[str]:
    raw = os.environ.get(key, default)
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _agent_binding(agent_id: str) -> list[dict]:
    if not agent_id:
        return []
    return [{"agent_id": agent_id, "weight": 1.0}]


def _chat_agent_binding(agent_kind: str) -> list[dict]:
    generic_agent = os.environ.get("RETELL_CHAT_AGENT_ID", "").strip()
    specific_agent = os.environ.get(f"RETELL_CHAT_AGENT_ID_{agent_kind.upper()}", "").strip()
    return _agent_binding(specific_agent or generic_agent)


def _build_payload() -> tuple[str, dict]:
    phone_number = _require("RETELL_FROM_NUMBER")
    payload = {
        "nickname": os.environ.get("RETELL_PHONE_NICKNAME", "Backfill Primary"),
        "allowed_inbound_country_list": _split_csv_env(
            "RETELL_ALLOWED_INBOUND_COUNTRIES", "US,CA"
        ),
        "allowed_outbound_country_list": _split_csv_env(
            "RETELL_ALLOWED_OUTBOUND_COUNTRIES", "US,CA"
        ),
        "inbound_agents": _agent_binding(os.environ.get("RETELL_AGENT_ID_INBOUND", "").strip()),
        "outbound_agents": _agent_binding(os.environ.get("RETELL_AGENT_ID_OUTBOUND", "").strip()),
        "inbound_sms_agents": _chat_agent_binding("inbound"),
        "outbound_sms_agents": _chat_agent_binding("outbound"),
    }
    return phone_number, payload


def _build_import_payload(phone_number: str, payload: dict) -> dict:
    import_payload = {
        "phone_number": phone_number,
        "termination_uri": _require("RETELL_TWILIO_TERMINATION_URI"),
        "transport": os.environ.get("RETELL_TWILIO_TRANSPORT", "TLS").strip().upper() or "TLS",
        **payload,
    }
    username = os.environ.get("RETELL_TWILIO_AUTH_USERNAME", "").strip()
    password = os.environ.get("RETELL_TWILIO_AUTH_PASSWORD", "").strip()
    if username:
        import_payload["sip_trunk_auth_username"] = username
    if password:
        import_payload["sip_trunk_auth_password"] = password
    return import_payload


def _build_update_payload(payload: dict) -> dict:
    update_payload = {
        "termination_uri": _require("RETELL_TWILIO_TERMINATION_URI"),
        "transport": os.environ.get("RETELL_TWILIO_TRANSPORT", "TLS").strip().upper() or "TLS",
        **payload,
    }
    username = os.environ.get("RETELL_TWILIO_AUTH_USERNAME", "").strip()
    password = os.environ.get("RETELL_TWILIO_AUTH_PASSWORD", "").strip()
    if username:
        update_payload["auth_username"] = username
    if password:
        update_payload["auth_password"] = password
    return update_payload


def main() -> None:
    api_key = _require("RETELL_API_KEY")
    phone_number, payload = _build_payload()
    headers = {"Authorization": f"Bearer {api_key}"}

    with httpx.Client(base_url=API_BASE, headers=headers, timeout=30.0) as client:
        response = client.get("/list-phone-numbers")
        response.raise_for_status()
        existing_numbers = response.json()
        existing = next(
            (item for item in existing_numbers if item.get("phone_number") == phone_number),
            None,
        )

        if existing is None:
            request_body = _build_import_payload(phone_number, payload)
            response = client.post("/import-phone-number", json=request_body)
            response.raise_for_status()
            number = response.json()
            action = "imported"
        else:
            request_body = _build_update_payload(payload)
            encoded_number = quote(phone_number, safe="")
            response = client.patch(f"/update-phone-number/{encoded_number}", json=request_body)
            response.raise_for_status()
            number = response.json()
            action = "updated"

    print(f"Retell phone number {action}: {number['phone_number']}")
    print(f"  nickname: {number.get('nickname')}")
    print(f"  type: {number.get('phone_number_type')}")
    print(
        "  inbound agents: "
        f"{[item.get('agent_id') for item in (number.get('inbound_agents') or [])]}"
    )
    print(
        "  outbound agents: "
        f"{[item.get('agent_id') for item in (number.get('outbound_agents') or [])]}"
    )
    trunk = number.get("sip_outbound_trunk_config") or {}
    if trunk:
        print(f"  termination uri: {trunk.get('termination_uri')}")


if __name__ == "__main__":
    main()
