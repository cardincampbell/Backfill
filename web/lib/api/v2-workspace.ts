import type { PlaceSuggestion } from "@/lib/api/places";
import { buildV2LocationPayloadFromPlace } from "@/lib/place-location-v2";
import { apiFetchV2, fetchV2Json, V2_API_PREFIX } from "./v2-client";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export type V2WorkspaceUser = {
  id: string;
  full_name?: string | null;
  email?: string | null;
  primary_phone_e164?: string | null;
};

export type V2WorkspaceLocation = {
  membership_id: string;
  membership_role: string;
  membership_scope: string;
  business_id: string;
  business_name: string;
  business_slug: string;
  location_id: string;
  location_name: string;
  location_slug: string;
  address_line_1?: string | null;
  locality?: string | null;
  region?: string | null;
  postal_code?: string | null;
  country_code: string;
  timezone: string;
  google_place_id?: string | null;
};

export type V2WorkspaceBusiness = {
  business_id: string;
  business_name: string;
  business_slug: string;
  membership_role: string;
  location_count: number;
  locations: V2WorkspaceLocation[];
};

export type V2BusinessCreatePayload = {
  legal_name: string;
  brand_name?: string;
  timezone?: string;
  primary_email?: string | null;
};

export type V2Workspace = {
  user: V2WorkspaceUser;
  onboarding_required: boolean;
  businesses: V2WorkspaceBusiness[];
  locations: V2WorkspaceLocation[];
};

export type V2ManagerAccessEntry = {
  id: string;
  location_id: string;
  entry_kind: "membership" | "invite";
  manager_name?: string | null;
  manager_email?: string | null;
  phone_e164?: string | null;
  role: string;
  invite_status: string;
  invite_channel: string;
  accepted_at?: string | null;
  revoked_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type V2ManagerAccessInvitePayload = {
  email: string;
  manager_name?: string;
  role?: string;
};

export type V2LocationSettings = {
  location_id: string;
  coverage_requires_manager_approval: boolean;
  late_arrival_policy: "wait" | "manager_action" | "start_coverage";
  missed_check_in_policy: "manager_action" | "start_coverage";
  agency_supply_approved: boolean;
  writeback_enabled: boolean;
  timezone?: string | null;
  scheduling_platform?: string | null;
  integration_status?: string | null;
  backfill_shifts_enabled: boolean;
  backfill_shifts_launch_state: string;
  backfill_shifts_beta_eligible: boolean;
};

export type V2LocationSettingsUpdate = Partial<
  Omit<V2LocationSettings, "location_id">
>;

export type V2WorkspaceBoard = {
  business_id: string;
  business_name: string;
  business_slug: string;
  location_id: string;
  location_name: string;
  location_slug: string;
  address_line_1?: string | null;
  locality?: string | null;
  region?: string | null;
  postal_code?: string | null;
  country_code: string;
  timezone: string;
  week_start_date: string;
  week_end_date: string;
  roles: Array<{
    role_id: string;
    role_code: string;
    role_name: string;
    min_headcount?: number | null;
    max_headcount?: number | null;
  }>;
  workers: Array<{
    employee_id: string;
    full_name: string;
    preferred_name?: string | null;
    phone_e164?: string | null;
    email?: string | null;
    home_location_id?: string | null;
    avg_response_time_seconds?: number | null;
    role_ids: string[];
    role_names: string[];
    reliability_score: number;
    can_cover_here: boolean;
    can_blast_here: boolean;
  }>;
  shifts: Array<{
    shift_id: string;
    role_id: string;
    role_code: string;
    role_name: string;
    starts_at: string;
    ends_at: string;
    status: string;
    seats_requested: number;
    seats_filled: number;
    requires_manager_approval: boolean;
    premium_cents: number;
    notes?: string | null;
    current_assignment?: {
      assignment_id: string;
      employee_id?: string | null;
      employee_name?: string | null;
      status: string;
      assigned_via: string;
      accepted_at?: string | null;
    } | null;
    coverage_case_id?: string | null;
    coverage_case_status?: string | null;
    pending_offer_count: number;
    delivered_offer_count: number;
    manager_action_required: boolean;
  }>;
  action_summary: {
    total: number;
    approval_required: number;
    active_coverage: number;
    open_shifts: number;
  };
};

export type V2ShiftCreatePayload = {
  location_id: string;
  role_id: string;
  timezone: string;
  starts_at: string;
  ends_at: string;
  seats_requested?: number;
  requires_manager_approval?: boolean;
  premium_cents?: number;
  notes?: string | null;
  source_system?: string;
  source_shift_id?: string | null;
  shift_metadata?: Record<string, unknown>;
};

export type V2ShiftUpdatePayload = Partial<
  Omit<V2ShiftCreatePayload, "location_id" | "source_system" | "source_shift_id">
> & {
  role_id?: string;
  shift_metadata?: Record<string, unknown>;
};

export type V2CoverageCase = {
  id: string;
  shift_id: string;
  location_id: string;
  role_id: string;
  status: string;
  phase_target: string;
  reason_code?: string | null;
  priority: number;
  requires_manager_approval: boolean;
  triggered_by?: string | null;
  case_metadata: Record<string, unknown>;
  opened_at?: string | null;
  closed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type V2CoverageExecutionDecision = {
  coverage_case_id: string;
  shift_id: string;
  recommended_phase?: string | null;
  recommendation_reason: string;
  phase_1_candidate_count: number;
  phase_2_candidate_count: number;
  phase_1_plan: {
    phase: string;
    operating_mode: string;
    strategy: string;
    time_to_shift_minutes: number;
    dispatch_limit: number;
    offer_ttl_minutes: number;
    premium_cents: number;
    phase_2_eligible: boolean;
    phase_2_reason?: string | null;
  };
  phase_2_plan: {
    phase: string;
    operating_mode: string;
    strategy: string;
    time_to_shift_minutes: number;
    dispatch_limit: number;
    offer_ttl_minutes: number;
    premium_cents: number;
    phase_2_eligible: boolean;
    phase_2_reason?: string | null;
  };
};

export type V2CoverageDispatchResult = {
  decision: V2CoverageExecutionDecision;
  phase_executed?: string | null;
  coverage_case: V2CoverageCase;
  candidate_count: number;
  offers: Array<{
    id: string;
    status: string;
    employee_id: string;
    channel: string;
    expires_at?: string | null;
  }>;
};

export type V2EmployeeEnrollmentPayload = {
  location_id: string;
  role_ids: string[];
  full_name: string;
  preferred_name?: string | null;
  phone_e164?: string | null;
  email?: string | null;
  employment_type?: string | null;
  notes?: string | null;
  employee_metadata?: Record<string, unknown>;
};

export async function getV2Workspace(): Promise<V2Workspace | null> {
  return fetchV2Json<V2Workspace>(`${V2_API_PREFIX}/workspace`);
}

export async function createV2Business(payload: V2BusinessCreatePayload) {
  const response = await apiFetchV2(`${V2_API_PREFIX}/businesses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    id: string;
    legal_name: string;
    brand_name?: string | null;
    slug: string;
    timezone: string;
  };
}

export async function createV2LocationFromPlace(
  businessId: string,
  place: PlaceSuggestion,
  options?: {
    timezone?: string;
    settings?: Record<string, unknown>;
  },
) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/locations`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildV2LocationPayloadFromPlace(place, options)),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    id: string;
    business_id: string;
    name: string;
    slug: string;
  };
}

export async function deleteV2Location(businessId: string, locationId: string) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/locations/${locationId}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as { deleted: boolean; location_id: string };
}

