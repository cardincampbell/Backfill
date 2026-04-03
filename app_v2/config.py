from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv()


def _normalized_env_value(name: str) -> str:
    raw_value = os.environ.get(name, "")
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _database_url_from_env() -> str:
    return _normalized_env_value("V2_DATABASE_URL") or _normalized_env_value("DATABASE_URL")


def _render_database_url(url) -> str:
    return url.render_as_string(hide_password=False)


def _default_allowed_origins() -> list[str]:
    configured = [
        value.strip()
        for value in os.environ.get("BACKFILL_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    ]
    if configured:
        return configured

    web_base_url = os.environ.get("BACKFILL_WEB_BASE_URL", "https://usebackfill.com").rstrip("/")
    parsed = urlparse(web_base_url)
    hostname = (parsed.hostname or "").strip().lower()
    scheme = parsed.scheme or "https"

    origins: list[str] = []
    if hostname:
        origins.append(f"{scheme}://{hostname}")
        if hostname.startswith("www."):
            origins.append(f"{scheme}://{hostname[4:]}")
        else:
            origins.append(f"{scheme}://www.{hostname}")

    for local_origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        if local_origin not in origins:
            origins.append(local_origin)

    return origins


def _default_expose_internal_errors() -> bool:
    raw = os.environ.get("BACKFILL_V2_EXPOSE_INTERNAL_ERRORS")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    environment = os.environ.get(
        "RAILWAY_ENVIRONMENT_NAME",
        os.environ.get("ENVIRONMENT", "development"),
    ).strip().lower()
    return environment in {"development", "dev", "local", "test", "testing"}


@dataclass(frozen=True)
class V2Settings:
    database_url: str = field(default_factory=_database_url_from_env)
    api_prefix: str = os.environ.get("BACKFILL_V2_API_PREFIX", "/api/v2")
    web_base_url: str = os.environ.get("BACKFILL_WEB_BASE_URL", "https://usebackfill.com").rstrip("/")
    api_base_url: str = os.environ.get("BACKFILL_API_BASE_URL", "https://api.usebackfill.com").rstrip("/")
    environment: str = os.environ.get("RAILWAY_ENVIRONMENT_NAME", os.environ.get("ENVIRONMENT", "development"))
    session_ttl_hours: int = int(os.environ.get("BACKFILL_V2_SESSION_TTL_HOURS", "336"))
    step_up_ttl_minutes: int = int(
        os.environ.get(
            "BACKFILL_V2_STEP_UP_TTL_MINUTES",
            os.environ.get("BACKFILL_DASHBOARD_STEP_UP_TTL_MINUTES", "15"),
        )
    )
    session_cookie_name: str = os.environ.get("BACKFILL_V2_SESSION_COOKIE_NAME", "backfill_v2_session")
    twilio_account_sid: str = os.environ.get("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.environ.get("TWILIO_AUTH_TOKEN", "")
    twilio_verify_service_sid: str = os.environ.get("TWILIO_VERIFY_SERVICE_SID", "")
    google_places_api_key: str = os.environ.get(
        "GOOGLE_PLACES_API_KEY",
        os.environ.get("GOOGLE_MAPS_API_KEY", ""),
    )
    backfill_google_places_enabled: bool = os.environ.get(
        "BACKFILL_GOOGLE_PLACES_ENABLED",
        "1",
    ).strip().lower() in {"1", "true", "yes", "on"}
    google_places_region_code: str = os.environ.get(
        "BACKFILL_GOOGLE_PLACES_REGION_CODE",
        "US",
    )
    google_places_country_codes: list[str] = field(
        default_factory=lambda: [
            value.strip().lower()
            for value in os.environ.get("BACKFILL_GOOGLE_PLACES_COUNTRY_CODES", "us").split(",")
            if value.strip()
        ]
    )
    backfill_phone_number: str = os.environ.get("BACKFILL_PHONE_NUMBER", "+18002225345")
    sendgrid_api_key: str = os.environ.get("SENDGRID_API_KEY", "")
    backfill_email_from: str = os.environ.get("BACKFILL_EMAIL_FROM", "")
    backfill_email_from_name: str = os.environ.get("BACKFILL_EMAIL_FROM_NAME", "Backfill")
    retell_api_key: str = os.environ.get("RETELL_API_KEY", "")
    retell_agent_id: str = os.environ.get("RETELL_AGENT_ID", "")
    retell_agent_id_inbound: str = os.environ.get("RETELL_AGENT_ID_INBOUND", "")
    retell_agent_id_outbound: str = os.environ.get("RETELL_AGENT_ID_OUTBOUND", "")
    retell_chat_agent_id: str = os.environ.get("RETELL_CHAT_AGENT_ID", "")
    retell_chat_agent_id_inbound: str = os.environ.get("RETELL_CHAT_AGENT_ID_INBOUND", "")
    retell_chat_agent_id_outbound: str = os.environ.get("RETELL_CHAT_AGENT_ID_OUTBOUND", "")
    retell_from_number: str = os.environ.get("RETELL_FROM_NUMBER", "")
    sevenshifts_client_id: str = os.environ.get("SEVENSHIFTS_CLIENT_ID", "")
    sevenshifts_client_secret: str = os.environ.get("SEVENSHIFTS_CLIENT_SECRET", "")
    sevenshifts_webhook_secret: str = os.environ.get("SEVENSHIFTS_WEBHOOK_SECRET", "")
    deputy_client_id: str = os.environ.get("DEPUTY_CLIENT_ID", "")
    deputy_client_secret: str = os.environ.get("DEPUTY_CLIENT_SECRET", "")
    deputy_webhook_secret: str = os.environ.get("DEPUTY_WEBHOOK_SECRET", "")
    wheniwork_developer_key: str = os.environ.get("WHENIWORK_DEVELOPER_KEY", "")
    wheniwork_webhook_secret: str = os.environ.get("WHENIWORK_WEBHOOK_SECRET", "")
    homebase_api_key: str = os.environ.get("HOMEBASE_API_KEY", "")
    webhook_timeout_seconds: float = float(os.environ.get("BACKFILL_V2_WEBHOOK_TIMEOUT_SECONDS", "10"))
    webhook_max_attempts: int = int(os.environ.get("BACKFILL_V2_WEBHOOK_MAX_ATTEMPTS", "5"))
    scheduler_webhook_limit_per_minute: int = int(os.environ.get("BACKFILL_V2_SCHEDULER_WEBHOOK_LIMIT_PER_MINUTE", "240"))
    retell_webhook_limit_per_minute: int = int(os.environ.get("BACKFILL_V2_RETELL_WEBHOOK_LIMIT_PER_MINUTE", "240"))
    worker_api_key: str = os.environ.get("BACKFILL_V2_WORKER_API_KEY", "")
    run_migrations_on_startup: bool = os.environ.get(
        "BACKFILL_V2_RUN_MIGRATIONS_ON_STARTUP",
        "",
    ).strip().lower() in {"1", "true", "yes", "on"}
    backfill_allowed_origins: list[str] = field(default_factory=_default_allowed_origins)
    sql_echo: bool = os.environ.get("BACKFILL_V2_SQL_ECHO", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    expose_internal_errors: bool = field(default_factory=_default_expose_internal_errors)

    @property
    def has_database_url(self) -> bool:
        return bool(self.database_url)

    @property
    def async_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError("V2_DATABASE_URL (or DATABASE_URL) is required for the V2 backend")

        url = make_url(self.database_url)
        if url.get_backend_name() != "postgresql":
            raise RuntimeError(
                f"Backfill V2 requires PostgreSQL. Received backend {url.get_backend_name()!r}."
            )
        if url.drivername == "postgresql":
            return _render_database_url(url.set(drivername="postgresql+asyncpg"))
        return _render_database_url(url)

    @property
    def sync_database_url(self) -> str:
        url = make_url(self.async_database_url)
        if url.drivername == "postgresql+asyncpg":
            return _render_database_url(url.set(drivername="postgresql+psycopg"))
        return _render_database_url(url)

    @property
    def advisory_lock_database_url(self) -> str:
        url = make_url(self.sync_database_url)
        if "+" in url.drivername:
            return _render_database_url(url.set(drivername="postgresql"))
        return _render_database_url(url)

    @property
    def session_cookie_secure(self) -> bool:
        return urlparse(self.web_base_url).scheme == "https"

    @property
    def session_cookie_domain(self) -> str | None:
        hostname = (urlparse(self.web_base_url).hostname or "").strip().lower()
        if not hostname or hostname in {"localhost", "127.0.0.1"}:
            return None
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return f".{hostname}"


v2_settings = V2Settings()
