"""
Homebase adapter — read-only companion mode.

Backfill pulls roster and schedule data for context.
All fill operations run in the Native Lite companion layer —
nothing writes back to Homebase (read-only API).

Auth: API key per location account (HOMEBASE_API_KEY)
Docs: https://joinhomebase.com/api/

Phase 1 — roster + schedule polling implemented.
No webhook support — use on-demand sync or periodic polling.
"""
from __future__ import annotations

import httpx

from app.integrations.base import SchedulingAdapter

_BASE = "https://app.joinhomebase.com/api/public"


class HomebaseAdapter(SchedulingAdapter):
    """
    Read-only Homebase integration.

    Roster sync   → GET /v1/employees
    Schedule sync → GET /v1/schedules
    on_vacancy    → no-op (vacancies always created in Native Lite)
    push_fill     → no-op (Homebase is read-only)
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def sync_roster(self, location_id: int) -> list[dict]:
        """Fetch employees from Homebase and return normalized worker dicts."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/v1/employees",
                headers=self._headers(),
            )
            resp.raise_for_status()
        workers = []
        for emp in resp.json().get("employees", []):
            if not emp.get("active", True):
                continue
            workers.append({
                "name": f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip(),
                "phone": emp.get("phone_number") or "",
                "email": emp.get("email"),
                "source_id": str(emp.get("id") or emp.get("employee_id") or ""),
                "roles": [emp["job_title"]] if emp.get("job_title") else [],
                "location_id": location_id,
                "source": "homebase",
                "sms_consent_status": "pending",
                "voice_consent_status": "pending",
            })
        return workers

    async def sync_schedule(self, location_id: int, date_range: tuple) -> list[dict]:
        """Fetch schedules from Homebase for a date window."""
        start, end = date_range
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/v1/schedules",
                headers=self._headers(),
                params={"start_date": str(start), "end_date": str(end)},
            )
            resp.raise_for_status()
        shifts = []
        for s in resp.json().get("schedules", []):
            shifts.append({
                "location_id": location_id,
                "scheduling_platform_id": str(s.get("id") or s.get("schedule_id") or ""),
                "role": s.get("role", "unknown"),
                "date": s.get("date", ""),
                "start_time": s.get("start_time", ""),
                "end_time": s.get("end_time", ""),
                "pay_rate": float(s.get("hourly_rate") or 0),
                "status": "scheduled",
                "source_platform": "homebase",
            })
        return shifts

    async def on_vacancy(self, shift: dict) -> None:
        # Read-only: vacancies are always created in Native Lite,
        # never detected from Homebase events (no webhook support).
        pass

    # push_fill is intentionally a no-op — Homebase is read-only (inherited from base)
