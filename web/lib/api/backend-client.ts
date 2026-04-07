import { SESSION_COOKIE } from "@/lib/auth/constants";
import { API_BASE_URL } from "./client";

export const API_PREFIX =
  process.env.NEXT_PUBLIC_BACKFILL_API_PREFIX ?? "/api";

async function getSessionToken(): Promise<string | undefined> {
  if (typeof window !== "undefined") return undefined;
  const { cookies } = await import("next/headers");
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE)?.value;
}

let clientSessionRecoveryPromise: Promise<boolean> | null = null;

async function attemptClientSessionRecovery(): Promise<boolean> {
  if (typeof window === "undefined") {
    return false;
  }

  if (!clientSessionRecoveryPromise) {
    clientSessionRecoveryPromise = (async () => {
      try {
        const response = await fetch("/auth/restore", {
          method: "POST",
          credentials: "include",
        });
        return response.ok && response.status !== 204;
      } catch {
        return false;
      } finally {
        clientSessionRecoveryPromise = null;
      }
    })();
  }

  return clientSessionRecoveryPromise;
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
  const authHeaders: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {};
  try {
    const requestInit: RequestInit = {
      ...init,
      credentials: typeof window !== "undefined" ? "include" : init?.credentials,
      headers: { ...authHeaders, ...init?.headers },
    };
    let response = await fetch(url, requestInit);
    if (typeof window !== "undefined" && response.status === 401) {
      const restored = await attemptClientSessionRecovery();
      if (restored) {
        response = await fetch(url, requestInit);
      }
    }
    return response;
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
