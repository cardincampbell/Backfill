import type { PlatformEvent, PlatformEventListQuery } from "@/lib/types/events";
import { apiFetchApp, API_PREFIX } from "./backend-client";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function listPlatformEvents(
  businessId: string,
  query: PlatformEventListQuery = {},
): Promise<PlatformEvent[]> {
  const search = new URLSearchParams();
  if (query.locationId) {
    search.set("location_id", query.locationId);
  }
  if (query.entityType) {
    search.set("entity_type", query.entityType);
  }
  if (query.eventType) {
    search.set("event_type", query.eventType);
  }
  if (typeof query.limit === "number") {
    search.set("limit", String(query.limit));
  }
  const suffix = search.size > 0 ? `?${search.toString()}` : "";
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/events${suffix}`,
    { next: { revalidate: 0 } },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as PlatformEvent[];
}
