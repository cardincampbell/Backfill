from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.demand_features import PosSalesFact
from app.services import pos_sales


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self):
        self.added: list[object] = []
        self.flush_count = 0
        self.execute_rows: list[object] = []
        self.execute_responses: list[list[object]] = []
        self.execute_count = 0

    def add(self, instance):
        now = datetime.now(timezone.utc)
        if getattr(instance, "id", None) is None:
            instance.id = uuid4()
        if hasattr(instance, "created_at") and getattr(instance, "created_at", None) is None:
            instance.created_at = now
        if hasattr(instance, "updated_at") and getattr(instance, "updated_at", None) is None:
            instance.updated_at = now
        self.added.append(instance)

    async def flush(self):
        self.flush_count += 1

    async def execute(self, _stmt):
        self.execute_count += 1
        if self.execute_responses:
            return _FakeExecuteResult(self.execute_responses.pop(0))
        return _FakeExecuteResult(self.execute_rows)


def _payload(**overrides):
    base = {
        "business_id": uuid4(),
        "location_id": uuid4(),
        "provider": "toast",
        "provider_account_id": "acct_123",
        "provider_location_id": "loc_456",
        "observed_at": datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
        "bucket_start": datetime(2026, 4, 21, 15, 0, tzinfo=timezone.utc),
        "bucket_end": datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
        "gross_sales_cents": 42500,
        "net_sales_cents": 39125,
        "order_count": 17,
        "guest_count": 24,
        "refund_count": 1,
        "source_payload": {"provider_record_id": "bucket_2026-04-21T15:00:00Z"},
    }
    base.update(overrides)
    return base


def test_build_pos_sales_fact_dedupe_key_is_stable():
    payload_one = _payload(
        source_payload={
            "provider_record_id": "bucket_2026-04-21T15:00:00Z",
            "nested": {"a": 1, "b": 2},
        }
    )
    payload_two = _payload(
        source_payload={
            "nested": {"b": 2, "a": 1},
            "provider_record_id": "bucket_2026-04-21T15:00:00Z",
        }
    )

    key_one = pos_sales.build_pos_sales_fact_dedupe_key(payload_one)
    key_two = pos_sales.build_pos_sales_fact_dedupe_key(payload_two)

    assert key_one.startswith("sha256:")
    assert key_one == key_two


@pytest.mark.asyncio
async def test_upsert_pos_sales_fact_persists_new_row():
    session = _FakeSession()
    payload = _payload()

    row = await pos_sales.upsert_pos_sales_fact(session, payload)

    assert row.business_id == payload["business_id"]
    assert row.location_id == payload["location_id"]
    assert row.provider == "toast"
    assert row.gross_sales_cents == 42500
    assert row.net_sales_cents == 39125
    assert row.order_count == 17
    assert row.guest_count == 24
    assert row.refund_count == 1
    assert row.dedupe_key.startswith("sha256:")
    assert row.source_payload["provider_record_id"] == "bucket_2026-04-21T15:00:00Z"
    assert session.added[-1] is row
    assert session.flush_count == 1
    assert session.execute_count == 1


