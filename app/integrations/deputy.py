"""
Deputy adapter — OAuth 2.0 per-installation, read + write.

Docs: https://developer.deputy.com/
Auth: OAuth 2.0 client_credentials (per Deputy installation URL)
      DEPUTY_CLIENT_ID + DEPUTY_CLIENT_SECRET
"""
from __future__ import annotations

import httpx

from app.integrations.base import SchedulingAdapter


class DeputyAdapter(SchedulingAdapter):
    """
    Full read+write integration with Deputy.

    Each location has its own Deputy installation URL (install_url).
    access_token is fetched via OAuth and cached until expiry.

    Roster sync   → GET /api/v1/resource/Employee
    Schedule sync → GET /api/v1/resource/Roster
    Vacancy       → Deputy webhook (Employee.Update, Roster.Delete) via scheduling_hooks
    Fill write-back → POST /api/v1/resource/Timesheet
    """

    def __init__(self, client_id: str, client_secret: str, install_url: str):
        """
        client_id / client_secret: from DEPUTY_CLIENT_ID / DEPUTY_CLIENT_SECRET
        install_url: per-location Deputy installation (e.g. https://myco.na.deputy.com)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.install_url = install_url.rstrip("/")
        self._token: str | None = None

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.install_url}/oauth/v1/access_token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                    "scope": "longlife_refresh_token",
                },
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        return self._token

    async def _headers(self) -> dict:
        token = await self._get_token()
        return {"Authorization": f"OAuth {token}", "Content-Type": "application/json"}

    async def sync_roster(self, location_id: int) -> list[dict]:
        """Fetch all active employees from Deputy."""
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.install_url}/api/v1/resource/Employee",
                headers=headers,
                params={"max": 500},
            )
            resp.raise_for_status()
        workers = []
        for emp in resp.json():
            if not emp.get("Active"):
                continue
            workers.append({
                "name": f"{emp.get('FirstName', '')} {emp.get('LastName', '')}".strip(),
                "phone": emp.get("MobilePhone") or emp.get("Phone") or "",
                "email": emp.get("Email"),
                "source_id": str(emp.get("Id") or emp.get("id") or ""),
                "roles": [emp["Role"]] if emp.get("Role") else [],
                "location_id": location_id,
                "source": "deputy",
                "sms_consent_status": "pending",
                "voice_consent_status": "pending",
            })
        return workers

    async def sync_schedule(self, location_id: int, date_range: tuple) -> list[dict]:
        """Fetch roster entries (scheduled shifts) from Deputy."""
        start, end = date_range
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.install_url}/api/v1/resource/Roster",
                headers=headers,
                params={"max": 500, "start": str(start), "end": str(end)},
            )
            resp.raise_for_status()
        shifts = []
        for r in resp.json():
            date_str = (r.get("Date") or "")[:10]
            shifts.append({
                "location_id": location_id,
                "scheduling_platform_id": str(r.get("Id") or r.get("id") or ""),
                "role": r.get("OperationalUnitName", "unknown"),
                "date": date_str,
                "start_time": r.get("StartTime", ""),
                "end_time": r.get("EndTime", ""),
                "pay_rate": float(r.get("Cost") or 0),
                "status": "scheduled",
                "source_platform": "deputy",
            })
        return shifts

    async def on_vacancy(self, shift: dict) -> None:
        # Vacancies are detected via Deputy webhooks (Roster Delete events)
        # handled in scheduling_hooks.py, which calls create_vacancy().
        pass

    async def push_fill(self, shift: dict, worker: dict) -> None:
        """Create a Timesheet entry in Deputy to record the fill."""
        headers = await self._headers()
        external_shift_id = shift.get("scheduling_platform_id")
        external_employee_id = worker.get("source_id")
        if not external_shift_id or not external_employee_id:
            return
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.install_url}/api/v1/resource/Roster/{external_shift_id}",
                headers=headers,
                json={"Employee": external_employee_id, "Published": True},
            )
            resp.raise_for_status()
