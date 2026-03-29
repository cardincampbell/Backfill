import { apiFetch } from "./api/client";

const API_BASE_URL =
  process.env.BACKFILL_API_BASE_URL?.replace(/\/$/, "") ??
  (process.env.NODE_ENV === "production"
    ? "https://api.usebackfill.com"
    : "http://127.0.0.1:8000");

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

function withSetupHeaders(
  setupToken?: string,
  headers?: HeadersInit
): HeadersInit | undefined {
  if (!setupToken) {
    return headers;
  }
  return {
    ...(headers ?? {}),
    "X-Backfill-Setup-Token": setupToken,
  };
}

export async function createLocation(input: {
  name: string;
  organization_id?: number;
  organization_name?: string;
  vertical?: string;
  address?: string;
  employee_count?: number;
  manager_name?: string;
  manager_phone?: string;
  manager_email?: string;
  scheduling_platform?: string;
  integration_status?: string;
  scheduling_platform_id?: string;
  writeback_enabled?: boolean;
  writeback_subscription_tier?: string;
  onboarding_info?: string;
}, options?: { setupToken?: string }) {
  const response = await apiFetch(`${API_BASE_URL}/api/locations`, {
    method: "POST",
    headers: withSetupHeaders(options?.setupToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(input),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as { id: number; name: string };
}

export async function getLocation(locationId: number, options?: { setupToken?: string }) {
  const response = await apiFetch(`${API_BASE_URL}/api/locations/${locationId}`, {
    headers: withSetupHeaders(options?.setupToken),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    id: number;
    name: string;
    organization_id?: number | null;
    organization_name?: string | null;
    vertical?: string | null;
    address?: string | null;
    employee_count?: number | null;
    manager_name?: string | null;
    manager_phone?: string | null;
    manager_email?: string | null;
    scheduling_platform?: string | null;
    scheduling_platform_id?: string | null;
    integration_status?: string | null;
    writeback_enabled?: boolean;
    writeback_subscription_tier?: string | null;
    onboarding_info?: string | null;
  };
}

export async function connectAndSyncLocation(locationId: number, options?: { setupToken?: string }) {
  const response = await apiFetch(`${API_BASE_URL}/api/locations/${locationId}/connect-sync`, {
    method: "POST",
    headers: withSetupHeaders(options?.setupToken),
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
  location_id: number;
  platform?: string;
}) {
  const response = await apiFetch(`${API_BASE_URL}/api/onboarding/link`, {
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

export async function getSignupSession(token: string) {
  const response = await apiFetch(`${API_BASE_URL}/api/onboarding/sessions/${token}`, {
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    id: number;
    status: string;
    call_type?: string | null;
    contact_name?: string | null;
    contact_phone?: string | null;
    contact_email?: string | null;
    role_name?: string | null;
    business_name?: string | null;
    location_name?: string | null;
    vertical?: string | null;
    location_count?: number | null;
    employee_count?: number | null;
    address?: string | null;
    pain_point_summary?: string | null;
    urgency?: string | null;
    notes?: string | null;
    setup_kind?: string | null;
    scheduling_platform?: string | null;
    extracted_fields: Record<string, unknown>;
  };
}

export async function completeSignupSession(
  token: string,
  input: {
    business_name: string;
    location_name?: string;
    contact_name?: string;
    contact_phone: string;
    contact_email?: string;
    role_name?: string;
    vertical?: string;
    location_count?: number;
    employee_count?: number;
    address?: string;
    pain_point_summary?: string;
    urgency?: string;
    notes?: string;
    setup_kind?: string;
    scheduling_platform?: string;
  }
) {
  const response = await apiFetch(`${API_BASE_URL}/api/onboarding/sessions/${token}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    status: string;
    location: { id: number; name: string };
    next_path: string;
  };
}

export async function updateLocation(
  locationId: number,
  input: {
    name?: string;
    organization_id?: number;
    organization_name?: string;
    vertical?: string;
    address?: string;
    employee_count?: number;
    manager_name?: string;
    manager_phone?: string;
    manager_email?: string;
    scheduling_platform?: string;
    scheduling_platform_id?: string;
    integration_status?: string;
    onboarding_info?: string;
    writeback_enabled?: boolean;
    writeback_subscription_tier?: string;
  },
  options?: { setupToken?: string }
) {
  const response = await apiFetch(`${API_BASE_URL}/api/locations/${locationId}`, {
    method: "PATCH",
    headers: withSetupHeaders(options?.setupToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(input),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    id: number;
    name?: string;
    writeback_enabled?: boolean;
    writeback_subscription_tier?: string | null;
    scheduling_platform?: string | null;
  };
}

export async function syncLocationRoster(locationId: number, options?: { setupToken?: string }) {
  const response = await apiFetch(`${API_BASE_URL}/api/locations/${locationId}/sync-roster`, {
    method: "POST",
    headers: withSetupHeaders(options?.setupToken),
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

export async function syncLocationSchedule(locationId: number, options?: { setupToken?: string }) {
  const response = await apiFetch(`${API_BASE_URL}/api/locations/${locationId}/sync-schedule`, {
    method: "POST",
    headers: withSetupHeaders(options?.setupToken),
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
  location_id?: number;
  preferred_channel?: string;
  roles: string[];
  certifications: string[];
  source?: string;
}, options?: { setupToken?: string }) {
  const response = await apiFetch(`${API_BASE_URL}/api/workers`, {
    method: "POST",
    headers: withSetupHeaders(options?.setupToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(input),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as { id: number; name: string };
}

export async function importWorkersCsvForLocation(
  locationId: number,
  file: File,
  options?: { setupToken?: string }
) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiFetch(
    `${API_BASE_URL}/api/workers/import-csv?location_id=${locationId}`,
    {
      method: "POST",
      headers: withSetupHeaders(options?.setupToken),
      body: formData,
      cache: "no-store"
    }
  );

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as { created: number; skipped: number };
}
