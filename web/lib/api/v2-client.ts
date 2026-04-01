import { V2_SESSION_COOKIE } from "@/lib/auth/constants";
import { API_BASE_URL } from "./client";

export const V2_API_PREFIX =
  process.env.NEXT_PUBLIC_BACKFILL_V2_API_PREFIX ?? "/api/v2";

async function getV2SessionToken(): Promise<string | undefined> {
  if (typeof window !== "undefined") return undefined;
  const { cookies } = await import("next/headers");
  const cookieStore = await cookies();
  return cookieStore.get(V2_SESSION_COOKIE)?.value;
}

function resolveUrl(pathOrUrl: string): string {
  if (/^https?:\/\//i.test(pathOrUrl)) {
    return pathOrUrl;
  }
  if (pathOrUrl.startsWith("/")) {
    return `${API_BASE_URL}${pathOrUrl}`;
  }
  return `${API_BASE_URL}${V2_API_PREFIX}/${pathOrUrl}`;
}

export async function apiFetchV2(
  pathOrUrl: string,
  init?: RequestInit,
): Promise<Response> {
  const token = await getV2SessionToken();
  const authHeaders: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {};
  return fetch(resolveUrl(pathOrUrl), {
    ...init,
    credentials: typeof window !== "undefined" ? "include" : init?.credentials,
    headers: { ...authHeaders, ...init?.headers },
  });
}

export async function fetchV2Json<T>(path: string): Promise<T | null> {
  try {
    const response = await apiFetchV2(path, {
      next: { revalidate: 0 },
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}
