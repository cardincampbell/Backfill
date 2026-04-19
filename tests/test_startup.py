from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import bootstrap as bootstrap_module


def test_run_migrations_with_advisory_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[tuple[str, tuple[object, ...]]] = []
    upgrade_calls: list[tuple[str, str]] = []

    class FakeCursor:
        def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
            executed.append((sql, params))

        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def fake_connect(url: str, autocommit: bool = False) -> FakeConnection:
        assert url == "postgresql://postgres:postgres@db.example.com:5432/backfill"
        assert autocommit is True
        return FakeConnection()

    def fake_upgrade(cfg, revision: str) -> None:
        upgrade_calls.append((cfg.get_main_option("sqlalchemy.url"), revision))

    monkeypatch.setattr(
        bootstrap_module,
        "settings",
        SimpleNamespace(
            advisory_lock_database_url="postgresql://postgres:postgres@db.example.com:5432/backfill",
            sync_database_url="postgresql+psycopg://postgres:postgres@db.example.com:5432/backfill",
            run_migrations_on_startup=True,
        ),
    )
    monkeypatch.setattr(bootstrap_module.psycopg, "connect", fake_connect)
    monkeypatch.setattr(bootstrap_module.alembic.command, "upgrade", fake_upgrade)

    bootstrap_module.run_migrations_with_advisory_lock()

    assert executed == [
        ("SELECT pg_advisory_lock(%s)", (bootstrap_module.MIGRATION_ADVISORY_LOCK_KEY,)),
        ("SELECT pg_advisory_unlock(%s)", (bootstrap_module.MIGRATION_ADVISORY_LOCK_KEY,)),
    ]
    assert upgrade_calls == [
        ("postgresql+psycopg://postgres:postgres@db.example.com:5432/backfill", "head"),
    ]


@pytest.mark.asyncio
async def test_run_startup_migrations_if_enabled_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bootstrap_module,
        "settings",
        SimpleNamespace(run_migrations_on_startup=True),
    )

    await bootstrap_module.run_startup_migrations_if_enabled()


@pytest.mark.asyncio
async def test_run_startup_migrations_if_disabled_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bootstrap_module,
        "settings",
        SimpleNamespace(run_migrations_on_startup=False),
    )

    await bootstrap_module.run_startup_migrations_if_enabled()


def test_register_llm_adapters_delegates_to_adapter_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        bootstrap_module.llm_adapters,
        "register_configured_adapters",
        lambda: calls.append("register"),
    )

    bootstrap_module.register_llm_adapters()

    assert calls == ["register"]
