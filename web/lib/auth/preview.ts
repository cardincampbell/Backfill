const PREVIEW_AUTH_BYPASS_ENABLED =
  process.env.NEXT_PUBLIC_BACKFILL_PREVIEW_AUTH_BYPASS === "true";

const PREVIEW_PHONE_STORAGE_KEY = "backfill_preview_phone";
const PREVIEW_WORKSPACE_STORAGE_KEY = "backfill_preview_workspace";
export const PREVIEW_WORKSPACE_COOKIE = "backfill_preview_workspace";

export type PreviewWorkspace = {
  primaryLocationId: number;
  locationIds: number[];
};

function normalizeWorkspace(workspace: PreviewWorkspace): PreviewWorkspace | null {
  const locationIds = Array.from(
    new Set(
      workspace.locationIds
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0),
    ),
  );
  const primaryLocationId = Number(workspace.primaryLocationId);
  if (!Number.isInteger(primaryLocationId) || primaryLocationId <= 0) {
    return null;
  }
  if (!locationIds.includes(primaryLocationId)) {
    locationIds.unshift(primaryLocationId);
  }
  return { primaryLocationId, locationIds };
}

export function parsePreviewWorkspace(raw: string | null | undefined): PreviewWorkspace | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as PreviewWorkspace;
    return normalizeWorkspace(parsed);
  } catch {
    return null;
  }
}

export function isPreviewAuthBypassEnabled(): boolean {
  return PREVIEW_AUTH_BYPASS_ENABLED;
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

export function storePreviewWorkspace(workspace: PreviewWorkspace): void {
  if (typeof window === "undefined") return;
  const normalized = normalizeWorkspace(workspace);
  if (!normalized) return;
  const serialized = JSON.stringify(normalized);
  window.sessionStorage.setItem(PREVIEW_WORKSPACE_STORAGE_KEY, serialized);
  document.cookie = `${PREVIEW_WORKSPACE_COOKIE}=${encodeURIComponent(serialized)}; path=/; SameSite=Lax`;
}

export function getStoredPreviewWorkspace(): PreviewWorkspace | null {
  if (typeof window === "undefined") return null;
  return parsePreviewWorkspace(
    window.sessionStorage.getItem(PREVIEW_WORKSPACE_STORAGE_KEY),
  );
}

export function clearStoredPreviewWorkspace(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(PREVIEW_WORKSPACE_STORAGE_KEY);
  document.cookie = `${PREVIEW_WORKSPACE_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
}
