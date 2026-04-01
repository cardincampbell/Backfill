from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv()


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


@dataclass(frozen=True)
class V2Settings:
    database_url: str = os.environ.get("V2_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    api_prefix: str = os.environ.get("BACKFILL_V2_API_PREFIX", "/api/v2")
    web_base_url: str = os.environ.get("BACKFILL_WEB_BASE_URL", "https://usebackfill.com").rstrip("/")
    api_base_url: str = os.environ.get("BACKFILL_API_BASE_URL", "https://api.usebackfill.com").rstrip("/")
    environment: str = os.environ.get("RAILWAY_ENVIRONMENT_NAME", os.environ.get("ENVIRONMENT", "development"))
    session_ttl_hours: int = int(os.environ.get("BACKFILL_V2_SESSION_TTL_HOURS", "336"))
    session_cookie_name: str = os.environ.get("BACKFILL_V2_SESSION_COOKIE_NAME", "backfill_v2_session")
    twilio_account_sid: str = os.environ.get("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.environ.get("TWILIO_AUTH_TOKEN", "")
    twilio_verify_service_sid: str = os.environ.get("TWILIO_VERIFY_SERVICE_SID", "")
    backfill_phone_number: str = os.environ.get("BACKFILL_PHONE_NUMBER", "+18002225345")
    sendgrid_api_key: str = os.environ.get("SENDGRID_API_KEY", "")
    backfill_email_from: str = os.environ.get("BACKFILL_EMAIL_FROM", "")
    backfill_email_from_name: str = os.environ.get("BACKFILL_EMAIL_FROM_NAME", "Backfill")
    worker_api_key: str = os.environ.get("BACKFILL_V2_WORKER_API_KEY", "")
    backfill_allowed_origins: list[str] = field(default_factory=_default_allowed_origins)
    sql_echo: bool = os.environ.get("BACKFILL_V2_SQL_ECHO", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

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
            return str(url.set(drivername="postgresql+asyncpg"))
        return self.database_url

    @property
    def sync_database_url(self) -> str:
        url = make_url(self.async_database_url)
        if url.drivername == "postgresql+asyncpg":
            return str(url.set(drivername="postgresql+psycopg"))
        return str(url)

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
