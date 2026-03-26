"""
When I Work adapter — developer key auth, read + conditional write.

Docs: https://apidocs.wheniwork.com/
Auth: W-Token header (developer key per account)

Write support is conditional — WIW shift assignment write-back is tested
in sandbox before enabling. Set _write_supported=True once confirmed.
"""
from __future__ import annotations

import httpx

from app.integrations.base import SchedulingAdapter

_BASE = "https://api.wheniwork.com/2"


class WhenIWorkAdapter(SchedulingAdapter):
    """
    Read + conditional write integration with When I Work.

    Roster sync   → GET /2/users
    Schedule sync → GET /2/shifts
    Open shifts   → GET /2/openshifts
    Fill write-back → POST /2/shifts/{id} (only if _write_supported=True)
    """

    def __init__(self, api_token: str, account_id: str, write_supported: bool = False):
        """
        api_token: per-account W-Token from When I Work login
        account_id: WIW account/location identifier
        write_supported: flip True once shift assignment write-back is confirmed
        """
        self.api_token = api_token
        self.account_id = account_id
        self._write_supported = write_supported

    def _headers(self) -> dict:
        return {
            "W-Token": self.api_token,
            "Content-Type": "application/json",
        }

    async def sync_roster(self, location_id: int) -> list[dict]:
        """Fetch all users (employees) from WIW."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/users",
                headers=self._headers(),
                params={"account_id": self.account_id, "include_deleted": False},
            )
            resp.raise_for_status()
        workers = []
        for u in resp.json().get("users", []):
            workers.append({
                "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip(),
                "phone": u.get("phone_number") or "",
                "email": u.get("email"),
                "source_id": str(u.get("id") or u.get("user_id") or ""),
                "roles": [u["role"]] if u.get("role") else [],
                "location_id": location_id,
                "source": "wheniwork",
                "sms_consent_status": "pending",
                "voice_consent_status": "pending",
            })
        return workers

    async def sync_schedule(self, location_id: int, date_range: tuple) -> list[dict]:
        """Fetch scheduled shifts from WIW for a date window."""
        start, end = date_range
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/shifts",
                headers=self._headers(),
                params={
                    "account_id": self.account_id,
                    "start": str(start),
                    "end": str(end),
                },
            )
            resp.raise_for_status()
        shifts = []
        for s in resp.json().get("shifts", []):
            shifts.append({
                "location_id": location_id,
                "scheduling_platform_id": str(s.get("id") or s.get("shift_id") or ""),
                "role": s.get("position_name", "unknown"),
                "date": (s.get("start_time") or "")[:10],
                "start_time": (s.get("start_time") or "")[11:19],
                "end_time": (s.get("end_time") or "")[11:19],
                "pay_rate": float(s.get("hourly_rate") or 0),
                "status": "scheduled",
                "source_platform": "wheniwork",
            })
        return shifts

    async def on_vacancy(self, shift: dict) -> None:
        # Open shifts (unassigned) are detected via GET /2/openshifts
        # or WIW webhook events (if available).  The scheduling_hooks router
        # handles webhook events and calls create_vacancy().
        pass

    async def push_fill(self, shift: dict, worker: dict) -> None:
        """Assign worker to shift in WIW — only if write_supported is confirmed."""
        if not self._write_supported:
            # Native Lite companion mode: fill state stays in Backfill only.
            return
        external_shift_id = shift.get("scheduling_platform_id")
        external_user_id = worker.get("source_id")
        if not external_shift_id or not external_user_id:
            return
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_BASE}/shifts/{external_shift_id}",
                headers=self._headers(),
                json={"user_id": external_user_id},
            )
            resp.raise_for_status()
