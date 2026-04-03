from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app_v2.config import v2_settings
from app_v2.models.common import SchedulerProvider
from app_v2.models.integrations import SchedulerConnection


@dataclass
class ExternalEmployeeRecord:
    external_ref: str
    full_name: str
    phone_e164: str | None = None
    email: str | None = None
    role_names: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class ExternalShiftRecord:
    external_ref: str
    role_name: str
    starts_at: datetime
    ends_at: datetime
    timezone: str
    status: str = "scheduled"
    seats_requested: int = 1
    assigned_external_refs: list[str] = field(default_factory=list)
    requires_manager_approval: bool = False
    premium_cents: int = 0
    notes: str | None = None
    metadata: dict = field(default_factory=dict)


class SchedulerAdapter(ABC):
    @abstractmethod
    async def sync_roster(self, connection: SchedulerConnection) -> list[ExternalEmployeeRecord]:
        raise NotImplementedError

    @abstractmethod
    async def sync_schedule(
        self,
        connection: SchedulerConnection,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ExternalShiftRecord]:
        raise NotImplementedError

    async def push_fill(
        self,
        connection: SchedulerConnection,
        *,
        external_shift_ref: str,
        external_employee_ref: str,
    ) -> None:
        return None


class NativeAdapter(SchedulerAdapter):
    async def sync_roster(self, connection: SchedulerConnection) -> list[ExternalEmployeeRecord]:
        return []

    async def sync_schedule(
        self,
        connection: SchedulerConnection,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ExternalShiftRecord]:
        return []


def _credentials_value(connection: SchedulerConnection, *keys: str) -> str:
    payload = connection.credentials or {}
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value).strip()
    return ""


def _iso_to_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            value = value / 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _role_name(*values: Any) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value).strip()
    return "team_member"


def _assigned_refs(*values: Any) -> list[str]:
    refs: list[str] = []
    for value in values:
        if value in (None, ""):
            continue
        if isinstance(value, list):
            refs.extend(str(item).strip() for item in value if str(item).strip())
            continue
        refs.append(str(value).strip())
    deduped: list[str] = []
    for item in refs:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


class SevenShiftsAdapter(SchedulerAdapter):
    base_url = "https://api.7shifts.com/v2"
    token_url = "https://app.7shifts.com/oauth2/token"

    def __init__(self, *, client_id: str, client_secret: str, company_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.company_id = company_id
        self._token: str | None = None

    async def _headers(self) -> dict[str, str]:
        if not self._token:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                )
                response.raise_for_status()
                self._token = response.json()["access_token"]
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def sync_roster(self, connection: SchedulerConnection) -> list[ExternalEmployeeRecord]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/company/{self.company_id}/users",
                headers=await self._headers(),
                params={"limit": 500},
            )
            response.raise_for_status()
        records: list[ExternalEmployeeRecord] = []
        for employee in response.json().get("data", []):
            records.append(
                ExternalEmployeeRecord(
                    external_ref=str(employee.get("id") or employee.get("user_id") or "").strip(),
                    full_name=f"{employee.get('firstname', '')} {employee.get('lastname', '')}".strip() or "Unknown Employee",
                    phone_e164=(employee.get("mobile_phone") or employee.get("phone") or "").strip() or None,
                    email=(employee.get("email") or "").strip() or None,
                    role_names=[_role_name(employee.get("role"), employee.get("role_name"))],
                    metadata=employee,
                )
            )
        return [record for record in records if record.external_ref]

    async def sync_schedule(
        self,
        connection: SchedulerConnection,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ExternalShiftRecord]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/company/{self.company_id}/shifts",
                headers=await self._headers(),
                params={
                    "start": window_start.date().isoformat(),
                    "end": window_end.date().isoformat(),
                    "limit": 500,
                },
            )
            response.raise_for_status()
        shifts: list[ExternalShiftRecord] = []
        timezone_value = connection.location.timezone if connection.location else "America/Los_Angeles"
        for payload in response.json().get("data", []):
            starts_at = _iso_to_datetime(payload.get("start"))
            ends_at = _iso_to_datetime(payload.get("end"))
            external_ref = str(payload.get("id") or payload.get("shift_id") or "").strip()
            if not external_ref or starts_at is None or ends_at is None:
                continue
            shifts.append(
                ExternalShiftRecord(
                    external_ref=external_ref,
                    role_name=_role_name(payload.get("role_name"), payload.get("role")),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    timezone=(payload.get("timezone") or timezone_value),
                    status=str(payload.get("status") or "scheduled").strip().lower(),
                    seats_requested=max(1, int(payload.get("seats") or 1)),
                    assigned_external_refs=_assigned_refs(
                        payload.get("user_id"),
                        payload.get("user_ids"),
                        payload.get("assigned_user_ids"),
                    ),
                    notes=(payload.get("notes") or "").strip() or None,
                    metadata=payload,
                )
            )
        return shifts

    async def push_fill(
        self,
        connection: SchedulerConnection,
        *,
        external_shift_ref: str,
        external_employee_ref: str,
    ) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/company/{self.company_id}/shifts/{external_shift_ref}/assign",
                headers=await self._headers(),
                json={"user_id": external_employee_ref},
            )
            response.raise_for_status()


