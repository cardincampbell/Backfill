import { SESSION_COOKIE } from "./constants";

const DEFAULT_SESSION_COOKIE_MAX_AGE_SECONDS = 180 * 24 * 60 * 60;

export function getBrowserSessionToken(): string | null {
  if (typeof window === "undefined") return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${SESSION_COOKIE}=([^;]*)`),
  );
  return match?.[1] ?? null;
}

export function persistBrowserSessionToken(
  sessionToken: string,
  maxAgeSeconds: number = DEFAULT_SESSION_COOKIE_MAX_AGE_SECONDS,
): void {
  if (typeof window === "undefined") return;
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${SESSION_COOKIE}=${sessionToken}; path=/; max-age=${maxAgeSeconds}; SameSite=Lax${secure}`;
}

export function clearBrowserSessionToken(): void {
  if (typeof window === "undefined") return;
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${SESSION_COOKIE}=; path=/; max-age=0; SameSite=Lax${secure}`;
}
