from __future__ import annotations

from types import SimpleNamespace

import pytest

from app_v2 import main as main_module


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
        main_module,
        "v2_settings",
        SimpleNamespace(
            advisory_lock_database_url="postgresql://postgres:postgres@db.example.com:5432/backfill",
            sync_database_url="postgresql+psycopg://postgres:postgres@db.example.com:5432/backfill",
            run_migrations_on_startup=True,
        ),
    )
    monkeypatch.setattr(main_module.psycopg, "connect", fake_connect)
    monkeypatch.setattr(main_module.alembic.command, "upgrade", fake_upgrade)

    main_module._run_migrations_with_advisory_lock()

    assert executed == [
        ("SELECT pg_advisory_lock(%s)", (main_module.MIGRATION_ADVISORY_LOCK_KEY,)),
        ("SELECT pg_advisory_unlock(%s)", (main_module.MIGRATION_ADVISORY_LOCK_KEY,)),
    ]
    assert upgrade_calls == [
        ("postgresql+psycopg://postgres:postgres@db.example.com:5432/backfill", "head"),
    ]


@pytest.mark.asyncio
async def test_run_startup_migrations_if_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_to_thread(func):
        calls.append("to_thread")
        func()

    monkeypatch.setattr(
        main_module,
        "v2_settings",
        SimpleNamespace(run_migrations_on_startup=True),
    )
    monkeypatch.setattr(main_module.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(main_module, "_run_migrations_with_advisory_lock", lambda: calls.append("run"))

    await main_module._run_startup_migrations_if_enabled()

    assert calls == ["to_thread", "run"]


@pytest.mark.asyncio
async def test_run_startup_migrations_if_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main_module,
        "v2_settings",
        SimpleNamespace(run_migrations_on_startup=False),
    )

    async def fail_to_thread(_func):
        raise AssertionError("to_thread should not run when startup migrations are disabled")

    monkeypatch.setattr(main_module.asyncio, "to_thread", fail_to_thread)

    await main_module._run_startup_migrations_if_enabled()
