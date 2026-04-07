import { API_PREFIX, apiFetchApp } from "./backend-client";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export type BusinessLocation = {
  id: string;
  business_id: string;
  name: string;
  display_name: string;
  slug: string;
  address_line_1?: string | null;
  address_line_2?: string | null;
  locality?: string | null;
  region?: string | null;
  postal_code?: string | null;
  country_code: string;
  timezone: string;
  latitude?: string | null;
  longitude?: string | null;
  google_place_id?: string | null;
  google_place_metadata: Record<string, unknown>;
  is_active: boolean;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type BusinessRole = {
  id: string;
  business_id: string;
  code: string;
  name: string;
  category?: string | null;
  description?: string | null;
  min_notice_minutes: number;
  default_shift_length_minutes?: number | null;
  coverage_priority: number;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type LocationRoleAssignment = {
  id: string;
  location_id: string;
  role_id: string;
  is_active: boolean;
  min_headcount?: number | null;
  max_headcount?: number | null;
  premium_rules: Record<string, unknown>;
  coverage_settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type LocationRoleUpsertPayload = {
  role_id: string;
  min_headcount?: number | null;
  max_headcount?: number | null;
  premium_rules?: Record<string, unknown>;
  coverage_settings?: Record<string, unknown>;
};

export type BusinessRoleCreatePayload = {
  name: string;
  code?: string;
  category?: string | null;
  description?: string | null;
  min_notice_minutes?: number;
  default_shift_length_minutes?: number | null;
  coverage_priority?: number;
  metadata_json?: Record<string, unknown>;
};

export type LocationRoleCreateAndAssignPayload = BusinessRoleCreatePayload & {
  min_headcount?: number | null;
  max_headcount?: number | null;
  premium_rules?: Record<string, unknown>;
  coverage_settings?: Record<string, unknown>;
};

export type LocationRoleCreateAndAssignResult = {
  role: BusinessRole;
  location_role: LocationRoleAssignment;
};

export async function listBusinessLocations(
  businessId: string,
): Promise<BusinessLocation[]> {
  const response = await apiFetchApp(`${API_PREFIX}/businesses/${businessId}/locations`);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as BusinessLocation[];
}

export async function listBusinessRoles(
  businessId: string,
): Promise<BusinessRole[]> {
  const response = await apiFetchApp(`${API_PREFIX}/businesses/${businessId}/roles`);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as BusinessRole[];
}

export async function createBusinessRole(
  businessId: string,
  payload: BusinessRoleCreatePayload,
): Promise<BusinessRole> {
  const response = await apiFetchApp(`${API_PREFIX}/businesses/${businessId}/roles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as BusinessRole;
}

export async function createAndAssignLocationRole(
  businessId: string,
  locationId: string,
  payload: LocationRoleCreateAndAssignPayload,
): Promise<LocationRoleCreateAndAssignResult> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/roles`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as LocationRoleCreateAndAssignResult;
}

export async function getLocationRoles(
  businessId: string,
  locationId: string,
): Promise<LocationRoleAssignment[]> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/roles`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as LocationRoleAssignment[];
}

export async function replaceLocationRoles(
  businessId: string,
  locationId: string,
  roles: LocationRoleUpsertPayload[],
): Promise<LocationRoleAssignment[]> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/roles`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ roles }),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as LocationRoleAssignment[];
}
