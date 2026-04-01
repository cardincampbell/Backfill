from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import alembic.command
import psycopg
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_v2.api import router as api_router
from app_v2.config import v2_settings

logger = logging.getLogger(__name__)
MIGRATION_ADVISORY_LOCK_KEY = 2_420_401_001


def _run_migrations_with_advisory_lock() -> None:
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    logger.info("Running V2 migrations with advisory lock")
    with psycopg.connect(v2_settings.advisory_lock_database_url, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_ADVISORY_LOCK_KEY,))
        try:
            alembic_cfg = AlembicConfig(str(alembic_ini_path))
            alembic_cfg.set_main_option("sqlalchemy.url", v2_settings.sync_database_url)
            alembic.command.upgrade(alembic_cfg, "head")
        finally:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_ADVISORY_LOCK_KEY,))
    logger.info("V2 migrations applied successfully")


async def _run_startup_migrations_if_enabled() -> None:
    if not v2_settings.run_migrations_on_startup:
        return
    await asyncio.to_thread(_run_migrations_with_advisory_lock)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await _run_startup_migrations_if_enabled()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Backfill",
        description="Postgres-first operations, staffing, and coverage platform for Backfill",
        version="2.0.0",
        lifespan=lifespan,
    )

    if v2_settings.backfill_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=v2_settings.backfill_allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": "v2"}

    @app.get("/meta")
    async def meta() -> dict[str, str]:
        return {
            "environment": v2_settings.environment,
            "database_backend": "postgresql",
            "api_prefix": v2_settings.api_prefix,
        }

    app.include_router(api_router)
    return app


app = create_app()
