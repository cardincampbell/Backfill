from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_v2.api import router as api_router
from app_v2.config import v2_settings


def create_app() -> FastAPI:
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
