import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"Required env var {key!r} is not set")
    return val


class Settings:
    # Retell
    retell_api_key: str = os.environ.get("RETELL_API_KEY", "")
    retell_agent_id: str = os.environ.get("RETELL_AGENT_ID", "")
    retell_agent_id_inbound: str = os.environ.get("RETELL_AGENT_ID_INBOUND", "")
    retell_agent_id_outbound: str = os.environ.get("RETELL_AGENT_ID_OUTBOUND", "")
    retell_chat_agent_id: str = os.environ.get("RETELL_CHAT_AGENT_ID", "")
    retell_chat_agent_id_inbound: str = os.environ.get("RETELL_CHAT_AGENT_ID_INBOUND", "")
    retell_chat_agent_id_outbound: str = os.environ.get("RETELL_CHAT_AGENT_ID_OUTBOUND", "")
    retell_from_number: str = os.environ.get("RETELL_FROM_NUMBER", "")
    retell_sms_enabled: bool = os.environ.get("RETELL_SMS_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    # Twilio
    twilio_account_sid: str = os.environ.get("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.environ.get("TWILIO_AUTH_TOKEN", "")
    backfill_phone_number: str = os.environ.get("BACKFILL_PHONE_NUMBER", "+18002225345")

    # Backend
    database_url: str = os.environ.get("DATABASE_URL", "backfill.db")
    backfill_webhook_url: str = os.environ.get("BACKFILL_WEBHOOK_URL", "")
    backfill_web_base_url: str = os.environ.get("BACKFILL_WEB_BASE_URL", "https://usebackfill.com").rstrip("/")
    backfill_internal_api_key: str = os.environ.get("BACKFILL_INTERNAL_API_KEY", "")
    backfill_dashboard_session_ttl_hours: int = int(
        os.environ.get("BACKFILL_DASHBOARD_SESSION_TTL_HOURS", "24")
    )
    backfill_dashboard_access_request_ttl_minutes: int = int(
        os.environ.get("BACKFILL_DASHBOARD_ACCESS_REQUEST_TTL_MINUTES", "20")
    )
    backfill_setup_access_ttl_hours: int = int(
        os.environ.get("BACKFILL_SETUP_ACCESS_TTL_HOURS", "72")
    )
    backfill_ops_worker_enabled: bool = os.environ.get(
        "BACKFILL_OPS_WORKER_ENABLED",
        "1",
    ).strip().lower() in {"1", "true", "yes", "on"}
    backfill_ops_worker_poll_seconds: float = float(
        os.environ.get("BACKFILL_OPS_WORKER_POLL_SECONDS", "5")
    )
    backfill_ops_worker_batch_limit: int = int(
        os.environ.get("BACKFILL_OPS_WORKER_BATCH_LIMIT", "20")
    )
    backfill_allowed_origins: List[str] = [
        value.strip()
        for value in os.environ.get("BACKFILL_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    ]
    shift_late_arrival_grace_minutes: int = int(
        os.environ.get("SHIFT_LATE_ARRIVAL_GRACE_MINUTES", "15")
    )
    retell_reconcile_default_lookback_minutes: int = int(
        os.environ.get("RETELL_RECONCILE_DEFAULT_LOOKBACK_MINUTES", "20")
    )
    retell_reconcile_overlap_minutes: int = int(
        os.environ.get("RETELL_RECONCILE_OVERLAP_MINUTES", "5")
    )
    retell_reconcile_urgent_window_hours: int = int(
        os.environ.get("RETELL_RECONCILE_URGENT_WINDOW_HOURS", "3")
    )
    retell_reconcile_targeted_lookback_minutes: int = int(
        os.environ.get("RETELL_RECONCILE_TARGETED_LOOKBACK_MINUTES", "180")
    )
    retell_reconcile_failure_lookback_minutes: int = int(
        os.environ.get("RETELL_RECONCILE_FAILURE_LOOKBACK_MINUTES", "60")
    )
    retell_webhook_stale_minutes: int = int(
        os.environ.get("RETELL_WEBHOOK_STALE_MINUTES", "10")
    )
    retell_reconcile_drift_grace_minutes: int = int(
        os.environ.get("RETELL_RECONCILE_DRIFT_GRACE_MINUTES", "3")
    )

    # 7shifts
    sevenshifts_client_id: str = os.environ.get("SEVENSHIFTS_CLIENT_ID", "")
    sevenshifts_client_secret: str = os.environ.get("SEVENSHIFTS_CLIENT_SECRET", "")
    sevenshifts_webhook_secret: str = os.environ.get("SEVENSHIFTS_WEBHOOK_SECRET", "")

    # Deputy
    deputy_client_id: str = os.environ.get("DEPUTY_CLIENT_ID", "")
    deputy_client_secret: str = os.environ.get("DEPUTY_CLIENT_SECRET", "")
    deputy_webhook_secret: str = os.environ.get("DEPUTY_WEBHOOK_SECRET", "")

    # When I Work
    wheniwork_developer_key: str = os.environ.get("WHENIWORK_DEVELOPER_KEY", "")
    wheniwork_webhook_secret: str = os.environ.get("WHENIWORK_WEBHOOK_SECRET", "")

    # Homebase
    homebase_api_key: str = os.environ.get("HOMEBASE_API_KEY", "")


settings = Settings()
