from __future__ import annotations

import pytest

from app_v2.config import V2Settings, _database_url_from_env


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("postgresql://postgres:secret@db.example.com:5432/backfill", "postgresql://postgres:secret@db.example.com:5432/backfill"),
        (" postgresql://postgres:secret@db.example.com:5432/backfill", "postgresql://postgres:secret@db.example.com:5432/backfill"),
        ('"postgresql://postgres:secret@db.example.com:5432/backfill"', "postgresql://postgres:secret@db.example.com:5432/backfill"),
        ("'postgresql://postgres:secret@db.example.com:5432/backfill'", "postgresql://postgres:secret@db.example.com:5432/backfill"),
    ],
)
def test_database_url_from_env_normalizes_whitespace_and_quotes(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    expected: str,
) -> None:
    monkeypatch.delenv("V2_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", raw_value)

    assert _database_url_from_env() == expected
    assert V2Settings().database_url == expected


def test_database_url_prefers_v2_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("V2_DATABASE_URL", '"postgresql://postgres:v2@db.example.com:5432/backfill_v2"')
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:v1@db.example.com:5432/backfill_v1")

    assert _database_url_from_env() == "postgresql://postgres:v2@db.example.com:5432/backfill_v2"
    assert V2Settings().database_url == "postgresql://postgres:v2@db.example.com:5432/backfill_v2"