class DeputyAdapter(SchedulerAdapter):
    def __init__(self, *, client_id: str, client_secret: str, install_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.install_url = install_url.rstrip("/")
        self._token: str | None = None

    async def _headers(self) -> dict[str, str]:
        if not self._token:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.install_url}/oauth/v1/access_token",
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "client_credentials",
                        "scope": "longlife_refresh_token",
                    },
                )
                response.raise_for_status()
                self._token = response.json()["access_token"]
        return {"Authorization": f"OAuth {self._token}", "Content-Type": "application/json"}

    async def sync_roster(self, connection: SchedulerConnection) -> list[ExternalEmployeeRecord]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.install_url}/api/v1/resource/Employee",
                headers=await self._headers(),
                params={"max": 500},
            )
            response.raise_for_status()
        records: list[ExternalEmployeeRecord] = []
        for employee in response.json():
            if not employee.get("Active"):
                continue
            external_ref = str(employee.get("Id") or employee.get("id") or "").strip()
            if not external_ref:
                continue
            records.append(
                ExternalEmployeeRecord(
                    external_ref=external_ref,
                    full_name=f"{employee.get('FirstName', '')} {employee.get('LastName', '')}".strip() or "Unknown Employee",
                    phone_e164=(employee.get("MobilePhone") or employee.get("Phone") or "").strip() or None,
                    email=(employee.get("Email") or "").strip() or None,
                    role_names=[_role_name(employee.get("Role"), employee.get("OperationalUnitName"))],
                    metadata=employee,
                )
            )
        return records

    async def sync_schedule(
        self,
        connection: SchedulerConnection,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ExternalShiftRecord]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.install_url}/api/v1/resource/Roster",
                headers=await self._headers(),
                params={
                    "max": 500,
                    "start": window_start.date().isoformat(),
                    "end": window_end.date().isoformat(),
                },
            )
            response.raise_for_status()
        shifts: list[ExternalShiftRecord] = []
        timezone_value = connection.location.timezone if connection.location else "America/Los_Angeles"
        for payload in response.json():
            external_ref = str(payload.get("Id") or payload.get("id") or "").strip()
            starts_at = _iso_to_datetime(payload.get("StartTime") or payload.get("start"))
            ends_at = _iso_to_datetime(payload.get("EndTime") or payload.get("end"))
            if not external_ref or starts_at is None or ends_at is None:
                continue
            shifts.append(
                ExternalShiftRecord(
                    external_ref=external_ref,
                    role_name=_role_name(payload.get("OperationalUnitName"), payload.get("Role")),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    timezone=(payload.get("Timezone") or timezone_value),
                    status=str(payload.get("Status") or payload.get("status") or "scheduled").strip().lower(),
                    seats_requested=max(1, int(payload.get("Slots") or 1)),
                    assigned_external_refs=_assigned_refs(payload.get("Employee"), payload.get("employee_id")),
                    notes=(payload.get("Comment") or "").strip() or None,
                    metadata=payload,
                )
            )
        return shifts

    async def push_fill(
        self,
        connection: SchedulerConnection,
        *,
        external_shift_ref: str,
        external_employee_ref: str,
    ) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.install_url}/api/v1/resource/Roster/{external_shift_ref}",
                headers=await self._headers(),
                json={"Employee": external_employee_ref, "Published": True},
            )
            response.raise_for_status()


