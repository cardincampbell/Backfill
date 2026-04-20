from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_db_session
from app.main import app
from app.models.auto_scheduler import (
    ReplayRun,
    ScheduleRun,
    ScheduleRunApply,
    ScheduleRunAssignment,
    ScheduleRunExplanation,
    ScheduleRunInput,
    ScheduleRunMetric,
    ScheduleRunRejection,
)
from app.models.common import ScheduleApplyStatus, ScheduleRunStatus, ScheduleRunType
from app.models.integrations import ProviderCallbackLog


class DummyInternalSession:
    async def commit(self):
        return None

    async def rollback(self):
        return None


async def _override_db():
    yield DummyInternalSession()


def _schedule_run_read_fixture() -> ScheduleRun:
    now = datetime.now(timezone.utc)
    return ScheduleRun(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        run_type=ScheduleRunType.draft_generate,
        status=ScheduleRunStatus.completed,
        optimizer_engine="ortools_cp_sat_v1",
        objective_version="v1",
        constraints_version="v1",
        policy_version="v1",
        input_snapshot_version="v1",
        input_snapshot_hash="sha256:authoring",
        run_metadata={"scope_shift_count": 1},
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


def _schedule_run_apply_fixture(schedule_run: ScheduleRun) -> ScheduleRunApply:
    now = datetime.now(timezone.utc)
    return ScheduleRunApply(
        id=uuid4(),
        schedule_run_id=schedule_run.id,
        business_id=schedule_run.business_id,
        location_id=schedule_run.location_id,
        planning_window_start=schedule_run.planning_window_start,
        planning_window_end=schedule_run.planning_window_end,
        status=ScheduleApplyStatus.applied,
        target_snapshot_hash="sha256:target",
        current_snapshot_hash="sha256:current",
        stale_reason=None,
        apply_metadata={"applied_assignment_count": 1},
        applied_at=now,
        created_at=now,
        updated_at=now,
    )


def _schedule_run_detail_fixture() -> ScheduleRun:
    schedule_run = _schedule_run_read_fixture()
    schedule_run.inputs = ScheduleRunInput(
        schedule_run_id=schedule_run.id,
        shift_payload={"shifts": [{"shift_id": str(uuid4())}]},
        fixed_shift_payload={"shifts": [{"shift_id": str(uuid4())}]},
        generated_demand_payload={"proposed_shifts": [], "metadata": {}},
        employee_payload={"employees": [{"employee_id": str(uuid4())}]},
        availability_payload={"eligible_employee_ids_by_shift": {}},
        policy_payload={"publish_mode": "draft_only"},
        labor_payload={"employees": {}},
        reliability_payload={"employees": []},
        reliability_snapshot_generated_at=schedule_run.created_at,
        reliability_snapshot_hash="sha256:reliability",
        reliability_snapshot_version="v1",
        source_metadata={"authoring_snapshot_hash": "sha256:authoring"},
        created_at=schedule_run.created_at,
        updated_at=schedule_run.updated_at,
    )
    schedule_run.proposed_shifts = []
    schedule_run.assignments = [
        ScheduleRunAssignment(
            id=uuid4(),
            schedule_run_id=schedule_run.id,
            shift_id=uuid4(),
            employee_id=uuid4(),
            decision_score=95.0,
            decision_rank=1,
            assignment_payload={"source": "optimizer"},
            created_at=schedule_run.created_at,
            updated_at=schedule_run.updated_at,
        )
    ]
    schedule_run.rejections = [
        ScheduleRunRejection(
            id=uuid4(),
            schedule_run_id=schedule_run.id,
            shift_id=uuid4(),
            employee_id=uuid4(),
            candidate_rank=2,
            rejection_reason_codes=["lower_ranked_candidate"],
            score_payload={"total_score": 80.0},
            constraint_failure_payload={},
            created_at=schedule_run.created_at,
            updated_at=schedule_run.updated_at,
        )
    ]
    schedule_run.explanation = ScheduleRunExplanation(
        schedule_run_id=schedule_run.id,
        summary_payload={"assigned_shift_count": 1},
        fairness_payload={},
        overtime_payload={},
        coverage_payload={},
        unassigned_shift_payload={},
        created_at=schedule_run.created_at,
        updated_at=schedule_run.updated_at,
    )
    schedule_run.metrics = ScheduleRunMetric(
        schedule_run_id=schedule_run.id,
        shift_count=1,
        assigned_shift_count=1,
        unassigned_shift_count=0,
        candidate_considered_count=2,
        overtime_assignment_count=0,
        fairness_spread_metrics={"avg_hours": 6.0},
        solver_runtime_ms=12,
        objective_value=95.0,
        created_at=schedule_run.created_at,
        updated_at=schedule_run.updated_at,
    )
    schedule_run.applies = [_schedule_run_apply_fixture(schedule_run)]
    schedule_run.replay_runs = [
        ReplayRun(
            id=uuid4(),
            schedule_run_id=schedule_run.id,
            business_id=schedule_run.business_id,
            location_id=schedule_run.location_id,
            planning_window_start=schedule_run.planning_window_start,
            planning_window_end=schedule_run.planning_window_end,
            status=ScheduleRunStatus.completed,
            comparison_version="v1",
            target_snapshot_hash="sha256:target",
            actual_snapshot_hash="sha256:actual",
            actual_assignment_payload={},
            actual_outcome_payload={},
            metrics_payload={},
            replay_metadata={},
            started_at=schedule_run.created_at,
            completed_at=schedule_run.created_at,
            created_at=schedule_run.created_at,
            updated_at=schedule_run.updated_at,
        )
    ]
    return schedule_run


def test_coverage_runtime_process_route_rejects_invalid_worker_key(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/internal/coverage/runtime/process",
            json={"limit": 5},
            headers={"X-Backfill-Worker-Key": "wrong_key"},
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "worker_auth_failed"}
    finally:
        app.dependency_overrides.clear()


def test_migrations_run_route_rejects_invalid_worker_key(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.migrations.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/internal/migrations/run",
            headers={"X-Backfill-Worker-Key": "wrong_key"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "worker_auth_failed"}


def test_migrations_run_route_executes_bootstrap_migration_helper(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        "app.api.routes.migrations.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr(
        "app.api.routes.migrations.run_migrations_with_advisory_lock",
        lambda: calls.append("run"),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/internal/migrations/run",
            headers={"X-Backfill-Worker-Key": "worker_test_key"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "Migrations applied successfully",
    }
    assert calls == ["run"]


def test_auto_scheduler_generate_route_returns_completed_run(monkeypatch):
    captured: dict[str, object] = {}
    schedule_run = _schedule_run_read_fixture()

    async def fake_generate(
        _session,
        *,
        business_id,
        location_id,
        planning_window_start,
        planning_window_end,
        source_metadata,
        optimizer=None,
    ):
        captured["business_id"] = business_id
        captured["location_id"] = location_id
        captured["planning_window_start"] = planning_window_start
        captured["planning_window_end"] = planning_window_end
        captured["source_metadata"] = source_metadata
        captured["optimizer"] = optimizer
        return schedule_run

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr(
        "app.api.routes.internal.auto_scheduler.create_and_execute_schedule_run_for_scope",
        fake_generate,
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/internal/auto-scheduler/runs/generate",
                json={
                    "business_id": str(schedule_run.business_id),
                    "location_id": str(schedule_run.location_id),
                    "planning_window_start": "2026-04-20T07:00:00Z",
                    "planning_window_end": "2026-04-27T07:00:00Z",
                    "source_metadata": {"request_id": "req_123"},
                },
                headers={"X-Backfill-Worker-Key": "worker_test_key"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(schedule_run.id)
        assert payload["status"] == "completed"
        assert payload["run_metadata"]["scope_shift_count"] == 1
        assert captured["business_id"] == schedule_run.business_id
        assert captured["location_id"] == schedule_run.location_id
        assert captured["source_metadata"] == {"request_id": "req_123"}
    finally:
        app.dependency_overrides.clear()


def test_auto_scheduler_apply_route_returns_apply_record(monkeypatch):
    captured: dict[str, object] = {}
    schedule_run = _schedule_run_read_fixture()
    apply_record = _schedule_run_apply_fixture(schedule_run)

    async def fake_apply(_session, schedule_run_id):
        captured["schedule_run_id"] = schedule_run_id
        return apply_record

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr(
        "app.api.routes.internal.auto_scheduler.apply_schedule_run_from_live_scope",
        fake_apply,
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/internal/auto-scheduler/runs/{schedule_run.id}/apply",
                headers={"X-Backfill-Worker-Key": "worker_test_key"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(apply_record.id)
        assert payload["schedule_run_id"] == str(schedule_run.id)
        assert payload["status"] == "applied"
        assert payload["apply_metadata"]["applied_assignment_count"] == 1
        assert captured["schedule_run_id"] == schedule_run.id
    finally:
        app.dependency_overrides.clear()


def test_auto_scheduler_list_runs_route_returns_runs(monkeypatch):
    schedule_run = _schedule_run_read_fixture()
    captured: dict[str, object] = {}

    async def fake_list(_session, *, business_id, location_id=None, limit=25, status=None):
        captured["business_id"] = business_id
        captured["location_id"] = location_id
        captured["limit"] = limit
        captured["status"] = status
        return [schedule_run]

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr(
        "app.api.routes.internal.auto_scheduler.list_schedule_runs",
        fake_list,
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/internal/auto-scheduler/runs?business_id={schedule_run.business_id}&location_id={schedule_run.location_id}&status=completed&limit=10",
                headers={"X-Backfill-Worker-Key": "worker_test_key"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["id"] == str(schedule_run.id)
        assert payload[0]["status"] == "completed"
        assert captured["business_id"] == schedule_run.business_id
        assert captured["location_id"] == schedule_run.location_id
        assert captured["limit"] == 10
        assert captured["status"] == "completed"
    finally:
        app.dependency_overrides.clear()


def test_auto_scheduler_detail_route_returns_run_detail(monkeypatch):
    schedule_run = _schedule_run_detail_fixture()

    async def fake_get(_session, schedule_run_id):
        assert schedule_run_id == schedule_run.id
        return schedule_run

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr(
        "app.api.routes.internal.auto_scheduler.get_schedule_run_detail",
        fake_get,
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/internal/auto-scheduler/runs/{schedule_run.id}",
                headers={"X-Backfill-Worker-Key": "worker_test_key"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(schedule_run.id)
        assert payload["inputs"]["reliability_snapshot_hash"] == "sha256:reliability"
        assert payload["assignments"][0]["decision_rank"] == 1
        assert payload["rejections"][0]["rejection_reason_codes"] == ["lower_ranked_candidate"]
        assert payload["metrics"]["candidate_considered_count"] == 2
        assert payload["applies"][0]["status"] == "applied"
        assert payload["replay_run_ids"] == [str(schedule_run.replay_runs[0].id)]
    finally:
        app.dependency_overrides.clear()


def test_coverage_runtime_process_route_returns_service_batch_result(monkeypatch):
    captured: dict[str, int] = {}

    async def fake_process(_session, *, limit: int):
        captured["limit"] = limit
        return {
            "reconcile": {
                "claimed_count": 1,
                "filled_count": 0,
                "cancelled_count": 0,
                "exhausted_count": 0,
                "unchanged_count": 1,
                "failed_count": 0,
                "processed_case_ids": ["case_a"],
            },
            "offer_expiry": {
                "expired_count": 0,
                "exhausted_case_ids": [],
                "advanced_offer_ids": [],
            },
            "queued_cases": {
                "claimed_count": 1,
                "executed_count": 1,
                "exhausted_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "processed_case_ids": ["case_b"],
            },
            "delivery": {
                "claimed_count": 1,
                "sent_count": 1,
                "failed_count": 0,
                "processed_event_ids": ["evt_1"],
            },
            "processed_case_ids": ["case_a", "case_b"],
        }

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.coverage_runtime.process_coverage_runtime_batch", fake_process)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/internal/coverage/runtime/process",
            json={"limit": 7},
            headers={"X-Backfill-Worker-Key": "worker_test_key"},
        )
        assert response.status_code == 200
        assert captured["limit"] == 7
        assert response.json() == {
            "reconcile": {
                "claimed_count": 1,
                "filled_count": 0,
                "cancelled_count": 0,
                "exhausted_count": 0,
                "unchanged_count": 1,
                "failed_count": 0,
                "processed_case_ids": ["case_a"],
            },
            "offer_expiry": {
                "expired_count": 0,
                "exhausted_case_ids": [],
                "advanced_offer_ids": [],
            },
            "queued_cases": {
                "claimed_count": 1,
                "executed_count": 1,
                "exhausted_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "processed_case_ids": ["case_b"],
            },
            "delivery": {
                "claimed_count": 1,
                "sent_count": 1,
                "failed_count": 0,
                "processed_event_ids": ["evt_1"],
            },
            "processed_case_ids": ["case_a", "case_b"],
        }
    finally:
        app.dependency_overrides.clear()


def test_coverage_runtime_process_route_returns_503_when_worker_key_not_configured(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key=""),
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/internal/coverage/runtime/process",
                json={"limit": 3},
                headers={"X-Backfill-Worker-Key": "anything"},
            )
        assert response.status_code == 503
        assert response.json() == {"detail": "worker_api_key_not_configured"}
    finally:
        app.dependency_overrides.clear()


def test_runtime_tick_route_rejects_invalid_worker_key(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/internal/runtime/tick",
            json={"limit": 5},
            headers={"X-Backfill-Worker-Key": "wrong_key"},
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "worker_auth_failed"}
    finally:
        app.dependency_overrides.clear()


def test_runtime_tick_route_returns_orchestration_batch_result(monkeypatch):
    captured: dict[str, int] = {}

    async def fake_process(_session, *, limit: int):
        captured["limit"] = limit
        return {
            "status": "processed",
            "summary": {
                "callback_claimed_count": 1,
                "callback_processed_count": 1,
                "callback_failed_count": 0,
                "callback_dead_lettered_count": 0,
                "coverage_claimed_case_count": 2,
                "coverage_processed_case_count": 2,
                "offer_expiry_expired_count": 0,
                "offer_expiry_advanced_offer_count": 0,
                "offer_expiry_exhausted_case_count": 0,
                "delivery_claimed_count": 1,
                "projection_monitored_business_count": 1,
                "projection_blocked_business_count": 0,
                "projection_stale_employee_count": 0,
                "projection_missing_employee_count": 0,
                "total_failed_count": 0,
            },
            "callbacks": {
                "claimed_count": 1,
                "processed_count": 1,
                "failed_count": 0,
                "dead_lettered_count": 0,
                "processed_callback_ids": ["cb_1"],
            },
            "runtime_projections": {
                "status": "ready",
                "checked_at": "2026-04-10T20:00:00Z",
                "freshness_target_seconds": 900,
                "monitored_business_count": 1,
                "candidate_employee_count": 4,
                "fresh_employee_count": 4,
                "stale_employee_count": 0,
                "missing_employee_count": 0,
                "blocked_business_count": 0,
                "blocked_business_ids": [],
            },
            "coverage_runtime": {
                "reconcile": {
                    "claimed_count": 1,
                    "filled_count": 0,
                    "cancelled_count": 0,
                    "exhausted_count": 0,
                    "unchanged_count": 1,
                    "failed_count": 0,
                    "processed_case_ids": ["case_a"],
                },
                "offer_expiry": {
                    "expired_count": 0,
                    "exhausted_case_ids": [],
                    "advanced_offer_ids": [],
                },
                "queued_cases": {
                    "claimed_count": 1,
                    "executed_count": 1,
                    "exhausted_count": 0,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "processed_case_ids": ["case_b"],
                },
                "delivery": {
                    "claimed_count": 1,
                    "sent_count": 1,
                    "failed_count": 0,
                    "processed_event_ids": ["evt_1"],
                },
                "processed_case_ids": ["case_a", "case_b"],
            },
        }

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.runtime_orchestration.process_runtime_tick", fake_process)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/internal/runtime/tick",
            json={"limit": 9},
            headers={"X-Backfill-Worker-Key": "worker_test_key"},
        )
        assert response.status_code == 200
        assert captured["limit"] == 9
        assert response.json() == {
            "status": "processed",
            "summary": {
                "callback_claimed_count": 1,
                "callback_processed_count": 1,
                "callback_failed_count": 0,
                "callback_dead_lettered_count": 0,
                "coverage_claimed_case_count": 2,
                "coverage_processed_case_count": 2,
                "offer_expiry_expired_count": 0,
                "offer_expiry_advanced_offer_count": 0,
                "offer_expiry_exhausted_case_count": 0,
                "delivery_claimed_count": 1,
                "projection_monitored_business_count": 1,
                "projection_blocked_business_count": 0,
                "projection_stale_employee_count": 0,
                "projection_missing_employee_count": 0,
                "total_failed_count": 0,
            },
            "callbacks": {
                "claimed_count": 1,
                "processed_count": 1,
                "failed_count": 0,
                "dead_lettered_count": 0,
                "processed_callback_ids": ["cb_1"],
            },
            "runtime_projections": {
                "status": "ready",
                "checked_at": "2026-04-10T20:00:00Z",
                "freshness_target_seconds": 900,
                "monitored_business_count": 1,
                "candidate_employee_count": 4,
                "fresh_employee_count": 4,
                "stale_employee_count": 0,
                "missing_employee_count": 0,
                "blocked_business_count": 0,
                "blocked_business_ids": [],
            },
            "coverage_runtime": {
                "reconcile": {
                    "claimed_count": 1,
                    "filled_count": 0,
                    "cancelled_count": 0,
                    "exhausted_count": 0,
                    "unchanged_count": 1,
                    "failed_count": 0,
                    "processed_case_ids": ["case_a"],
                },
                "offer_expiry": {
                    "expired_count": 0,
                    "exhausted_case_ids": [],
                    "advanced_offer_ids": [],
                },
                "queued_cases": {
                    "claimed_count": 1,
                    "executed_count": 1,
                    "exhausted_count": 0,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "processed_case_ids": ["case_b"],
                },
                "delivery": {
                    "claimed_count": 1,
                    "sent_count": 1,
                    "failed_count": 0,
                    "processed_event_ids": ["evt_1"],
                },
                "processed_case_ids": ["case_a", "case_b"],
            },
        }
    finally:
        app.dependency_overrides.clear()


def test_coverage_invariants_route_returns_scan_result(monkeypatch):
    async def fake_scan(_session, *, limit_per_code: int):
        assert limit_per_code == 12
        return {
            "checked_at": "2026-04-17T20:00:00Z",
            "issue_count": 2,
            "counts_by_code": {
                "employee_missing_availability_rules": 1,
                "coverage_case_terminal_with_actionable_offers": 1,
            },
            "counts_by_severity": {
                "high": 2,
            },
            "issues": [
                {
                    "code": "employee_missing_availability_rules",
                    "severity": "high",
                    "aggregate_type": "employee",
                    "aggregate_id": str(uuid4()),
                    "message": "Active employee has no recurring availability rules.",
                    "metadata": {"employee_name": "Taylor Smith"},
                },
                {
                    "code": "coverage_case_terminal_with_actionable_offers",
                    "severity": "high",
                    "aggregate_type": "coverage_case",
                    "aggregate_id": str(uuid4()),
                    "message": "Terminal coverage case still has actionable offers.",
                    "metadata": {"offer_ids": [str(uuid4())]},
                },
            ],
        }

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.invariants.scan_scheduler_coverage_invariants", fake_scan)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/internal/coverage/invariants?limit_per_code=12",
                headers={"X-Backfill-Worker-Key": "worker_test_key"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["issue_count"] == 2
        assert body["counts_by_code"]["employee_missing_availability_rules"] == 1
        assert body["issues"][0]["severity"] == "high"
    finally:
        app.dependency_overrides.clear()


def test_provider_callback_replay_route_returns_recovery_result(monkeypatch):
    callback_log_id = uuid4()

    async def fake_replay(_session, *, callback_log_id, mode):
        return {
            "callback_log_id": callback_log_id,
            "mode": mode,
            "action": "preview",
            "allowed": False,
            "reason_codes": ["callback_already_processed"],
            "warnings": [],
            "provider": "retell",
            "route_key": "retell_webhook",
            "status_before": "processed",
            "status_after": "processed",
            "error_message": None,
            "response_kind": None,
            "response_payload": {},
        }

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.recovery.replay_provider_callback_log", fake_replay)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/internal/providers/callbacks/{callback_log_id}/replay",
                json={"mode": "dry_run"},
                headers={"X-Backfill-Worker-Key": "worker_test_key"},
            )
        assert response.status_code == 200
        assert response.json() == {
            "callback_log_id": str(callback_log_id),
            "mode": "dry_run",
            "action": "preview",
            "allowed": False,
            "reason_codes": ["callback_already_processed"],
            "warnings": [],
            "provider": "retell",
            "route_key": "retell_webhook",
            "status_before": "processed",
            "status_after": "processed",
            "error_message": None,
            "response_kind": None,
            "response_payload": {},
        }
    finally:
        app.dependency_overrides.clear()


def test_coverage_outbox_replay_route_returns_recovery_result(monkeypatch):
    outbox_event_id = uuid4()
    offer_id = uuid4()
    coverage_case_id = uuid4()

    async def fake_replay(_session, *, outbox_event_id, mode):
        return {
            "outbox_event_id": outbox_event_id,
            "mode": mode,
            "action": "reprocessed",
            "allowed": True,
            "reason_codes": [],
            "warnings": [],
            "topic": "coverage.offer.created",
            "status_before": "failed",
            "status_after": "sent",
            "offer_id": offer_id,
            "coverage_case_id": coverage_case_id,
            "processed": True,
            "sent": True,
            "failed": False,
            "error_message": None,
            "result_payload": {"provider_message_id": "msg_123"},
        }

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.recovery.replay_coverage_outbox_event", fake_replay)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/internal/coverage/outbox/{outbox_event_id}/replay",
                json={"mode": "reprocess_if_preconditions_match"},
                headers={"X-Backfill-Worker-Key": "worker_test_key"},
            )
        assert response.status_code == 200
        assert response.json() == {
            "outbox_event_id": str(outbox_event_id),
            "mode": "reprocess_if_preconditions_match",
            "action": "reprocessed",
            "allowed": True,
            "reason_codes": [],
            "warnings": [],
            "topic": "coverage.offer.created",
            "status_before": "failed",
            "status_after": "sent",
            "offer_id": str(offer_id),
            "coverage_case_id": str(coverage_case_id),
            "processed": True,
            "sent": True,
            "failed": False,
            "error_message": None,
            "result_payload": {"provider_message_id": "msg_123"},
        }
    finally:
        app.dependency_overrides.clear()


def test_feed_projection_process_route_rejects_invalid_worker_key(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/internal/feed/projections/process",
            json={"limit": 5},
            headers={"X-Backfill-Worker-Key": "wrong_key"},
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "worker_auth_failed"}
    finally:
        app.dependency_overrides.clear()


def test_feed_projection_process_route_returns_service_batch_result(monkeypatch):
    captured: dict[str, int] = {}

    async def fake_process(_session, *, limit: int):
        captured["limit"] = limit
        return {
            "projection_name": "dashboard_activity_feed",
            "status": "processed",
            "claimed": True,
            "cursor_status": "idle",
            "processed_count": 2,
            "processed_source_event_ids": ["evt_1", "evt_2"],
            "latest_source_event_id": "evt_2",
            "latest_source_created_at": "2026-04-10T20:10:00Z",
        }

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.feed_projections.process_feed_projection_batch", fake_process)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/internal/feed/projections/process",
            json={"limit": 11},
            headers={"X-Backfill-Worker-Key": "worker_test_key"},
        )
        assert response.status_code == 200
        assert captured["limit"] == 11
        assert response.json() == {
            "projection_name": "dashboard_activity_feed",
            "status": "processed",
            "claimed": True,
            "cursor_status": "idle",
            "processed_count": 2,
            "processed_source_event_ids": ["evt_1", "evt_2"],
            "latest_source_event_id": "evt_2",
            "latest_source_created_at": "2026-04-10T20:10:00Z",
        }
    finally:
        app.dependency_overrides.clear()


def test_feed_projection_rebuild_route_returns_service_batch_result(monkeypatch):
    captured: dict[str, int] = {}

    async def fake_rebuild(_session, *, limit: int):
        captured["limit"] = limit
        return {
            "projection_name": "dashboard_activity_feed",
            "status": "processed",
            "claimed": True,
            "cursor_status": "idle",
            "deleted_count": 4,
            "processed_count": 3,
            "processed_source_event_ids": ["evt_3", "evt_4", "evt_5"],
            "latest_source_event_id": "evt_5",
            "latest_source_created_at": "2026-04-10T20:15:00Z",
        }

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.feed_projections.rebuild_feed_projection", fake_rebuild)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/internal/feed/projections/rebuild",
            json={"limit": 25},
            headers={"X-Backfill-Worker-Key": "worker_test_key"},
        )
        assert response.status_code == 200
        assert captured["limit"] == 25
        assert response.json() == {
            "projection_name": "dashboard_activity_feed",
            "status": "processed",
            "claimed": True,
            "cursor_status": "idle",
            "deleted_count": 4,
            "processed_count": 3,
            "processed_source_event_ids": ["evt_3", "evt_4", "evt_5"],
            "latest_source_event_id": "evt_5",
            "latest_source_created_at": "2026-04-10T20:15:00Z",
        }
    finally:
        app.dependency_overrides.clear()


def test_runtime_tick_route_returns_503_when_worker_key_not_configured(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key=""),
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/internal/runtime/tick",
                json={"limit": 3},
                headers={"X-Backfill-Worker-Key": "anything"},
            )
        assert response.status_code == 503
        assert response.json() == {"detail": "worker_api_key_not_configured"}
    finally:
        app.dependency_overrides.clear()


def test_list_provider_callback_logs_requires_valid_worker_key(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.get(
            "/api/internal/providers/callbacks",
            headers={"X-Backfill-Worker-Key": "wrong_key"},
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "worker_auth_failed"}
    finally:
        app.dependency_overrides.clear()


def test_list_provider_callback_logs_returns_filtered_rows(monkeypatch):
    now = datetime(2026, 4, 10, 20, 0, tzinfo=timezone.utc)
    row = ProviderCallbackLog(
        id=uuid4(),
        provider="retell",
        route_key="retell_webhook",
        event_type="function_call",
        provider_event_id="evt_123",
        dedupe_key="retell:evt_123",
        status="processed",
        headers={"x-retell-signature": "sig"},
        payload={"event": "function_call"},
        result_payload={"status": "ok"},
        error_message=None,
        received_at=now,
        processed_at=now,
        created_at=now,
        updated_at=now,
    )

    async def fake_list(_session, **kwargs):
        assert kwargs["provider"] == "retell"
        assert kwargs["route_key"] == "retell_webhook"
        assert kwargs["status"] == "processed"
        assert kwargs["event_type"] == "function_call"
        assert kwargs["provider_event_id"] == "evt_123"
        assert kwargs["dedupe_key"] == "retell:evt_123"
        assert kwargs["limit"] == 25
        return [row]

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.provider_callbacks.list_callback_logs", fake_list)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.get(
            "/api/internal/providers/callbacks"
            "?provider=retell&route_key=retell_webhook&status=processed"
            "&event_type=function_call&provider_event_id=evt_123&dedupe_key=retell:evt_123&limit=25",
            headers={"X-Backfill-Worker-Key": "worker_test_key"},
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(row.id),
                "provider": "retell",
                "route_key": "retell_webhook",
                "event_type": "function_call",
                "provider_event_id": "evt_123",
                "dedupe_key": "retell:evt_123",
                "status": "processed",
                "headers": {"x-retell-signature": "sig"},
                "payload": {"event": "function_call"},
                "result_payload": {"status": "ok"},
                "error_message": None,
                "received_at": "2026-04-10T20:00:00Z",
                "processed_at": "2026-04-10T20:00:00Z",
                "created_at": "2026-04-10T20:00:00Z",
                "updated_at": "2026-04-10T20:00:00Z",
            }
        ]
    finally:
        app.dependency_overrides.clear()


def test_get_provider_callback_log_returns_row(monkeypatch):
    now = datetime(2026, 4, 10, 20, 5, tzinfo=timezone.utc)
    callback_log_id = uuid4()
    row = ProviderCallbackLog(
        id=callback_log_id,
        provider="twilio",
        route_key="twilio_sms_status",
        event_type="delivered",
        provider_event_id="SM123",
        dedupe_key="twilio:SM123",
        status="processed",
        headers={},
        payload={"MessageSid": "SM123"},
        result_payload={"status": "delivered"},
        error_message=None,
        received_at=now,
        processed_at=now,
        created_at=now,
        updated_at=now,
    )

    async def fake_get(_session, **kwargs):
        assert kwargs["callback_log_id"] == callback_log_id
        return row

    monkeypatch.setattr(
        "app.api.routes.internal.settings",
        SimpleNamespace(worker_api_key="worker_test_key"),
    )
    monkeypatch.setattr("app.api.routes.internal.provider_callbacks.get_callback_log", fake_get)

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/internal/providers/callbacks/{callback_log_id}",
            headers={"X-Backfill-Worker-Key": "worker_test_key"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(callback_log_id)
        assert payload["provider"] == "twilio"
        assert payload["route_key"] == "twilio_sms_status"
        assert payload["result_payload"]["status"] == "delivered"
    finally:
        app.dependency_overrides.clear()
