from __future__ import annotations

from app import migrate as migrate_module


def test_migrate_main_runs_migrations(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(migrate_module, "_configure_logging", lambda: calls.append("logging"))
    monkeypatch.setattr(
        migrate_module,
        "run_migrations_with_advisory_lock",
        lambda: calls.append("migrate"),
    )

    migrate_module.main()

    assert calls == ["logging", "migrate"]