class WhenIWorkAdapter(SchedulerAdapter):
    base_url = "https://api.wheniwork.com/2"

    def __init__(self, *, api_token: str, account_id: str, write_supported: bool = False):
        self.api_token = api_token
        self.account_id = account_id
        self.write_supported = write_supported

    def _headers(self) -> dict[str, str]:
        return {"W-Token": self.api_token, "Content-Type": "application/json"}

    async def sync_roster(self, connection: SchedulerConnection) -> list[ExternalEmployeeRecord]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/users",
                headers=self._headers(),
                params={"account_id": self.account_id, "include_deleted": False},
            )
            response.raise_for_status()
        records: list[ExternalEmployeeRecord] = []
        for user in response.json().get("users", []):
            external_ref = str(user.get("id") or user.get("user_id") or "").strip()
            if not external_ref:
                continue
            records.append(
                ExternalEmployeeRecord(
                    external_ref=external_ref,
                    full_name=f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Unknown Employee",
                    phone_e164=(user.get("phone_number") or "").strip() or None,
                    email=(user.get("email") or "").strip() or None,
                    role_names=[_role_name(user.get("role"), user.get("position_name"))],
                    metadata=user,
                )
            )
        return records

    async def sync_schedule(
        self,
        connection: SchedulerConnection,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ExternalShiftRecord]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/shifts",
                headers=self._headers(),
                params={
                    "account_id": self.account_id,
                    "start": window_start.date().isoformat(),
                    "end": window_end.date().isoformat(),
                },
            )
            response.raise_for_status()
        shifts: list[ExternalShiftRecord] = []
        timezone_value = connection.location.timezone if connection.location else "America/Los_Angeles"
        for payload in response.json().get("shifts", []):
            external_ref = str(payload.get("id") or payload.get("shift_id") or "").strip()
            starts_at = _iso_to_datetime(payload.get("start_time") or payload.get("start"))
            ends_at = _iso_to_datetime(payload.get("end_time") or payload.get("end"))
            if not external_ref or starts_at is None or ends_at is None:
                continue
            shifts.append(
                ExternalShiftRecord(
                    external_ref=external_ref,
                    role_name=_role_name(payload.get("position_name"), payload.get("role")),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    timezone=(payload.get("timezone") or timezone_value),
                    status=str(payload.get("status") or "scheduled").strip().lower(),
                    seats_requested=max(1, int(payload.get("slots") or 1)),
                    assigned_external_refs=_assigned_refs(payload.get("user_id"), payload.get("user_ids")),
                    notes=(payload.get("notes") or "").strip() or None,
                    metadata=payload,
                )
            )
        return shifts

    async def push_fill(
        self,
        connection: SchedulerConnection,
        *,
        external_shift_ref: str,
        external_employee_ref: str,
    ) -> None:
        if not self.write_supported:
            return None
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/shifts/{external_shift_ref}",
                headers=self._headers(),
                json={"user_id": external_employee_ref},
            )
            response.raise_for_status()


