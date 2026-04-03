from __future__ import annotations

import pytest

from app.config import Settings, _database_url_from_env


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
    monkeypatch.setenv("DATABASE_URL", raw_value)

    assert _database_url_from_env() == expected
    assert Settings().database_url == expected


def test_database_url_reads_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        '"postgresql://postgres:secret@db.example.com:5432/backfill"',
    )

    assert _database_url_from_env() == "postgresql://postgres:secret@db.example.com:5432/backfill"
    assert Settings().database_url == "postgresql://postgres:secret@db.example.com:5432/backfill"


def test_derived_database_urls_preserve_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres:secret-password@db.example.com:5432/backfill",
    )

    settings = Settings()

    assert settings.async_database_url == (
        "postgresql+asyncpg://postgres:secret-password@db.example.com:5432/backfill"
    )
    assert settings.sync_database_url == (
        "postgresql+psycopg://postgres:secret-password@db.example.com:5432/backfill"
    )
    assert settings.advisory_lock_database_url == (
        "postgresql://postgres:secret-password@db.example.com:5432/backfill"
    )
    assert "***" not in settings.async_database_url
    assert "***" not in settings.sync_database_url
    assert "***" not in settings.advisory_lock_database_url
