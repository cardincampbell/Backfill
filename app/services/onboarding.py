"""
Helpers for manager onboarding handoff.

The phone call captures intent and basics. Structured setup happens on the web.
"""
from __future__ import annotations

from typing import Optional

from app.services.messaging import send_sms

BASE_URL = "https://backfill.com"


def _normalize_platform(platform: Optional[str]) -> str:
    value = (platform or "").strip().lower().replace(" ", "_")
    aliases = {
        "7shifts": "7shifts",
        "seven_shifts": "7shifts",
        "deputy": "deputy",
        "when_i_work": "wheniwork",
        "wheniwork": "wheniwork",
        "homebase": "homebase",
    }
    return aliases.get(value, "")


def build_onboarding_path(kind: str, platform: Optional[str] = None) -> str:
    route_kind = kind.strip().lower()
    normalized_platform = _normalize_platform(platform)

    if route_kind == "integration":
        if normalized_platform:
            return f"/setup/connect?platform={normalized_platform}"
        return "/setup/connect"
    if route_kind == "csv_upload":
        return "/setup/upload"
    if route_kind == "manual_form":
        return "/setup/add"
    raise ValueError(f"Unsupported onboarding link kind: {kind!r}")


def build_onboarding_url(kind: str, platform: Optional[str] = None) -> str:
    return f"{BASE_URL}{build_onboarding_path(kind, platform=platform)}"


def send_onboarding_link(phone: str, kind: str, platform: Optional[str] = None) -> dict:
    path = build_onboarding_path(kind, platform=platform)
    url = f"{BASE_URL}{path}"
    message = (
        f"Backfill setup: use this link to continue onboarding: {url} "
        "Reply here if you need help."
    )
    message_sid = send_sms(phone, message)
    return {
        "kind": kind,
        "platform": _normalize_platform(platform) or None,
        "path": path,
        "url": url,
        "message_sid": message_sid,
    }
