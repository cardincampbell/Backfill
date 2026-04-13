import { apiFetchApp } from "./backend-client";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export type CalendarFeed = {
  feed_url: string;
  rotated_at: string | null;
};

export async function getCalendarFeed(
  businessId: string,
  locationId: string,
): Promise<CalendarFeed> {
  const response = await apiFetchApp(
    `/api/ops/businesses/${businessId}/locations/${locationId}/calendar-feed`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json() as Promise<CalendarFeed>;
}

export async function rotateCalendarFeed(
  businessId: string,
  locationId: string,
): Promise<CalendarFeed> {
  const response = await apiFetchApp(
    `/api/ops/businesses/${businessId}/locations/${locationId}/calendar-feed/rotate`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json() as Promise<CalendarFeed>;
}
