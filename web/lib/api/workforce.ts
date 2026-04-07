import { API_PREFIX, apiFetchApp } from "./backend-client";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export type EmployeeSummary = {
  id: string;
  business_id: string;
  primary_location_id?: string | null;
  primary_location_name?: string | null;
  primary_role_id?: string | null;
  primary_role_name?: string | null;
  external_ref?: string | null;
  employee_number?: string | null;
  full_name: string;
  preferred_name?: string | null;
  phone_e164?: string | null;
  email?: string | null;
  status: string;
  employment_type?: string | null;
  hire_date?: string | null;
  termination_date?: string | null;
  notes?: string | null;
  employee_metadata: Record<string, unknown>;
  role_ids: string[];
  location_ids: string[];
  created_at: string;
  updated_at: string;
};

export type EmployeeRoleAssignment = {
  id: string;
  employee_id: string;
  role_id: string;
  role_code?: string | null;
  role_name?: string | null;
  proficiency_level: number;
  is_primary: boolean;
  acquired_at?: string | null;
  role_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type EmployeeLocationAssignment = {
  id: string;
  employee_id: string;
  location_id: string;
  location_name?: string | null;
  location_slug?: string | null;
  is_primary: boolean;
  access_level: string;
  location_source?: string | null;
  can_cover_last_minute: boolean;
  can_blast: boolean;
  travel_radius_miles?: number | null;
  location_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type EmployeeProfile = EmployeeSummary & {
  roles: EmployeeRoleAssignment[];
  locations: EmployeeLocationAssignment[];
};

export type EmployeeRoleUpsertPayload = {
  role_id: string;
  proficiency_level?: number;
  is_primary?: boolean;
  role_metadata?: Record<string, unknown>;
};

export type EmployeeLocationUpsertPayload = {
  location_id: string;
  is_primary?: boolean;
  access_level?: string;
  location_source?: string | null;
  can_cover_last_minute?: boolean;
  can_blast?: boolean;
  travel_radius_miles?: number | null;
  location_metadata?: Record<string, unknown>;
};

export type EmployeeUpdatePayload = {
  full_name?: string | null;
  preferred_name?: string | null;
  phone_e164?: string | null;
  email?: string | null;
  external_ref?: string | null;
  employee_number?: string | null;
  employment_type?: string | null;
  status?: string | null;
  hire_date?: string | null;
  termination_date?: string | null;
  notes?: string | null;
  employee_metadata?: Record<string, unknown>;
  roles?: EmployeeRoleUpsertPayload[];
  locations?: EmployeeLocationUpsertPayload[];
};

export async function listEmployees(
  businessId: string,
): Promise<EmployeeSummary[]> {
  const response = await apiFetchApp(`${API_PREFIX}/businesses/${businessId}/employees`);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as EmployeeSummary[];
}

export async function getEmployeeProfile(
  businessId: string,
  employeeId: string,
): Promise<EmployeeProfile> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/employees/${employeeId}`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as EmployeeProfile;
}

export async function updateEmployee(
  businessId: string,
  employeeId: string,
  payload: EmployeeUpdatePayload,
): Promise<EmployeeProfile> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/employees/${employeeId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as EmployeeProfile;
}
