/** Cookie name used for the dashboard session token. */
export const SESSION_COOKIE = "backfill_session";
export const TRUSTED_DEVICE_COOKIE =
  process.env.NEXT_PUBLIC_BACKFILL_TRUSTED_DEVICE_COOKIE_NAME ??
  "backfill_device";
export const SESSION_HANDOFF_COOKIE = "backfill_session_handoff";
export const SESSION_HANDOFF_STORAGE_KEY = "backfill_session_handoff_token";
