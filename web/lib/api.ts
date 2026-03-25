import {
  AuditLog,
  Cascade,
  DashboardSummary,
  Restaurant,
  Shift,
  ShiftStatusResponse,
  Worker
} from "./types";

const API_BASE_URL =
  process.env.BACKFILL_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

async function fetchJson<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
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

export async function getDashboardSummary(): Promise<DashboardSummary | null> {
  return fetchJson<DashboardSummary>("/api/dashboard");
}

export async function getRestaurants(): Promise<Restaurant[]> {
  return (await fetchJson<Restaurant[]>("/api/restaurants")) ?? [];
}

export async function getWorkers(restaurantId?: number): Promise<Worker[]> {
  const path = restaurantId ? `/api/workers?restaurant_id=${restaurantId}` : "/api/workers";
  return (await fetchJson<Worker[]>(path)) ?? [];
}

export async function getShifts(restaurantId?: number): Promise<Shift[]> {
  const path = restaurantId ? `/api/shifts?restaurant_id=${restaurantId}` : "/api/shifts";
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
  const [summary, restaurants, shifts, audits] = await Promise.all([
    getDashboardSummary(),
    getRestaurants(),
    getShifts(),
    getAuditLog()
  ]);

  return {
    summary,
    restaurants,
    shifts,
    audits,
    backendReachable: summary !== null
  };
}
