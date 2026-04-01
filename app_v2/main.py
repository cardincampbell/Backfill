from __future__ import annotations

import logging
import os

import alembic.command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_v2.api import router as api_router
from app_v2.config import v2_settings

logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    """Run alembic upgrade head at startup so the schema is always current."""
    try:
        ini_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
        alembic_cfg = AlembicConfig(ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", v2_settings.sync_database_url)
        alembic.command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied successfully")
    except Exception:
        logger.exception("Alembic migration failed — continuing app startup")


def create_app() -> FastAPI:
    _run_migrations()

    app = FastAPI(
        title="Backfill",
        description="Postgres-first operations, staffing, and coverage platform for Backfill",
        version="2.0.0",
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
