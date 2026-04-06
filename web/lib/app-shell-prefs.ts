export type AppShellSidebarTab = "nav" | "copilot";

export const APP_SHELL_SIDEBAR_TAB_COOKIE = "backfill_shell_sidebar_tab";
const APP_SHELL_SIDEBAR_TAB_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

function deriveSharedCookieDomain(hostname: string): string | null {
  const normalized = hostname.trim().toLowerCase();
  if (!normalized || normalized === "localhost" || normalized === "127.0.0.1") {
    return null;
  }
  if (normalized === "usebackfill.com" || normalized === "www.usebackfill.com") {
    return ".usebackfill.com";
  }
  return null;
}

export function normalizeAppShellSidebarTab(
  value: string | null | undefined,
): AppShellSidebarTab {
  return value === "copilot" ? "copilot" : "nav";
}

export function persistAppShellSidebarTabPreference(
  value: AppShellSidebarTab,
): void {
  if (typeof document === "undefined" || typeof window === "undefined") {
    return;
  }
  const parts = [
    `${APP_SHELL_SIDEBAR_TAB_COOKIE}=${encodeURIComponent(value)}`,
    "Path=/",
    `Max-Age=${APP_SHELL_SIDEBAR_TAB_MAX_AGE_SECONDS}`,
    "SameSite=Lax",
  ];
  if (window.location.protocol === "https:") {
    parts.push("Secure");
  }
  const domain = deriveSharedCookieDomain(window.location.hostname);
  if (domain) {
    parts.push(`Domain=${domain}`);
  }
  document.cookie = parts.join("; ");
}
