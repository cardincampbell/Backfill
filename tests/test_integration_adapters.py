from __future__ import annotations

import pytest

from app.integrations.deputy import DeputyAdapter
from app.integrations.homebase import HomebaseAdapter
from app.integrations.seven_shifts import SevenShiftsAdapter
from app.integrations.when_i_work import WhenIWorkAdapter


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    def __init__(self, responses, calls):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, **kwargs):
        self._calls.append(("GET", url, kwargs))
        return self._responses.pop(0)

    async def post(self, url, **kwargs):
        self._calls.append(("POST", url, kwargs))
        return self._responses.pop(0)


def _install_fake_client(monkeypatch, module, responses, calls):
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        lambda: _FakeAsyncClient(responses, calls),
    )


@pytest.mark.asyncio
async def test_seven_shifts_sync_and_writeback_normalize_payloads(monkeypatch):
    from app.integrations import seven_shifts

    calls = []
    responses = [
        _FakeResponse({"access_token": "token-123"}),
        _FakeResponse(
            {
                "data": [
                    {
                        "id": 77,
                        "firstname": "James",
                        "lastname": "Cook",
                        "mobile_phone": "+13105550103",
                        "email": "james@example.com",
                        "role": "line_cook",
                    }
                ]
            }
        ),
        _FakeResponse({"data": []}),
        _FakeResponse({"ok": True}),
    ]
    _install_fake_client(monkeypatch, seven_shifts, responses, calls)

    adapter = SevenShiftsAdapter(client_id="cid", client_secret="secret", company_id="company-123")

    workers = await adapter.sync_roster(location_id=9)
    assert workers == [
        {
            "name": "James Cook",
            "phone": "+13105550103",
            "email": "james@example.com",
            "source_id": "77",
            "roles": ["line_cook"],
            "location_id": 9,
            "source": "7shifts",
            "sms_consent_status": "pending",
            "voice_consent_status": "pending",
        }
    ]

    await adapter.sync_schedule(location_id=9, date_range=("2026-03-25", "2026-03-27"))
    await adapter.push_fill(
        {"scheduling_platform_id": "shift-1"},
        {"source_id": "worker-1"},
    )

    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/oauth2/token")
    assert calls[1][0] == "GET"
    assert calls[1][1].endswith("/v2/company/company-123/users")
    assert calls[2][1].endswith("/v2/company/company-123/shifts")
    assert calls[3][1].endswith("/v2/company/company-123/shifts/shift-1/assign")
    assert calls[3][2]["json"] == {"user_id": "worker-1"}


@pytest.mark.asyncio
async def test_deputy_sync_schedule_and_writeback_use_install_url(monkeypatch):
    from app.integrations import deputy

    calls = []
    responses = [
        _FakeResponse({"access_token": "deputy-token"}),
        _FakeResponse(
            [
                {
                    "Id": 88,
                    "Date": "2026-03-25T00:00:00",
                    "StartTime": "09:00:00",
                    "EndTime": "17:00:00",
                    "OperationalUnitName": "line_cook",
                    "Cost": 24.5,
                }
            ]
        ),
        _FakeResponse({"ok": True}),
    ]
    _install_fake_client(monkeypatch, deputy, responses, calls)

    adapter = DeputyAdapter(
        client_id="cid",
        client_secret="secret",
        install_url="https://demo.na.deputy.com",
    )

    shifts = await adapter.sync_schedule(location_id=4, date_range=("2026-03-25", "2026-03-27"))
    assert shifts == [
        {
            "location_id": 4,
            "scheduling_platform_id": "88",
            "role": "line_cook",
            "date": "2026-03-25",
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "pay_rate": 24.5,
            "status": "scheduled",
            "source_platform": "deputy",
        }
    ]

    await adapter.push_fill(
        {"scheduling_platform_id": "roster-1"},
        {"source_id": "employee-9"},
    )

    assert calls[0][1] == "https://demo.na.deputy.com/oauth/v1/access_token"
    assert calls[1][1] == "https://demo.na.deputy.com/api/v1/resource/Roster"
    assert calls[2][1] == "https://demo.na.deputy.com/api/v1/resource/Roster/roster-1"
    assert calls[2][2]["json"] == {"Employee": "employee-9", "Published": True}


@pytest.mark.asyncio
async def test_when_i_work_sync_and_conditional_writeback(monkeypatch):
    from app.integrations import when_i_work

    calls = []
    responses = [
        _FakeResponse(
            {
                "users": [
                    {
                        "id": 101,
                        "first_name": "Devon",
                        "last_name": "Lee",
                        "phone_number": "+13105550104",
                        "email": "devon@example.com",
                        "role": "server",
                    }
                ]
            }
        ),
        _FakeResponse({"ok": True}),
    ]
    _install_fake_client(monkeypatch, when_i_work, responses, calls)

    adapter = WhenIWorkAdapter(api_token="wiw-token", account_id="acct-1", write_supported=True)
    workers = await adapter.sync_roster(location_id=5)
    assert workers[0]["name"] == "Devon Lee"
    assert workers[0]["source_id"] == "101"

    await adapter.push_fill(
        {"scheduling_platform_id": "shift-55"},
        {"source_id": "user-7"},
    )
    assert calls[0][1].endswith("/2/users")
    assert calls[1][1].endswith("/2/shifts/shift-55")
    assert calls[1][2]["json"] == {"user_id": "user-7"}


@pytest.mark.asyncio
async def test_when_i_work_skips_writeback_when_not_supported(monkeypatch):
    from app.integrations import when_i_work

    calls = []
    _install_fake_client(monkeypatch, when_i_work, [], calls)

    adapter = WhenIWorkAdapter(api_token="wiw-token", account_id="acct-1", write_supported=False)
    await adapter.push_fill(
        {"scheduling_platform_id": "shift-55"},
        {"source_id": "user-7"},
    )

    assert calls == []


@pytest.mark.asyncio
async def test_homebase_sync_roster_and_schedule_normalize_payloads(monkeypatch):
    from app.integrations import homebase

    calls = []
    responses = [
        _FakeResponse(
            {
                "employees": [
                    {
                        "id": 201,
                        "first_name": "Ava",
                        "last_name": "Stone",
                        "phone_number": "+13105550105",
                        "email": "ava@example.com",
                        "job_title": "barista",
                        "active": True,
                    }
                ]
            }
        ),
        _FakeResponse(
            {
                "schedules": [
                    {
                        "id": 301,
                        "role": "barista",
                        "date": "2026-03-25",
                        "start_time": "07:00:00",
                        "end_time": "15:00:00",
                        "hourly_rate": 21,
                    }
                ]
            }
        ),
    ]
    _install_fake_client(monkeypatch, homebase, responses, calls)

    adapter = HomebaseAdapter(api_key="hb-key")
    workers = await adapter.sync_roster(location_id=12)
    shifts = await adapter.sync_schedule(location_id=12, date_range=("2026-03-25", "2026-03-26"))

    assert workers[0]["name"] == "Ava Stone"
    assert workers[0]["source"] == "homebase"
    assert shifts[0]["scheduling_platform_id"] == "301"
    assert shifts[0]["source_platform"] == "homebase"
    assert calls[0][1].endswith("/api/public/v1/employees")
    assert calls[1][1].endswith("/api/public/v1/schedules")
