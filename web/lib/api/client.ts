/**
 * Shared API client utilities.
 * All domain API modules import from here.
 *
 * Works in both server components and client components.
 * Server-side requests forward the session cookie as a Bearer token to the
 * backend. Client-side requests rely on the browser's HttpOnly cookie via
 * `credentials: "include"`.
 */

import { SESSION_COOKIE } from "../auth/constants";

export const API_BASE_URL =
  process.env.BACKFILL_API_BASE_URL?.replace(/\/$/, "") ??
  (process.env.NODE_ENV === "production"
    ? "https://api.usebackfill.com"
    : "http://127.0.0.1:8000");

export const USE_MOCKS = process.env.BACKFILL_SHIFTS_MOCKS !== "false";

// Server-side only: dynamic import of next/headers cookies().
async function getSessionToken(): Promise<string | undefined> {
  if (typeof window !== "undefined") return undefined;
  const { cookies } = await import("next/headers");
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE)?.value;
}

/**
 * Fetch wrapper that injects auth headers automatically.
 * Use this instead of raw fetch() for all API calls.
 */
export async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  const token = await getSessionToken();
  const authHeaders: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {};
  return fetch(url, {
    ...init,
    credentials: typeof window !== "undefined" ? "include" : init?.credentials,
    headers: { ...authHeaders, ...init?.headers },
  });
}

export async function fetchJson<T>(path: string): Promise<T | null> {
  try {
    const response = await apiFetch(`${API_BASE_URL}${path}`, {
      next: { revalidate: 0 },
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}
