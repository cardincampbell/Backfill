/**
 * Auth session module — wired to Codex's SMS-based dashboard auth.
 *
 * Flow:
 * 1. POST /api/auth/request-access  { phone } → sends SMS with magic link
 * 2. User clicks link → /auth/verify?token=bflink_xxx
 * 3. POST /api/auth/exchange  { token } → returns session_token + principal
 * 4. Browser stores session_token in cookie
 * 5. All subsequent server-side fetches read the cookie and pass Bearer header
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE } from "./constants";

const API_BASE_URL =
  process.env.BACKFILL_API_BASE_URL?.replace(/\/$/, "") ??
  (process.env.NODE_ENV === "production"
    ? "https://api.usebackfill.com"
    : "http://127.0.0.1:8000");

export { SESSION_COOKIE };

export type Session = {
  principal_type: string;
  session_id: number | null;
  subject_phone: string | null;
  organization: {
    id: number;
    name: string;
    [key: string]: unknown;
  } | null;
  location_ids: number[];
  locations: Array<{
    id: number;
    name: string;
    [key: string]: unknown;
  }>;
};

/**
 * Returns the current session, or null if not authenticated.
 * Validates the session token against the backend on every call.
 */
export async function getSession(): Promise<Session | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      next: { revalidate: 0 },
    });
    if (!res.ok) return null;
    return (await res.json()) as Session;
  } catch {
    return null;
  }
}

/**
 * Require authentication for a server component.
 * Redirects to /login if no session exists.
 */
export async function requireAuth(): Promise<Session> {
  const session = await getSession();
  if (!session) {
    redirect("/login");
  }
  return session;
}

/**
 * Get the auth headers to propagate to backend API calls.
 * Returns empty object when no session cookie is present.
 */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}
