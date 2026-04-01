from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app_v2.models.common import (
    AssignmentStatus,
    CoverageCaseStatus,
    CoverageRunStatus,
    CoverageOperatingMode,
    OfferStatus,
    OutboxStatus,
    ShiftStatus,
)
from app_v2.models.business import Business, LocationRole
from app_v2.models.coverage import (
    CoverageCase,
    CoverageCandidate,
    CoverageCaseRun,
    CoverageContactAttempt,
    CoverageOffer,
    CoverageOfferResponse,
    OutboxEvent,
)
from app_v2.models.scheduling import Shift, ShiftAssignment
from app_v2.schemas.coverage import (
    CoverageCandidatePreview,
    CoverageOfferResponseCreate,
    Phase1ExecutionRequest,
)
from app_v2.services import coverage


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarResult(self._values)


class FakeCoverageSession:
    def __init__(
        self,
        *,
        shift: Shift,
        case: CoverageCase,
        offer: CoverageOffer | None = None,
        business: Business | None = None,
        location_role: LocationRole | None = None,
        run: CoverageCaseRun | None = None,
    ):
        self.shift = shift
        self.case = case
        self.offer = offer
        self.business = business
        self.location_role = location_role
        self.run = run
        self.added: list[object] = []
        self.execute_queue: list[list[object]] = []
        self.scalar_queue: list[object] = []

    async def get(self, model, object_id):
        if model is Shift and object_id == self.shift.id:
            return self.shift
        if model is CoverageCase and object_id == self.case.id:
            return self.case
        if model is CoverageOffer and self.offer is not None and object_id == self.offer.id:
            return self.offer
        if model is CoverageCaseRun and self.run is not None and object_id == self.run.id:
            return self.run
        if model is Business and self.business is not None and object_id == self.business.id:
            return self.business
        return None

    async def scalar(self, query):
        descriptions = getattr(query, "column_descriptions", [])
        entity = descriptions[0].get("entity") if descriptions else None
        if entity is Shift:
            return self.shift
        if entity is LocationRole:
            return self.location_role
        if entity is CoverageContactAttempt:
            return None
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return 0

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)


