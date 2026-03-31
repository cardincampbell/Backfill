import {
  AuditLog,
  Cascade,
  DashboardSummary,
  Location,
  LocationStatusResponse,
  Shift,
  ShiftStatusResponse,
  Worker
} from "./types";
import {
  PREVIEW_WORKSPACE_COOKIE,
  parsePreviewWorkspace,
} from "./auth/preview";
import { getAuthHeaders } from "./auth/session";

const API_BASE_URL =
  process.env.BACKFILL_API_BASE_URL?.replace(/\/$/, "") ??
  (process.env.NODE_ENV === "production"
    ? "https://api.usebackfill.com"
    : "http://127.0.0.1:8000");

async function fetchJson<T>(path: string): Promise<T | null> {
  try {
    const authHeaders = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { ...authHeaders },
      next: { revalidate: 0 }
    });

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as T;
  } catch {
    return null;
  }
}

async function getPreviewWorkspaceCookieValue(): Promise<string | null> {
  if (typeof window !== "undefined") {
    const match = document.cookie.match(
      new RegExp(`(?:^|;\\s*)${PREVIEW_WORKSPACE_COOKIE}=([^;]*)`)
    );
    return match?.[1] ? decodeURIComponent(match[1]) : null;
  }

  const { cookies } = await import("next/headers");
  const cookieStore = await cookies();
  return cookieStore.get(PREVIEW_WORKSPACE_COOKIE)?.value ?? null;
}

export async function getDashboardSummary(): Promise<DashboardSummary | null> {
  return fetchJson<DashboardSummary>("/api/dashboard");
}

export async function getLocations(): Promise<Location[]> {
  const rows = (await fetchJson<Location[]>("/api/locations")) ?? [];
  const authHeaders = await getAuthHeaders();
  if (authHeaders.Authorization) {
    return rows;
  }

  const previewWorkspace = parsePreviewWorkspace(
    await getPreviewWorkspaceCookieValue(),
  );
  if (!previewWorkspace) {
    return [];
  }

  const rank = new Map(
    previewWorkspace.locationIds.map((locationId, index) => [locationId, index]),
  );
  const filtered = rows.filter((location) => rank.has(location.id));
  if (!filtered.length) {
    return [];
  }

  return [...filtered].sort(
    (left, right) =>
      (rank.get(left.id) ?? Number.MAX_SAFE_INTEGER) -
      (rank.get(right.id) ?? Number.MAX_SAFE_INTEGER),
  );
}

export async function getLocationStatus(locationId: number): Promise<LocationStatusResponse | null> {
  return fetchJson<LocationStatusResponse>(`/api/locations/${locationId}/status`);
}

export async function getWorkers(locationId?: number): Promise<Worker[]> {
  const path = locationId ? `/api/workers?location_id=${locationId}` : "/api/workers";
  return (await fetchJson<Worker[]>(path)) ?? [];
}

export async function getShifts(locationId?: number): Promise<Shift[]> {
  const path = locationId ? `/api/shifts?location_id=${locationId}` : "/api/shifts";
  return (await fetchJson<Shift[]>(path)) ?? [];
}

export async function getCascades(shiftId?: number): Promise<Cascade[]> {
  const path = shiftId ? `/api/cascades?shift_id=${shiftId}` : "/api/cascades";
  return (await fetchJson<Cascade[]>(path)) ?? [];
}

export async function getAuditLog(): Promise<AuditLog[]> {
  return (await fetchJson<AuditLog[]>("/api/audit-log?limit=10")) ?? [];
}

export async function getShiftStatus(shiftId: number): Promise<ShiftStatusResponse | null> {
  return fetchJson<ShiftStatusResponse>(`/api/shifts/${shiftId}/status`);
}

export async function getSupportSnapshot() {
  const [summary, locations, shifts, audits] = await Promise.all([
    getDashboardSummary(),
    getLocations(),
    getShifts(),
    getAuditLog()
  ]);

  return {
    summary,
    locations,
    shifts,
    audits,
    backendReachable: summary !== null
  };
}
