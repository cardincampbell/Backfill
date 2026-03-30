const DASHBOARD_AUTH_REQUIRED =
  process.env.NEXT_PUBLIC_BACKFILL_DASHBOARD_AUTH_REQUIRED === "true";

const PREVIEW_PHONE_STORAGE_KEY = "backfill_preview_phone";

export function isPreviewAuthBypassEnabled(): boolean {
  return !DASHBOARD_AUTH_REQUIRED;
}

export function storePreviewPhone(phone: string): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(PREVIEW_PHONE_STORAGE_KEY, phone);
}

export function getStoredPreviewPhone(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(PREVIEW_PHONE_STORAGE_KEY);
}

export function clearStoredPreviewPhone(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(PREVIEW_PHONE_STORAGE_KEY);
}
