from __future__ import annotations

import logging
from pathlib import Path

import alembic.command
import psycopg
from alembic.config import Config as AlembicConfig

from app.config import settings
from app.services import llm_adapters

logger = logging.getLogger(__name__)
MIGRATION_ADVISORY_LOCK_KEY = 2_420_401_001


def run_migrations_with_advisory_lock() -> None:
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    logger.info("Running migrations with advisory lock")
    with psycopg.connect(settings.advisory_lock_database_url, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_ADVISORY_LOCK_KEY,))
        try:
            alembic_cfg = AlembicConfig(str(alembic_ini_path))
            alembic_cfg.set_main_option("sqlalchemy.url", settings.sync_database_url)
            alembic.command.upgrade(alembic_cfg, "head")
        finally:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_ADVISORY_LOCK_KEY,))
    logger.info("Migrations applied successfully")


async def run_startup_migrations_if_enabled() -> None:
    if settings.run_migrations_on_startup:
        logger.warning(
            "BACKFILL_RUN_MIGRATIONS_ON_STARTUP is enabled but ignored; "
            "run migrations via /internal/migrations/run or a release step instead"
        )
    return None


def register_llm_adapters() -> None:
    llm_adapters.register_configured_adapters()


async def initialize_runtime() -> None:
    await run_startup_migrations_if_enabled()
    register_llm_adapters()
