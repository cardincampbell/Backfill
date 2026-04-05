import {
  SESSION_COOKIE,
  SESSION_HANDOFF_COOKIE,
  SESSION_HANDOFF_STORAGE_KEY,
} from "@/lib/auth/constants";
import { API_BASE_URL } from "./client";

export const API_PREFIX =
  process.env.NEXT_PUBLIC_BACKFILL_API_PREFIX ?? "/api";

async function getSessionToken(): Promise<string | undefined> {
  if (typeof window !== "undefined") return undefined;
  const { cookies } = await import("next/headers");
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE)?.value;
}

function getClientSessionHandoffToken(): string | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  const hasHandoffMarker = document.cookie
    .split(";")
    .some((cookie) =>
      cookie.trim().startsWith(`${SESSION_HANDOFF_COOKIE}=`),
    );
  if (!hasHandoffMarker) {
    return undefined;
  }
  try {
    const token = window.sessionStorage.getItem(SESSION_HANDOFF_STORAGE_KEY)?.trim();
    return token || undefined;
  } catch {
    return undefined;
  }
}

function resolveUrl(pathOrUrl: string): string {
  if (/^https?:\/\//i.test(pathOrUrl)) {
    return pathOrUrl;
  }
  if (pathOrUrl.startsWith("/")) {
    return `${API_BASE_URL}${pathOrUrl}`;
  }
  return `${API_BASE_URL}${API_PREFIX}/${pathOrUrl}`;
}

export async function apiFetchApp(
  pathOrUrl: string,
  init?: RequestInit,
): Promise<Response> {
  const url = resolveUrl(pathOrUrl);
  const method = (init?.method ?? "GET").toUpperCase();
  const token = await getSessionToken();
  const clientHandoffToken = getClientSessionHandoffToken();
  const authToken = token ?? clientHandoffToken;
  const authHeaders: Record<string, string> = authToken
    ? { Authorization: `Bearer ${authToken}` }
    : {};
  try {
    return await fetch(url, {
      ...init,
      credentials: typeof window !== "undefined" ? "include" : init?.credentials,
      headers: { ...authHeaders, ...init?.headers },
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message : "Unknown network error";
    throw new Error(`Network request failed for ${method} ${url}: ${reason}`);
  }
}

export async function fetchAppJson<T>(path: string): Promise<T | null> {
  try {
    const response = await apiFetchApp(path, {
      next: { revalidate: 0 },
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch (error) {
    if (typeof window !== "undefined") {
      console.error(`Backfill API fetch failed for ${path}`, error);
    }
    return null;
  }
}
