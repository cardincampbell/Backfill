from datetime import datetime, timedelta

def _make_shift_payload(restaurant_id: int, start_delta_hours: int = 12):
    start = datetime.utcnow() + timedelta(hours=start_delta_hours)
    end = start + timedelta(hours=8)
    return {
        "restaurant_id": restaurant_id,
        "role": "line_cook",
        "date": start.date().isoformat(),
        "start_time": start.strftime("%H:%M:%S"),
        "end_time": end.strftime("%H:%M:%S"),
        "pay_rate": 22.0,
        "requirements": ["food_handler_card"],
    }


def test_native_lite_read_update_export_and_dashboard(client):
    restaurant = client.post(
        "/api/restaurants",
        json={
            "name": "Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
    ).json()
    restaurant_id = restaurant["id"]

    worker = client.post(
        "/api/workers",
        json={
            "name": "James",
            "phone": "+13105550102",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "restaurant_id": restaurant_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    ).json()
    shift = client.post("/api/shifts", json=_make_shift_payload(restaurant_id)).json()

    updated_worker = client.patch(
        f"/api/workers/{worker['id']}",
        json={"preferred_channel": "both", "rating": 4.8},
    )
    assert updated_worker.status_code == 200
    assert updated_worker.json()["preferred_channel"] == "both"

    workers = client.get(f"/api/workers?restaurant_id={restaurant_id}")
    shifts = client.get(f"/api/shifts?restaurant_id={restaurant_id}")
    dashboard = client.get(f"/api/dashboard?restaurant_id={restaurant_id}")
    workers_csv = client.get(f"/api/exports/workers?restaurant_id={restaurant_id}")
    shifts_csv = client.get(f"/api/exports/shifts?restaurant_id={restaurant_id}")

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


def test_onboarding_link_endpoint_sends_expected_setup_url(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.onboarding.send_sms", lambda to, body: sent.append((to, body)) or "SM999")

    response = client.post(
        "/api/onboarding/link",
        json={
            "phone": "+13105550100",
            "kind": "integration",
            "platform": "Deputy",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "deputy"
    assert payload["path"] == "/setup/connect?platform=deputy"
    assert payload["url"].endswith("/setup/connect?platform=deputy")
    assert sent


def test_connect_sync_endpoint_marks_native_lite_restaurant(client):
    restaurant = client.post(
        "/api/restaurants",
        json={
            "name": "Native Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
    ).json()

    response = client.post(f"/api/restaurants/{restaurant['id']}/connect-sync")
    refreshed = client.get(f"/api/restaurants/{restaurant['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "native_lite"
    assert refreshed.status_code == 200
    assert refreshed.json()["integration_status"] == "native_lite"


def test_restaurant_writeback_defaults_to_disabled_and_can_be_enabled(client):
    restaurant = client.post(
        "/api/restaurants",
        json={
            "name": "Premium Toggle Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "7shifts",
            "scheduling_platform_id": "company-123",
        },
    ).json()

    initial = client.get(f"/api/restaurants/{restaurant['id']}/status")
    assert initial.status_code == 200
    initial_payload = initial.json()
    assert initial_payload["integration"]["mode"] == "companion"
    assert initial_payload["integration"]["writeback_supported"] is True
    assert initial_payload["integration"]["writeback_enabled"] is False

    updated = client.patch(
        f"/api/restaurants/{restaurant['id']}",
        json={"writeback_enabled": True, "writeback_subscription_tier": "premium"},
    )
    assert updated.status_code == 200
    assert updated.json()["writeback_enabled"] is True
    assert updated.json()["writeback_subscription_tier"] == "premium"

    refreshed = client.get(f"/api/restaurants/{restaurant['id']}/status")
    assert refreshed.status_code == 200
    refreshed_payload = refreshed.json()
    assert refreshed_payload["integration"]["mode"] == "companion_writeback"
    assert refreshed_payload["integration"]["writeback_enabled"] is True
    assert refreshed_payload["integration"]["writeback_subscription_tier"] == "premium"


def test_restaurant_status_endpoint_returns_operational_summary(client):
    restaurant = client.post(
        "/api/restaurants",
        json={
            "name": "Status Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
    ).json()
    restaurant_id = restaurant["id"]

    client.post(
        "/api/workers",
        json={
            "name": "James",
            "phone": "+13105550102",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "restaurant_id": restaurant_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift = client.post("/api/shifts", json=_make_shift_payload(restaurant_id)).json()
    client.patch(f"/api/shifts/{shift['id']}", json={"status": "vacant"})

    response = client.get(f"/api/restaurants/{restaurant_id}/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["restaurant"]["id"] == restaurant_id
    assert payload["integration"]["mode"] == "native"
    assert payload["metrics"]["workers_total"] == 1
    assert payload["metrics"]["shifts_vacant"] == 1
    assert len(payload["worker_preview"]) == 1
    assert len(payload["recent_shifts"]) == 1


def test_manager_shift_creation_starts_backfill(client, monkeypatch):
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body: "SM123")
    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"
    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)
    restaurant = client.post(
        "/api/restaurants",
        json={
            "name": "Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
    ).json()
    restaurant_id = restaurant["id"]

    client.post(
        "/api/workers",
        json={
            "name": "James",
            "phone": "+13105550102",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "restaurant_id": restaurant_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )

    response = client.post(
        "/api/manager/shifts",
        json={
            **_make_shift_payload(restaurant_id, start_delta_hours=2),
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
