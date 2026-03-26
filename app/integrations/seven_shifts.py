"""
7shifts adapter — OAuth 2.0 client_credentials, read + write.

Docs: https://developers.7shifts.com/
Auth: OAuth 2.0 — SEVENSHIFTS_CLIENT_ID + SEVENSHIFTS_CLIENT_SECRET
"""
from __future__ import annotations

import httpx

from app.integrations.base import SchedulingAdapter

_BASE = "https://api.7shifts.com/v2"
_TOKEN_URL = "https://app.7shifts.com/oauth2/token"


class SevenShiftsAdapter(SchedulingAdapter):
    """
    Full read+write integration with 7shifts.

    Roster sync  → GET /v2/company/{id}/users
    Schedule sync → GET /v2/company/{id}/shifts
    Vacancy       → handled via Backfill webhook (7shifts sends shift.deleted or punch.callout)
    Fill write-back → POST /v2/company/{id}/shifts/{shift_id}/assign
    """

    def __init__(self, client_id: str, client_secret: str, company_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.company_id = company_id
        self._token: str | None = None

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        return self._token

    async def _headers(self) -> dict:
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def sync_roster(self, location_id: int) -> list[dict]:
        """Pull employees from 7shifts and return normalized worker dicts."""
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/company/{self.company_id}/users",
                headers=headers,
                params={"limit": 500},
            )
            resp.raise_for_status()
        workers = []
        for emp in resp.json().get("data", []):
            workers.append({
                "name": f"{emp.get('firstname', '')} {emp.get('lastname', '')}".strip(),
                "phone": emp.get("mobile_phone") or emp.get("phone") or "",
                "email": emp.get("email"),
                "source_id": str(emp.get("id") or emp.get("user_id") or ""),
                "roles": [emp["role"]] if emp.get("role") else [],
                "location_id": location_id,
                "source": "7shifts",
                "sms_consent_status": "pending",
                "voice_consent_status": "pending",
            })
        return workers

    async def sync_schedule(self, location_id: int, date_range: tuple) -> list[dict]:
        """Pull shifts from 7shifts for a date window."""
        start, end = date_range
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/company/{self.company_id}/shifts",
                headers=headers,
                params={"start": str(start), "end": str(end), "limit": 500},
            )
            resp.raise_for_status()
        shifts = []
        for s in resp.json().get("data", []):
            shifts.append({
                "location_id": location_id,
                "scheduling_platform_id": str(s.get("id") or s.get("shift_id") or ""),
                "role": s.get("role_name", "unknown"),
                "date": s.get("start", "")[:10],
                "start_time": s.get("start", "")[11:19],
                "end_time": s.get("end", "")[11:19],
                "pay_rate": float(s.get("hourly_wage") or 0),
                "status": "scheduled",
                "source_platform": "7shifts",
            })
        return shifts

    async def on_vacancy(self, shift: dict) -> None:
        # Vacancy is created in Backfill when 7shifts sends a webhook
        # (punch.callout or shift.deleted). No action needed here — the
        # scheduling_hooks router translates the webhook into create_vacancy().
        pass

    async def push_fill(self, shift: dict, worker: dict) -> None:
        """Write fill confirmation back to 7shifts by assigning the worker to the shift."""
        external_shift_id = shift.get("scheduling_platform_id")
        external_worker_id = worker.get("source_id")
        if not external_shift_id or not external_worker_id:
            return
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_BASE}/company/{self.company_id}/shifts/{external_shift_id}/assign",
                headers=headers,
                json={"user_id": external_worker_id},
            )
            resp.raise_for_status()
