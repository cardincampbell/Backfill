from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.auto_scheduler import ScheduleRun, ScheduleRunApply, ScheduleRunAssignment, ScheduleRunInput
from app.models.common import (
    MembershipRole,
    MembershipStatus,
    ScheduleApplyStatus,
    ScheduleRunStatus,
    ScheduleRunType,
    SessionRiskLevel,
)
from app.models.identity import Membership, Session, User
from app.services.auth import AuthContext
from app.services.schedule_weeks import schedule_week_window


class DummySchedulingSession:
    def __init__(self):
        self.commit_count = 0

    async def commit(self):
        self.commit_count += 1
        return None

    async def rollback(self):
        return None


async def _override_db():
    yield DummySchedulingSession()


def _make_auth_context(*, business_id, location_id) -> AuthContext:
    user = User(
        id=uuid4(),
        full_name="Owner User",
        email="owner@example.com",
        primary_phone_e164="+15555550100",
        is_phone_verified=True,
        onboarding_completed_at=datetime.now(timezone.utc),
        profile_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session = Session(
        id=uuid4(),
        user_id=user.id,
        token_hash="hashed",
        risk_level=SessionRiskLevel.low,
        elevated_actions=[],
        last_seen_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        session_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    membership = Membership(
        id=uuid4(),
        user_id=user.id,
        business_id=business_id,
        location_id=location_id,
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        accepted_at=datetime.now(timezone.utc),
        membership_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def _schedule_run_detail_fixture(*, business_id, location_id, week_start_date: date) -> ScheduleRun:
    now = datetime.now(timezone.utc)
    window = schedule_week_window("America/Los_Angeles", week_start_date)
    schedule_run = ScheduleRun(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        planning_window_start=window.starts_at,
        planning_window_end=window.ends_at,
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
    schedule_run.assignments = [
        ScheduleRunAssignment(
            id=uuid4(),
            schedule_run_id=schedule_run.id,
            shift_id=uuid4(),
            employee_id=uuid4(),
            decision_score=0.91,
            decision_rank=1,
            assignment_payload={"source": "optimizer"},
            created_at=now,
            updated_at=now,
        )
    ]
    schedule_run.rejections = []
    schedule_run.applies = []
    schedule_run.replay_runs = []
    return schedule_run


def test_ensure_predictive_schedule_route_returns_latest_matching_run(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    week_start_date = date(2026, 4, 20)
    auth_ctx = _make_auth_context(business_id=business_id, location_id=location_id)
    schedule_run = _schedule_run_detail_fixture(
        business_id=business_id,
        location_id=location_id,
        week_start_date=week_start_date,
    )
    created = {"count": 0}
    captured: dict[str, object] = {}

    async def override_auth():
        return auth_ctx

    async def fake_get_location(_session, _business_id, _location_id):
        assert _business_id == business_id
        assert _location_id == location_id
        return type("LocationStub", (), {"timezone": "America/Los_Angeles"})()

    async def fake_current_scope_snapshot_hash(_session, **_kwargs):
        captured["hash_kwargs"] = _kwargs
        return "sha256:authoring"

    async def fake_latest_schedule_run_for_scope(_session, **_kwargs):
        return schedule_run

    async def fake_create_and_execute_schedule_run_for_scope(*_args, **_kwargs):
        created["count"] += 1
        return schedule_run

    async def fake_get_schedule_run_detail(_session, schedule_run_id):
        assert schedule_run_id == schedule_run.id
        return schedule_run

    monkeypatch.setattr(
        "app.api.routes.scheduling.businesses_service.get_location",
        fake_get_location,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.current_scope_snapshot_hash",
        fake_current_scope_snapshot_hash,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.latest_schedule_run_for_scope",
        fake_latest_schedule_run_for_scope,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.create_and_execute_schedule_run_for_scope",
        fake_create_and_execute_schedule_run_for_scope,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.get_schedule_run_detail",
        fake_get_schedule_run_detail,
    )

    db_session = DummySchedulingSession()

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/businesses/{business_id}/locations/{location_id}/schedule-weeks/{week_start_date.isoformat()}/predictive-schedule"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(schedule_run.id)
        assert payload["status"] == "completed"
        assert payload["assignments"][0]["decision_rank"] == 1
        assert captured["hash_kwargs"]["generated_demand_payload"] == {"proposed_shifts": [], "metadata": {}}
        assert created["count"] == 0
    finally:
        app.dependency_overrides.clear()


def test_ensure_predictive_schedule_route_returns_compliance_summary(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    week_start_date = date(2026, 4, 20)
    auth_ctx = _make_auth_context(business_id=business_id, location_id=location_id)
    db_session = DummySchedulingSession()
    schedule_run = _schedule_run_detail_fixture(
        business_id=business_id,
        location_id=location_id,
        week_start_date=week_start_date,
    )
    assignment = schedule_run.assignments[0]
    schedule_run.inputs = ScheduleRunInput(
        schedule_run_id=schedule_run.id,
        shift_payload={"shifts": []},
        fixed_shift_payload={"shifts": []},
        generated_demand_payload={"proposed_shifts": [], "metadata": {}},
        employee_payload={"employees": []},
        availability_payload={},
        policy_payload={"publish_mode": "draft_only"},
        labor_payload={},
        compliance_payload={
            "employees_by_shift": {
                str(assignment.shift_id): {
                    str(assignment.employee_id): {
                        "status": "warning",
                        "profile_code": "ca_restaurant_v1",
                        "profile_display_name": "California restaurant baseline",
                        "profile_source_version": "ca_rule_pack_v3",
                        "profile_source_hash": "sha256:ca-pack",
                        "profile_source_urls": ["https://example.com/ca-rule-pack"],
                        "warning_rule_codes": ["meal_break_first_window"],
                        "premium_total_cents": 0,
                        "unresolved_premium_rule_codes": ["meal_break_first_window"],
                        "override_applied": False,
                        "override_artifact_id": None,
                        "rule_results": [
                            {
                                "rule_code": "meal_break_first_window",
                                "status": "warning",
                                "artifact_type_allowed": "meal_waiver",
                            }
                        ],
                    }
                }
            }
        },
        reliability_payload={"employees": []},
        reliability_snapshot_generated_at=schedule_run.created_at,
        reliability_snapshot_hash="sha256:reliability",
        reliability_snapshot_version="v1",
        source_metadata={"authoring_snapshot_hash": "sha256:authoring"},
        created_at=schedule_run.created_at,
        updated_at=schedule_run.updated_at,
    )
    schedule_run.applies = []
    created = {"count": 0}

    async def override_db():
        yield db_session

    async def override_auth():
        return auth_ctx

    async def fake_get_location(_session, _business_id, _location_id):
        return type("LocationStub", (), {"timezone": "America/Los_Angeles"})()

    async def fake_current_scope_snapshot_hash(_session, **_kwargs):
        return "sha256:authoring"

    async def fake_latest_schedule_run_for_scope(_session, **_kwargs):
        return schedule_run

    async def fake_create_and_execute_schedule_run_for_scope(*_args, **_kwargs):
        created["count"] += 1
        return schedule_run

    async def fake_get_schedule_run_detail(_session, schedule_run_id):
        assert schedule_run_id == schedule_run.id
        return schedule_run

    monkeypatch.setattr(
        "app.api.routes.scheduling.businesses_service.get_location",
        fake_get_location,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.current_scope_snapshot_hash",
        fake_current_scope_snapshot_hash,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.latest_schedule_run_for_scope",
        fake_latest_schedule_run_for_scope,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.create_and_execute_schedule_run_for_scope",
        fake_create_and_execute_schedule_run_for_scope,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.get_schedule_run_detail",
        fake_get_schedule_run_detail,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/businesses/{business_id}/locations/{location_id}/schedule-weeks/{week_start_date.isoformat()}/predictive-schedule"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["compliance_summary"]["selected_assignment_count"] == 1
        assert payload["compliance_summary"]["warning_assignment_count"] == 1
        assert payload["compliance_summary"]["override_eligible_warning_count"] == 1
        assert payload["compliance_summary"]["override_eligible_artifact_types"] == ["meal_waiver"]
        assert payload["compliance_summary"]["unresolved_premium_rule_codes"] == ["meal_break_first_window"]
        assert len(payload["compliance_review_items"]) == 1
        assert payload["compliance_review_items"][0]["shift_id"] == str(assignment.shift_id)
        assert payload["compliance_review_items"][0]["employee_id"] == str(assignment.employee_id)
        assert payload["compliance_review_items"][0]["override_eligible_artifact_types"] == ["meal_waiver"]
        assert payload["compliance_review_items"][0]["issues"][0]["rule_code"] == "meal_break_first_window"
        assert payload["compliance_review_items"][0]["issues"][0]["artifact_type_allowed"] == "meal_waiver"
        assert payload["compliance_review_items"][0]["issues"][0]["rule_source_references"] == [
            {
                "rule_code": "meal_break_first_window",
                "source_kind": "labor_rule_profile",
                "source_code": "ca_restaurant_v1",
                "source_label": "California restaurant baseline",
                "jurisdiction_code": None,
                "source_document_title": None,
                "source_urls": ["https://example.com/ca-rule-pack"],
                "source_version": "ca_rule_pack_v3",
                "source_hash": "sha256:ca-pack",
                "version_id": None,
                "payload_hash": None,
                "effective_at": None,
            }
        ]
        assert created["count"] == 0
        assert db_session.commit_count == 0
    finally:
        app.dependency_overrides.clear()


def test_ensure_predictive_schedule_route_commits_new_run(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    week_start_date = date(2026, 4, 27)
    auth_ctx = _make_auth_context(business_id=business_id, location_id=location_id)
    schedule_run = _schedule_run_detail_fixture(
        business_id=business_id,
        location_id=location_id,
        week_start_date=week_start_date,
    )
    db_session = DummySchedulingSession()

    async def override_auth():
        return auth_ctx

    async def override_db():
        yield db_session

    async def fake_get_location(_session, _business_id, _location_id):
        return type("LocationStub", (), {"timezone": "America/Los_Angeles"})()

    async def fake_current_scope_snapshot_hash(_session, **_kwargs):
        return "sha256:authoring"

    async def fake_latest_schedule_run_for_scope(_session, **_kwargs):
        return None

    async def fake_create_and_execute_schedule_run_for_scope(*_args, **_kwargs):
        return schedule_run

    async def fake_get_schedule_run_detail(_session, schedule_run_id):
        assert schedule_run_id == schedule_run.id
        return schedule_run

    monkeypatch.setattr(
        "app.api.routes.scheduling.businesses_service.get_location",
        fake_get_location,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.current_scope_snapshot_hash",
        fake_current_scope_snapshot_hash,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.latest_schedule_run_for_scope",
        fake_latest_schedule_run_for_scope,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.create_and_execute_schedule_run_for_scope",
        fake_create_and_execute_schedule_run_for_scope,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.get_schedule_run_detail",
        fake_get_schedule_run_detail,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/businesses/{business_id}/locations/{location_id}/schedule-weeks/{week_start_date.isoformat()}/predictive-schedule"
        )
        assert response.status_code == 200
        assert db_session.commit_count == 1
    finally:
        app.dependency_overrides.clear()


def test_apply_predictive_schedule_route_returns_apply_record(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    week_start_date = date(2026, 4, 20)
    auth_ctx = _make_auth_context(business_id=business_id, location_id=location_id)
    schedule_run = _schedule_run_detail_fixture(
        business_id=business_id,
        location_id=location_id,
        week_start_date=week_start_date,
    )
    now = datetime.now(timezone.utc)
    apply_record = ScheduleRunApply(
        id=uuid4(),
        schedule_run_id=schedule_run.id,
        business_id=business_id,
        location_id=location_id,
        planning_window_start=schedule_run.planning_window_start,
        planning_window_end=schedule_run.planning_window_end,
        status=ScheduleApplyStatus.applied,
        target_snapshot_hash="sha256:authoring",
        current_snapshot_hash="sha256:authoring",
        stale_reason=None,
        apply_metadata={"applied_assignment_count": 1},
        applied_at=now,
        created_at=now,
        updated_at=now,
    )

    async def override_auth():
        return auth_ctx

    async def fake_get_location(_session, _business_id, _location_id):
        return type("LocationStub", (), {"timezone": "America/Los_Angeles"})()

    async def fake_load_schedule_run(_session, schedule_run_id):
        assert schedule_run_id == schedule_run.id
        return schedule_run

    async def fake_apply_schedule_run_from_live_scope(_session, schedule_run_id):
        assert schedule_run_id == schedule_run.id
        return apply_record

    monkeypatch.setattr(
        "app.api.routes.scheduling.businesses_service.get_location",
        fake_get_location,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.load_schedule_run",
        fake_load_schedule_run,
    )
    monkeypatch.setattr(
        "app.api.routes.scheduling.auto_scheduler.apply_schedule_run_from_live_scope",
        fake_apply_schedule_run_from_live_scope,
    )

    db_session = DummySchedulingSession()

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/businesses/{business_id}/locations/{location_id}/schedule-weeks/{week_start_date.isoformat()}/predictive-schedule/{schedule_run.id}/apply"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "applied"
        assert payload["schedule_run_id"] == str(schedule_run.id)
        assert db_session.commit_count == 1
    finally:
        app.dependency_overrides.clear()
