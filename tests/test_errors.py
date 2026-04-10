from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.orm.exc import StaleDataError

from app import main as main_module


def test_unhandled_exceptions_return_json_with_request_id(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            run_migrations_on_startup=False,
            backfill_allowed_origins=[],
            environment="test",
            api_prefix="/api",
            expose_internal_errors=True,
        ),
    )

    app = main_module.create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("bad database url")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    assert response.headers["X-Backfill-Request-ID"]
    payload = response.json()
    assert payload["detail"] == "Internal server error"
    assert payload["request_id"] == response.headers["X-Backfill-Request-ID"]
    assert payload["debug"] == "ValueError: bad database url"
    assert payload["method"] == "GET"
    assert payload["path"] == "/boom"


def test_unhandled_exceptions_include_cors_headers_for_allowed_origin(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            run_migrations_on_startup=False,
            backfill_allowed_origins=["https://www.usebackfill.com"],
            environment="test",
            api_prefix="/api",
            expose_internal_errors=True,
        ),
    )

    app = main_module.create_app()

    @app.post("/boom")
    async def boom() -> None:
        raise RuntimeError("db down")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/boom", headers={"Origin": "https://www.usebackfill.com"})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "https://www.usebackfill.com"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["vary"] == "Origin"


def test_stale_data_errors_return_conflict_with_request_id(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            run_migrations_on_startup=False,
            backfill_allowed_origins=[],
            environment="test",
            api_prefix="/api",
            expose_internal_errors=True,
        ),
    )

    app = main_module.create_app()

    @app.post("/conflict")
    async def conflict() -> None:
        raise StaleDataError("update expected to affect 1 row; 0 matched")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/conflict")

    assert response.status_code == 409
    assert response.headers["X-Backfill-Request-ID"]
    payload = response.json()
    assert payload["detail"] == "write_conflict"
    assert payload["request_id"] == response.headers["X-Backfill-Request-ID"]
    assert payload["method"] == "POST"
    assert payload["path"] == "/conflict"
