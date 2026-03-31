import { API_BASE_URL, apiFetch } from "./client";
import { buildLocationPayloadFromPlace } from "@/lib/place-location";
import type { PlaceSuggestion } from "./places";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function deleteLocation(locationId: number) {
  const response = await apiFetch(`${API_BASE_URL}/api/locations/${locationId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as { deleted: boolean; location_id: number };
}

export async function createLocationFromPlace(
  place: PlaceSuggestion,
  input: Parameters<typeof buildLocationPayloadFromPlace>[1],
) {
  const response = await apiFetch(`${API_BASE_URL}/api/locations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildLocationPayloadFromPlace(place, input)),
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    id: number;
    name: string;
    organization_id?: number | null;
    organization_name?: string | null;
  };
}

export type InviteLocationManagerPayload = {
  email: string;
  manager_name?: string;
};

export type LocationManagerMembership = {
  id?: number | null;
  location_id: number;
  entry_kind: "membership" | "invite";
  phone?: string | null;
  manager_name?: string | null;
  manager_email?: string | null;
  role: string;
  invite_status: string;
  invite_channel: string;
  invited_by_phone?: string | null;
  accepted_at?: string | null;
  revoked_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export async function inviteLocationManager(
  locationId: number,
  payload: InviteLocationManagerPayload,
) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/locations/${locationId}/manager-memberships`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    location_id: number;
    created: boolean;
    delivery_id?: string | null;
    membership: LocationManagerMembership;
  };
}

export async function listLocationManagers(locationId: number) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/locations/${locationId}/manager-memberships`,
  );

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as LocationManagerMembership[];
}

export async function revokeLocationManager(
  locationId: number,
  membershipId: number,
) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/locations/${locationId}/manager-memberships/${membershipId}`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    revoked: boolean;
    location_id: number;
    access_kind: string;
    access_id: number;
  };
}

export async function revokeLocationManagerInvite(
  locationId: number,
  inviteId: number,
) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/locations/${locationId}/manager-invites/${inviteId}`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as {
    revoked: boolean;
    location_id: number;
    access_kind: string;
    access_id: number;
  };
}
