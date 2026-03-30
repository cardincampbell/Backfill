from datetime import date, datetime, timedelta
import re
from urllib.parse import parse_qs, urlparse

import httpx
from twilio.request_validator import RequestValidator

from app.config import settings


def _make_shift_payload(location_id: int, start_delta_hours: int = 12):
    start = datetime.utcnow() + timedelta(hours=start_delta_hours)
    end = start + timedelta(hours=8)
    return {
        "location_id": location_id,
        "role": "line_cook",
        "date": start.date().isoformat(),
        "start_time": start.strftime("%H:%M:%S"),
        "end_time": end.strftime("%H:%M:%S"),
        "pay_rate": 22.0,
        "requirements": ["food_handler_card"],
    }


def _create_backfill_shifts_import_job(client, location_id: int, csv_text: str):
    created = client.post(
        f"/api/locations/{location_id}/import-jobs",
        json={"import_type": "combined", "filename": "week.csv"},
    )
    assert created.status_code == 201
    job = created.json()

    uploaded = client.post(
        f"/api/import-jobs/{job['id']}/upload",
        files={"file": ("week.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert uploaded.status_code == 200
    return job, uploaded.json()


def _exchange_dashboard_session(public_client, phone: str, sent_messages):
    requested = public_client.post(
        "/api/auth/request-access",
        json={"phone": phone},
    )
    assert requested.status_code == 200
    assert sent_messages
    token_match = re.search(r"token=([^\s]+)", sent_messages[-1][1])
    assert token_match is not None
    access_token = token_match.group(1)
    exchanged = public_client.post("/api/auth/exchange", json={"token": access_token})
    assert exchanged.status_code == 200
    session_token = exchanged.json()["session_token"]
    return {"Authorization": f"Bearer {session_token}"}


def _signed_sms_headers(token: str, params):
    validator = RequestValidator(token)
    signature = validator.compute_signature("http://testserver/webhooks/twilio/sms", params)
    return {"X-Twilio-Signature": signature}


def _create_schedule_with_open_shift(client, location_id: int, *, role: str = "dishwasher"):
    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Maria Lopez,+13105550901,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location_id, csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]

    created_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": role,
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    assert created_shift.status_code == 200
    return schedule_id, created_shift.json()["shift"]["id"]


def _create_schedule_week(client, location_id: int):
    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Maria Lopez,+13105550921,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location_id, csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    return committed.json()["schedule_id"]


def test_internal_backfill_routes_require_internal_key(client, public_client):
    internal_response = client.get("/api/internal/backfill-shifts/webhook-health")
    assert internal_response.status_code == 200

    public_response = public_client.get("/api/internal/backfill-shifts/webhook-health")
    assert public_response.status_code == 401
    assert public_response.json()["detail"] == "Authentication required"


def test_dashboard_access_sms_exchange_and_location_scope(client, public_client, monkeypatch):
    sent_messages = []
    monkeypatch.setattr(settings, "backfill_dashboard_auth_required", True)
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: sent_messages.append((to, body)) or "SM-AUTH",
    )

    allowed = client.post(
        "/api/locations",
        json={
            "name": "Scoped Access Location",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550410",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    blocked = client.post(
        "/api/locations",
        json={
            "name": "Blocked Access Location",
            "manager_name": "Other Lead",
            "manager_phone": "+13105550411",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    unauthenticated = public_client.get(f"/api/locations/{allowed['id']}/settings")
    assert unauthenticated.status_code == 401

    requested = public_client.post(
        "/api/auth/request-access",
        json={"phone": "+1 (310) 555-0410"},
    )
    assert requested.status_code == 200
    request_payload = requested.json()
    assert request_payload["destination"].endswith("0410")
    assert request_payload["location_ids"] == [allowed["id"]]
    assert sent_messages and sent_messages[0][0] == "+13105550410"

    token_match = re.search(r"token=([^\s]+)", sent_messages[0][1])
    assert token_match is not None
    access_token = token_match.group(1)

    exchanged = public_client.post(
        "/api/auth/exchange",
        json={"token": access_token},
    )
    assert exchanged.status_code == 200
    exchange_payload = exchanged.json()
    session_token = exchange_payload["session_token"]
    assert session_token.startswith("bfsess_")
    assert exchange_payload["location_ids"] == [allowed["id"]]

    session_headers = {"Authorization": f"Bearer {session_token}"}
    me = public_client.get("/api/auth/me", headers=session_headers)
    assert me.status_code == 200
    me_payload = me.json()
    assert me_payload["subject_phone"] == "+13105550410"
    assert [item["id"] for item in me_payload["locations"]] == [allowed["id"]]

    allowed_settings = public_client.get(
        f"/api/locations/{allowed['id']}/settings",
        headers=session_headers,
    )
    assert allowed_settings.status_code == 200

    blocked_settings = public_client.get(
        f"/api/locations/{blocked['id']}/settings",
        headers=session_headers,
    )
    assert blocked_settings.status_code == 403
    assert blocked_settings.json()["detail"] == "Forbidden for this location"

    logout = public_client.post("/api/auth/logout", headers=session_headers)
    assert logout.status_code == 200

    expired_me = public_client.get("/api/auth/me", headers=session_headers)
    assert expired_me.status_code == 401


def test_dashboard_access_request_is_rate_limited(client, public_client, monkeypatch):
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: "SM-AUTH",
    )

    client.post(
        "/api/locations",
        json={
            "name": "Rate Limited Access",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550420",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )

    for _ in range(5):
        response = public_client.post(
            "/api/auth/request-access",
            json={"phone": "+13105550420"},
        )
        assert response.status_code == 200

    limited = public_client.post(
        "/api/auth/request-access",
        json={"phone": "+13105550420"},
    )
    assert limited.status_code == 429
    assert limited.json()["detail"] == "Rate limit exceeded"


def test_ai_web_action_can_return_schedule_exceptions_and_history(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Action Bistro",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550430",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Maria Lopez,+13105550431,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]

    created_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    assert created_shift.status_code == 200

    headers = _exchange_dashboard_session(public_client, "+13105550430", auth_messages)

    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Which shifts are unfilled this week?",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-14",
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "completed"
    assert payload["mode"] == "result"
    assert payload["ui_payload"]["kind"] == "schedule_exceptions"
    assert payload["ui_payload"]["data"]["summary"]["total_items"] >= 1
    action_request_id = payload["action_request_id"]

    fetched = public_client.get(f"/api/ai-actions/{action_request_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["action_request_id"] == action_request_id
    assert fetched.json()["summary"] == payload["summary"]

    history = public_client.get(
        f"/api/locations/{location['id']}/ai-action-history",
        headers=headers,
    )
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["location_id"] == location["id"]
    assert history_payload["items"][0]["action_request_id"] == action_request_id
    assert "unfilled" in history_payload["items"][0]["text"].lower()


def test_ai_web_action_records_runtime_fallback_metadata(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    class _FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            raise httpx.ConnectError("upstream model unavailable")

    monkeypatch.setattr(settings, "backfill_ai_provider", "openai")
    monkeypatch.setattr(settings, "backfill_ai_model", "gpt-4.1-mini")
    monkeypatch.setattr(settings, "openai_api_key", "test-openai-key")
    monkeypatch.setattr(settings, "backfill_ai_fallback_enabled", True)
    monkeypatch.setattr("app.services.ai_runtime.httpx.AsyncClient", _FailingClient)

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Runtime Fallback Cafe",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550435",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    headers = _exchange_dashboard_session(public_client, "+13105550435", auth_messages)

    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Which shifts are unfilled this week?",
            "context": {
                "week_start_date": "2026-04-14",
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "completed"
    assert payload["runtime"]["requested_provider"] == "openai"
    assert payload["runtime"]["provider"] == "rules"
    assert payload["runtime"]["fallback_used"] is True
    assert payload["runtime"]["fallback_provider"] == "rules"
    assert payload["runtime"]["fallback_reason"] == "ConnectError"

    action_request_id = payload["action_request_id"]
    fetched = public_client.get(f"/api/ai-actions/{action_request_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["runtime"]["fallback_used"] is True

    history = public_client.get(
        f"/api/locations/{location['id']}/ai-action-history",
        headers=headers,
    )
    assert history.status_code == 200
    assert history.json()["items"][0]["runtime"]["fallback_used"] is True

    filtered_history = public_client.get(
        f"/api/locations/{location['id']}/ai-action-history?fallback_only=true",
        headers=headers,
    )
    assert filtered_history.status_code == 200
    assert len(filtered_history.json()["items"]) == 1

    debug = public_client.get(
        f"/api/ai-actions/{action_request_id}/debug",
        headers=headers,
    )
    assert debug.status_code == 200
    debug_payload = debug.json()
    parsed_event = next(event for event in debug_payload["events"] if event["event_type"] == "parsed")
    assert parsed_event["payload_json"]["runtime"]["fallback_used"] is True
    assert debug_payload["request"]["result_summary_json"]["runtime"]["fallback_reason"] == "ConnectError"

    stats = public_client.get(
        f"/api/locations/{location['id']}/ai-runtime-stats?days=7",
        headers=headers,
    )
    assert stats.status_code == 200
    stats_payload = stats.json()
    assert stats_payload["summary"]["total_actions"] == 1
    assert stats_payload["summary"]["fallback_count"] == 1
    assert stats_payload["provider_counts"]["rules"] == 1
    assert stats_payload["action_counts"]["get_unfilled_shifts"] == 1
    assert stats_payload["recent_fallbacks"][0]["runtime"]["fallback_used"] is True

    monkeypatch.setattr(settings, "backfill_ai_openai_channels", ["web"])
    capabilities = public_client.get(
        f"/api/locations/{location['id']}/ai-capabilities",
        headers=headers,
    )
    assert capabilities.status_code == 200
    capabilities_payload = capabilities.json()
    assert capabilities_payload["provider_policy"]["default_provider"] == "openai"
    assert capabilities_payload["provider_policy"]["intent_provider_by_channel"]["web"] == "openai"
    assert capabilities_payload["provider_policy"]["intent_provider_by_channel"]["sms"] == "rules"
    publish_capability = next(
        item for item in capabilities_payload["actions"] if item["action_type"] == "publish_schedule"
    )
    assert publish_capability["requires_confirmation"] is True
    assert "web" in publish_capability["channels"]

    feedback = public_client.post(
        f"/api/ai-actions/{action_request_id}/feedback",
        headers=headers,
        json={"helpful": True, "correct": True, "notes": "Fallback still returned the right result."},
    )
    assert feedback.status_code == 200
    feedback_payload = feedback.json()
    assert feedback_payload["feedback_recorded"] is True
    assert feedback_payload["feedback"]["helpful"] is True

    stats_after_feedback = public_client.get(
        f"/api/locations/{location['id']}/ai-runtime-stats?days=7",
        headers=headers,
    )
    assert stats_after_feedback.status_code == 200
    assert stats_after_feedback.json()["summary"]["total_feedback"] == 1
    assert stats_after_feedback.json()["summary"]["helpful_count"] == 1
    assert stats_after_feedback.json()["summary"]["correct_count"] == 1

    recent_internal = client.get("/api/internal/ai-actions/recent")
    assert recent_internal.status_code == 200
    recent_items = recent_internal.json()["items"]
    assert recent_items[0]["action_request_id"] == action_request_id
    assert recent_items[0]["location_id"] == location["id"]
    assert recent_items[0]["runtime"]["fallback_used"] is True


def test_ai_capabilities_and_policy_can_disable_specific_actions(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )
    monkeypatch.setattr(settings, "backfill_ai_disabled_actions_web", ["delete_shift"])

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Disabled Action Cafe",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550436",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    schedule_id, shift_id = _create_schedule_with_open_shift(client, location["id"])
    headers = _exchange_dashboard_session(public_client, "+13105550436", auth_messages)

    capabilities = public_client.get(
        f"/api/locations/{location['id']}/ai-capabilities",
        headers=headers,
    )
    assert capabilities.status_code == 200
    delete_capability = next(
        item for item in capabilities.json()["actions"] if item["action_type"] == "delete_shift"
    )
    assert delete_capability["enabled_by_channel"]["web"] is False
    assert "web" in delete_capability["disabled_channels"]

    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Delete the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "redirected"
    assert payload["redirect"]["reason"] == "action_disabled"


def test_ai_action_expiry_retry_and_session_inspection(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Retry Cafe",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550437",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    schedule_id, shift_id = _create_schedule_with_open_shift(client, location["id"])
    headers = _exchange_dashboard_session(public_client, "+13105550437", auth_messages)

    active = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Delete the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert active.status_code == 200
    active_payload = active.json()
    assert active_payload["status"] == "awaiting_confirmation"

    sessions = public_client.get(
        f"/api/locations/{location['id']}/ai-active-sessions",
        headers=headers,
    )
    assert sessions.status_code == 200
    assert sessions.json()["items"][0]["action_request_id"] == active_payload["action_request_id"]
    assert sessions.json()["items"][0]["action_type"] == "delete_shift"

    internal_sessions = client.get(f"/api/internal/ai-actions/sessions?location_id={location['id']}")
    assert internal_sessions.status_code == 200
    assert internal_sessions.json()["items"][0]["action_request_id"] == active_payload["action_request_id"]

    monkeypatch.setattr(settings, "backfill_ai_action_session_ttl_minutes", -1)
    expired = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Delete the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert expired.status_code == 200
    expired_action_id = expired.json()["action_request_id"]

    expire_run = client.post(f"/api/internal/ai-actions/expire-stale?location_id={location['id']}")
    assert expire_run.status_code == 200
    assert expire_run.json()["expired_count"] >= 1

    expired_detail = public_client.get(
        f"/api/ai-actions/{expired_action_id}",
        headers=headers,
    )
    assert expired_detail.status_code == 200
    assert expired_detail.json()["status"] == "expired"

    expired_debug = public_client.get(
        f"/api/ai-actions/{expired_action_id}/debug",
        headers=headers,
    )
    assert expired_debug.status_code == 200
    assert expired_debug.json()["state_summary"]["retryable"] is True

    monkeypatch.setattr(settings, "backfill_ai_action_session_ttl_minutes", 30)
    retried = public_client.post(
        f"/api/ai-actions/{expired_action_id}/retry",
        headers=headers,
    )
    assert retried.status_code == 200
    retried_payload = retried.json()
    assert retried_payload["status"] == "awaiting_confirmation"
    assert retried_payload["action_request_id"] != expired_action_id

    confirmed = public_client.post(
        f"/api/ai-actions/{retried_payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "completed"


def test_internal_ai_action_recovery_routes(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Internal Recovery Cafe",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550438",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    schedule_id, shift_id = _create_schedule_with_open_shift(client, location["id"])
    headers = _exchange_dashboard_session(public_client, "+13105550438", auth_messages)

    first_action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Delete the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert first_action.status_code == 200
    first_action_id = first_action.json()["action_request_id"]

    debug = public_client.get(f"/api/ai-actions/{first_action_id}/debug", headers=headers)
    assert debug.status_code == 200
    recovery_actions = debug.json()["recovery_actions"]
    assert recovery_actions["internal_retry_route"] == f"/api/internal/ai-actions/{first_action_id}/retry"
    assert recovery_actions["internal_cancel_route"] == f"/api/internal/ai-actions/{first_action_id}/cancel"
    assert recovery_actions["internal_expire_route"] == f"/api/internal/ai-actions/{first_action_id}/expire"

    cancelled = client.post(f"/api/internal/ai-actions/{first_action_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    cancelled_detail = public_client.get(f"/api/ai-actions/{first_action_id}", headers=headers)
    assert cancelled_detail.status_code == 200
    assert cancelled_detail.json()["status"] == "cancelled"

    second_action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Delete the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert second_action.status_code == 200
    second_action_id = second_action.json()["action_request_id"]

    expired = client.post(f"/api/internal/ai-actions/{second_action_id}/expire")
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"

    retried = client.post(f"/api/internal/ai-actions/{second_action_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "awaiting_confirmation"
    assert retried.json()["action_request_id"] != second_action_id


def test_ai_action_attention_routes_show_pending_and_expired_items(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Attention Cafe",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550439",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    schedule_id, shift_id = _create_schedule_with_open_shift(client, location["id"])
    headers = _exchange_dashboard_session(public_client, "+13105550439", auth_messages)

    pending = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Delete the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert pending.status_code == 200
    pending_action_id = pending.json()["action_request_id"]

    monkeypatch.setattr(settings, "backfill_ai_action_session_ttl_minutes", -1)
    expired = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Delete the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert expired.status_code == 200
    expired_action_id = expired.json()["action_request_id"]
    expire_run = client.post(f"/api/internal/ai-actions/expire-stale?location_id={location['id']}")
    assert expire_run.status_code == 200
    monkeypatch.setattr(settings, "backfill_ai_action_session_ttl_minutes", 30)

    attention = public_client.get(
        f"/api/locations/{location['id']}/ai-action-attention",
        headers=headers,
    )
    assert attention.status_code == 200
    payload = attention.json()
    assert payload["summary"]["total"] >= 2
    items_by_id = {item["action_request_id"]: item for item in payload["items"]}
    assert items_by_id[pending_action_id]["attention_reason"] == "pending_confirmation"
    assert any(action["type"] == "open" for action in items_by_id[pending_action_id]["recovery_actions"])
    assert items_by_id[expired_action_id]["attention_reason"] == "expired"
    assert any(action["type"] == "retry" for action in items_by_id[expired_action_id]["recovery_actions"])

    internal_attention = client.get(f"/api/internal/ai-actions/attention?location_id={location['id']}")
    assert internal_attention.status_code == 200
    internal_payload = internal_attention.json()
    assert internal_payload["summary"]["total"] >= 2
    internal_items = {item["action_request_id"]: item for item in internal_payload["items"]}
    assert internal_items[pending_action_id]["location_name"] == location["name"]
    assert internal_items[expired_action_id]["attention_reason"] == "expired"


def test_ai_web_publish_action_requires_confirmation_and_can_be_confirmed(client, public_client, monkeypatch):
    auth_messages = []
    outbound_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: outbound_messages.append((to, body)) or "SM-NOTIFY",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Publish Cafe",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550440",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Sam Cook,+13105550441,prep_cook,2026-04-14,08:00,16:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]

    headers = _exchange_dashboard_session(public_client, "+13105550440", auth_messages)

    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Publish next week",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-14",
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"
    assert payload["mode"] == "confirmation"
    assert payload["requires_confirmation"] is True
    assert payload["ui_payload"]["kind"] == "publish_preview"

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "Published the schedule." in confirmed_payload["summary"]

    review = client.get(f"/api/schedules/{schedule_id}/review")
    assert review.status_code == 200
    assert review.json()["schedule"]["lifecycle_state"] == "published"

    stored = public_client.get(f"/api/ai-actions/{payload['action_request_id']}", headers=headers)
    assert stored.status_code == 200
    assert stored.json()["status"] == "completed"


def test_ai_web_action_can_approve_pending_fill_after_confirmation(client, public_client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Fill Approval Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550450",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "coverage_requires_manager_approval": True,
        },
    ).json()

    schedule_id, open_shift_id = _create_schedule_with_open_shift(client, location["id"])
    created_worker = client.post(
        "/api/workers",
        json={
            "name": "James",
            "phone": "+13105550451",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert created_worker.status_code == 201

    started = client.post(f"/api/shifts/{open_shift_id}/coverage/start")
    assert started.status_code == 200

    worker_yes = {"From": "+13105550451", "Body": "YES"}
    worker_response = client.post(
        "/webhooks/twilio/sms",
        data=worker_yes,
        headers=_signed_sms_headers("test-token", worker_yes),
    )
    assert worker_response.status_code == 200
    assert "manager for approval" in worker_response.text.lower()

    headers = _exchange_dashboard_session(public_client, "+13105550450", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Approve James for the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "shift_id": open_shift_id,
                "week_start_date": "2026-04-13",
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"
    assert payload["mode"] == "confirmation"
    assert "approve james" in payload["summary"].lower()

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "approved james" in confirmed_payload["summary"].lower()

    current = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current.status_code == 200
    target_shift = next(shift for shift in current.json()["shifts"] if shift["id"] == open_shift_id)
    assert target_shift["assignment"]["worker_name"] == "James"
    assert target_shift["assignment"]["assignment_status"] == "confirmed"


def test_ai_web_action_can_decline_pending_fill_after_confirmation(client, public_client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Fill Decline Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550460",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "coverage_requires_manager_approval": True,
        },
    ).json()

    schedule_id, open_shift_id = _create_schedule_with_open_shift(client, location["id"])
    created_worker = client.post(
        "/api/workers",
        json={
            "name": "Drew",
            "phone": "+13105550461",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert created_worker.status_code == 201

    started = client.post(f"/api/shifts/{open_shift_id}/coverage/start")
    assert started.status_code == 200

    worker_yes = {"From": "+13105550461", "Body": "YES"}
    worker_response = client.post(
        "/webhooks/twilio/sms",
        data=worker_yes,
        headers=_signed_sms_headers("test-token", worker_yes),
    )
    assert worker_response.status_code == 200
    assert "manager for approval" in worker_response.text.lower()

    headers = _exchange_dashboard_session(public_client, "+13105550460", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Decline Drew and keep looking",
            "context": {
                "schedule_id": schedule_id,
                "shift_id": open_shift_id,
                "week_start_date": "2026-04-13",
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"
    assert "decline drew" in payload["summary"].lower()

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "keep looking" in confirmed_payload["summary"].lower()

    coverage = client.get(f"/api/locations/{location['id']}/coverage?week_start=2026-04-13")
    assert coverage.status_code == 200
    target_shift = next(item for item in coverage.json()["at_risk_shifts"] if item["shift_id"] == open_shift_id)
    assert target_shift["coverage_status"] != "awaiting_manager_approval"
    assert target_shift["claimed_by_worker_id"] is None


def test_ai_web_action_can_start_open_shift_coverage_after_confirmation(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Open Shift Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550470",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    schedule_id, open_shift_id = _create_schedule_with_open_shift(client, location["id"])
    created_worker = client.post(
        "/api/workers",
        json={
            "name": "Taylor",
            "phone": "+13105550471",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert created_worker.status_code == 201

    headers = _exchange_dashboard_session(public_client, "+13105550470", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Start coverage for the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"
    assert payload["mode"] == "confirmation"

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "started coverage" in confirmed_payload["summary"].lower()

    coverage = client.get(f"/api/locations/{location['id']}/coverage?week_start=2026-04-13")
    assert coverage.status_code == 200
    target_shift = next(item for item in coverage.json()["at_risk_shifts"] if item["shift_id"] == open_shift_id)
    assert target_shift["cascade_id"] is not None
    assert target_shift["coverage_status"] != "unassigned"


def test_ai_web_action_can_clarify_which_open_shift_to_start(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Clarification Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550480",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    schedule_id, first_shift_id = _create_schedule_with_open_shift(client, location["id"])
    second_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-16",
            "start_time": "15:00:00",
            "end_time": "23:00:00",
        },
    )
    assert second_shift.status_code == 200
    second_shift_id = second_shift.json()["shift"]["id"]
    created_worker = client.post(
        "/api/workers",
        json={
            "name": "Jordan",
            "phone": "+13105550481",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert created_worker.status_code == 201

    headers = _exchange_dashboard_session(public_client, "+13105550480", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Start coverage for the open shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_clarification"
    assert payload["mode"] == "clarification"
    assert len(payload["clarification"]["candidates"]) == 2

    clarified = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/clarify",
        headers=headers,
        json={"selection": {"shift_id": second_shift_id}},
    )
    assert clarified.status_code == 200
    clarified_payload = clarified.json()
    assert clarified_payload["status"] == "awaiting_confirmation"
    assert "15:00" in clarified_payload["summary"]

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "completed"

    coverage = client.get(f"/api/locations/{location['id']}/coverage?week_start=2026-04-13")
    assert coverage.status_code == 200
    coverage_items = {item["shift_id"]: item for item in coverage.json()["at_risk_shifts"]}
    assert coverage_items[second_shift_id]["cascade_id"] is not None
    assert coverage_items[second_shift_id]["coverage_status"] != "unassigned"
    assert coverage_items[first_shift_id]["cascade_id"] is None


def test_ai_web_action_can_cancel_open_shift_offer_after_confirmation(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Cancel Offer Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550482",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    client.post(
        "/api/workers",
        json={
            "name": "Jordan",
            "phone": "+13105550483",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )

    schedule_id, shift_id = _create_schedule_with_open_shift(client, location["id"])
    started = client.post(f"/api/shifts/{shift_id}/coverage/start")
    assert started.status_code == 200

    headers = _exchange_dashboard_session(public_client, "+13105550482", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Cancel the open shift offer",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"
    assert "cancel the active offer" in payload["summary"].lower()

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "cancelled the active offer" in confirmed_payload["summary"].lower()

    current = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current.status_code == 200
    target_shift = next(shift for shift in current.json()["shifts"] if shift["id"] == shift_id)
    assert target_shift["coverage"]["status"] == "none"
    assert target_shift["available_actions"] == ["start_coverage", "close_shift"]


def test_ai_web_action_can_close_open_shift_after_confirmation(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Close Shift Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550484",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    schedule_id, shift_id = _create_schedule_with_open_shift(client, location["id"])
    headers = _exchange_dashboard_session(public_client, "+13105550484", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Close the open shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"
    assert "close the open dishwasher shift" in payload["summary"].lower()

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "closed the open dishwasher shift" in confirmed_payload["summary"].lower()

    current = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current.status_code == 200
    target_shift = next(shift for shift in current.json()["shifts"] if shift["id"] == shift_id)
    assert target_shift["assignment"]["assignment_status"] == "closed"
    assert target_shift["coverage"]["status"] == "closed"
    assert target_shift["available_actions"] == ["reopen_shift", "reopen_and_offer"]


def test_ai_web_action_can_create_open_shift_after_confirmation(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Create Shift Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550485",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    schedule_id = _create_schedule_week(client, location["id"])

    headers = _exchange_dashboard_session(public_client, "+13105550485", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Create an open dishwasher shift on 2026-04-15 from 11 to 7",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"
    assert "create an open dishwasher shift" in payload["summary"].lower()

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "created the open dishwasher shift" in confirmed_payload["summary"].lower()

    current = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current.status_code == 200
    target_shift = next(
        shift
        for shift in current.json()["shifts"]
        if shift["role"] == "dishwasher" and shift["date"] == "2026-04-15" and shift["start_time"] == "11:00:00"
    )
    assert target_shift["assignment"]["worker_id"] is None
    assert target_shift["assignment"]["assignment_status"] == "open"
    assert target_shift["available_actions"] == ["start_coverage", "close_shift"]


def test_ai_web_action_can_create_and_offer_open_shift_when_context_requests_it(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Create Offer Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550486",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    client.post(
        "/api/workers",
        json={
            "name": "Taylor",
            "phone": "+13105550487",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    schedule_id = _create_schedule_week(client, location["id"])
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    headers = _exchange_dashboard_session(public_client, "+13105550486", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Create an open dishwasher shift on 2026-04-16 from 15 to 23",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "start_open_shift_offer": True,
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "started offering it" in confirmed_payload["summary"].lower()

    coverage = client.get(f"/api/locations/{location['id']}/coverage?week_start=2026-04-13")
    assert coverage.status_code == 200
    target_shift = next(
        item
        for item in coverage.json()["at_risk_shifts"]
        if item["role"] == "dishwasher" and item["date"] == "2026-04-16" and item["start_time"] == "15:00:00"
    )
    assert target_shift["cascade_id"] is not None
    assert target_shift["coverage_status"] != "unassigned"


def test_ai_web_action_can_reopen_and_offer_closed_open_shift(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Reopen Shift Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550488",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    client.post(
        "/api/workers",
        json={
            "name": "Taylor",
            "phone": "+13105550489",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    schedule_id, shift_id = _create_schedule_with_open_shift(client, location["id"])
    closed = client.post(f"/api/shifts/{shift_id}/open-shift/close")
    assert closed.status_code == 200

    headers = _exchange_dashboard_session(public_client, "+13105550488", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Reopen and offer the shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"
    assert "reopen the closed dishwasher shift" in payload["summary"].lower()

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "started offering it" in confirmed_payload["summary"].lower()

    current = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current.status_code == 200
    target_shift = next(shift for shift in current.json()["shifts"] if shift["id"] == shift_id)
    assert target_shift["assignment"]["assignment_status"] == "open"
    assert target_shift["coverage"]["status"] == "active"
    assert target_shift["available_actions"] == ["cancel_offer", "close_shift"]


def test_ai_web_action_can_assign_shift_after_confirmation(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Assign Shift Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550490",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    client.post(
        "/api/workers",
        json={
            "name": "Taylor",
            "phone": "+13105550491",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    schedule_id, shift_id = _create_schedule_with_open_shift(client, location["id"])

    headers = _exchange_dashboard_session(public_client, "+13105550490", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Assign Taylor to the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"
    assert "assign taylor" in payload["summary"].lower()

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "assigned taylor" in confirmed_payload["summary"].lower()

    current = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current.status_code == 200
    target_shift = next(shift for shift in current.json()["shifts"] if shift["id"] == shift_id)
    assert target_shift["assignment"]["worker_name"] == "Taylor"
    assert target_shift["assignment"]["assignment_status"] == "assigned"


def test_ai_web_action_can_clarify_which_worker_to_assign(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Assign Clarify Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550492",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    first_worker = client.post(
        "/api/workers",
        json={
            "name": "Taylor",
            "phone": "+13105550493",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    client.post(
        "/api/workers",
        json={
            "name": "Jordan",
            "phone": "+13105550494",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    schedule_id, shift_id = _create_schedule_with_open_shift(client, location["id"])

    headers = _exchange_dashboard_session(public_client, "+13105550492", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Assign the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_clarification"
    assert len(payload["clarification"]["candidates"]) == 2

    clarified = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/clarify",
        headers=headers,
        json={"selection": {"worker_id": first_worker["id"]}},
    )
    assert clarified.status_code == 200
    clarified_payload = clarified.json()
    assert clarified_payload["status"] == "awaiting_confirmation"
    assert "taylor" in clarified_payload["summary"].lower()

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "completed"

    current = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    target_shift = next(shift for shift in current.json()["shifts"] if shift["id"] == shift_id)
    assert target_shift["assignment"]["worker_name"] == "Taylor"
    assert target_shift["assignment"]["assignment_status"] == "assigned"


def test_ai_web_action_can_edit_shift_after_confirmation(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Edit Shift Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550495",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    schedule_id = _create_schedule_week(client, location["id"])
    created = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "worker_id": None,
            "assignment_status": "open",
        },
    )
    assert created.status_code == 200
    shift_id = created.json()["shift"]["id"]

    headers = _exchange_dashboard_session(public_client, "+13105550495", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Move the dishwasher shift to 12 to 8",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"
    assert "update the dishwasher shift" in payload["summary"].lower()

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "updated the dishwasher shift" in confirmed_payload["summary"].lower()

    current = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current.status_code == 200
    target_shift = next(shift for shift in current.json()["shifts"] if shift["id"] == shift_id)
    assert target_shift["start_time"] == "12:00:00"
    assert target_shift["end_time"] == "20:00:00"


def test_ai_web_action_can_delete_shift_after_confirmation(client, public_client, monkeypatch):
    auth_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None, dynamic_variables=None: auth_messages.append((to, body)) or "SM-AUTH",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "AI Delete Shift Cafe",
            "manager_name": "Nina Ops",
            "manager_phone": "+13105550496",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    schedule_id = _create_schedule_week(client, location["id"])
    created = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "worker_id": None,
            "assignment_status": "open",
        },
    )
    assert created.status_code == 200
    shift_id = created.json()["shift"]["id"]

    headers = _exchange_dashboard_session(public_client, "+13105550496", auth_messages)
    action = public_client.post(
        "/api/ai-actions/web",
        headers=headers,
        json={
            "location_id": location["id"],
            "text": "Delete the dishwasher shift",
            "context": {
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert action.status_code == 200
    payload = action.json()
    assert payload["status"] == "awaiting_confirmation"
    assert "delete the dishwasher shift" in payload["summary"].lower()

    confirmed = public_client.post(
        f"/api/ai-actions/{payload['action_request_id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "deleted the dishwasher shift" in confirmed_payload["summary"].lower()

    current = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current.status_code == 200
    assert all(shift["id"] != shift_id for shift in current.json()["shifts"])


def test_native_lite_read_update_export_and_dashboard(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
    ).json()
    location_id = location["id"]

    worker = client.post(
        "/api/workers",
        json={
            "name": "James",
            "phone": "+13105550102",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    shift = client.post("/api/shifts", json=_make_shift_payload(location_id)).json()

    updated_worker = client.patch(
        f"/api/workers/{worker['id']}",
        json={"preferred_channel": "both", "rating": 4.8},
    )
    assert updated_worker.status_code == 200
    assert updated_worker.json()["preferred_channel"] == "both"

    workers = client.get(f"/api/workers?location_id={location_id}")
    shifts = client.get(f"/api/shifts?location_id={location_id}")
    dashboard = client.get(f"/api/dashboard?location_id={location_id}")
    workers_csv = client.get(f"/api/exports/workers?location_id={location_id}")
    shifts_csv = client.get(f"/api/exports/shifts?location_id={location_id}")

    assert workers.status_code == 200
    assert len(workers.json()) == 1
    assert shifts.status_code == 200
    assert len(shifts.json()) == 1
    assert dashboard.status_code == 200
    assert dashboard.json()["workers"] == 1
    assert "broadcast_cascades_active" in dashboard.json()
    assert "workers_on_standby" in dashboard.json()
    assert "James" in workers_csv.json()["csv"]
    assert "line_cook" in shifts_csv.json()["csv"]
    assert client.get(f"/api/shifts/{shift['id']}/status").status_code == 200


def test_import_workers_csv_rejects_files_over_10mb(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "CSV Limit Shop",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
    ).json()

    oversized_csv = b"name,phone\n" + (b"a" * (10 * 1024 * 1024 + 1))
    response = client.post(
        f"/api/workers/import-csv?location_id={location['id']}",
        files={"file": ("workers.csv", oversized_csv, "text/csv")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "CSV file exceeds 10 MB limit"


def test_backfill_shifts_roster_actions_and_eligibility(client, monkeypatch):
    invite_messages = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: invite_messages.append((to, body)) or "SM-INVITE",
    )

    source_location = client.post(
        "/api/locations",
        json={
            "name": "Roster Source",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550180",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    target_location = client.post(
        "/api/locations",
        json={
            "name": "Roster Target",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550181",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    worker = client.post(
        "/api/workers",
        json={
            "name": "Jordan Smith",
            "phone": "+13105550182",
            "roles": ["line_cook"],
            "priority_rank": 2,
            "location_id": source_location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "pending",
        },
    )
    assert worker.status_code == 201
    worker_payload = worker.json()
    assert worker_payload["employment_status"] == "active"

    roster = client.get(f"/api/locations/{source_location['id']}/roster")
    assert roster.status_code == 200
    roster_payload = roster.json()
    assert roster_payload["summary"]["total_workers"] == 1
    assert roster_payload["summary"]["active_workers"] == 1
    assert roster_payload["workers"][0]["enrollment_status"] == "enrolled"

    eligible = client.get(
        f"/api/locations/{source_location['id']}/eligible-workers?role=line_cook"
    )
    assert eligible.status_code == 200
    assert [item["id"] for item in eligible.json()["workers"]] == [worker_payload["id"]]

    deactivated = client.post(f"/api/workers/{worker_payload['id']}/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["employment_status"] == "inactive"

    eligible = client.get(
        f"/api/locations/{source_location['id']}/eligible-workers?role=line_cook"
    )
    assert eligible.status_code == 200
    assert eligible.json()["workers"] == []

    active_only_roster = client.get(
        f"/api/locations/{source_location['id']}/roster?include_inactive=false"
    )
    assert active_only_roster.status_code == 200
    assert active_only_roster.json()["workers"] == []

    reactivated = client.post(f"/api/workers/{worker_payload['id']}/reactivate")
    assert reactivated.status_code == 200
    assert reactivated.json()["employment_status"] == "active"

    transferred = client.post(
        f"/api/workers/{worker_payload['id']}/transfer",
        json={
            "target_location_id": target_location["id"],
            "roles": ["prep_cook"],
            "priority_rank": 1,
        },
    )
    assert transferred.status_code == 200
    transferred_payload = transferred.json()
    assert transferred_payload["location_id"] == target_location["id"]
    assert "prep_cook" in transferred_payload["roles"]
    assert transferred_payload["employment_status"] == "active"
    assert target_location["id"] in transferred_payload["locations_worked"]
    assert source_location["id"] in transferred_payload["locations_worked"]

    source_roster = client.get(f"/api/locations/{source_location['id']}/roster")
    assert source_roster.status_code == 200
    assert source_roster.json()["workers"][0]["active_assignment"]["is_active"] is False

    target_roster = client.get(f"/api/locations/{target_location['id']}/roster")
    assert target_roster.status_code == 200
    assert target_roster.json()["workers"][0]["active_assignment"]["is_active"] is True
    assert target_roster.json()["workers"][0]["active_assignment"]["priority_rank"] == 1

    eligible = client.get(
        f"/api/locations/{target_location['id']}/eligible-workers?role=prep_cook"
    )
    assert eligible.status_code == 200
    assert [item["id"] for item in eligible.json()["workers"]] == [worker_payload["id"]]

    invite_preview = client.get(
        f"/api/locations/{target_location['id']}/enrollment-invite-preview"
    )
    assert invite_preview.status_code == 200
    assert invite_preview.json() == {
        "location_id": target_location["id"],
        "join_number": "+18002225345",
        "join_keyword": "JOIN",
        "sms_copy": (
            "Backfill for Roster Target: Roster Target is using Backfill for schedules, "
            "callouts, and open shifts. Reply JOIN to enroll. Msg frequency varies. "
            "Reply STOP to opt out."
        ),
    }

    pending_worker = client.post(
        "/api/workers",
        json={
            "name": "Sam Pending",
            "phone": "+13105550183",
            "roles": ["prep_cook"],
            "priority_rank": 3,
            "location_id": target_location["id"],
            "sms_consent_status": "pending",
            "voice_consent_status": "pending",
        },
    )
    assert pending_worker.status_code == 201
    pending_worker_payload = pending_worker.json()

    invite_send = client.post(
        f"/api/locations/{target_location['id']}/enrollment-invites",
        json={
            "worker_ids": [
                worker_payload["id"],
                pending_worker_payload["id"],
                999999,
            ]
        },
    )
    assert invite_send.status_code == 200
    assert invite_send.json()["summary"] == {
        "requested": 3,
        "sent": 1,
        "skipped_enrolled": 1,
        "skipped_inactive": 0,
        "skipped_missing_phone": 0,
        "skipped_not_found": 1,
        "failed": 0,
    }
    assert invite_send.json()["join_number"] == "+18002225345"
    assert invite_send.json()["join_keyword"] == "JOIN"
    assert invite_send.json()["results"] == [
        {
            "worker_id": worker_payload["id"],
            "worker_name": "Jordan Smith",
            "status": "skipped_enrolled",
        },
        {
            "worker_id": pending_worker_payload["id"],
            "worker_name": "Sam Pending",
            "status": "sent",
            "message_sid": "SM-INVITE",
        },
        {
            "worker_id": 999999,
            "status": "skipped_not_found",
        },
    ]
    assert invite_messages == [
        (
            "+13105550183",
            invite_preview.json()["sms_copy"],
        )
    ]


def test_backfill_shifts_import_publish_and_amend_flow(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Backfill Shifts Cafe",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550121",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Maria Lopez,+13105550111,line_cook,2026-04-14,09:00,17:00",
            "Jordan Smith,,dishwasher,2026-04-15,11:00,19:00",
        ]
    )
    job, upload = _create_backfill_shifts_import_job(client, location["id"], csv_text)

    assert upload["columns"] == ["employee_name", "mobile", "role", "date", "start", "end"]
    assert upload["status"] == "mapping"

    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    mapping_payload = mapped.json()
    assert mapping_payload["status"] == "action_needed"
    assert mapping_payload["summary"]["shift_rows"] == 2
    assert mapping_payload["summary"]["warning_rows"] == 1

    rows = client.get(f"/api/import-jobs/{job['id']}/rows")
    assert rows.status_code == 200
    warning_row = rows.json()["rows"][1]
    assert warning_row["row_number"] == 3
    assert warning_row["error_code"] == "assigned_worker_unresolved"

    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    committed_payload = committed.json()
    assert committed_payload["status"] == "completed"
    assert committed_payload["created_workers"] == 1
    assert committed_payload["created_shifts"] == 2
    assert committed_payload["schedule_id"] is not None
    assert committed_payload["week_start_date"] == "2026-04-13"

    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current_schedule.status_code == 200
    current_payload = current_schedule.json()
    assert current_payload["schedule"]["lifecycle_state"] == "draft"
    assert len(current_payload["shifts"]) == 2
    assert current_payload["summary"]["filled_shifts"] == 1
    assert current_payload["summary"]["open_shifts"] == 1
    assert current_payload["publish_readiness"]["can_publish"] is True
    assert current_payload["publish_readiness"]["blocking_issue_count"] == 0
    assert "open_shift_unassigned" in current_payload["publish_readiness"]["warning_codes"]
    initial_open_shift = next(
        shift for shift in current_payload["shifts"] if shift["assignment"]["worker_id"] is None
    )

    coverage = client.get(f"/api/locations/{location['id']}/coverage?week_start=2026-04-13")
    assert coverage.status_code == 200
    assert coverage.json()["at_risk_shifts"][0] == {
        "shift_id": initial_open_shift["id"],
        "role": "dishwasher",
        "date": "2026-04-15",
        "start_time": "11:00:00",
        "current_status": "scheduled",
        "cascade_id": None,
        "coverage_status": "unassigned",
        "current_tier": None,
        "outreach_mode": None,
        "manager_action_required": False,
        "standby_depth": 0,
        "confirmed_worker_id": None,
        "claimed_by_worker_id": None,
        "claimed_by_worker_name": None,
        "claimed_at": None,
        "offered_worker_count": 0,
        "responded_worker_count": 0,
        "last_outreach_at": None,
        "last_response_at": None,
    }

    published = client.post(f"/api/schedules/{committed_payload['schedule_id']}/publish")
    assert published.status_code == 200
    published_payload = published.json()
    assert published_payload["lifecycle_state"] == "published"
    assert published_payload["delivery_summary"]["eligible_workers"] == 1
    assert published_payload["delivery_summary"]["sms_sent"] == 0
    assert published_payload["delivery_summary"]["not_enrolled"] == 1

    new_worker = client.post(
        "/api/workers",
        json={
            "name": "Jordan Smith",
            "phone": "+13105550112",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert new_worker.status_code == 201

    amended = client.patch(
        f"/api/shifts/{initial_open_shift['id']}/assignment",
        json={
            "worker_id": new_worker.json()["id"],
            "assignment_status": "assigned",
            "notes": "Manager reassigned after import review",
        },
    )
    assert amended.status_code == 200
    amended_payload = amended.json()
    assert amended_payload["assignment"]["worker_name"] == "Jordan Smith"
    assert amended_payload["schedule_lifecycle_state"] == "amended"


def test_backfill_shifts_import_commit_notifies_manager_with_review_link(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM123",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Import Prompt Cafe",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550125",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Maria Lopez,+13105550126,line_cook,2026-04-14,09:00,17:00",
            "Jordan Smith,+13105550127,,2026-04-15,11:00,19:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    assert mapped.json()["status"] == "action_needed"

    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    assert committed.json()["status"] == "partially_completed"

    assert sent == [
        (
            "+13105550125",
            (
                "Backfill: Your first draft for Apr 13-19 is ready. "
                "1 of 1 shifts are assigned. "
                "1 need review: a role is missing on one import row. "
                f"Reply APPROVE or tap to review: https://usebackfill.com/dashboard/locations/{location['id']}?tab=imports&job_id={job['id']}&row=3"
            ),
        )
    ]


def test_backfill_shifts_copy_last_week(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Copy Week Bakery",
            "manager_name": "Ari Lead",
            "manager_phone": "+13105550131",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Sam Cook,+13105550141,prep_cook,2026-04-13,08:00,16:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]

    copied = client.post(
        f"/api/locations/{location['id']}/schedules/copy-last-week",
        json={
            "source_schedule_id": schedule_id,
            "target_week_start_date": "2026-04-20",
        },
    )
    assert copied.status_code == 200
    copied_payload = copied.json()
    assert copied_payload["copied_shift_count"] == 1
    assert copied_payload["week_start_date"] == "2026-04-20"

    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-20"
    )
    assert current_schedule.status_code == 200
    shift = current_schedule.json()["shifts"][0]
    assert shift["date"] == "2026-04-20"
    assert shift["assignment"]["worker_name"] == "Sam Cook"


def test_backfill_shifts_copy_last_week_notifies_manager(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM123",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Copy Prompt Bakery",
            "manager_name": "Ari Lead",
            "manager_phone": "+13105550135",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Sam Cook,+13105550141,prep_cook,2026-04-13,08:00,16:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    sent.clear()

    copied = client.post(
        f"/api/locations/{location['id']}/schedules/copy-last-week",
        json={
            "source_schedule_id": committed.json()["schedule_id"],
            "target_week_start_date": "2026-04-20",
        },
    )
    assert copied.status_code == 200

    assert sent == [
        (
            "+13105550135",
            (
                "Backfill: Your draft for Apr 20-26 is ready. "
                "1 of 1 shifts are assigned. "
                f"Reply APPROVE to publish or REVIEW to edit: https://usebackfill.com/dashboard/locations/{location['id']}?tab=schedule&week_start=2026-04-20"
            ),
        )
    ]


def test_backfill_shifts_can_copy_day_without_assignments(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Copy Day Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550142",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Sam Cook,+13105550143,prep_cook,2026-04-14,08:00,16:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    copied = client.post(
        f"/api/schedules/{schedule_id}/copy-day",
        json={
            "source_date": "2026-04-14",
            "target_date": "2026-04-17",
            "copy_assignments": False,
        },
    )

    assert copied.status_code == 200
    payload = copied.json()
    assert payload["schedule_id"] == schedule_id
    assert payload["source_date"] == "2026-04-14"
    assert payload["target_date"] == "2026-04-17"
    assert payload["copied_shift_count"] == 1
    assert payload["replaced_shift_count"] == 0
    assert payload["copied_assignments"] == 0
    assert payload["skipped_assignments"] == 0
    assert payload["schedule_lifecycle_state"] == "amended"
    copied_shift = next(
        shift
        for shift in payload["schedule_view"]["shifts"]
        if shift["date"] == "2026-04-17"
    )
    assert copied_shift["role"] == "prep_cook"
    assert copied_shift["assignment"]["worker_id"] is None
    assert copied_shift["assignment"]["assignment_status"] == "open"
    assert copied_shift["available_actions"] == ["start_coverage", "close_shift"]


def test_backfill_shifts_can_copy_day_with_assignments_and_replace_target_day(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Replace Day Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550144",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Sam Cook,+13105550145,prep_cook,2026-04-14,08:00,16:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    target_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-16",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    assert target_shift.status_code == 200

    conflict = client.post(
        f"/api/schedules/{schedule_id}/copy-day",
        json={
            "source_date": "2026-04-14",
            "target_date": "2026-04-16",
            "copy_assignments": True,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "Target date already has shifts"}

    copied = client.post(
        f"/api/schedules/{schedule_id}/copy-day",
        json={
            "source_date": "2026-04-14",
            "target_date": "2026-04-16",
            "copy_assignments": True,
            "replace_target_day": True,
        },
    )

    assert copied.status_code == 200
    payload = copied.json()
    assert payload["copied_shift_count"] == 1
    assert payload["replaced_shift_count"] == 1
    assert payload["copied_assignments"] == 1
    assert payload["skipped_assignments"] == 0
    target_day_shifts = [
        shift
        for shift in payload["schedule_view"]["shifts"]
        if shift["date"] == "2026-04-16"
    ]
    assert len(target_day_shifts) == 1
    assert target_day_shifts[0]["role"] == "prep_cook"
    assert target_day_shifts[0]["assignment"]["worker_name"] == "Sam Cook"
    assert target_day_shifts[0]["assignment"]["assignment_status"] == "assigned"
    assert target_day_shifts[0]["available_actions"] == []


def test_backfill_shifts_can_create_and_apply_schedule_template(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Template Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550146",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Sam Cook,+13105550147,prep_cook,2026-04-14,08:00,16:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]

    created_template = client.post(
        f"/api/schedules/{schedule_id}/templates",
        json={
            "name": "Weekday Prep Template",
            "description": "Reusable prep schedule",
            "include_assignments": True,
        },
    )
    assert created_template.status_code == 200
    template_payload = created_template.json()["template"]
    assert template_payload["name"] == "Weekday Prep Template"
    assert template_payload["description"] == "Reusable prep schedule"
    assert template_payload["source_schedule_id"] == schedule_id
    assert template_payload["shift_count"] == 1
    assert template_payload["assigned_shift_count"] == 1
    assert template_payload["shifts"][0]["day_of_week"] == 1
    assert template_payload["shifts"][0]["worker_name"] == "Sam Cook"

    templates = client.get(f"/api/locations/{location['id']}/schedule-templates")
    assert templates.status_code == 200
    assert templates.json()["location_id"] == location["id"]
    assert templates.json()["templates"][0]["id"] == template_payload["id"]

    applied = client.post(
        f"/api/schedule-templates/{template_payload['id']}/apply",
        json={"target_week_start_date": "2026-04-20"},
    )
    assert applied.status_code == 200
    applied_payload = applied.json()
    assert applied_payload["created_schedule"] is True
    assert applied_payload["target_week_start_date"] == "2026-04-20"
    assert applied_payload["created_shift_count"] == 1
    assert applied_payload["replaced_shift_count"] == 0
    assert applied_payload["copied_assignments"] == 1
    assert applied_payload["skipped_assignments"] == 0
    assert applied_payload["schedule_lifecycle_state"] == "draft"
    copied_shift = next(
        shift
        for shift in applied_payload["schedule_view"]["shifts"]
        if shift["date"] == "2026-04-21"
    )
    assert copied_shift["role"] == "prep_cook"
    assert copied_shift["assignment"]["worker_name"] == "Sam Cook"
    assert copied_shift["assignment"]["assignment_status"] == "assigned"
    assert copied_shift["available_actions"] == []


def test_backfill_shifts_can_replace_schedule_from_template_and_skip_invalid_assignments(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Template Replace Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550148",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Sam Cook,+13105550149,prep_cook,2026-04-14,08:00,16:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]

    created_template = client.post(
        f"/api/schedules/{schedule_id}/templates",
        json={
            "name": "Replaceable Prep Template",
            "include_assignments": True,
        },
    )
    assert created_template.status_code == 200
    template_payload = created_template.json()["template"]
    template_id = template_payload["id"]
    worker_id = template_payload["shifts"][0]["worker_id"]
    assert worker_id is not None

    first_apply = client.post(
        f"/api/schedule-templates/{template_id}/apply",
        json={"target_week_start_date": "2026-04-20"},
    )
    assert first_apply.status_code == 200

    deactivated = client.post(f"/api/workers/{worker_id}/deactivate")
    assert deactivated.status_code == 200

    conflict = client.post(
        f"/api/schedule-templates/{template_id}/apply",
        json={"target_week_start_date": "2026-04-20"},
    )
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "Target schedule already has shifts"}

    replaced = client.post(
        f"/api/schedule-templates/{template_id}/apply",
        json={
            "target_week_start_date": "2026-04-20",
            "replace_existing": True,
        },
    )
    assert replaced.status_code == 200
    replaced_payload = replaced.json()
    assert replaced_payload["created_schedule"] is False
    assert replaced_payload["created_shift_count"] == 1
    assert replaced_payload["replaced_shift_count"] == 1
    assert replaced_payload["copied_assignments"] == 0
    assert replaced_payload["skipped_assignments"] == 1
    target_shift = next(
        shift
        for shift in replaced_payload["schedule_view"]["shifts"]
        if shift["date"] == "2026-04-21"
    )
    assert target_shift["assignment"]["worker_id"] is None
    assert target_shift["assignment"]["assignment_status"] == "open"
    assert target_shift["available_actions"] == ["start_coverage", "close_shift"]


def test_backfill_shifts_can_apply_template_range_and_continue_past_conflicts(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Template Range Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550150",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Sam Cook,+13105550151,prep_cook,2026-04-14,08:00,16:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]

    created_template = client.post(
        f"/api/schedules/{schedule_id}/templates",
        json={
            "name": "Multiweek Prep Template",
            "include_assignments": True,
        },
    )
    assert created_template.status_code == 200
    template_id = created_template.json()["template"]["id"]

    first_apply = client.post(
        f"/api/schedule-templates/{template_id}/apply",
        json={"target_week_start_date": "2026-04-20"},
    )
    assert first_apply.status_code == 200

    applied_range = client.post(
        f"/api/schedule-templates/{template_id}/apply-range",
        json={
            "target_week_start_dates": ["2026-04-20", "2026-04-27"],
            "replace_existing": False,
        },
    )
    assert applied_range.status_code == 200
    payload = applied_range.json()
    assert payload["processed_count"] == 2
    assert payload["success_count"] == 1
    assert payload["error_count"] == 1
    assert payload["results"][0] == {
        "target_week_start_date": "2026-04-20",
        "status": "error",
        "error": "Target schedule already has shifts",
    }
    assert payload["results"][1]["target_week_start_date"] == "2026-04-27"
    assert payload["results"][1]["status"] == "ok"
    assert payload["results"][1]["created_schedule"] is True
    assert payload["results"][1]["copied_assignments"] == 1

    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-27"
    )
    assert current_schedule.status_code == 200
    copied_shift = current_schedule.json()["shifts"][0]
    assert copied_shift["date"] == "2026-04-28"
    assert copied_shift["assignment"]["worker_name"] == "Sam Cook"


def test_backfill_shifts_can_update_refresh_and_delete_template(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Template Lifecycle Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550152",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Sam Cook,+13105550153,prep_cook,2026-04-14,08:00,16:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    source_schedule_id = committed.json()["schedule_id"]

    created_template = client.post(
        f"/api/schedules/{source_schedule_id}/templates",
        json={
            "name": "Original Prep Template",
            "include_assignments": True,
        },
    )
    assert created_template.status_code == 200
    template_id = created_template.json()["template"]["id"]

    updated = client.patch(
        f"/api/schedule-templates/{template_id}",
        json={
            "name": "Updated Prep Template",
            "description": "Template maintained from schedule",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["template"]["name"] == "Updated Prep Template"
    assert updated.json()["template"]["description"] == "Template maintained from schedule"

    copied = client.post(
        f"/api/locations/{location['id']}/schedules/copy-last-week",
        json={
            "source_schedule_id": source_schedule_id,
            "target_week_start_date": "2026-04-20",
        },
    )
    assert copied.status_code == 200
    copied_schedule_id = copied.json()["schedule_id"]

    target_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-20"
    )
    assert target_schedule.status_code == 200
    target_shift_id = target_schedule.json()["shifts"][0]["id"]

    edited = client.patch(
        f"/api/schedules/{copied_schedule_id}/shifts",
        json={
            "shift_ids": [target_shift_id],
            "start_time": "09:00:00",
            "notes": "Refreshed template",
        },
    )
    assert edited.status_code == 200

    refreshed = client.post(
        f"/api/schedule-templates/{template_id}/refresh",
        json={
            "source_schedule_id": copied_schedule_id,
            "include_assignments": False,
        },
    )
    assert refreshed.status_code == 200
    refreshed_payload = refreshed.json()
    assert refreshed_payload["source_schedule_id"] == copied_schedule_id
    assert refreshed_payload["replaced_shift_count"] == 1
    assert refreshed_payload["shift_count"] == 1
    assert refreshed_payload["assigned_shift_count"] == 0
    assert refreshed_payload["template"]["name"] == "Updated Prep Template"
    assert refreshed_payload["template"]["source_schedule_id"] == copied_schedule_id
    assert refreshed_payload["template"]["shifts"][0]["start_time"] == "09:00:00"
    assert refreshed_payload["template"]["shifts"][0]["notes"] == "Refreshed template"
    assert refreshed_payload["template"]["shifts"][0]["worker_id"] is None

    deleted = client.delete(f"/api/schedule-templates/{template_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    templates = client.get(f"/api/locations/{location['id']}/schedule-templates")
    assert templates.status_code == 200
    assert templates.json()["templates"] == []

    apply_deleted = client.post(
        f"/api/schedule-templates/{template_id}/apply",
        json={"target_week_start_date": "2026-04-27"},
    )
    assert apply_deleted.status_code == 404
    assert apply_deleted.json() == {"detail": "Schedule template not found"}


def test_backfill_shifts_can_manually_author_template_slots_and_preview(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Manual Template Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550154",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker = client.post(
        "/api/workers",
        json={
            "name": "Sam Cook",
            "phone": "+13105550155",
            "roles": ["prep_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()

    created = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={
            "name": "Manual Week Template",
            "description": "Built without a source schedule",
        },
    )
    assert created.status_code == 200
    template = created.json()["template"]
    assert template["shift_count"] == 0
    assert template["available_actions"] == ["edit", "clone", "delete", "add_shift"]

    first_shift = client.post(
        f"/api/schedule-templates/{template['id']}/shifts",
        json={
            "day_of_week": 1,
            "role": "prep_cook",
            "start_time": "08:00:00",
            "end_time": "16:00:00",
            "worker_id": worker["id"],
            "notes": "Morning prep",
        },
    )
    assert first_shift.status_code == 200
    first_shift_payload = first_shift.json()["shift"]
    assert first_shift_payload["assignment_status"] == "assigned"
    assert first_shift_payload["warnings"] == []

    updated_shift = client.patch(
        f"/api/schedule-template-shifts/{first_shift_payload['id']}",
        json={
            "start_time": "09:00:00",
            "notes": "Updated prep block",
        },
    )
    assert updated_shift.status_code == 200
    assert updated_shift.json()["shift"]["start_time"] == "09:00:00"
    assert updated_shift.json()["shift"]["notes"] == "Updated prep block"

    duplicated_shift = client.post(
        f"/api/schedule-template-shifts/{first_shift_payload['id']}/duplicate?day_of_week=2"
    )
    assert duplicated_shift.status_code == 200
    duplicated_shift_payload = duplicated_shift.json()["shift"]
    assert duplicated_shift_payload["day_of_week"] == 2

    fetched = client.get(f"/api/schedule-templates/{template['id']}")
    assert fetched.status_code == 200
    fetched_template = fetched.json()["template"]
    assert fetched_template["shift_count"] == 2
    assert fetched_template["assigned_shift_count"] == 2
    assert fetched_template["validation_summary"]["warning_count"] == 0
    assert fetched_template["available_actions"] == [
        "edit",
        "clone",
        "delete",
        "add_shift",
        "preview",
        "apply",
        "apply_range",
    ]

    preview = client.get(
        f"/api/schedule-templates/{template['id']}/preview?target_week_start_date=2026-05-04"
    )
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["existing_shift_count"] == 0
    assert preview_payload["replace_required"] is False
    assert preview_payload["summary"] == {
        "shift_count": 2,
        "copied_assignment_count": 2,
        "skipped_assignment_count": 0,
    }
    assert [shift["date"] for shift in preview_payload["shifts"]] == ["2026-05-05", "2026-05-06"]
    assert all(shift["assignment"]["worker_name"] == "Sam Cook" for shift in preview_payload["shifts"])

    deleted_shift = client.delete(f"/api/schedule-template-shifts/{duplicated_shift_payload['id']}")
    assert deleted_shift.status_code == 200
    assert deleted_shift.json()["deleted"] is True
    assert deleted_shift.json()["template"]["shift_count"] == 1


def test_backfill_shifts_template_clone_and_validation_drift(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Template Drift Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550156",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker = client.post(
        "/api/workers",
        json={
            "name": "Sam Cook",
            "phone": "+13105550157",
            "roles": ["prep_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()

    created = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Drift Template"},
    )
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]

    added_shift = client.post(
        f"/api/schedule-templates/{template_id}/shifts",
        json={
            "day_of_week": 1,
            "role": "prep_cook",
            "start_time": "08:00:00",
            "end_time": "16:00:00",
            "worker_id": worker["id"],
        },
    )
    assert added_shift.status_code == 200

    clone = client.post(
        f"/api/schedule-templates/{template_id}/clone",
        json={"name": "Drift Template Copy"},
    )
    assert clone.status_code == 200
    cloned_template = clone.json()["template"]
    assert cloned_template["name"] == "Drift Template Copy"
    assert cloned_template["shift_count"] == 1

    deactivated = client.post(f"/api/workers/{worker['id']}/deactivate")
    assert deactivated.status_code == 200

    fetched = client.get(f"/api/schedule-templates/{cloned_template['id']}")
    assert fetched.status_code == 200
    fetched_template = fetched.json()["template"]
    assert fetched_template["validation_summary"]["warning_count"] == 1
    assert fetched_template["validation_summary"]["invalid_assignment_count"] == 1
    assert fetched_template["shifts"][0]["warnings"] == [
        {
            "code": "worker_inactive",
            "message": "Assigned worker is not active",
        }
    ]

    applied = client.post(
        f"/api/schedule-templates/{cloned_template['id']}/apply",
        json={"target_week_start_date": "2026-05-11"},
    )
    assert applied.status_code == 200
    assert applied.json()["copied_assignments"] == 0
    assert applied.json()["skipped_assignments"] == 1
    applied_shift = applied.json()["schedule_view"]["shifts"][0]
    assert applied_shift["assignment"]["worker_id"] is None
    assert applied_shift["assignment"]["assignment_status"] == "open"


def test_backfill_shifts_template_bulk_slot_routes_and_filtered_apply(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Bulk Template Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550158",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker = client.post(
        "/api/workers",
        json={
            "name": "Sam Cook",
            "phone": "+13105550159",
            "roles": ["prep_cook", "dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()

    created = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Bulk Ops Template"},
    )
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]

    bulk_created = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 1,
                    "role": "prep_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": worker["id"],
                },
                {
                    "day_of_week": 2,
                    "role": "dishwasher",
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                    "worker_id": worker["id"],
                },
            ]
        },
    )
    assert bulk_created.status_code == 200
    bulk_created_payload = bulk_created.json()
    assert bulk_created_payload["processed_count"] == 2
    assert bulk_created_payload["success_count"] == 2
    assert bulk_created_payload["error_count"] == 0
    shift_ids = [item["shift"]["id"] for item in bulk_created_payload["results"]]

    bulk_updated = client.patch(
        f"/api/schedule-templates/{template_id}/shifts",
        json={
            "shift_ids": shift_ids,
            "notes": "Bulk updated notes",
            "pay_rate": 24.5,
        },
    )
    assert bulk_updated.status_code == 200
    assert bulk_updated.json()["processed_count"] == 2
    assert bulk_updated.json()["success_count"] == 2
    assert bulk_updated.json()["updated_fields"] == ["notes", "pay_rate"]

    bulk_duplicated = client.post(
        f"/api/schedule-templates/{template_id}/shifts/duplicate",
        json={"shift_ids": [shift_ids[0]], "day_of_week": 4},
    )
    assert bulk_duplicated.status_code == 200
    assert bulk_duplicated.json()["processed_count"] == 1
    assert bulk_duplicated.json()["success_count"] == 1
    assert bulk_duplicated.json()["template"]["shift_count"] == 3

    preview = client.get(
        f"/api/schedule-templates/{template_id}/preview?target_week_start_date=2026-05-18&day_of_week=1&day_of_week=4"
    )
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["day_of_week_filter"] == [1, 4]
    assert preview_payload["summary"]["shift_count"] == 2
    assert [shift["date"] for shift in preview_payload["shifts"]] == ["2026-05-19", "2026-05-22"]

    applied = client.post(
        f"/api/schedule-templates/{template_id}/apply",
        json={
            "target_week_start_date": "2026-05-18",
            "day_of_week_filter": [1, 4],
        },
    )
    assert applied.status_code == 200
    assert applied.json()["day_of_week_filter"] == [1, 4]
    assert applied.json()["created_shift_count"] == 2
    assert [shift["date"] for shift in applied.json()["schedule_view"]["shifts"]] == ["2026-05-19", "2026-05-22"]

    applied_range = client.post(
        f"/api/schedule-templates/{template_id}/apply-range",
        json={
            "target_week_start_dates": ["2026-05-25"],
            "day_of_week_filter": [2],
        },
    )
    assert applied_range.status_code == 200
    assert applied_range.json()["day_of_week_filter"] == [2]
    assert applied_range.json()["success_count"] == 1

    schedule_next = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-05-25"
    )
    assert schedule_next.status_code == 200
    assert [shift["date"] for shift in schedule_next.json()["shifts"]] == ["2026-05-27"]

    bulk_deleted = client.post(
        f"/api/schedule-templates/{template_id}/shifts/delete",
        json={"shift_ids": [shift_ids[1]]},
    )
    assert bulk_deleted.status_code == 200
    assert bulk_deleted.json()["processed_count"] == 1
    assert bulk_deleted.json()["success_count"] == 1
    assert bulk_deleted.json()["template"]["shift_count"] == 2


def test_backfill_shifts_template_detail_includes_overlap_and_summaries(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Overlap Template Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550160",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker = client.post(
        "/api/workers",
        json={
            "name": "Sam Cook",
            "phone": "+13105550161",
            "roles": ["prep_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()

    created = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Overlap Template"},
    )
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]

    bulk_created = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 1,
                    "role": "prep_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": worker["id"],
                },
                {
                    "day_of_week": 1,
                    "role": "prep_cook",
                    "start_time": "12:00:00",
                    "end_time": "18:00:00",
                    "worker_id": worker["id"],
                },
            ]
        },
    )
    assert bulk_created.status_code == 200

    fetched = client.get(f"/api/schedule-templates/{template_id}")
    assert fetched.status_code == 200
    template = fetched.json()["template"]
    assert template["validation_summary"]["overlap_count"] == 1
    assert template["validation_summary"]["warning_count"] == 2
    assert template["daily_summary"] == [
        {
            "day_of_week": 1,
            "shift_count": 2,
            "assigned_shift_count": 2,
            "total_hours": 14.0,
        }
    ]
    assert template["role_summary"] == [
        {
            "role": "prep_cook",
            "shift_count": 2,
            "assigned_shift_count": 2,
            "total_hours": 14.0,
        }
    ]
    assert template["worker_summary"] == [
        {
            "worker_id": worker["id"],
            "worker_name": "Sam Cook",
            "shift_count": 2,
            "total_hours": 14.0,
        }
    ]
    assert template["template_warnings"] == [
        {
            "code": "template_overlap",
            "message": "Template shifts overlap in time",
            "shift_ids": sorted([template["shifts"][0]["id"], template["shifts"][1]["id"]]),
        }
    ]
    assert all(
        warning["code"] == "template_overlap"
        for shift in template["shifts"]
        for warning in shift["warnings"]
    )


def test_backfill_shifts_template_staffing_plan_auto_assign_and_generate_draft(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Planning Template Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550162",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    prep_worker = client.post(
        "/api/workers",
        json={
            "name": "Prep One",
            "phone": "+13105550163",
            "roles": ["prep_cook"],
            "location_id": location["id"],
            "max_hours_per_week": 40,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    dish_worker = client.post(
        "/api/workers",
        json={
            "name": "Dish One",
            "phone": "+13105550164",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "max_hours_per_week": 24,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()

    created = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Planning Template"},
    )
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]

    bulk_created = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 1,
                    "role": "prep_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                },
                {
                    "day_of_week": 2,
                    "role": "dishwasher",
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                },
                {
                    "day_of_week": 3,
                    "role": "cashier",
                    "start_time": "10:00:00",
                    "end_time": "14:00:00",
                },
            ]
        },
    )
    assert bulk_created.status_code == 200

    staffing_plan = client.get(f"/api/schedule-templates/{template_id}/staffing-plan")
    assert staffing_plan.status_code == 200
    plan = staffing_plan.json()
    assert plan["staffing_plan"]["summary"] == {
        "shift_count": 3,
        "total_hours": 20.0,
        "assigned_shift_count": 0,
        "open_shift_count": 3,
        "assigned_hours": 0.0,
        "open_hours": 20.0,
        "eligible_worker_count": 2,
        "staffing_gap_count": 1,
        "auto_assignable_shift_count": 2,
        "overtime_risk_count": 0,
        "over_capacity_worker_count": 0,
        "review_required_count": 3,
        "recommended_assignment_count": 2,
        "coverage_risk_count": 3,
        "assignment_strategy": "priority_first",
        "ready_to_generate": True,
        "ready_to_publish": False,
    }
    role_summary = {item["role"]: item for item in plan["staffing_plan"]["roles"]}
    assert role_summary["prep_cook"]["eligible_worker_count"] == 1
    assert role_summary["dishwasher"]["eligible_worker_count"] == 1
    assert role_summary["cashier"]["eligible_worker_count"] == 0
    suggestions = {item["role"]: item["suggested_workers"] for item in plan["staffing_plan"]["shifts"]}
    assert suggestions["prep_cook"][0]["worker_id"] == prep_worker["id"]
    assert suggestions["dishwasher"][0]["worker_id"] == dish_worker["id"]
    assert suggestions["cashier"] == []

    auto_assigned = client.post(
        f"/api/schedule-templates/{template_id}/auto-assign",
        json={},
    )
    assert auto_assigned.status_code == 200
    assert auto_assigned.json()["summary"] == {
        "processed_count": 3,
        "auto_assigned_count": 2,
        "cleared_invalid_count": 0,
        "unchanged_assigned_count": 0,
        "unassigned_count": 1,
        "assignment_strategy": "priority_first",
    }
    template_after = auto_assigned.json()["template"]
    assigned_by_role = {shift["role"]: shift for shift in template_after["shifts"]}
    assert assigned_by_role["prep_cook"]["worker_id"] == prep_worker["id"]
    assert assigned_by_role["dishwasher"]["worker_id"] == dish_worker["id"]
    assert assigned_by_role["cashier"]["worker_id"] is None

    generated = client.post(
        f"/api/schedule-templates/{template_id}/generate-draft",
        json={
            "target_week_start_date": "2026-06-01",
            "day_of_week_filter": [1, 2],
            "auto_assign_open_shifts": True,
        },
    )
    assert generated.status_code == 200
    payload = generated.json()
    assert payload["generated_from_template"] is True
    assert payload["generation_mode"] == "draft"
    assert payload["created_shift_count"] == 2
    assert payload["auto_assign_summary"]["auto_assigned_count"] == 0
    assert payload["copied_assignments"] == 2
    assert [shift["date"] for shift in payload["schedule_view"]["shifts"]] == ["2026-06-02", "2026-06-03"]


def test_backfill_shifts_template_suggestions_apply_clear_and_strategy(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Strategy Template Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550168",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    priority_worker = client.post(
        "/api/workers",
        json={
            "name": "Priority Cook",
            "phone": "+13105550169",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "priority_rank": 1,
            "max_hours_per_week": 40,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    balance_worker = client.post(
        "/api/workers",
        json={
            "name": "Balance Cook",
            "phone": "+13105550170",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "priority_rank": 2,
            "max_hours_per_week": 40,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()

    created = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Strategy Template"},
    )
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]

    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 1,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": priority_worker["id"],
                    "assignment_status": "assigned",
                },
                {
                    "day_of_week": 2,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": priority_worker["id"],
                    "assignment_status": "assigned",
                },
                {
                    "day_of_week": 3,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                },
            ]
        },
    )
    assert seeded.status_code == 200
    open_shift_id = next(
        shift["id"]
        for shift in seeded.json()["template"]["shifts"]
        if shift["worker_id"] is None
    )

    default_plan = client.get(f"/api/schedule-templates/{template_id}/staffing-plan")
    assert default_plan.status_code == 200
    default_open_shift = next(
        shift for shift in default_plan.json()["staffing_plan"]["shifts"] if shift["shift_id"] == open_shift_id
    )
    assert default_plan.json()["staffing_plan"]["summary"]["assignment_strategy"] == "priority_first"
    assert default_plan.json()["staffing_plan"]["summary"]["review_required_count"] == 1
    assert default_plan.json()["staffing_plan"]["summary"]["ready_to_publish"] is False
    assert default_open_shift["recommended_worker_id"] == priority_worker["id"]
    assert default_open_shift["suggested_workers"][0]["score_breakdown"]["total"] >= 0
    assert "recommended" in default_open_shift["suggested_workers"][0]["reason_codes"]

    balanced_plan = client.get(
        f"/api/schedule-templates/{template_id}/staffing-plan?strategy=balance_hours"
    )
    assert balanced_plan.status_code == 200
    balanced_open_shift = next(
        shift for shift in balanced_plan.json()["staffing_plan"]["shifts"] if shift["shift_id"] == open_shift_id
    )
    assert balanced_open_shift["recommended_worker_id"] == balance_worker["id"]
    assert balanced_open_shift["suggestion_strategy"] == "balance_hours"
    assert balanced_open_shift["suggested_workers"][0]["confidence"] in {"high", "medium"}

    suggestions = client.get(
        f"/api/schedule-templates/{template_id}/suggestions?strategy=balance_hours"
    )
    assert suggestions.status_code == 200
    suggestions_payload = suggestions.json()
    assert suggestions_payload["summary"]["suggestion_shift_count"] == 1
    assert suggestions_payload["suggestions"][0]["recommended_worker_id"] == balance_worker["id"]

    applied = client.post(
        f"/api/schedule-templates/{template_id}/suggestions/apply",
        json={"assignment_strategy": "balance_hours"},
    )
    assert applied.status_code == 200
    applied_payload = applied.json()
    assert applied_payload["applied_count"] == 1
    assert applied_payload["assignment_strategy"] == "balance_hours"
    applied_shift = next(
        shift for shift in applied_payload["template"]["shifts"] if shift["id"] == open_shift_id
    )
    assert applied_shift["worker_id"] == balance_worker["id"]

    cleared = client.post(
        f"/api/schedule-templates/{template_id}/assignments/clear",
        json={"shift_ids": [open_shift_id]},
    )
    assert cleared.status_code == 200
    cleared_payload = cleared.json()
    assert cleared_payload["cleared_count"] == 1
    cleared_shift = next(
        shift for shift in cleared_payload["template"]["shifts"] if shift["id"] == open_shift_id
    )
    assert cleared_shift["worker_id"] is None
    assert cleared_shift["assignment_status"] == "open"

    generated = client.post(
        f"/api/schedule-templates/{template_id}/generate-draft",
        json={
            "target_week_start_date": "2026-07-06",
            "auto_assign_open_shifts": True,
            "assignment_strategy": "balance_hours",
        },
    )
    assert generated.status_code == 200
    generated_payload = generated.json()
    generated_shift = next(
        shift for shift in generated_payload["schedule_view"]["shifts"] if shift["date"] == "2026-07-09"
    )
    assert generated_payload["assignment_strategy"] == "balance_hours"
    assert generated_payload["auto_assign_summary"]["assignment_strategy"] == "balance_hours"
    assert generated_shift["assignment"]["worker_id"] == balance_worker["id"]


def test_backfill_shifts_template_apply_auto_assigns_open_shifts_when_requested(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Apply Assign Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550165",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker = client.post(
        "/api/workers",
        json={
            "name": "Prep One",
            "phone": "+13105550166",
            "roles": ["prep_cook"],
            "location_id": location["id"],
            "max_hours_per_week": 16,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()

    created = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Apply Assign Template"},
    )
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]

    added = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 1,
                    "role": "prep_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                },
                {
                    "day_of_week": 2,
                    "role": "prep_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                },
                {
                    "day_of_week": 3,
                    "role": "prep_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                },
            ]
        },
    )
    assert added.status_code == 200

    applied = client.post(
        f"/api/schedule-templates/{template_id}/apply",
        json={
            "target_week_start_date": "2026-06-08",
            "auto_assign_open_shifts": True,
        },
    )
    assert applied.status_code == 200
    payload = applied.json()
    assert payload["auto_assign_open_shifts"] is True
    assert payload["auto_assign_summary"] == {
        "processed_count": 3,
        "auto_assigned_count": 2,
        "cleared_invalid_count": 0,
        "unchanged_assigned_count": 0,
        "unassigned_count": 1,
        "assignment_strategy": "priority_first",
    }
    assigned = [
        shift for shift in payload["schedule_view"]["shifts"]
        if shift["assignment"]["worker_id"] == worker["id"]
    ]
    open_shifts = [
        shift for shift in payload["schedule_view"]["shifts"]
        if shift["assignment"]["worker_id"] is None
    ]
    assert len(assigned) == 2
    assert len(open_shifts) == 1
    assert payload["copied_assignments"] == 2
    assert payload["skipped_assignments"] == 0


def test_backfill_shifts_create_from_template_review_publish_readiness_and_versions(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Review Template Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550175",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker = client.post(
        "/api/workers",
        json={
            "name": "Sam Cook",
            "phone": "+13105550176",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Publish Review Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]

    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": worker["id"],
                    "assignment_status": "assigned",
                },
                {
                    "day_of_week": 1,
                    "role": "dishwasher",
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                },
            ]
        },
    )
    assert seeded.status_code == 200

    draft_options = client.get(f"/api/locations/{location['id']}/schedule-draft-options")
    assert draft_options.status_code == 200
    assert draft_options.json()["recommended_basis"] == {
        "basis_type": "template",
        "template_id": template_id,
    }

    created = client.post(
        f"/api/locations/{location['id']}/schedules/create-from-template",
        json={
            "template_id": template_id,
            "target_week_start_date": "2026-07-13",
        },
    )
    assert created.status_code == 200
    payload = created.json()
    schedule_id = payload["schedule_id"]
    assert payload["basis_type"] == "template"
    assert payload["generation_mode"] == "template_apply"
    assert payload["schedule_view"]["publish_readiness"]["can_publish"] is True

    review = client.get(f"/api/schedules/{schedule_id}/review")
    assert review.status_code == 200
    review_payload = review.json()
    assert review_payload["publish_readiness"]["can_publish"] is True
    assert review_payload["summary"]["open_shifts"] == 1

    readiness = client.get(f"/api/schedules/{schedule_id}/publish-readiness")
    assert readiness.status_code == 200
    assert readiness.json()["publish_readiness"]["status_label"] == "ready"

    versions = client.get(f"/api/schedules/{schedule_id}/versions")
    assert versions.status_code == 200
    versions_payload = versions.json()["versions"]
    assert len(versions_payload) == 1
    assert versions_payload[0]["version_number"] == 1
    assert versions_payload[0]["version_type"] == "draft_snapshot"
    assert versions_payload[0]["change_summary"]["event"] == "schedule_template_applied"
    assert versions_payload[0]["event_label"] == "Draft saved"
    assert versions_payload[0]["impact_summary"]["has_changes"] is False
    assert versions_payload[0]["shift_count"] == 2
    assert versions_payload[0]["assigned_shift_count"] == 1
    assert versions_payload[0]["open_shift_count"] == 1

    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    readiness_after = client.get(f"/api/schedules/{schedule_id}/publish-readiness")
    assert readiness_after.status_code == 200
    assert readiness_after.json()["publish_readiness"]["can_publish"] is False
    assert readiness_after.json()["publish_readiness"]["state_reason"] == "already_published"

    versions_after = client.get(f"/api/schedules/{schedule_id}/versions")
    assert versions_after.status_code == 200
    versions_after_payload = versions_after.json()["versions"]
    assert [item["version_type"] for item in versions_after_payload] == [
        "draft_snapshot",
        "publish_snapshot",
    ]
    assert versions_after_payload[1]["event_label"] == "Schedule published"
    assert versions_after_payload[1]["default_compare_mode"] == "first_publish"
    assert versions_after_payload[1]["event_narrative"] == (
        "Schedule published. This was the first published version of the week."
    )


def test_backfill_shifts_ai_draft_uses_template_or_schedule_basis(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "AI Draft Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550177",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    client.post(
        "/api/workers",
        json={
            "name": "Jordan Cook",
            "phone": "+13105550178",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "priority_rank": 1,
            "max_hours_per_week": 40,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "AI Draft Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]
    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                },
                {
                    "day_of_week": 1,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                },
            ]
        },
    )
    assert seeded.status_code == 200

    from_template = client.post(
        f"/api/locations/{location['id']}/schedules/ai-draft",
        json={
            "target_week_start_date": "2026-07-20",
            "auto_assign_open_shifts": True,
            "assignment_strategy": "priority_first",
        },
    )
    assert from_template.status_code == 200
    template_payload = from_template.json()
    assert template_payload["basis_type"] == "template"
    assert template_payload["basis_template_id"] == template_id
    assert template_payload["generation_mode"] == "ai_draft"
    assert template_payload["schedule_view"]["summary"]["filled_shifts"] == 2
    first_schedule_id = template_payload["schedule_id"]

    from_schedule = client.post(
        f"/api/locations/{location['id']}/schedules/ai-draft",
        json={
            "target_week_start_date": "2026-07-27",
            "source_schedule_id": first_schedule_id,
            "auto_assign_open_shifts": True,
            "assignment_strategy": "balance_hours",
        },
    )
    assert from_schedule.status_code == 200
    schedule_payload = from_schedule.json()
    assert schedule_payload["basis_type"] == "schedule"
    assert schedule_payload["basis_schedule_id"] == first_schedule_id
    assert schedule_payload["generated_from_schedule"] is True
    assert schedule_payload["assignment_strategy"] == "balance_hours"
    assert schedule_payload["auto_assign_summary"]["assignment_strategy"] == "balance_hours"
    assert schedule_payload["schedule_view"]["summary"]["filled_shifts"] == 2

    draft_options = client.get(f"/api/locations/{location['id']}/schedule-draft-options")
    assert draft_options.status_code == 200
    assert draft_options.json()["can_generate_ai_draft"] is True
    assert draft_options.json()["latest_schedule"]["id"] == schedule_payload["schedule_id"]


def test_backfill_shifts_change_summary_and_message_preview_for_derived_schedule(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Derived Review Cafe",
            "manager_name": "Mira Lead",
            "manager_phone": "+13105550179",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker_one = client.post(
        "/api/workers",
        json={
            "name": "Taylor Cook",
            "phone": "+13105550180",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    worker_two = client.post(
        "/api/workers",
        json={
            "name": "Alex Cook",
            "phone": "+13105550181",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Derived Review Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]

    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": worker_one["id"],
                    "assignment_status": "assigned",
                },
                {
                    "day_of_week": 1,
                    "role": "dishwasher",
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                },
            ]
        },
    )
    assert seeded.status_code == 200

    source_schedule = client.post(
        f"/api/locations/{location['id']}/schedules/create-from-template",
        json={
            "template_id": template_id,
            "target_week_start_date": "2026-08-03",
        },
    )
    assert source_schedule.status_code == 200
    source_schedule_id = source_schedule.json()["schedule_id"]

    derived_schedule = client.post(
        f"/api/locations/{location['id']}/schedules/ai-draft",
        json={
            "target_week_start_date": "2026-08-10",
            "source_schedule_id": source_schedule_id,
            "auto_assign_open_shifts": False,
        },
    )
    assert derived_schedule.status_code == 200
    derived_payload = derived_schedule.json()
    schedule_id = derived_payload["schedule_id"]
    shifts = derived_payload["schedule_view"]["shifts"]
    assigned_shift = next(
        shift for shift in shifts if (shift["assignment"] or {}).get("worker_id") == worker_one["id"]
    )
    open_shift = next(
        shift for shift in shifts if (shift["assignment"] or {}).get("worker_id") is None
    )

    reassign = client.patch(
        f"/api/shifts/{assigned_shift['id']}/assignment",
        json={
            "worker_id": worker_two["id"],
            "assignment_status": "assigned",
        },
    )
    assert reassign.status_code == 200

    edit_role = client.patch(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "shift_ids": [open_shift["id"]],
            "role": "prep_cook",
        },
    )
    assert edit_role.status_code == 200

    created_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "cashier",
            "date": "2026-08-12",
            "start_time": "11:00:00",
            "end_time": "15:00:00",
        },
    )
    assert created_shift.status_code == 200

    change_summary = client.get(f"/api/schedules/{schedule_id}/change-summary")
    assert change_summary.status_code == 200
    change_payload = change_summary.json()
    assert change_payload["change_summary"]["basis"]["basis_type"] == "derived_schedule"
    assert change_payload["change_summary"]["summary"]["added_shift_count"] == 1
    assert change_payload["change_summary"]["summary"]["reassigned_count"] == 1
    assert change_payload["change_summary"]["summary"]["role_change_count"] == 1
    codes = {item["code"] for item in change_payload["change_summary"]["changes"]}
    assert {"shift_added", "assignment_changed", "role_changed"} <= codes
    assert "1 shift added" in change_payload["change_summary"]["highlights"]
    assert "1 reassignment" in change_payload["review_summary"]["change_highlights"]
    assert change_payload["review_summary"]["recommended_action"] == "review_before_publish"
    assert change_payload["review_summary"]["review_item_count"] == 2

    message_preview = client.get(f"/api/schedules/{schedule_id}/message-preview")
    assert message_preview.status_code == 200
    preview_payload = message_preview.json()["message_preview"]
    assert preview_payload["review_link"].endswith(
        f"/dashboard/locations/{location['id']}?tab=schedule&week_start=2026-08-10"
    )
    assert preview_payload["publish_mode"] == "initial"
    assert "2 need review" in preview_payload["draft_ready"]
    assert "1 employee received their schedule" in preview_payload["publish_success"]
    assert preview_payload["publish_blocked"] is None

    rationale = client.get(f"/api/schedules/{schedule_id}/draft-rationale")
    assert rationale.status_code == 200
    rationale_payload = rationale.json()["draft_rationale"]
    assert rationale_payload["origin_type"] == "schedule"
    assert rationale_payload["origin_reference"]["schedule_id"] == source_schedule_id
    assert "2026-08-03" in rationale_payload["narrative"]
    assert change_payload["review_summary"]["publish_impact_summary"]["added_to_target_count"] == 1
    assert change_payload["review_summary"]["publish_impact_summary"]["new_assignment_count"] == 1
    assert preview_payload["worker_update_count"] == 1


def test_backfill_shifts_change_summary_uses_latest_published_version_baseline(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Published Diff Cafe",
            "manager_name": "Mira Lead",
            "manager_phone": "+13105550182",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker_one = client.post(
        "/api/workers",
        json={
            "name": "Bailey Cook",
            "phone": "+13105550183",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    worker_two = client.post(
        "/api/workers",
        json={
            "name": "Morgan Cook",
            "phone": "+13105550184",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Published Diff Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]
    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": worker_one["id"],
                    "assignment_status": "assigned",
                }
            ]
        },
    )
    assert seeded.status_code == 200

    created = client.post(
        f"/api/locations/{location['id']}/schedules/create-from-template",
        json={
            "template_id": template_id,
            "target_week_start_date": "2026-08-17",
        },
    )
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]

    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    shift_id = created.json()["schedule_view"]["shifts"][0]["id"]
    amended = client.patch(
        f"/api/shifts/{shift_id}/assignment",
        json={
            "worker_id": worker_two["id"],
            "assignment_status": "assigned",
        },
    )
    assert amended.status_code == 200

    change_summary = client.get(f"/api/schedules/{schedule_id}/change-summary")
    assert change_summary.status_code == 200
    payload = change_summary.json()
    assert payload["change_summary"]["basis"]["basis_type"] == "published_version"
    assert payload["publish_diff"]["basis"]["basis_type"] == "last_published_version"
    assert payload["change_summary"]["summary"]["reassigned_count"] == 1
    assert payload["change_summary"]["summary"]["total_change_count"] == 1
    assert payload["change_summary"]["changes"][0]["code"] == "assignment_changed"
    assert "1 reassignment" in payload["change_summary"]["highlights"]
    assert payload["review_summary"]["headline"] == "Schedule is ready to publish."
    assert payload["review_summary"]["recommended_action"] == "approve_by_text"
    assert payload["review_summary"]["draft_rationale"]["origin_type"] == "template"
    assert payload["review_summary"]["publish_impact_summary"] == {
        "target_worker_count": 1,
        "basis_worker_count": 1,
        "affected_worker_count": 2,
        "added_to_target_count": 1,
        "removed_from_target_count": 1,
        "updated_in_both_count": 0,
        "unchanged_worker_count": 0,
        "workers_with_schedule_update_count": 1,
        "workers_removed_from_schedule_count": 1,
        "new_assignment_count": 1,
        "changed_shift_count": 0,
        "added_shift_only_count": 0,
        "removed_shift_only_count": 0,
    }

    preview = client.get(f"/api/schedules/{schedule_id}/message-preview")
    assert preview.status_code == 200
    preview_payload = preview.json()["message_preview"]
    assert preview_payload["publish_mode"] == "update"
    assert preview_payload["worker_update_count"] == 1
    assert "Reply APPROVE to publish or REVIEW to edit" in preview_payload["draft_ready"]
    assert "Published your schedule updates for Aug 17-23." in preview_payload["publish_success"]
    assert "1 reassignment" in preview_payload["publish_success"]
    assert "1 employee was told they are no longer scheduled." in preview_payload["publish_success"]
    assert preview_payload["publish_blocked"] is None

    publish_diff = client.get(f"/api/schedules/{schedule_id}/publish-diff")
    assert publish_diff.status_code == 200
    publish_diff_payload = publish_diff.json()["publish_diff"]
    assert publish_diff_payload["basis"]["basis_type"] == "last_published_version"
    assert publish_diff_payload["summary"]["reassigned_count"] == 1
    assert publish_diff_payload["summary"]["has_changes"] is True
    assert publish_diff_payload["worker_impact"]["summary"] == {
        "target_worker_count": 1,
        "basis_worker_count": 1,
        "affected_worker_count": 2,
        "added_to_target_count": 1,
        "removed_from_target_count": 1,
        "updated_in_both_count": 0,
        "unchanged_worker_count": 0,
        "workers_with_schedule_update_count": 1,
        "workers_removed_from_schedule_count": 1,
        "new_assignment_count": 1,
        "changed_shift_count": 0,
        "added_shift_only_count": 0,
        "removed_shift_only_count": 0,
    }

    publish_impact = client.get(f"/api/schedules/{schedule_id}/publish-impact")
    assert publish_impact.status_code == 200
    assert publish_impact.json()["worker_impact"]["delivery_estimate"] == {
        "current_delivery": {
            "worker_count": 1,
            "sms_enrolled_count": 1,
            "not_enrolled_count": 0,
            "unreachable_count": 0,
        },
        "changed_workers_only": {
            "worker_count": 1,
            "sms_enrolled_count": 1,
            "not_enrolled_count": 0,
            "unreachable_count": 0,
        },
    }

    versions = client.get(f"/api/schedules/{schedule_id}/versions")
    assert versions.status_code == 200
    versions_payload = versions.json()["versions"]
    assert [item["version_type"] for item in versions_payload] == [
        "draft_snapshot",
        "publish_snapshot",
        "amendment_snapshot",
    ]
    assert versions_payload[2]["event_label"] == "Draft amended"
    assert versions_payload[2]["diff_summary"]["reassigned_count"] == 1
    assert versions_payload[2]["impact_summary"]["reassignment_count"] == 1
    assert versions_payload[2]["worker_impact_summary"]["affected_worker_count"] == 2
    assert versions_payload[2]["worker_impact_summary"]["new_assignment_count"] == 1
    assert versions_payload[2]["is_current_version"] is True
    assert versions_payload[1]["is_current_version"] is False
    assert versions_payload[1]["compare_to_current_available"] is True

    version_diff = client.get(
        f"/api/schedules/{schedule_id}/versions/{versions_payload[1]['id']}/diff?compare_to=previous_publish"
    )
    assert version_diff.status_code == 200
    first_publish_diff = version_diff.json()["version_diff"]
    assert first_publish_diff["compare_mode"] == "first_publish"
    assert first_publish_diff["first_publish"] is True
    assert first_publish_diff["event_label"] == "Schedule published"

    amendment_diff = client.get(
        f"/api/schedules/{schedule_id}/versions/{versions_payload[2]['id']}/diff?compare_to=previous"
    )
    assert amendment_diff.status_code == 200
    amendment_diff_payload = amendment_diff.json()["version_diff"]
    assert amendment_diff_payload["compare_mode"] == "previous"
    assert amendment_diff_payload["summary"]["reassigned_count"] == 1
    assert amendment_diff_payload["impact_summary"]["reassignment_count"] == 1

    current_compare = client.get(
        f"/api/schedules/{schedule_id}/versions/{versions_payload[1]['id']}/diff?compare_to=current"
    )
    assert current_compare.status_code == 200
    current_compare_payload = current_compare.json()["version_diff"]
    assert current_compare_payload["compare_mode"] == "current"
    assert current_compare_payload["worker_impact"]["summary"] == {
        "target_worker_count": 1,
        "basis_worker_count": 1,
        "affected_worker_count": 2,
        "added_to_target_count": 1,
        "removed_from_target_count": 1,
        "updated_in_both_count": 0,
        "unchanged_worker_count": 0,
        "workers_with_schedule_update_count": 1,
        "workers_removed_from_schedule_count": 1,
        "new_assignment_count": 1,
        "changed_shift_count": 0,
        "added_shift_only_count": 0,
        "removed_shift_only_count": 0,
    }


def test_backfill_shifts_import_supports_overnight_shift(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Overnight Diner",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550145",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Terry Cook,+13105550146,night_cook,2026-04-18,22:00,06:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)

    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    assert mapped.json()["status"] == "validating"

    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    assert committed.json()["created_shifts"] == 1

    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current_schedule.status_code == 200
    shift = current_schedule.json()["shifts"][0]
    assert shift["start_time"] == "22:00:00"
    assert shift["end_time"] == "06:00:00"
    assert shift["spans_midnight"] is True


def test_backfill_shifts_schedule_recall_and_archive_lifecycle(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Lifecycle Bistro",
            "manager_name": "Kai Lead",
            "manager_phone": "+13105550147",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Nora Cook,+13105550148,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]

    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200
    assert published.json()["lifecycle_state"] == "published"

    recalled = client.post(f"/api/schedules/{schedule_id}/recall")
    assert recalled.status_code == 200
    assert recalled.json()["lifecycle_state"] == "recalled"

    republished = client.post(f"/api/schedules/{schedule_id}/publish")
    assert republished.status_code == 200
    assert republished.json()["lifecycle_state"] == "published"

    archived = client.post(f"/api/schedules/{schedule_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["lifecycle_state"] == "archived"

    create_after_archive = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "12:00:00",
            "end_time": "20:00:00",
        },
    )
    assert create_after_archive.status_code == 400
    assert "read-only" in create_after_archive.json()["detail"]


def test_backfill_shifts_publish_notifies_manager(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM123",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Publish Prompt Deli",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550155",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Terry Cook,+13105550156,night_cook,2026-04-18,22:00,06:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    sent.clear()

    published = client.post(f"/api/schedules/{committed.json()['schedule_id']}/publish")
    assert published.status_code == 200
    assert published.json()["delivery_summary"]["sms_sent"] == 0
    assert published.json()["delivery_summary"]["not_enrolled"] == 1

    assert sent == [
        (
            "+13105550155",
            "Backfill: Published. Your team has been notified. 0 employees received their schedule. 1 still needs to opt in to SMS.",
        )
    ]


def test_backfill_shifts_publish_sends_worker_schedule_sms(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM123",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Delivery Prompt Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550157",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker = client.post(
        "/api/workers",
        json={
            "name": "Terry Cook",
            "phone": "+13105550158",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert worker.status_code == 201

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Terry Cook,+13105550158,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    sent.clear()

    published = client.post(f"/api/schedules/{committed.json()['schedule_id']}/publish")
    assert published.status_code == 200
    published_payload = published.json()
    assert published_payload["delivery_summary"]["eligible_workers"] == 1
    assert published_payload["delivery_summary"]["sms_sent"] == 1
    assert published_payload["delivery_summary"]["not_enrolled"] == 0
    assert published_payload["delivery_summary"]["sms_failed"] == 0

    assert sent == [
        (
            "+13105550158",
            "Backfill: Terry Cook, your schedule at Delivery Prompt Cafe for Apr 13-19: Tue Apr 14 09:00-17:00 line_cook. We'll text reminders before your shift. Reply STOP to opt out.",
        ),
        (
            "+13105550157",
            "Backfill: Published. Your team has been notified. 1 employee received their schedule. 0 still need to opt in to SMS.",
        ),
    ]


def test_backfill_shifts_amended_publish_notifies_manager_with_change_summary(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM123",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Amendment Prompt Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550159",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker_one = client.post(
        "/api/workers",
        json={
            "name": "Jamie Cook",
            "phone": "+13105550160",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    worker_two = client.post(
        "/api/workers",
        json={
            "name": "Parker Cook",
            "phone": "+13105550161",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Amendment Prompt Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]
    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": worker_one["id"],
                    "assignment_status": "assigned",
                }
            ]
        },
    )
    assert seeded.status_code == 200

    created = client.post(
        f"/api/locations/{location['id']}/schedules/create-from-template",
        json={
            "template_id": template_id,
            "target_week_start_date": "2026-08-24",
        },
    )
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]
    shift_id = created.json()["schedule_view"]["shifts"][0]["id"]

    first_publish = client.post(f"/api/schedules/{schedule_id}/publish")
    assert first_publish.status_code == 200
    sent.clear()

    amended = client.patch(
        f"/api/shifts/{shift_id}/assignment",
        json={
            "worker_id": worker_two["id"],
            "assignment_status": "assigned",
        },
    )
    assert amended.status_code == 200

    republished = client.post(f"/api/schedules/{schedule_id}/publish")
    assert republished.status_code == 200
    assert republished.json()["publish_diff"]["summary"]["reassigned_count"] == 1
    assert republished.json()["delivery_summary"] == {
        "eligible_workers": 2,
        "sms_sent": 1,
        "sms_removed_sent": 1,
        "not_enrolled": 0,
        "sms_failed": 0,
        "changed_worker_count": 1,
        "removed_worker_count": 1,
        "unchanged_worker_count": 0,
        "skipped_unchanged_workers": 0,
    }

    assert sent == [
        (
            "+13105550161",
            "Backfill: Parker Cook, you're now scheduled at Amendment Prompt Cafe for Aug 24-30: Mon Aug 24 08:00-16:00 line_cook. We'll text reminders before your shift. Reply HELP if this looks wrong.",
        ),
        (
            "+13105550160",
            "Backfill: Jamie Cook, your schedule at Amendment Prompt Cafe for Aug 24-30 was updated. You're no longer scheduled for: Mon Aug 24 08:00-16:00 line_cook. Reply HELP if this looks wrong.",
        ),
        (
            "+13105550159",
            "Backfill: Published your schedule updates for Aug 24-30. 1 reassignment. 1 employee received updated shifts. 1 employee was told they are no longer scheduled. 0 still need to opt in to SMS.",
        ),
    ]


def test_backfill_shifts_amended_publish_notifies_only_changed_workers(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM123",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Selective Update Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550162",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    changed_worker = client.post(
        "/api/workers",
        json={
            "name": "Casey Cook",
            "phone": "+13105550163",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    replacement_worker = client.post(
        "/api/workers",
        json={
            "name": "Skyler Cook",
            "phone": "+13105550164",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    unchanged_worker = client.post(
        "/api/workers",
        json={
            "name": "Riley Cook",
            "phone": "+13105550165",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Selective Update Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]
    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": changed_worker["id"],
                    "assignment_status": "assigned",
                },
                {
                    "day_of_week": 1,
                    "role": "dishwasher",
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                    "worker_id": unchanged_worker["id"],
                    "assignment_status": "assigned",
                },
            ]
        },
    )
    assert seeded.status_code == 200

    created = client.post(
        f"/api/locations/{location['id']}/schedules/create-from-template",
        json={
            "template_id": template_id,
            "target_week_start_date": "2026-08-31",
        },
    )
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]
    shifts = created.json()["schedule_view"]["shifts"]
    changed_shift_id = next(
        shift["id"] for shift in shifts if shift["assignment"]["worker_id"] == changed_worker["id"]
    )

    first_publish = client.post(f"/api/schedules/{schedule_id}/publish")
    assert first_publish.status_code == 200
    sent.clear()

    amended = client.patch(
        f"/api/shifts/{changed_shift_id}/assignment",
        json={
            "worker_id": replacement_worker["id"],
            "assignment_status": "assigned",
        },
    )
    assert amended.status_code == 200

    republished = client.post(f"/api/schedules/{schedule_id}/publish")
    assert republished.status_code == 200
    assert republished.json()["delivery_summary"]["unchanged_worker_count"] == 1
    assert republished.json()["delivery_summary"]["skipped_unchanged_workers"] == 1

    assert sent == [
        (
            "+13105550164",
            "Backfill: Skyler Cook, you're now scheduled at Selective Update Cafe for Aug 31-Sep 6: Mon Aug 31 08:00-16:00 line_cook. We'll text reminders before your shift. Reply HELP if this looks wrong.",
        ),
        (
            "+13105550163",
            "Backfill: Casey Cook, your schedule at Selective Update Cafe for Aug 31-Sep 6 was updated. You're no longer scheduled for: Mon Aug 31 08:00-16:00 line_cook. Reply HELP if this looks wrong.",
        ),
        (
            "+13105550162",
            "Backfill: Published your schedule updates for Aug 31-Sep 6. 1 reassignment. 1 employee received updated shifts. 1 employee was told they are no longer scheduled. 0 still need to opt in to SMS.",
        ),
    ]


def test_backfill_shifts_amended_publish_sends_specific_changed_shift_message(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM123",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Changed Shift Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550166",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker = client.post(
        "/api/workers",
        json={
            "name": "Avery Cook",
            "phone": "+13105550167",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Changed Shift Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]
    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": worker["id"],
                    "assignment_status": "assigned",
                }
            ]
        },
    )
    assert seeded.status_code == 200

    created = client.post(
        f"/api/locations/{location['id']}/schedules/create-from-template",
        json={
            "template_id": template_id,
            "target_week_start_date": "2026-09-07",
        },
    )
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]
    shift_id = created.json()["schedule_view"]["shifts"][0]["id"]

    first_publish = client.post(f"/api/schedules/{schedule_id}/publish")
    assert first_publish.status_code == 200
    sent.clear()

    edited = client.patch(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "shift_ids": [shift_id],
            "start_time": "10:00:00",
            "end_time": "18:00:00",
        },
    )
    assert edited.status_code == 200

    republished = client.post(f"/api/schedules/{schedule_id}/publish")
    assert republished.status_code == 200
    assert republished.json()["publish_diff"]["worker_impact"]["summary"]["changed_shift_count"] == 1

    assert sent == [
        (
            "+13105550167",
            "Backfill: Avery Cook, your schedule at Changed Shift Cafe for Sep 7-13 was updated. Added: Mon Sep 7 10:00-18:00 line_cook. Removed: Mon Sep 7 08:00-16:00 line_cook. Current schedule: Mon Sep 7 10:00-18:00 line_cook. Reply HELP if this looks wrong.",
        ),
        (
            "+13105550166",
            "Backfill: Published your schedule updates for Sep 7-13. 1 timing change. 1 employee received updated shifts. 0 still need to opt in to SMS.",
        ),
    ]


def test_backfill_shifts_publish_preview_includes_initial_worker_messages(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Preview Launch Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550168",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    enrolled_worker = client.post(
        "/api/workers",
        json={
            "name": "Taylor Cook",
            "phone": "+13105550169",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    pending_worker = client.post(
        "/api/workers",
        json={
            "name": "Jordan Cook",
            "phone": "+13105550170",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "pending",
            "voice_consent_status": "granted",
        },
    ).json()
    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Preview Launch Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]
    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": enrolled_worker["id"],
                    "assignment_status": "assigned",
                },
                {
                    "day_of_week": 1,
                    "role": "dishwasher",
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                    "worker_id": pending_worker["id"],
                    "assignment_status": "assigned",
                },
            ]
        },
    )
    assert seeded.status_code == 200

    created = client.post(
        f"/api/locations/{location['id']}/schedules/create-from-template",
        json={
            "template_id": template_id,
            "target_week_start_date": "2026-09-14",
        },
    )
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]

    preview = client.get(f"/api/schedules/{schedule_id}/publish-preview")
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["publish_preview"]["publish_mode"] == "initial"
    assert payload["publish_preview"]["manager_message_preview"]["publish_success"] == (
        "Backfill: Published. Your team has been notified. "
        "1 employee received their schedule. 1 still needs to opt in to SMS."
    )
    assert payload["publish_preview"]["delivery_estimate"] == {
        "eligible_workers": 2,
        "sms_sent": 1,
        "sms_removed_sent": 0,
        "not_enrolled": 1,
        "unreachable_count": 0,
        "changed_worker_count": 2,
        "removed_worker_count": 0,
        "unchanged_worker_count": 0,
        "skipped_unchanged_workers": 0,
    }
    previews_by_name = {
        item["worker_name"]: item for item in payload["publish_preview"]["worker_message_previews"]
    }
    assert previews_by_name["Taylor Cook"]["message_type"] == "schedule_published"
    assert previews_by_name["Taylor Cook"]["delivery_status"] == "will_send"
    assert previews_by_name["Taylor Cook"]["message_body"] == (
        "Backfill: Taylor Cook, your schedule at Preview Launch Cafe for Sep 14-20: "
        "Mon Sep 14 08:00-16:00 line_cook. "
        "We'll text reminders before your shift. Reply STOP to opt out."
    )
    assert previews_by_name["Jordan Cook"]["message_type"] == "schedule_published"
    assert previews_by_name["Jordan Cook"]["delivery_status"] == "not_enrolled"
    assert previews_by_name["Jordan Cook"]["message_body"] == (
        "Backfill: Jordan Cook, your schedule at Preview Launch Cafe for Sep 14-20: "
        "Tue Sep 15 09:00-17:00 dishwasher. "
        "We'll text reminders before your shift. Reply STOP to opt out."
    )


def test_backfill_shifts_publish_preview_includes_changed_removed_and_skipped_workers(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Preview Selective Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550171",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    changed_worker = client.post(
        "/api/workers",
        json={
            "name": "Casey Cook",
            "phone": "+13105550172",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    replacement_worker = client.post(
        "/api/workers",
        json={
            "name": "Skyler Cook",
            "phone": "+13105550173",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    unchanged_worker = client.post(
        "/api/workers",
        json={
            "name": "Riley Cook",
            "phone": "+13105550174",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Preview Selective Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]
    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": changed_worker["id"],
                    "assignment_status": "assigned",
                },
                {
                    "day_of_week": 1,
                    "role": "dishwasher",
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                    "worker_id": unchanged_worker["id"],
                    "assignment_status": "assigned",
                },
            ]
        },
    )
    assert seeded.status_code == 200

    created = client.post(
        f"/api/locations/{location['id']}/schedules/create-from-template",
        json={
            "template_id": template_id,
            "target_week_start_date": "2026-09-21",
        },
    )
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]
    shifts = created.json()["schedule_view"]["shifts"]
    changed_shift_id = next(
        shift["id"] for shift in shifts if shift["assignment"]["worker_id"] == changed_worker["id"]
    )

    first_publish = client.post(f"/api/schedules/{schedule_id}/publish")
    assert first_publish.status_code == 200

    amended = client.patch(
        f"/api/shifts/{changed_shift_id}/assignment",
        json={
            "worker_id": replacement_worker["id"],
            "assignment_status": "assigned",
        },
    )
    assert amended.status_code == 200

    preview = client.get(f"/api/schedules/{schedule_id}/publish-preview")
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["publish_preview"]["publish_mode"] == "update"
    assert payload["publish_preview"]["manager_message_preview"]["publish_success"] == (
        "Backfill: Published your schedule updates for Sep 21-27. "
        "1 reassignment. 1 employee received updated shifts. "
        "1 employee was told they are no longer scheduled. 0 still need to opt in to SMS."
    )
    assert payload["publish_preview"]["delivery_estimate"] == {
        "eligible_workers": 2,
        "sms_sent": 1,
        "sms_removed_sent": 1,
        "not_enrolled": 0,
        "unreachable_count": 0,
        "changed_worker_count": 1,
        "removed_worker_count": 1,
        "unchanged_worker_count": 1,
        "skipped_unchanged_workers": 1,
    }
    previews_by_name = {
        item["worker_name"]: item for item in payload["publish_preview"]["worker_message_previews"]
    }
    assert previews_by_name["Skyler Cook"]["message_type"] == "schedule_added"
    assert previews_by_name["Skyler Cook"]["delivery_status"] == "will_send"
    assert previews_by_name["Skyler Cook"]["message_body"] == (
        "Backfill: Skyler Cook, you're now scheduled at Preview Selective Cafe for Sep 21-27: "
        "Mon Sep 21 08:00-16:00 line_cook. "
        "We'll text reminders before your shift. Reply HELP if this looks wrong."
    )
    assert previews_by_name["Casey Cook"]["message_type"] == "schedule_removed"
    assert previews_by_name["Casey Cook"]["delivery_status"] == "will_send"
    assert previews_by_name["Casey Cook"]["message_body"] == (
        "Backfill: Casey Cook, your schedule at Preview Selective Cafe for Sep 21-27 was updated. "
        "You're no longer scheduled for: Mon Sep 21 08:00-16:00 line_cook. "
        "Reply HELP if this looks wrong."
    )
    assert previews_by_name["Riley Cook"]["delivery_status"] == "skipped_unchanged"
    assert previews_by_name["Riley Cook"]["message_type"] is None
    assert previews_by_name["Riley Cook"]["message_body"] is None


def test_backfill_shifts_publish_preview_includes_changed_shift_message(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Preview Changed Shift Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550175",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker = client.post(
        "/api/workers",
        json={
            "name": "Avery Cook",
            "phone": "+13105550176",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Preview Changed Shift Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]
    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": worker["id"],
                    "assignment_status": "assigned",
                }
            ]
        },
    )
    assert seeded.status_code == 200

    created = client.post(
        f"/api/locations/{location['id']}/schedules/create-from-template",
        json={
            "template_id": template_id,
            "target_week_start_date": "2026-09-28",
        },
    )
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]
    shift_id = created.json()["schedule_view"]["shifts"][0]["id"]

    first_publish = client.post(f"/api/schedules/{schedule_id}/publish")
    assert first_publish.status_code == 200

    edited = client.patch(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "shift_ids": [shift_id],
            "start_time": "10:00:00",
            "end_time": "18:00:00",
        },
    )
    assert edited.status_code == 200

    preview = client.get(f"/api/schedules/{schedule_id}/publish-preview")
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["publish_preview"]["publish_mode"] == "update"
    assert payload["publish_preview"]["delivery_estimate"] == {
        "eligible_workers": 1,
        "sms_sent": 1,
        "sms_removed_sent": 0,
        "not_enrolled": 0,
        "unreachable_count": 0,
        "changed_worker_count": 1,
        "removed_worker_count": 0,
        "unchanged_worker_count": 0,
        "skipped_unchanged_workers": 0,
    }
    worker_preview = payload["publish_preview"]["worker_message_previews"][0]
    assert worker_preview["worker_name"] == "Avery Cook"
    assert worker_preview["message_type"] == "schedule_changed"
    assert worker_preview["delivery_status"] == "will_send"
    assert worker_preview["message_body"] == (
        "Backfill: Avery Cook, your schedule at Preview Changed Shift Cafe for Sep 28-Oct 4 was updated. "
        "Added: Mon Sep 28 10:00-18:00 line_cook. "
        "Removed: Mon Sep 28 08:00-16:00 line_cook. "
        "Current schedule: Mon Sep 28 10:00-18:00 line_cook. "
        "Reply HELP if this looks wrong."
    )


def test_backfill_shifts_schedule_shift_create_and_delete_are_schedule_aware(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Grid Ops Cafe",
            "manager_name": "Mina Lead",
            "manager_phone": "+13105550149",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Luis Cook,+13105550150,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]

    created_draft_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "prep_cook",
            "date": "2026-04-15",
            "start_time": "10:00:00",
            "end_time": "18:00:00",
            "notes": "Draft-added shift",
        },
    )
    assert created_draft_shift.status_code == 200
    draft_payload = created_draft_shift.json()
    assert draft_payload["schedule_lifecycle_state"] == "draft"
    assert draft_payload["assignment"]["assignment_status"] == "open"

    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    created_published_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-16",
            "start_time": "12:00:00",
            "end_time": "20:00:00",
        },
    )
    assert created_published_shift.status_code == 200
    published_payload = created_published_shift.json()
    assert published_payload["schedule_lifecycle_state"] == "amended"

    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current_schedule.status_code == 200
    assert len(current_schedule.json()["shifts"]) == 3

    deleted = client.delete(f"/api/shifts/{published_payload['shift']['id']}")
    assert deleted.status_code == 200
    deleted_payload = deleted.json()
    assert deleted_payload["deleted"] is True
    assert deleted_payload["schedule_lifecycle_state"] == "amended"

    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current_schedule.status_code == 200
    remaining_shift_ids = {shift["id"] for shift in current_schedule.json()["shifts"]}
    assert published_payload["shift"]["id"] not in remaining_shift_ids
    assert len(remaining_shift_ids) == 2


def test_backfill_shifts_create_shift_can_auto_offer_open_shift(client, monkeypatch):
    worker_offers = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Auto Offer Cafe",
            "manager_name": "Mina Lead",
            "manager_phone": "+13105550160",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker = client.post(
        "/api/workers",
        json={
            "name": "Jordan Cover",
            "phone": "+13105550161",
            "roles": ["dishwasher", "line_cook"],
            "priority_rank": 1,
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert worker.status_code == 201

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Jordan Cover,+13105550161,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]

    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    created = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
            "start_open_shift_offer": True,
        },
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["schedule_lifecycle_state"] == "amended"
    assert payload["shift"]["status"] == "vacant"
    assert payload["assignment"]["assignment_status"] == "open"
    assert payload["coverage"]["status"] == "active"
    assert payload["offer_result"]["status"] == "coverage_started"
    assert len(worker_offers) == 1
    assert worker_offers[0][0] == "+13105550161"
    assert "open shift available at auto offer cafe" in worker_offers[0][1].lower()


def test_backfill_shifts_batch_offer_open_shifts(client, monkeypatch):
    worker_offers = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Batch Offer Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550164",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    assigned_worker = client.post(
        "/api/workers",
        json={
            "name": "Assigned Cook",
            "phone": "+13105550165",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert assigned_worker.status_code == 201
    candidate = client.post(
        "/api/workers",
        json={
            "name": "Offer Cook",
            "phone": "+13105550166",
            "roles": ["dishwasher", "prep_cook"],
            "priority_rank": 1,
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert candidate.status_code == 201

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Assigned Cook,+13105550165,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    open_shift_one = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    open_shift_two = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "prep_cook",
            "date": "2026-04-16",
            "start_time": "10:00:00",
            "end_time": "18:00:00",
        },
    )
    assert open_shift_one.status_code == 200
    assert open_shift_two.status_code == 200

    started_direct = client.post(f"/api/shifts/{open_shift_one.json()['shift']['id']}/coverage/start")
    assert started_direct.status_code == 200

    offered = client.post(
        f"/api/schedules/{schedule_id}/offer-open-shifts",
        json={},
    )
    assert offered.status_code == 200
    payload = offered.json()
    assert payload["schedule_id"] == schedule_id
    assert payload["week_start_date"] == "2026-04-13"
    assert payload["summary"] == {
        "requested": 2,
        "started": 1,
        "already_active": 1,
        "skipped_assigned": 1,
        "skipped_not_open": 0,
    }
    assert [item["status"] for item in payload["results"]] == [
        "skipped_assigned",
        "coverage_active",
        "coverage_started",
    ]
    assert payload["review_link"].endswith(
        f"/dashboard/locations/{location['id']}?tab=coverage&week_start=2026-04-13"
    )
    assert len(worker_offers) == 2
    assert all("open shift available at batch offer cafe" in body.lower() for _, body, _ in worker_offers)


def test_backfill_shifts_can_reopen_closed_open_shift(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Reopen Shift Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550168",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Assigned Cook,+13105550169,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    open_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    assert open_shift.status_code == 200
    shift_id = open_shift.json()["shift"]["id"]
    assert open_shift.json()["available_actions"] == ["start_coverage", "close_shift"]

    closed = client.post(f"/api/shifts/{shift_id}/open-shift/close")
    assert closed.status_code == 200
    assert closed.json()["available_actions"] == ["reopen_shift", "reopen_and_offer"]

    reopened = client.post(f"/api/shifts/{shift_id}/open-shift/reopen")
    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )

    assert reopened.status_code == 200
    assert reopened.json()["status"] == "reopened"
    assert reopened.json()["assignment"]["assignment_status"] == "open"
    assert reopened.json()["coverage"]["status"] == "none"
    assert reopened.json()["available_actions"] == ["start_coverage", "close_shift"]
    assert current_schedule.status_code == 200
    reopened_shift = next(shift for shift in current_schedule.json()["shifts"] if shift["id"] == shift_id)
    assert reopened_shift["assignment"]["assignment_status"] == "open"
    assert reopened_shift["coverage"]["status"] == "none"
    assert reopened_shift["available_actions"] == ["start_coverage", "close_shift"]
    assert current_schedule.json()["summary"]["open_shifts"] == 1


def test_backfill_shifts_can_reopen_closed_open_shift_and_start_offer(client, monkeypatch):
    worker_offers = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Reopen Offer Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550170",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    candidate = client.post(
        "/api/workers",
        json={
            "name": "Offer Cook",
            "phone": "+13105550171",
            "roles": ["dishwasher"],
            "priority_rank": 1,
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert candidate.status_code == 201

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Assigned Cook,+13105550172,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    open_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    assert open_shift.status_code == 200
    shift_id = open_shift.json()["shift"]["id"]

    closed = client.post(f"/api/shifts/{shift_id}/open-shift/close")
    assert closed.status_code == 200

    reopened = client.post(
        f"/api/shifts/{shift_id}/open-shift/reopen?start_open_shift_offer=true"
    )
    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )

    assert reopened.status_code == 200
    assert reopened.json()["status"] == "coverage_started"
    assert reopened.json()["reopened"] is True
    assert current_schedule.status_code == 200
    reopened_shift = next(shift for shift in current_schedule.json()["shifts"] if shift["id"] == shift_id)
    assert reopened_shift["status"] == "vacant"
    assert reopened_shift["coverage"]["status"] == "active"
    assert reopened_shift["available_actions"] == ["cancel_offer", "close_shift"]
    assert len(worker_offers) == 1
    assert worker_offers[0][0] == "+13105550171"
    assert "open shift available at reopen offer cafe" in worker_offers[0][1].lower()


def test_backfill_shifts_bulk_shift_actions_can_close_and_report_errors(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Bulk Action Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550173",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Assigned Cook,+13105550174,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    open_shift_one = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    open_shift_two = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "prep_cook",
            "date": "2026-04-16",
            "start_time": "10:00:00",
            "end_time": "18:00:00",
        },
    )
    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )

    assert open_shift_one.status_code == 200
    assert open_shift_two.status_code == 200
    assert current_schedule.status_code == 200
    assigned_shift_id = next(
        shift["id"]
        for shift in current_schedule.json()["shifts"]
        if shift["assignment"]["worker_id"] is not None
    )

    acted = client.post(
        f"/api/schedules/{schedule_id}/shifts/actions",
        json={
            "shift_ids": [
                open_shift_one.json()["shift"]["id"],
                assigned_shift_id,
                open_shift_two.json()["shift"]["id"],
            ],
            "action": "close_shift",
        },
    )

    assert acted.status_code == 200
    payload = acted.json()
    assert payload["schedule_id"] == schedule_id
    assert payload["action"] == "close_shift"
    assert payload["processed_count"] == 3
    assert payload["success_count"] == 2
    assert payload["error_count"] == 1
    assert [item["status"] for item in payload["results"]] == ["ok", "error", "ok"]
    assert payload["results"][1]["error"] == "action_not_allowed"
    assert payload["results"][1]["available_actions"] == []
    assert payload["schedule_view"]["summary"]["open_shifts"] == 0
    closed_shifts = [
        shift
        for shift in payload["schedule_view"]["shifts"]
        if shift["id"] in {open_shift_one.json()["shift"]["id"], open_shift_two.json()["shift"]["id"]}
    ]
    assert all(shift["assignment"]["assignment_status"] == "closed" for shift in closed_shifts)
    assert all(shift["coverage"]["status"] == "closed" for shift in closed_shifts)
    assert all(shift["available_actions"] == ["reopen_shift", "reopen_and_offer"] for shift in closed_shifts)


def test_backfill_shifts_bulk_shift_actions_can_reopen_and_offer_closed_shifts(client, monkeypatch):
    worker_offers = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Bulk Reopen Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550175",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    candidate = client.post(
        "/api/workers",
        json={
            "name": "Offer Cook",
            "phone": "+13105550176",
            "roles": ["dishwasher", "prep_cook"],
            "priority_rank": 1,
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert candidate.status_code == 201

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Assigned Cook,+13105550177,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    open_shift_one = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    open_shift_two = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "prep_cook",
            "date": "2026-04-16",
            "start_time": "10:00:00",
            "end_time": "18:00:00",
        },
    )
    assert open_shift_one.status_code == 200
    assert open_shift_two.status_code == 200

    close_one = client.post(f"/api/shifts/{open_shift_one.json()['shift']['id']}/open-shift/close")
    close_two = client.post(f"/api/shifts/{open_shift_two.json()['shift']['id']}/open-shift/close")
    assert close_one.status_code == 200
    assert close_two.status_code == 200

    acted = client.post(
        f"/api/schedules/{schedule_id}/shifts/actions",
        json={
            "shift_ids": [
                open_shift_one.json()["shift"]["id"],
                open_shift_two.json()["shift"]["id"],
            ],
            "action": "reopen_and_offer",
        },
    )

    assert acted.status_code == 200
    payload = acted.json()
    assert payload["processed_count"] == 2
    assert payload["success_count"] == 2
    assert payload["error_count"] == 0
    assert [item["status"] for item in payload["results"]] == ["ok", "ok"]
    assert all(item["result"]["status"] == "coverage_started" for item in payload["results"])
    reopened_shifts = [
        shift
        for shift in payload["schedule_view"]["shifts"]
        if shift["id"] in {open_shift_one.json()["shift"]["id"], open_shift_two.json()["shift"]["id"]}
    ]
    assert all(shift["status"] == "vacant" for shift in reopened_shifts)
    assert all(shift["coverage"]["status"] == "active" for shift in reopened_shifts)
    assert all(shift["available_actions"] == ["cancel_offer", "close_shift"] for shift in reopened_shifts)
    assert len(worker_offers) == 2
    assert all("open shift available at bulk reopen cafe" in body.lower() for _, body, _ in worker_offers)


def test_backfill_shifts_bulk_assignments_can_assign_and_clear_shifts(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Bulk Assignment Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550178",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    assigned_worker = client.post(
        "/api/workers",
        json={
            "name": "Assigned Cook",
            "phone": "+13105550179",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    fill_worker = client.post(
        "/api/workers",
        json={
            "name": "Jordan Dish",
            "phone": "+13105550180",
            "roles": ["dishwasher"],
            "priority_rank": 1,
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert assigned_worker.status_code == 201
    assert fill_worker.status_code == 201

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Assigned Cook,+13105550179,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    open_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    assert open_shift.status_code == 200
    open_shift_id = open_shift.json()["shift"]["id"]

    before = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert before.status_code == 200
    assigned_shift_id = next(
        shift["id"]
        for shift in before.json()["shifts"]
        if shift["assignment"]["worker_id"] == assigned_worker.json()["id"]
    )

    updated = client.post(
        f"/api/schedules/{schedule_id}/shifts/assignments",
        json={
            "assignments": [
                {
                    "shift_id": open_shift_id,
                    "worker_id": fill_worker.json()["id"],
                    "notes": "Assigned from bulk grid",
                },
                {
                    "shift_id": assigned_shift_id,
                    "worker_id": None,
                    "notes": "Cleared from bulk grid",
                },
            ]
        },
    )

    assert updated.status_code == 200
    payload = updated.json()
    assert payload["schedule_id"] == schedule_id
    assert payload["processed_count"] == 2
    assert payload["success_count"] == 2
    assert payload["error_count"] == 0
    assert [item["status"] for item in payload["results"]] == ["ok", "ok"]

    open_shift_after = next(
        shift for shift in payload["schedule_view"]["shifts"] if shift["id"] == open_shift_id
    )
    cleared_shift_after = next(
        shift for shift in payload["schedule_view"]["shifts"] if shift["id"] == assigned_shift_id
    )
    assert open_shift_after["assignment"]["worker_id"] == fill_worker.json()["id"]
    assert open_shift_after["assignment"]["assignment_status"] == "assigned"
    assert open_shift_after["coverage"]["status"] == "none"
    assert open_shift_after["available_actions"] == []
    assert open_shift_after["notes"] == "Assigned from bulk grid"
    assert cleared_shift_after["assignment"]["worker_id"] is None
    assert cleared_shift_after["assignment"]["assignment_status"] == "open"
    assert cleared_shift_after["coverage"]["status"] == "none"
    assert cleared_shift_after["available_actions"] == ["start_coverage", "close_shift"]
    assert cleared_shift_after["notes"] == "Cleared from bulk grid"
    assert payload["schedule_view"]["summary"]["open_shifts"] == 1


def test_backfill_shifts_bulk_assignments_report_lifecycle_and_eligibility_errors(client, monkeypatch):
    worker_offers = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Assignment Guard Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550181",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    eligible_worker = client.post(
        "/api/workers",
        json={
            "name": "Eligible Cook",
            "phone": "+13105550182",
            "roles": ["dishwasher", "prep_cook"],
            "priority_rank": 1,
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    ineligible_worker = client.post(
        "/api/workers",
        json={
            "name": "Wrong Role",
            "phone": "+13105550183",
            "roles": ["cashier"],
            "priority_rank": 2,
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert eligible_worker.status_code == 201
    assert ineligible_worker.status_code == 201

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Assigned Cook,+13105550184,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    active_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    closed_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "prep_cook",
            "date": "2026-04-16",
            "start_time": "10:00:00",
            "end_time": "18:00:00",
        },
    )
    valid_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-17",
            "start_time": "09:00:00",
            "end_time": "17:00:00",
        },
    )
    assert active_shift.status_code == 200
    assert closed_shift.status_code == 200
    assert valid_shift.status_code == 200

    started = client.post(f"/api/shifts/{active_shift.json()['shift']['id']}/coverage/start")
    closed = client.post(f"/api/shifts/{closed_shift.json()['shift']['id']}/open-shift/close")
    assert started.status_code == 200
    assert closed.status_code == 200

    updated = client.post(
        f"/api/schedules/{schedule_id}/shifts/assignments",
        json={
            "assignments": [
                {
                    "shift_id": active_shift.json()["shift"]["id"],
                    "worker_id": eligible_worker.json()["id"],
                },
                {
                    "shift_id": closed_shift.json()["shift"]["id"],
                    "worker_id": eligible_worker.json()["id"],
                },
                {
                    "shift_id": valid_shift.json()["shift"]["id"],
                    "worker_id": ineligible_worker.json()["id"],
                },
                {
                    "shift_id": valid_shift.json()["shift"]["id"],
                    "worker_id": eligible_worker.json()["id"],
                    "notes": "Valid bulk assignment",
                },
            ]
        },
    )

    assert updated.status_code == 200
    payload = updated.json()
    assert payload["processed_count"] == 4
    assert payload["success_count"] == 1
    assert payload["error_count"] == 3
    assert [item["status"] for item in payload["results"]] == ["error", "error", "error", "ok"]
    assert payload["results"][0]["error"] == "Cannot change assignment while coverage workflow is active"
    assert payload["results"][1]["error"] == "Closed shifts must be reopened first"
    assert payload["results"][2]["error"] == "Worker is not eligible for this role"
    valid_shift_after = next(
        shift for shift in payload["schedule_view"]["shifts"] if shift["id"] == valid_shift.json()["shift"]["id"]
    )
    assert valid_shift_after["assignment"]["worker_id"] == eligible_worker.json()["id"]
    assert valid_shift_after["assignment"]["assignment_status"] == "assigned"
    assert valid_shift_after["available_actions"] == []
    active_shift_after = next(
        shift for shift in payload["schedule_view"]["shifts"] if shift["id"] == active_shift.json()["shift"]["id"]
    )
    closed_shift_after = next(
        shift for shift in payload["schedule_view"]["shifts"] if shift["id"] == closed_shift.json()["shift"]["id"]
    )
    assert active_shift_after["coverage"]["status"] == "active"
    assert active_shift_after["available_actions"] == ["cancel_offer", "close_shift"]
    assert closed_shift_after["assignment"]["assignment_status"] == "closed"
    assert closed_shift_after["available_actions"] == ["reopen_shift", "reopen_and_offer"]
    assert worker_offers


def test_backfill_shifts_bulk_edits_can_update_shift_details(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Bulk Edit Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550185",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Assigned Cook,+13105550186,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    open_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    closed_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "prep_cook",
            "date": "2026-04-16",
            "start_time": "10:00:00",
            "end_time": "18:00:00",
        },
    )
    assert open_shift.status_code == 200
    assert closed_shift.status_code == 200
    close_closed_shift = client.post(f"/api/shifts/{closed_shift.json()['shift']['id']}/open-shift/close")
    assert close_closed_shift.status_code == 200

    edited = client.patch(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "shift_ids": [
                open_shift.json()["shift"]["id"],
                closed_shift.json()["shift"]["id"],
            ],
            "start_time": "22:00:00",
            "end_time": "06:00:00",
            "pay_rate": 25,
            "shift_label": "Late Close",
            "notes": "Bulk edited shift",
        },
    )

    assert edited.status_code == 200
    payload = edited.json()
    assert payload["schedule_id"] == schedule_id
    assert payload["processed_count"] == 2
    assert payload["success_count"] == 2
    assert payload["error_count"] == 0
    assert payload["updated_fields"] == ["end_time", "notes", "pay_rate", "shift_label", "start_time"]
    updated_shifts = [
        shift
        for shift in payload["schedule_view"]["shifts"]
        if shift["id"] in {open_shift.json()["shift"]["id"], closed_shift.json()["shift"]["id"]}
    ]
    assert all(shift["start_time"] == "22:00:00" for shift in updated_shifts)
    assert all(shift["end_time"] == "06:00:00" for shift in updated_shifts)
    assert all(shift["spans_midnight"] is True for shift in updated_shifts)
    assert all(shift["pay_rate"] == 25.0 for shift in updated_shifts)
    assert all(shift["shift_label"] == "Late Close" for shift in updated_shifts)
    assert all(shift["notes"] == "Bulk edited shift" for shift in updated_shifts)
    open_shift_after = next(shift for shift in updated_shifts if shift["id"] == open_shift.json()["shift"]["id"])
    closed_shift_after = next(shift for shift in updated_shifts if shift["id"] == closed_shift.json()["shift"]["id"])
    assert open_shift_after["available_actions"] == ["start_coverage", "close_shift"]
    assert closed_shift_after["available_actions"] == ["reopen_shift", "reopen_and_offer"]


def test_backfill_shifts_bulk_edits_report_active_coverage_and_role_eligibility_errors(client, monkeypatch):
    worker_offers = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Bulk Edit Guard Cafe",
            "manager_name": "Nina Lead",
            "manager_phone": "+13105550187",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    candidate = client.post(
        "/api/workers",
        json={
            "name": "Offer Cook",
            "phone": "+13105550188",
            "roles": ["dishwasher", "prep_cook"],
            "priority_rank": 1,
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert candidate.status_code == 201

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Assigned Cook,+13105550189,line_cook,2026-04-14,09:00,17:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)
    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    committed = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert committed.status_code == 200
    schedule_id = committed.json()["schedule_id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    active_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
        },
    )
    valid_shift = client.post(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "role": "prep_cook",
            "date": "2026-04-16",
            "start_time": "10:00:00",
            "end_time": "18:00:00",
        },
    )
    assert active_shift.status_code == 200
    assert valid_shift.status_code == 200
    started = client.post(f"/api/shifts/{active_shift.json()['shift']['id']}/coverage/start")
    assert started.status_code == 200

    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current_schedule.status_code == 200
    assigned_shift_id = next(
        shift["id"]
        for shift in current_schedule.json()["shifts"]
        if shift["assignment"]["worker_id"] is not None
    )

    edited = client.patch(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "shift_ids": [
                active_shift.json()["shift"]["id"],
                assigned_shift_id,
                valid_shift.json()["shift"]["id"],
            ],
            "role": "dishwasher",
            "notes": "Bulk role update",
        },
    )

    assert edited.status_code == 200
    payload = edited.json()
    assert payload["processed_count"] == 3
    assert payload["success_count"] == 1
    assert payload["error_count"] == 2
    assert payload["updated_fields"] == ["notes", "role"]
    assert [item["status"] for item in payload["results"]] == ["error", "error", "ok"]
    assert payload["results"][0]["error"] == "Cannot edit shift while coverage workflow is active"
    assert payload["results"][1]["error"] == "Assigned worker is not eligible for updated role"
    valid_shift_after = next(
        shift for shift in payload["schedule_view"]["shifts"] if shift["id"] == valid_shift.json()["shift"]["id"]
    )
    active_shift_after = next(
        shift for shift in payload["schedule_view"]["shifts"] if shift["id"] == active_shift.json()["shift"]["id"]
    )
    assigned_shift_after = next(
        shift for shift in payload["schedule_view"]["shifts"] if shift["id"] == assigned_shift_id
    )
    assert valid_shift_after["role"] == "dishwasher"
    assert valid_shift_after["notes"] == "Bulk role update"
    assert valid_shift_after["available_actions"] == ["start_coverage", "close_shift"]
    assert active_shift_after["coverage"]["status"] == "active"
    assert active_shift_after["available_actions"] == ["cancel_offer", "close_shift"]
    assert assigned_shift_after["role"] == "line_cook"
    assert assigned_shift_after["notes"] is None
    assert worker_offers


def test_backfill_shifts_import_row_fix_and_recommit_is_incremental(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Action Needed Grill",
            "manager_name": "Lee Lead",
            "manager_phone": "+13105550151",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role,date,start,end",
            "Maria Lopez,+13105550161,line_cook,2026-04-14,09:00,17:00",
            "Jordan Smith,+13105550162,,2026-04-15,11:00,19:00",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)

    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
                "date": "date",
                "start": "start_time",
                "end": "end_time",
            }
        },
    )
    assert mapped.status_code == 200
    assert mapped.json()["status"] == "action_needed"

    rows = client.get(f"/api/import-jobs/{job['id']}/rows").json()["rows"]
    failed_row = next(row for row in rows if row["outcome"] == "failed")
    assert failed_row["error_code"] == "role_missing"

    first_commit = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert first_commit.status_code == 200
    first_payload = first_commit.json()
    assert first_payload["status"] == "partially_completed"
    assert first_payload["created_shifts"] == 1

    fixed = client.patch(
        f"/api/import-rows/{failed_row['id']}",
        json={
            "action": "fix",
            "normalized_payload": {"role": "dishwasher"},
        },
    )
    assert fixed.status_code == 200
    fixed_payload = fixed.json()
    assert fixed_payload["row"]["outcome"] == "success"
    assert fixed_payload["job"]["status"] == "validating"
    assert fixed_payload["action_needed_count"] == 0

    second_commit = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert second_commit.status_code == 200
    second_payload = second_commit.json()
    assert second_payload["created_shifts"] == 1
    assert second_payload["status"] == "completed"

    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current_schedule.status_code == 200
    schedule_payload = current_schedule.json()
    assert len(schedule_payload["shifts"]) == 2

    third_commit = client.post(f"/api/import-jobs/{job['id']}/commit")
    assert third_commit.status_code == 200
    assert third_commit.json()["created_shifts"] == 0

    current_schedule = client.get(
        f"/api/locations/{location['id']}/schedules/current?week_start=2026-04-13"
    )
    assert current_schedule.status_code == 200
    assert len(current_schedule.json()["shifts"]) == 2

    committed_row = next(
        row for row in client.get(f"/api/import-jobs/{job['id']}/rows").json()["rows"]
        if row["id"] == failed_row["id"]
    )
    assert committed_row["committed_at"] is not None

    edit_committed = client.patch(
        f"/api/import-rows/{failed_row['id']}",
        json={"action": "fix", "normalized_payload": {"role": "expediter"}},
    )
    assert edit_committed.status_code == 400
    assert "Committed import rows cannot be edited" in edit_committed.json()["detail"]


def test_backfill_shifts_import_row_ignore_retry_and_error_csv(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Roster Recovery Market",
            "manager_name": "Drew Lead",
            "manager_phone": "+13105550171",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    csv_text = "\n".join(
        [
            "employee_name,mobile,role",
            "Maria Lopez,5550177,cashier",
        ]
    )
    job, _ = _create_backfill_shifts_import_job(client, location["id"], csv_text)

    mapped = client.post(
        f"/api/import-jobs/{job['id']}/mapping",
        json={
            "mapping": {
                "employee_name": "worker_name",
                "mobile": "phone",
                "role": "role",
            }
        },
    )
    assert mapped.status_code == 200
    assert mapped.json()["status"] == "action_needed"

    rows_response = client.get(f"/api/import-jobs/{job['id']}/rows")
    assert rows_response.status_code == 200
    row = rows_response.json()["rows"][0]
    assert row["error_code"] == "phone_malformed"

    error_csv = client.get(f"/api/import-jobs/{job['id']}/error-csv")
    assert error_csv.status_code == 200
    assert error_csv.json()["count"] == 1
    assert "phone_malformed" in error_csv.json()["csv"]

    ignored = client.patch(
        f"/api/import-rows/{row['id']}",
        json={"action": "ignore"},
    )
    assert ignored.status_code == 200
    ignored_payload = ignored.json()
    assert ignored_payload["row"]["outcome"] == "skipped"
    assert ignored_payload["job"]["status"] == "validating"
    assert ignored_payload["action_needed_count"] == 0

    retried = client.patch(
        f"/api/import-rows/{row['id']}",
        json={
            "action": "retry",
            "normalized_payload": {"phone": "+13105550177"},
        },
    )
    assert retried.status_code == 200
    retried_payload = retried.json()
    assert retried_payload["row"]["outcome"] == "success"
    assert retried_payload["action_needed_count"] == 0

    error_csv = client.get(f"/api/import-jobs/{job['id']}/error-csv")
    assert error_csv.status_code == 200
    assert error_csv.json()["count"] == 0


def test_onboarding_link_endpoint_sends_expected_setup_url(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.onboarding.send_sms", lambda to, body: sent.append((to, body)) or "SM999")
    location = client.post(
        "/api/locations",
        json={
            "name": "Onboarding Link Cafe",
            "manager_name": "Jordan Ops",
            "manager_phone": "+13105550100",
            "scheduling_platform": "deputy",
        },
    ).json()

    response = client.post(
        "/api/onboarding/link",
        json={
            "phone": "+13105550100",
            "kind": "integration",
            "location_id": location["id"],
            "platform": "Deputy",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "deputy"
    parsed = urlparse(payload["url"])
    query = parse_qs(parsed.query)
    assert parsed.path == "/setup/connect"
    assert query["location_id"] == [str(location["id"])]
    assert query["platform"] == ["deputy"]
    assert query["setup_token"][0].startswith("bfsetup_")
    assert sent


def test_signup_session_api_loads_and_completes_from_retell_inbound_call(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.onboarding.send_sms",
        lambda to, body, **kwargs: sent.append((to, body, kwargs)) or "SM123",
    )

    webhook = client.post(
        "/webhooks/retell",
        json={
            "event": "call_analyzed",
            "call": {
                "call_id": "call_signup_api_123",
                "direction": "inbound",
                "call_status": "ended",
                "from_number": "+13105550199",
                "to_number": "+14244992663",
                "call_analysis": {
                    "call_type": "business_inquiry",
                    "caller_name": "Mina Patel",
                    "business_name": "Pacific Clinics",
                    "location_name": "Pacific Clinics West LA",
                    "business_email": "mina@pacificclinics.com",
                    "location_count": 5,
                    "pain_point_summary": "Need faster same-day coverage for hourly support staff.",
                    "urgency": "high",
                },
            },
        },
    )
    assert webhook.status_code == 200
    assert sent

    match = re.search(r"/signup/([A-Za-z0-9_\-]+)", sent[0][1])
    assert match is not None
    token = match.group(1)

    session = client.get(f"/api/onboarding/sessions/{token}")
    assert session.status_code == 200
    assert session.json()["business_name"] == "Pacific Clinics"
    assert session.json()["contact_phone"] == "+13105550199"
    assert "lead_source" not in session.json()

    completed = client.post(
        f"/api/onboarding/sessions/{token}/complete",
        json={
            "business_name": "Pacific Clinics",
            "contact_name": "Mina Patel",
            "contact_phone": "+13105550199",
            "contact_email": "mina@pacificclinics.com",
            "location_count": 5,
        },
    )

    assert completed.status_code == 200
    payload = completed.json()
    assert payload["status"] == "completed"
    assert payload["location"]["name"] == "Pacific Clinics West LA"
    next_query = parse_qs(urlparse(payload["next_path"]).query)
    assert next_query["location_id"] == [str(payload["location"]["id"])]
    assert next_query["from_signup"] == ["1"]
    assert next_query["setup_token"][0].startswith("bfsetup_")

    location = client.get(f"/api/locations/{payload['location']['id']}")
    assert location.status_code == 200
    assert location.json()["employee_count"] is None
    assert location.json()["manager_phone"] == "+13105550199"


def test_signup_session_completion_preserves_integration_setup_when_client_omits_it(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.onboarding.send_sms",
        lambda to, body, **kwargs: sent.append((to, body, kwargs)) or "SM124",
    )

    webhook = client.post(
        "/webhooks/retell",
        json={
            "event": "call_analyzed",
            "call": {
                "call_id": "call_signup_integration_123",
                "direction": "inbound",
                "call_status": "ended",
                "from_number": "+13105550200",
                "to_number": "+14244992663",
                "call_analysis": {
                    "call_type": "business_inquiry",
                    "caller_name": "Mina Patel",
                    "business_name": "Pacific Clinics",
                    "location_name": "Pacific Clinics West LA",
                    "business_email": "mina@pacificclinics.com",
                    "platform": "Deputy",
                },
            },
        },
    )
    assert webhook.status_code == 200
    assert sent

    match = re.search(r"/signup/([A-Za-z0-9_\-]+)", sent[0][1])
    assert match is not None
    token = match.group(1)

    completed = client.post(
        f"/api/onboarding/sessions/{token}/complete",
        json={
            "business_name": "Pacific Clinics",
            "contact_name": "Mina Patel",
            "contact_phone": "+13105550200",
            "contact_email": "mina@pacificclinics.com",
        },
    )

    assert completed.status_code == 200
    payload = completed.json()
    assert payload["location"]["scheduling_platform"] == "deputy"
    parsed = urlparse(payload["next_path"])
    query = parse_qs(parsed.query)
    assert parsed.path == "/setup/connect"
    assert query["location_id"] == [str(payload["location"]["id"])]
    assert query["from_signup"] == ["1"]
    assert query["platform"] == ["deputy"]
    assert query["setup_token"][0].startswith("bfsetup_")


def test_setup_access_token_scopes_setup_crud_to_one_location(client, public_client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.onboarding.send_sms", lambda to, body: sent.append((to, body)) or "SMSETUP")

    allowed = client.post(
        "/api/locations",
        json={
            "name": "Scoped Setup Location",
            "manager_name": "Taylor Lead",
            "manager_phone": "+13105550910",
            "scheduling_platform": "backfill_native",
        },
    ).json()
    blocked = client.post(
        "/api/locations",
        json={
            "name": "Blocked Setup Location",
            "manager_name": "Other Lead",
            "manager_phone": "+13105550911",
            "scheduling_platform": "backfill_native",
        },
    ).json()

    response = client.post(
        "/api/onboarding/link",
        json={
            "phone": "+13105550910",
            "kind": "csv_upload",
            "location_id": allowed["id"],
        },
    )
    assert response.status_code == 200
    setup_token = parse_qs(urlparse(response.json()["url"]).query)["setup_token"][0]
    headers = {"X-Backfill-Setup-Token": setup_token}

    allowed_get = public_client.get(f"/api/locations/{allowed['id']}", headers=headers)
    assert allowed_get.status_code == 200

    allowed_patch = public_client.patch(
        f"/api/locations/{allowed['id']}",
        json={"manager_name": "Updated Setup Manager"},
        headers=headers,
    )
    assert allowed_patch.status_code == 200
    assert allowed_patch.json()["manager_name"] == "Updated Setup Manager"

    worker_create = public_client.post(
        "/api/workers",
        json={
            "name": "Setup Worker",
            "phone": "+13105550912",
            "roles": ["line_cook"],
            "certifications": [],
            "location_id": allowed["id"],
        },
        headers=headers,
    )
    assert worker_create.status_code == 201

    blocked_get = public_client.get(f"/api/locations/{blocked['id']}", headers=headers)
    assert blocked_get.status_code == 403


def test_connect_sync_endpoint_marks_native_lite_restaurant(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Native Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
    ).json()

    response = client.post(f"/api/locations/{location['id']}/connect-sync")
    refreshed = client.get(f"/api/locations/{location['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "native_lite"
    assert refreshed.status_code == 200
    assert refreshed.json()["integration_status"] == "native_lite"


def test_restaurant_writeback_defaults_to_disabled_and_can_be_enabled(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Premium Toggle Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "7shifts",
            "scheduling_platform_id": "company-123",
        },
    ).json()

    initial = client.get(f"/api/locations/{location['id']}/status")
    assert initial.status_code == 200
    initial_payload = initial.json()
    assert initial_payload["integration"]["mode"] == "companion"
    assert initial_payload["integration"]["writeback_supported"] is True
    assert initial_payload["integration"]["writeback_enabled"] is False

    updated = client.patch(
        f"/api/locations/{location['id']}",
        json={"writeback_enabled": True, "writeback_subscription_tier": "premium"},
    )
    assert updated.status_code == 200
    assert updated.json()["writeback_enabled"] is True
    assert updated.json()["writeback_subscription_tier"] == "premium"

    refreshed = client.get(f"/api/locations/{location['id']}/status")
    assert refreshed.status_code == 200
    refreshed_payload = refreshed.json()
    assert refreshed_payload["integration"]["mode"] == "companion_writeback"
    assert refreshed_payload["integration"]["writeback_enabled"] is True
    assert refreshed_payload["integration"]["writeback_subscription_tier"] == "premium"


def test_internal_manager_digest_batch_route_respects_cooldown_and_activity(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM-DIGEST",
    )

    due_location = client.post(
        "/api/locations",
        json={
            "name": "Due Digest Cafe",
            "manager_name": "Pat Lead",
            "manager_phone": "+13105550140",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    recent_location = client.post(
        "/api/locations",
        json={
            "name": "Recent Digest Cafe",
            "manager_name": "Mina Lead",
            "manager_phone": "+13105550141",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "last_manager_digest_sent_at": datetime.utcnow().isoformat(),
        },
    ).json()
    empty_location = client.post(
        "/api/locations",
        json={
            "name": "Empty Digest Cafe",
            "manager_name": "Jules Lead",
            "manager_phone": "+13105550142",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    external_location = client.post(
        "/api/locations",
        json={
            "name": "Deputy Digest Cafe",
            "manager_name": "Ari Lead",
            "manager_phone": "+13105550143",
            "scheduling_platform": "deputy",
        },
    ).json()

    due_worker = client.post(
        "/api/workers",
        json={
            "name": "Terry Cook",
            "phone": "+13105550144",
            "roles": ["line_cook"],
            "location_id": due_location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    recent_worker = client.post(
        "/api/workers",
        json={
            "name": "Riley Cook",
            "phone": "+13105550145",
            "roles": ["line_cook"],
            "location_id": recent_location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()

    start_due = datetime.utcnow() + timedelta(hours=6)
    week_start_due = start_due.date() - timedelta(days=start_due.date().weekday())
    created_schedule_due = client.post(
        "/api/shifts",
        json={
            "location_id": due_location["id"],
            "schedule_id": None,
            "role": "line_cook",
            "date": start_due.date().isoformat(),
            "start_time": start_due.strftime("%H:%M:%S"),
            "end_time": (start_due + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 22.0,
            "requirements": [],
            "source_platform": "backfill_native",
            "status": "scheduled",
            "published_state": "published",
        },
    )
    assert created_schedule_due.status_code == 201
    due_shift = created_schedule_due.json()
    assign_due = client.patch(
        f"/api/shifts/{due_shift['id']}/assignment",
        json={"worker_id": due_worker["id"], "assignment_status": "assigned"},
    )
    assert assign_due.status_code == 200

    start_recent = datetime.utcnow() + timedelta(hours=7)
    created_schedule_recent = client.post(
        "/api/shifts",
        json={
            "location_id": recent_location["id"],
            "schedule_id": None,
            "role": "line_cook",
            "date": start_recent.date().isoformat(),
            "start_time": start_recent.strftime("%H:%M:%S"),
            "end_time": (start_recent + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 22.0,
            "requirements": [],
            "source_platform": "backfill_native",
            "status": "scheduled",
            "published_state": "published",
        },
    )
    assert created_schedule_recent.status_code == 201
    recent_shift = created_schedule_recent.json()
    assign_recent = client.patch(
        f"/api/shifts/{recent_shift['id']}/assignment",
        json={"worker_id": recent_worker["id"], "assignment_status": "assigned"},
    )
    assert assign_recent.status_code == 200

    response = client.post("/api/internal/backfill-shifts/send-manager-digests?lookahead_hours=24&cooldown_hours=12")
    due_refreshed = client.get(f"/api/locations/{due_location['id']}")
    recent_refreshed = client.get(f"/api/locations/{recent_location['id']}")

    assert response.status_code == 200
    assert response.json() == {
        "lookahead_hours": 24,
        "cooldown_hours": 12,
        "sent_count": 1,
        "sent_location_ids": [due_location["id"]],
        "skipped_recent_location_ids": [recent_location["id"]],
        "skipped_no_activity_location_ids": [empty_location["id"]],
        "skipped_ineligible_location_ids": [external_location["id"]],
    }
    assert due_refreshed.status_code == 200
    assert due_refreshed.json()["last_manager_digest_sent_at"] is not None
    assert recent_refreshed.status_code == 200
    assert recent_refreshed.json()["last_manager_digest_sent_at"] is not None
    assert sent == [
        (
            "+13105550140",
            (
                f"Backfill: Next 24h for Due Digest Cafe looks on track. 1 shift is scheduled and all assigned. "
                f"Review: https://usebackfill.com/dashboard/locations/{due_location['id']}?tab=schedule&week_start={week_start_due.isoformat()}"
            ),
        )
    ]


def test_restaurant_status_endpoint_returns_operational_summary(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Status Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
    ).json()
    location_id = location["id"]

    client.post(
        "/api/workers",
        json={
            "name": "James",
            "phone": "+13105550102",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift = client.post("/api/shifts", json=_make_shift_payload(location_id)).json()
    client.patch(f"/api/shifts/{shift['id']}", json={"status": "vacant"})

    response = client.get(f"/api/locations/{location_id}/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["location"]["id"] == location_id
    assert payload["integration"]["mode"] == "native"
    assert payload["metrics"]["workers_total"] == 1
    assert payload["metrics"]["shifts_vacant"] == 1
    assert len(payload["worker_preview"]) == 1
    assert len(payload["recent_shifts"]) == 1


def test_location_settings_endpoint_exposes_attendance_and_coverage_policies(client):
    created = client.post(
        "/api/locations",
        json={
            "name": "Policy Cafe",
            "manager_name": "Jordan Lead",
            "manager_phone": "+13105550189",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "coverage_requires_manager_approval": True,
            "late_arrival_policy": "manager_action",
            "missed_check_in_policy": "manager_action",
            "agency_supply_approved": True,
            "timezone": "America/Los_Angeles",
            "writeback_enabled": True,
            "backfill_shifts_enabled": True,
            "backfill_shifts_launch_state": "pilot",
            "backfill_shifts_beta_eligible": True,
        },
    )
    assert created.status_code == 201
    location = created.json()

    settings = client.get(f"/api/locations/{location['id']}/settings")

    assert settings.status_code == 200
    assert settings.json() == {
        "location_id": location["id"],
        "scheduling_platform": "backfill_native",
        "operating_mode": "backfill_shifts",
        "timezone": "America/Los_Angeles",
        "writeback_enabled": True,
        "backfill_shifts_enabled": True,
        "backfill_shifts_launch_state": "pilot",
        "backfill_shifts_beta_eligible": True,
        "coverage_requires_manager_approval": True,
        "late_arrival_policy": "manager_action",
        "missed_check_in_policy": "manager_action",
        "agency_supply_approved": True,
    }

    updated = client.patch(
        f"/api/locations/{location['id']}/settings",
        json={
            "backfill_shifts_enabled": False,
            "backfill_shifts_launch_state": "disabled",
            "backfill_shifts_beta_eligible": False,
            "coverage_requires_manager_approval": False,
            "late_arrival_policy": "start_coverage",
            "missed_check_in_policy": "start_coverage",
        },
    )
    location_after = client.get(f"/api/locations/{location['id']}")

    assert updated.status_code == 200
    assert updated.json()["backfill_shifts_enabled"] is False
    assert updated.json()["backfill_shifts_launch_state"] == "disabled"
    assert updated.json()["backfill_shifts_beta_eligible"] is False
    assert updated.json()["coverage_requires_manager_approval"] is False
    assert updated.json()["late_arrival_policy"] == "start_coverage"
    assert updated.json()["missed_check_in_policy"] == "start_coverage"
    assert location_after.status_code == 200
    assert location_after.json()["backfill_shifts_enabled"] is False
    assert location_after.json()["backfill_shifts_launch_state"] == "disabled"
    assert location_after.json()["backfill_shifts_beta_eligible"] is False
    assert location_after.json()["coverage_requires_manager_approval"] is False
    assert location_after.json()["late_arrival_policy"] == "start_coverage"
    assert location_after.json()["missed_check_in_policy"] == "start_coverage"


def test_backfill_shifts_metrics_endpoint_summarizes_launch_and_operations(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM123",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Metrics Cafe",
            "manager_name": "Jordan Lead",
            "manager_phone": "+13105550190",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "backfill_shifts_enabled": True,
            "backfill_shifts_launch_state": "pilot",
            "backfill_shifts_beta_eligible": True,
        },
    ).json()
    assigned_worker = client.post(
        "/api/workers",
        json={
            "name": "Taylor Cook",
            "phone": "+13105550191",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    pending_worker = client.post(
        "/api/workers",
        json={
            "name": "Jordan Cook",
            "phone": "+13105550192",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "pending",
            "voice_consent_status": "pending",
        },
    ).json()

    invites = client.post(
        f"/api/locations/{location['id']}/enrollment-invites",
        json={"worker_ids": [pending_worker["id"]]},
    )
    assert invites.status_code == 200

    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Metrics Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]
    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": assigned_worker["id"],
                    "assignment_status": "assigned",
                }
            ]
        },
    )
    assert seeded.status_code == 200

    created = client.post(
        f"/api/locations/{location['id']}/schedules/create-from-template",
        json={
            "template_id": template_id,
            "target_week_start_date": "2026-10-05",
        },
    )
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]
    shift_id = created.json()["schedule_view"]["shifts"][0]["id"]

    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    amended = client.patch(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "shift_ids": [shift_id],
            "start_time": "09:00:00",
            "end_time": "17:00:00",
        },
    )
    assert amended.status_code == 200

    callout_shift = client.post(
        "/api/shifts",
        json={
            "location_id": location["id"],
            "role": "dishwasher",
            "date": "2026-10-07",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
            "pay_rate": 18.0,
            "requirements": [],
        },
    )
    assert callout_shift.status_code == 201
    marked_called_out = client.patch(
        f"/api/shifts/{callout_shift.json()['id']}",
        json={
            "status": "vacant",
            "called_out_by": assigned_worker["id"],
        },
    )
    assert marked_called_out.status_code == 200

    metrics = client.get(f"/api/locations/{location['id']}/backfill-shifts-metrics?days=90")
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["location_id"] == location["id"]
    assert payload["window_days"] == 90
    assert payload["launch_controls"] == {
        "backfill_shifts_enabled": True,
        "backfill_shifts_launch_state": "pilot",
        "backfill_shifts_beta_eligible": True,
        "operating_mode": "backfill_shifts",
        "scheduling_platform": "backfill_native",
    }
    assert payload["summary"]["worker_count"] == 2
    assert payload["summary"]["enrolled_worker_count"] == 1
    assert payload["summary"]["pending_enrollment_count"] == 1
    assert payload["summary"]["invite_sent_count"] == 1
    assert payload["summary"]["schedule_publish_event_count"] == 1
    assert payload["summary"]["schedule_amendment_event_count"] == 1
    assert payload["summary"]["published_week_count"] == 1
    assert payload["summary"]["schedule_delivery_sent_count"] == 1
    assert payload["summary"]["schedule_delivery_failed_count"] == 0
    assert payload["summary"]["callout_shift_count"] == 1
    assert payload["summary"]["filled_callout_shift_count"] == 0
    assert payload["summary"]["fill_event_count"] == 0
    assert payload["rates"]["opt_in_rate"] == 0.5
    assert payload["rates"]["invite_conversion_rate"] == 0.0
    assert payload["rates"]["callout_fill_rate"] == 0.0
    assert payload["rates"]["delivery_success_rate"] == 1.0
    assert payload["rates"]["first_publish_achieved"] is True
    assert payload["rates"]["second_publish_achieved"] is False
    assert payload["recent_activity"]["last_schedule_publish_at"] is not None
    assert payload["recent_activity"]["last_schedule_amendment_at"] is not None
    assert payload["recent_activity"]["last_invite_sent_at"] is not None
    assert payload["recent_activity"]["last_callout_at"] is None


def test_run_due_backfill_shifts_automation_batches_internal_schedule_ops(client, monkeypatch):
    sent = []

    def _record_sms(to, body, metadata=None):
        sent.append((to, body))
        return "SM-AUTO"

    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: _record_sms(to, body))
    monkeypatch.setattr("app.services.messaging.send_sms", _record_sms)

    location = client.post(
        "/api/locations",
        json={
            "name": "Automation Cafe",
            "manager_name": "Jordan Lead",
            "manager_phone": "+13105550196",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()
    worker = client.post(
        "/api/workers",
        json={
            "name": "Taylor Cook",
            "phone": "+13105550197",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()

    start = datetime.utcnow() + timedelta(minutes=20)
    shift = client.post(
        "/api/shifts",
        json={
            "location_id": location["id"],
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 22.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
        },
    ).json()
    assigned = client.patch(
        f"/api/shifts/{shift['id']}/assignment",
        json={"worker_id": worker["id"], "assignment_status": "assigned"},
    )
    assert assigned.status_code == 200

    response = client.post(
        (
            "/api/internal/backfill-shifts/run-automation"
            f"?location_id={location['id']}"
            "&confirmation_within_minutes=120"
            "&check_in_within_minutes=30"
            "&reminder_within_minutes=30"
            "&run_unconfirmed_escalations=false"
            "&run_missed_check_in_escalations=false"
            "&run_manager_digests=false"
        )
    )
    refreshed_shift = client.get(f"/api/shifts/{shift['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["location_id"] == location["id"]
    assert payload["summary"] == {
        "completed_steps": 3,
        "failed_steps": 0,
        "skipped_steps": 3,
    }
    assert payload["steps"]["confirmation_requests"]["result"]["sent_count"] == 1
    assert payload["steps"]["check_in_requests"]["result"]["sent_count"] == 1
    assert payload["steps"]["shift_reminders"]["result"]["reminders_sent"] == 1
    assert payload["steps"]["unconfirmed_escalations"]["status"] == "skipped"
    assert payload["steps"]["missed_check_in_escalations"]["status"] == "skipped"
    assert payload["steps"]["manager_digests"]["status"] == "skipped"
    assert refreshed_shift.status_code == 200
    assert refreshed_shift.json()["confirmation_requested_at"] is not None
    assert refreshed_shift.json()["check_in_requested_at"] is not None
    assert refreshed_shift.json()["reminder_sent_at"] is not None
    assert len(sent) == 3


def test_internal_backfill_automation_can_be_queued_and_processed(client):
    location = client.post(
        "/api/locations",
        json={
            "name": "Queued Automation Cafe",
            "manager_name": "Jordan Lead",
            "manager_phone": "+13105550990",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    ).json()

    queued = client.post(
        (
            "/api/internal/backfill-shifts/run-automation"
            f"?location_id={location['id']}"
            "&run_confirmations=false"
            "&run_unconfirmed_escalations=false"
            "&run_check_ins=false"
            "&run_missed_check_in_escalations=false"
            "&run_reminders=false"
            "&run_manager_digests=false"
            "&enqueue=true"
        )
    )
    assert queued.status_code == 200
    queued_payload = queued.json()
    assert queued_payload["status"] == "queued"
    job_id = queued_payload["job"]["id"]

    jobs = client.get("/api/internal/ops/jobs?status=queued")
    assert jobs.status_code == 200
    assert [item["id"] for item in jobs.json()["jobs"]] == [job_id]

    processed = client.post("/api/internal/ops/process-due?limit=10")
    assert processed.status_code == 200
    processed_payload = processed.json()
    assert processed_payload["claimed_count"] == 1
    assert processed_payload["results"][0]["status"] == "completed"
    assert processed_payload["results"][0]["job_id"] == job_id

    completed = client.get("/api/internal/ops/jobs?status=completed")
    assert completed.status_code == 200
    assert [item["id"] for item in completed.json()["jobs"]] == [job_id]


def test_backfill_shifts_activity_endpoint_returns_recent_operational_feed(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM123",
    )

    location = client.post(
        "/api/locations",
        json={
            "name": "Activity Cafe",
            "manager_name": "Jordan Lead",
            "manager_phone": "+13105550193",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "backfill_shifts_enabled": True,
            "backfill_shifts_launch_state": "pilot",
            "backfill_shifts_beta_eligible": True,
        },
    ).json()
    assigned_worker = client.post(
        "/api/workers",
        json={
            "name": "Taylor Cook",
            "phone": "+13105550194",
            "roles": ["line_cook"],
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    pending_worker = client.post(
        "/api/workers",
        json={
            "name": "Jordan Cook",
            "phone": "+13105550195",
            "roles": ["dishwasher"],
            "location_id": location["id"],
            "sms_consent_status": "pending",
            "voice_consent_status": "pending",
        },
    ).json()

    invites = client.post(
        f"/api/locations/{location['id']}/enrollment-invites",
        json={"worker_ids": [pending_worker["id"]]},
    )
    assert invites.status_code == 200

    template = client.post(
        f"/api/locations/{location['id']}/schedule-templates",
        json={"name": "Activity Template"},
    )
    assert template.status_code == 200
    template_id = template.json()["template"]["id"]
    seeded = client.post(
        f"/api/schedule-templates/{template_id}/shifts/bulk",
        json={
            "slots": [
                {
                    "day_of_week": 0,
                    "role": "line_cook",
                    "start_time": "08:00:00",
                    "end_time": "16:00:00",
                    "worker_id": assigned_worker["id"],
                    "assignment_status": "assigned",
                }
            ]
        },
    )
    assert seeded.status_code == 200

    created = client.post(
        f"/api/locations/{location['id']}/schedules/create-from-template",
        json={
            "template_id": template_id,
            "target_week_start_date": "2026-10-12",
        },
    )
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]
    shift_id = created.json()["schedule_view"]["shifts"][0]["id"]

    published = client.post(f"/api/schedules/{schedule_id}/publish")
    assert published.status_code == 200

    amended = client.patch(
        f"/api/schedules/{schedule_id}/shifts",
        json={
            "shift_ids": [shift_id],
            "start_time": "09:00:00",
            "end_time": "17:00:00",
        },
    )
    assert amended.status_code == 200

    feed = client.get(
        f"/api/locations/{location['id']}/backfill-shifts-activity?days=90&limit=20"
    )

    assert feed.status_code == 200
    payload = feed.json()
    assert payload["location_id"] == location["id"]
    assert payload["window_days"] == 90
    assert payload["summary"]["total_events"] >= 4
    assert payload["summary"]["categories"]["roster"] >= 1
    assert payload["summary"]["categories"]["scheduling"] >= 2
    activity_types = {item["activity_type"] for item in payload["items"]}
    assert "worker_invited" in activity_types
    assert "schedule_published" in activity_types
    assert "schedule_amended" in activity_types
    publish_item = next(item for item in payload["items"] if item["activity_type"] == "schedule_published")
    assert publish_item["category"] == "scheduling"
    assert publish_item["review_link"] is not None
    assert f"/dashboard/locations/{location['id']}?tab=schedule&week_start=2026-10-12" in publish_item["review_link"]


def test_location_alias_endpoints_work_with_generic_payloads(client):
    created = client.post(
        "/api/locations",
        json={
            "name": "South Bay Fulfillment",
            "organization_name": "South Bay Ops",
            "vertical": "warehouse",
            "manager_name": "Jordan Lee",
            "manager_phone": "+13105550188",
            "scheduling_platform": "backfill_native",
        },
    )
    assert created.status_code == 201
    location = created.json()
    assert location["vertical"] == "warehouse"
    assert location["organization_name"] == "South Bay Ops"

    organizations = client.get("/api/organizations")
    assert organizations.status_code == 200
    assert organizations.json()[0]["name"] == "South Bay Ops"

    fetched = client.get(f"/api/locations/{location['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "South Bay Fulfillment"

    updated = client.patch(
        f"/api/locations/{location['id']}",
        json={
            "writeback_enabled": False,
            "vertical": "warehouse",
            "coverage_requires_manager_approval": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["vertical"] == "warehouse"
    assert updated.json()["coverage_requires_manager_approval"] is True

    worker = client.post(
        "/api/workers",
        json={
            "name": "Avery",
            "phone": "+13105550189",
            "roles": ["picker"],
            "certifications": ["forklift_cert"],
            "priority_rank": 1,
            "location_id": location["id"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    assert worker.status_code == 201
    assert worker.json()["location_id"] == location["id"]

    shift = client.post(
        "/api/shifts",
        json={
            "location_id": location["id"],
            "role": "picker",
            "date": (datetime.utcnow() + timedelta(hours=6)).date().isoformat(),
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "pay_rate": 24.0,
            "requirements": ["forklift_cert"],
        },
    )
    assert shift.status_code == 201
    assert shift.json()["location_id"] == location["id"]

    status = client.get(f"/api/locations/{location['id']}/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["location"]["id"] == location["id"]
    assert payload["location"]["vertical"] == "warehouse"

    workers = client.get(f"/api/workers?location_id={location['id']}")
    shifts = client.get(f"/api/shifts?location_id={location['id']}")
    dashboard = client.get(f"/api/dashboard?location_id={location['id']}")

    assert workers.status_code == 200
    assert len(workers.json()) == 1
    assert shifts.status_code == 200
    assert len(shifts.json()) == 1
    assert dashboard.status_code == 200
    assert dashboard.json()["location_id"] == location["id"]
    assert dashboard.json()["locations"] == 1


def test_retell_reconcile_endpoint_routes_to_recent_sync(client, monkeypatch):
    async def _fake_sync(db, lookback_minutes=180, limit=50):
        return {"status": "ok", "calls_synced": 2, "chats_synced": 1, "lookback_minutes": lookback_minutes}

    monkeypatch.setattr("app.services.retell_reconcile.sync_recent_activity", _fake_sync)

    response = client.post("/api/retell/reconcile", json={"lookback_minutes": 30, "limit": 5})

    assert response.status_code == 200
    assert response.json()["calls_synced"] == 2
    assert response.json()["lookback_minutes"] == 30


def test_retell_reconcile_endpoint_routes_to_specific_call(client, monkeypatch):
    async def _fake_sync_call(db, call_id):
        return {"status": "ok", "call_id": call_id, "conversation_id": 9}

    monkeypatch.setattr("app.services.retell_reconcile.sync_call_by_id", _fake_sync_call)

    response = client.post("/api/retell/reconcile", json={"call_id": "call_123"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "call_id": "call_123", "conversation_id": 9}


def test_manager_shift_creation_starts_backfill(client, monkeypatch):
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"
    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)
    location = client.post(
        "/api/locations",
        json={
            "name": "Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
    ).json()
    location_id = location["id"]

    client.post(
        "/api/workers",
        json={
            "name": "James",
            "phone": "+13105550102",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )

    response = client.post(
        "/api/manager/shifts",
        json={
            **_make_shift_payload(location_id, start_delta_hours=2),
            "start_backfill": True,
        },
    )
    assert response.status_code == 201
    shift = response.json()
    assert shift["status"] == "vacant"

    status = client.get(f"/api/shifts/{shift['id']}/status")
    cascades = client.get(f"/api/cascades?shift_id={shift['id']}")
    outreach = client.get(f"/api/outreach-attempts?shift_id={shift['id']}")

    assert status.status_code == 200
    assert status.json()["cascade"]["status"] == "active"
    assert cascades.status_code == 200
    assert len(cascades.json()) == 1
    assert outreach.status_code == 200
    assert len(outreach.json()) >= 1