export async function inviteV2LocationManager(
  businessId: string,
  locationId: string,
  payload: V2ManagerAccessInvitePayload,
) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/locations/${locationId}/manager-access`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    location_id: string;
    created: boolean;
    delivery_id?: string | null;
    access: V2ManagerAccessEntry;
  };
}

export async function listV2LocationManagers(
  businessId: string,
  locationId: string,
) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/locations/${locationId}/manager-access`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as V2ManagerAccessEntry[];
}

export async function revokeV2LocationManager(
  businessId: string,
  locationId: string,
  membershipId: string,
) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/locations/${locationId}/manager-access/${membershipId}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    revoked: boolean;
    location_id: string;
    access_kind: string;
    access_id: string;
  };
}

export async function revokeV2LocationManagerInvite(
  businessId: string,
  locationId: string,
  inviteId: string,
) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/locations/${locationId}/manager-invites/${inviteId}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    revoked: boolean;
    location_id: string;
    access_kind: string;
    access_id: string;
  };
}

export async function getV2LocationSettings(
  businessId: string,
  locationId: string,
) {
  return fetchV2Json<V2LocationSettings>(
    `${V2_API_PREFIX}/businesses/${businessId}/locations/${locationId}/settings`,
  );
}

export async function updateV2LocationSettings(
  businessId: string,
  locationId: string,
  payload: V2LocationSettingsUpdate,
) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/locations/${locationId}/settings`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as V2LocationSettings;
}

export async function getV2LocationBoard(
  businessId: string,
  locationId: string,
  weekStart?: string,
) {
  const qs = weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : "";
  return fetchV2Json<V2WorkspaceBoard>(
    `${V2_API_PREFIX}/workspace/businesses/${businessId}/locations/${locationId}/board${qs}`,
  );
}

export async function createV2Shift(
  businessId: string,
  payload: V2ShiftCreatePayload,
) {
  const response = await apiFetchV2(`${V2_API_PREFIX}/businesses/${businessId}/shifts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as V2WorkspaceBoard["shifts"][number];
}

export async function updateV2Shift(
  businessId: string,
  shiftId: string,
  payload: V2ShiftUpdatePayload,
) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/shifts/${shiftId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as V2WorkspaceBoard["shifts"][number];
}

export async function deleteV2Shift(businessId: string, shiftId: string) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/shifts/${shiftId}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as { deleted: boolean; shift_id: string };
}

export async function createV2CoverageCase(
  businessId: string,
  payload: {
    shift_id: string;
    phase_target?: string;
    reason_code?: string;
    priority?: number;
    requires_manager_approval?: boolean;
    triggered_by?: string;
    case_metadata?: Record<string, unknown>;
  },
) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/coverage-cases`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as V2CoverageCase;
}

export async function getV2CoveragePlan(
  businessId: string,
  coverageCaseId: string,
) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/coverage-cases/${coverageCaseId}/plan`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as V2CoverageExecutionDecision;
}

export async function executeV2CoverageCase(
  businessId: string,
  coverageCaseId: string,
  payload?: {
    phase_override?: string;
    channel?: string;
    dispatch_limit?: number;
    offer_ttl_minutes?: number;
    run_metadata?: Record<string, unknown>;
  },
) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/coverage-cases/${coverageCaseId}/execute`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as V2CoverageDispatchResult;
}

export async function enrollV2EmployeeAtLocation(
  businessId: string,
  payload: V2EmployeeEnrollmentPayload,
) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/businesses/${businessId}/employees/enroll`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    employee: {
      id: string;
      full_name: string;
      preferred_name?: string | null;
      email?: string | null;
      phone_e164?: string | null;
    };
    roles: Array<{
      id: string;
      role_id: string;
      is_primary: boolean;
    }>;
  };
}
