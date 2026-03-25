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
    assert "James" in workers_csv.json()["csv"]
    assert "line_cook" in shifts_csv.json()["csv"]
    assert client.get(f"/api/shifts/{shift['id']}/status").status_code == 200


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