@pytest.mark.asyncio
async def test_execute_phase_1_run_persists_run_candidates_offers(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    employee_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=datetime.now(timezone.utc) + timedelta(hours=6),
        ends_at=datetime.now(timezone.utc) + timedelta(hours=14),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.queued,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    business = Business(
        id=business_id,
        legal_name="Casa Vega LLC",
        brand_name="Casa Vega",
        slug="casa-vega",
        timezone="America/Los_Angeles",
        settings={},
        place_metadata={},
    )
    session = FakeCoverageSession(shift=shift, case=case, business=business)
    session.scalar_queue = [0]

    ranked = [
        CoverageCandidatePreview(
            employee_id=employee_id,
            employee_name="Taylor Smith",
            phone_e164="+15555550100",
            home_location_id=location_id,
            rank=1,
            score=92.0,
            scoring_factors={"total": 92.0},
            availability_snapshot={"rule_match": True},
        )
    ]

    async def fake_collect_phase_1_candidates(_session, _business_id, _shift_id):
        return shift, ranked

    monkeypatch.setattr(coverage, "_collect_phase_1_candidates", fake_collect_phase_1_candidates)

    result = await coverage.execute_phase_1_run(
        session,
        business_id,
        case_id,
        Phase1ExecutionRequest(dispatch_limit=1, channel="sms", offer_ttl_minutes=10),
    )

    runs = [obj for obj in session.added if isinstance(obj, CoverageCaseRun)]
    candidates = [obj for obj in session.added if isinstance(obj, CoverageCandidate)]
    offers = [obj for obj in session.added if isinstance(obj, CoverageOffer)]
    outbox = [obj for obj in session.added if isinstance(obj, OutboxEvent)]

    assert result.run.phase_no == 1
    assert result.run.status == CoverageRunStatus.completed
    assert result.plan.operating_mode == CoverageOperatingMode.standard_queue
    assert result.plan.dispatch_limit == 1
    assert result.candidate_count == 1
    assert len(candidates) == 1
    assert len(offers) == 1
    assert offers[0].status == OfferStatus.pending
    assert offers[0].offer_metadata["operating_mode"] == CoverageOperatingMode.standard_queue
    assert len(outbox) == 1
    assert outbox[0].status == OutboxStatus.pending
    assert result.coverage_case.status == CoverageCaseStatus.running
    assert runs


@pytest.mark.asyncio
async def test_respond_to_offer_accepts_and_assigns_shift():
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    offer_id = uuid4()
    sibling_id = uuid4()
    employee_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=datetime.now(timezone.utc) + timedelta(hours=6),
        ends_at=datetime.now(timezone.utc) + timedelta(hours=14),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.running,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    offer = CoverageOffer(
        id=offer_id,
        coverage_case_id=case_id,
        employee_id=employee_id,
        channel="sms",
        status=OfferStatus.pending,
        idempotency_key="offer-main",
        offer_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    sibling = CoverageOffer(
        id=sibling_id,
        coverage_case_id=case_id,
        employee_id=uuid4(),
        channel="sms",
        status=OfferStatus.pending,
        idempotency_key="offer-sibling",
        offer_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    session = FakeCoverageSession(shift=shift, case=case, offer=offer)
    session.execute_queue = [[sibling]]

    result = await coverage.respond_to_offer(
        session,
        business_id,
        offer_id,
        CoverageOfferResponseCreate(response="accepted", response_channel="web"),
    )

    assignments = [obj for obj in session.added if isinstance(obj, ShiftAssignment)]
    responses = [obj for obj in session.added if isinstance(obj, CoverageOfferResponse)]

    assert responses
    assert assignments
    assert assignments[0].status == AssignmentStatus.accepted
    assert offer.status == OfferStatus.accepted
    assert sibling.status == OfferStatus.cancelled
    assert shift.status == ShiftStatus.covered
    assert shift.seats_filled == 1
    assert case.status == CoverageCaseStatus.filled
    assert result.assignment_id == assignments[0].id
    assert result.assignment_status == AssignmentStatus.accepted


@pytest.mark.asyncio
async def test_respond_to_offer_decline_dispatches_next_ranked_offer():
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    run_id = uuid4()
    offer_id = uuid4()
    employee_id = uuid4()
    next_employee_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=datetime.now(timezone.utc) + timedelta(hours=6),
        ends_at=datetime.now(timezone.utc) + timedelta(hours=14),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.running,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    offer = CoverageOffer(
        id=offer_id,
        coverage_case_id=case_id,
        coverage_case_run_id=run_id,
        employee_id=employee_id,
        channel="sms",
        status=OfferStatus.pending,
        idempotency_key="offer-main",
        offer_metadata={"phase_no": 1},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    next_candidate = CoverageCandidate(
        id=uuid4(),
        coverage_case_run_id=run_id,
        employee_id=next_employee_id,
        rank=2,
        score=80.0,
        qualification_status="qualified",
        exclusion_reasons=[],
        scoring_factors={"total": 80.0},
        availability_snapshot={"rule_match": True},
        candidate_metadata={"employee_name": "Next Person"},
    )

    run = CoverageCaseRun(
        id=run_id,
        coverage_case_id=case_id,
        phase_no=1,
        strategy="phase_1_sequential_compressed",
        status=CoverageRunStatus.completed,
        run_metadata={"offer_ttl_minutes": 2, "operating_mode": CoverageOperatingMode.compressed_queue},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session = FakeCoverageSession(shift=shift, case=case, offer=offer, run=run)
    session.execute_queue = [[]]
    session.scalar_queue = [next_candidate]

    result = await coverage.respond_to_offer(
        session,
        business_id,
        offer_id,
        CoverageOfferResponseCreate(response="declined", response_channel="web"),
    )

    offers = [obj for obj in session.added if isinstance(obj, CoverageOffer)]
    outbox = [obj for obj in session.added if isinstance(obj, OutboxEvent)]

    assert offer.status == OfferStatus.declined
    assert len(offers) == 1
    assert offers[0].employee_id == next_employee_id
    assert offers[0].status == OfferStatus.pending
    assert offers[0].offer_metadata["operating_mode"] == CoverageOperatingMode.compressed_queue
    assert len(outbox) == 1
    assert case.status == CoverageCaseStatus.running
    assert result.coverage_case.status == CoverageCaseStatus.running


@pytest.mark.asyncio
async def test_execute_phase_2_run_requires_exhaustion_or_opt_in(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=datetime.now(timezone.utc) + timedelta(hours=3),
        ends_at=datetime.now(timezone.utc) + timedelta(hours=11),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.queued,
        phase_target="phase_2",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    business = Business(
        id=business_id,
        legal_name="Casa Vega LLC",
        brand_name="Casa Vega",
        slug="casa-vega",
        timezone="America/Los_Angeles",
        settings={},
        place_metadata={},
    )
    session = FakeCoverageSession(shift=shift, case=case, business=business)

    async def fake_collect_phase_1_candidates(_session, _business_id, _shift_id):
        return shift, [
            CoverageCandidatePreview(
                employee_id=uuid4(),
                employee_name="Local Candidate",
                rank=1,
                score=91.0,
            )
        ]

    async def fake_collect_phase_2_candidates(_session, _business_id, _shift_id):
        return shift, []

    monkeypatch.setattr(coverage, "_collect_phase_1_candidates", fake_collect_phase_1_candidates)
    monkeypatch.setattr(coverage, "_collect_phase_2_candidates", fake_collect_phase_2_candidates)

    with pytest.raises(ValueError, match="phase_2_not_allowed:phase_1_candidates_available"):
        await coverage.execute_phase_2_run(
            session,
            business_id,
            case_id,
            coverage.Phase2ExecutionRequest(channel="sms"),
        )


@pytest.mark.asyncio
async def test_execute_phase_2_run_uses_blast_mode_when_urgent(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    employee_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=datetime.now(timezone.utc) + timedelta(minutes=35),
        ends_at=datetime.now(timezone.utc) + timedelta(hours=8),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
        premium_cents=900,
    )
    case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.queued,
        phase_target="phase_2",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    business = Business(
        id=business_id,
        legal_name="Casa Vega LLC",
        brand_name="Casa Vega",
        slug="casa-vega",
        timezone="America/Los_Angeles",
        settings={},
        place_metadata={},
    )
    session = FakeCoverageSession(shift=shift, case=case, business=business)
    session.scalar_queue = [0]

    ranked = [
        CoverageCandidatePreview(
            employee_id=employee_id,
            employee_name="Cross Location Candidate",
            home_location_id=uuid4(),
            rank=1,
            score=88.0,
            source="phase_2",
            scoring_factors={"total": 88.0},
            availability_snapshot={"rule_match": True},
        )
    ]

    async def fake_collect_phase_1_candidates(_session, _business_id, _shift_id):
        return shift, []

    async def fake_collect_phase_2_candidates(_session, _business_id, _shift_id):
        return shift, ranked

    monkeypatch.setattr(coverage, "_collect_phase_1_candidates", fake_collect_phase_1_candidates)
    monkeypatch.setattr(coverage, "_collect_phase_2_candidates", fake_collect_phase_2_candidates)

    result = await coverage.execute_phase_2_run(
        session,
        business_id,
        case_id,
        coverage.Phase2ExecutionRequest(channel="sms"),
    )

    offers = [obj for obj in session.added if isinstance(obj, CoverageOffer)]
    assert result.plan.operating_mode == CoverageOperatingMode.blast
    assert result.plan.dispatch_limit == 5
    assert result.plan.premium_cents == 900
    assert offers[0].offer_metadata["premium_cents"] == 900
    assert offers[0].offer_metadata["operating_mode"] == CoverageOperatingMode.blast


@pytest.mark.asyncio
async def test_plan_coverage_case_execution_prefers_phase_1_when_available(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=datetime.now(timezone.utc) + timedelta(hours=5),
        ends_at=datetime.now(timezone.utc) + timedelta(hours=13),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.queued,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    business = Business(
        id=business_id,
        legal_name="Casa Vega LLC",
        brand_name="Casa Vega",
        slug="casa-vega",
        timezone="America/Los_Angeles",
        settings={},
        place_metadata={},
    )
    session = FakeCoverageSession(shift=shift, case=case, business=business)

    async def fake_collect_phase_1_candidates(_session, _business_id, _shift_id):
        return shift, [CoverageCandidatePreview(employee_id=uuid4(), employee_name="Local One", rank=1, score=81.0)]

    async def fake_collect_phase_2_candidates(_session, _business_id, _shift_id):
        return shift, [CoverageCandidatePreview(employee_id=uuid4(), employee_name="Cross One", rank=1, score=70.0)]

    monkeypatch.setattr(coverage, "_collect_phase_1_candidates", fake_collect_phase_1_candidates)
    monkeypatch.setattr(coverage, "_collect_phase_2_candidates", fake_collect_phase_2_candidates)

    decision = await coverage.plan_coverage_case_execution(session, business_id, case_id)

    assert decision.recommended_phase == "phase_1"
    assert decision.recommendation_reason == "phase_1_candidates_available"
    assert decision.phase_1_candidate_count == 1
    assert decision.phase_2_plan.phase_2_eligible is False


@pytest.mark.asyncio
async def test_execute_next_coverage_phase_exhausts_case_when_no_candidates(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=datetime.now(timezone.utc) + timedelta(hours=2),
        ends_at=datetime.now(timezone.utc) + timedelta(hours=10),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.queued,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    business = Business(
        id=business_id,
        legal_name="Casa Vega LLC",
        brand_name="Casa Vega",
        slug="casa-vega",
        timezone="America/Los_Angeles",
        settings={},
        place_metadata={},
    )
    session = FakeCoverageSession(shift=shift, case=case, business=business)

    async def fake_collect_phase_1_candidates(_session, _business_id, _shift_id):
        return shift, []

    async def fake_collect_phase_2_candidates(_session, _business_id, _shift_id):
        return shift, []

    monkeypatch.setattr(coverage, "_collect_phase_1_candidates", fake_collect_phase_1_candidates)
    monkeypatch.setattr(coverage, "_collect_phase_2_candidates", fake_collect_phase_2_candidates)

    result = await coverage.execute_next_coverage_phase(
        session,
        business_id,
        case_id,
        coverage.CoverageExecutionDispatchRequest(channel="sms"),
    )

    assert result.phase_executed is None
    assert result.decision.recommended_phase is None
    assert result.decision.recommendation_reason == "phase_2_no_candidates"
    assert result.coverage_case.status == CoverageCaseStatus.exhausted
