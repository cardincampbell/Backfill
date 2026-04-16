from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm.exc import StaleDataError
from starlette.responses import JSONResponse

from app.api import router as api_router
from app.api.routes.retell_provider import public_router as retell_public_router
from app.bootstrap import initialize_runtime
from app.config import settings

logger = logging.getLogger(__name__)


def _cors_error_headers(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin", "").strip()
    if not origin or origin not in settings.backfill_allowed_origins:
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    await initialize_runtime()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Backfill",
        description="Postgres-first operations, staffing, and coverage platform for Backfill",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Backfill-Request-ID"] = request_id
        return response

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", uuid4().hex)
        logger.exception(
            "Unhandled exception request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
            exc_info=exc,
        )
        payload: dict[str, str] = {
            "detail": "Internal server error",
            "request_id": request_id,
        }
        if settings.expose_internal_errors:
            payload["debug"] = f"{exc.__class__.__name__}: {exc}"
            payload["path"] = request.url.path
            payload["method"] = request.method
        headers = {"X-Backfill-Request-ID": request_id, **_cors_error_headers(request)}
        return JSONResponse(
            status_code=500,
            content=payload,
            headers=headers,
        )

    @app.exception_handler(StaleDataError)
    async def handle_stale_data_error(request: Request, exc: StaleDataError):
        request_id = getattr(request.state, "request_id", uuid4().hex)
        logger.warning(
            "Write conflict request_id=%s method=%s path=%s error=%s",
            request_id,
            request.method,
            request.url.path,
            exc,
        )
        payload: dict[str, str] = {
            "detail": "write_conflict",
            "request_id": request_id,
        }
        if settings.expose_internal_errors:
            payload["debug"] = f"{exc.__class__.__name__}: {exc}"
            payload["path"] = request.url.path
            payload["method"] = request.method
        headers = {"X-Backfill-Request-ID": request_id, **_cors_error_headers(request)}
        return JSONResponse(
            status_code=409,
            content=payload,
            headers=headers,
        )

    if settings.backfill_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.backfill_allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/meta")
    async def meta() -> dict[str, str]:
        return {
            "environment": settings.environment,
            "database_backend": "postgresql",
            "api_prefix": settings.api_prefix,
        }

    app.include_router(api_router)
    app.include_router(retell_public_router)
    return app


app = create_app()