@pytest.mark.asyncio
async def test_upsert_pos_sales_fact_updates_existing_row_on_correction():
    session = _FakeSession()
    existing = PosSalesFact(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        provider="toast",
        provider_account_id="acct_old",
        provider_location_id="loc_old",
        observed_at=datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
        bucket_start=datetime(2026, 4, 21, 15, 0, tzinfo=timezone.utc),
        bucket_end=datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
        gross_sales_cents=100,
        net_sales_cents=90,
        order_count=1,
        guest_count=2,
        refund_count=0,
        source_payload={"provider_record_id": "bucket_2026-04-21T15:00:00Z"},
        ingested_at=datetime(2026, 4, 21, 16, 1, tzinfo=timezone.utc),
        dedupe_key="sha256:existing",
    )
    session.execute_rows = [existing]

    row = await pos_sales.upsert_pos_sales_fact(
        session,
        _payload(
            business_id=existing.business_id,
            location_id=existing.location_id,
            provider_account_id="acct_new",
            provider_location_id="loc_new",
            gross_sales_cents=50000,
            net_sales_cents=47000,
            order_count=20,
            guest_count=28,
            refund_count=2,
        ),
    )

    assert row is existing
    assert row.provider_account_id == "acct_new"
    assert row.provider_location_id == "loc_new"
    assert row.gross_sales_cents == 50000
    assert row.net_sales_cents == 47000
    assert row.order_count == 20
    assert row.guest_count == 28
    assert row.refund_count == 2
    assert session.added == []
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_upsert_pos_sales_facts_dedupes_duplicate_rows_inside_batch():
    session = _FakeSession()
    payload = _payload()
    session.execute_responses = [[], []]

    rows = await pos_sales.upsert_pos_sales_facts(
        session,
        [
            payload,
            {
                **payload,
                "net_sales_cents": 40500,
                "order_count": 18,
            },
        ],
    )

    assert len(rows) == 1
    assert rows[0].net_sales_cents == 40500
    assert rows[0].order_count == 18
    assert session.execute_count == 1
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_list_pos_sales_facts_returns_rows():
    session = _FakeSession()
    row = PosSalesFact(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        provider="toast",
        provider_account_id="acct_123",
        provider_location_id="loc_456",
        observed_at=datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
        bucket_start=datetime(2026, 4, 21, 15, 0, tzinfo=timezone.utc),
        bucket_end=datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
        gross_sales_cents=42500,
        net_sales_cents=39125,
        order_count=17,
        guest_count=24,
        refund_count=1,
        source_payload={},
        ingested_at=datetime(2026, 4, 21, 16, 5, tzinfo=timezone.utc),
        dedupe_key="sha256:test",
    )
    session.execute_rows = [row]

    rows = await pos_sales.list_pos_sales_facts(
        session,
        business_id=row.business_id,
        location_id=row.location_id,
        provider=row.provider,
        bucket_start=datetime(2026, 4, 21, 15, 0, tzinfo=timezone.utc),
        bucket_end=datetime(2026, 4, 21, 17, 0, tzinfo=timezone.utc),
    )

    assert rows == [row]


def test_summarize_pos_sales_by_local_bucket_builds_trailing_means():
    location_id = uuid4()
    rows = [
        PosSalesFact(
            id=uuid4(),
            business_id=uuid4(),
            location_id=location_id,
            provider="toast",
            provider_account_id="acct_123",
            provider_location_id="loc_456",
            observed_at=datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc),
            bucket_start=datetime(2026, 4, 14, 15, 0, tzinfo=timezone.utc),
            bucket_end=datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc),
            gross_sales_cents=30000,
            net_sales_cents=27000,
            order_count=12,
            guest_count=18,
            refund_count=1,
            source_payload={},
            ingested_at=datetime(2026, 4, 14, 16, 5, tzinfo=timezone.utc),
            dedupe_key="sha256:one",
        ),
        PosSalesFact(
            id=uuid4(),
            business_id=uuid4(),
            location_id=location_id,
            provider="toast",
            provider_account_id="acct_123",
            provider_location_id="loc_456",
            observed_at=datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
            bucket_start=datetime(2026, 4, 21, 15, 0, tzinfo=timezone.utc),
            bucket_end=datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
            gross_sales_cents=50000,
            net_sales_cents=46000,
            order_count=20,
            guest_count=30,
            refund_count=2,
            source_payload={},
            ingested_at=datetime(2026, 4, 21, 16, 5, tzinfo=timezone.utc),
            dedupe_key="sha256:two",
        ),
    ]

    summaries = pos_sales.summarize_pos_sales_by_local_bucket(
        rows,
        timezone_name="America/Los_Angeles",
        bucket_minutes=60,
    )

    key = (str(location_id), 1, 8, 60)
    assert summaries[key]["pos_sales_sample_count_28d"] == 2
    assert summaries[key]["pos_gross_sales_cents_mean_28d"] == 40000
    assert summaries[key]["pos_net_sales_cents_mean_28d"] == 36500
    assert summaries[key]["pos_order_count_mean_28d"] == 16.0
    assert summaries[key]["pos_guest_count_mean_28d"] == 24.0
    assert summaries[key]["pos_refund_count_mean_28d"] == 1.5
