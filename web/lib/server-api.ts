const API_BASE_URL =
  process.env.BACKFILL_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function createRestaurant(input: {
  name: string;
  address?: string;
  manager_name?: string;
  manager_phone?: string;
  manager_email?: string;
  scheduling_platform?: string;
  integration_status?: string;
  scheduling_platform_id?: string;
  writeback_enabled?: boolean;
  writeback_subscription_tier?: string;
  onboarding_info?: string;
}) {
  const response = await fetch(`${API_BASE_URL}/api/restaurants`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as { id: number; name: string };
}

export async function connectAndSyncRestaurant(restaurantId: number) {
  const response = await fetch(`${API_BASE_URL}/api/restaurants/${restaurantId}/connect-sync`, {
    method: "POST",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    status: string;
    platform: string;
    mode: string;
    roster_sync?: { created: number; updated: number; skipped: number } | null;
    schedule_sync?: { created: number; updated: number; skipped: number } | null;
    error?: string;
  };
}

export async function sendOnboardingLink(input: {
  phone: string;
  kind: string;
  platform?: string;
}) {
  const response = await fetch(`${API_BASE_URL}/api/onboarding/link`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    kind: string;
    platform?: string | null;
    path: string;
    url: string;
    message_sid?: string | null;
  };
}

export async function updateRestaurant(
  restaurantId: number,
  input: {
    writeback_enabled?: boolean;
    writeback_subscription_tier?: string;
  }
) {
  const response = await fetch(`${API_BASE_URL}/api/restaurants/${restaurantId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as { id: number; writeback_enabled?: boolean };
}

export async function syncRestaurantRoster(restaurantId: number) {
  const response = await fetch(`${API_BASE_URL}/api/restaurants/${restaurantId}/sync-roster`, {
    method: "POST",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    status: string;
    platform: string;
    created: number;
    updated: number;
    skipped: number;
  };
}

export async function syncRestaurantSchedule(restaurantId: number) {
  const response = await fetch(`${API_BASE_URL}/api/restaurants/${restaurantId}/sync-schedule`, {
    method: "POST",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    status: string;
    platform: string;
    created: number;
    updated: number;
    skipped: number;
  };
}

export async function createWorker(input: {
  name: string;
  phone: string;
  email?: string;
  restaurant_id: number;
  preferred_channel?: string;
  roles: string[];
  certifications: string[];
  source?: string;
}) {
  const response = await fetch(`${API_BASE_URL}/api/workers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as { id: number; name: string };
}

export async function importWorkersCsv(restaurantId: number, file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    `${API_BASE_URL}/api/workers/import-csv?restaurant_id=${restaurantId}`,
    {
      method: "POST",
      body: formData,
      cache: "no-store"
    }
  );

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as { created: number; skipped: number };
}