class HomebaseAdapter(SchedulerAdapter):
    base_url = "https://app.joinhomebase.com/api/public"

    def __init__(self, *, api_key: str):
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def sync_roster(self, connection: SchedulerConnection) -> list[ExternalEmployeeRecord]:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/v1/employees", headers=self._headers())
            response.raise_for_status()
        records: list[ExternalEmployeeRecord] = []
        for employee in response.json().get("employees", []):
            if not employee.get("active", True):
                continue
            external_ref = str(employee.get("id") or employee.get("employee_id") or "").strip()
            if not external_ref:
                continue
            records.append(
                ExternalEmployeeRecord(
                    external_ref=external_ref,
                    full_name=f"{employee.get('first_name', '')} {employee.get('last_name', '')}".strip() or "Unknown Employee",
                    phone_e164=(employee.get("phone_number") or "").strip() or None,
                    email=(employee.get("email") or "").strip() or None,
                    role_names=[_role_name(employee.get("job_title"))],
                    metadata=employee,
                )
            )
        return records

    async def sync_schedule(
        self,
        connection: SchedulerConnection,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ExternalShiftRecord]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/schedules",
                headers=self._headers(),
                params={
                    "start_date": window_start.date().isoformat(),
                    "end_date": window_end.date().isoformat(),
                },
            )
            response.raise_for_status()
        shifts: list[ExternalShiftRecord] = []
        timezone_value = connection.location.timezone if connection.location else "America/Los_Angeles"
        for payload in response.json().get("schedules", []):
            external_ref = str(payload.get("id") or payload.get("schedule_id") or "").strip()
            starts_at = _iso_to_datetime(payload.get("start_time") or payload.get("start"))
            ends_at = _iso_to_datetime(payload.get("end_time") or payload.get("end"))
            if not external_ref or starts_at is None or ends_at is None:
                continue
            shifts.append(
                ExternalShiftRecord(
                    external_ref=external_ref,
                    role_name=_role_name(payload.get("role"), payload.get("job_title")),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    timezone=(payload.get("timezone") or timezone_value),
                    status=str(payload.get("status") or "scheduled").strip().lower(),
                    seats_requested=max(1, int(payload.get("slots") or 1)),
                    assigned_external_refs=_assigned_refs(payload.get("employee_id"), payload.get("employee_ids")),
                    notes=(payload.get("notes") or "").strip() or None,
                    metadata=payload,
                )
            )
        return shifts


def _secret_hint(secret: str | None) -> str | None:
    if not secret:
        return None
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"


def webhook_secret_for_connection(connection: SchedulerConnection, provider: SchedulerProvider) -> str:
    if connection.webhook_secret:
        return connection.webhook_secret
    if provider == SchedulerProvider.seven_shifts:
        return v2_settings.sevenshifts_webhook_secret
    if provider == SchedulerProvider.deputy:
        return v2_settings.deputy_webhook_secret
    if provider == SchedulerProvider.when_i_work:
        return v2_settings.wheniwork_webhook_secret
    return ""


def adapter_for_connection(connection: SchedulerConnection) -> SchedulerAdapter:
    provider = SchedulerProvider(connection.provider)
    if provider == SchedulerProvider.backfill_native:
        return NativeAdapter()
    if provider == SchedulerProvider.seven_shifts:
        client_id = _credentials_value(connection, "client_id") or v2_settings.sevenshifts_client_id
        client_secret = _credentials_value(connection, "client_secret") or v2_settings.sevenshifts_client_secret
        company_id = (connection.provider_location_ref or "").strip()
        if not (client_id and client_secret and company_id):
            raise RuntimeError("7shifts connection requires client_id, client_secret, and provider_location_ref")
        return SevenShiftsAdapter(client_id=client_id, client_secret=client_secret, company_id=company_id)
    if provider == SchedulerProvider.deputy:
        client_id = _credentials_value(connection, "client_id") or v2_settings.deputy_client_id
        client_secret = _credentials_value(connection, "client_secret") or v2_settings.deputy_client_secret
        install_url = (connection.install_url or connection.provider_location_ref or "").strip()
        if not (client_id and client_secret and install_url):
            raise RuntimeError("Deputy connection requires client_id, client_secret, and install_url")
        return DeputyAdapter(client_id=client_id, client_secret=client_secret, install_url=install_url)
    if provider == SchedulerProvider.when_i_work:
        api_token = _credentials_value(connection, "api_token") or v2_settings.wheniwork_developer_key
        account_id = (connection.provider_location_ref or "").strip()
        if not (api_token and account_id):
            raise RuntimeError("When I Work connection requires api_token and provider_location_ref")
        write_supported = bool(connection.connection_metadata.get("write_supported"))
        return WhenIWorkAdapter(api_token=api_token, account_id=account_id, write_supported=write_supported)
    if provider == SchedulerProvider.homebase:
        api_key = _credentials_value(connection, "api_key") or v2_settings.homebase_api_key
        if not api_key:
            raise RuntimeError("Homebase connection requires api_key")
        return HomebaseAdapter(api_key=api_key)
    raise RuntimeError(f"Unsupported scheduler provider {provider.value!r}")


def build_connection_secret_hint(secret: str | None) -> str | None:
    return _secret_hint(secret)
