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
  reliability_score?: number | null;
  status: string;
  employment_type?: string | null;
  hire_date?: string | null;
  termination_date?: string | null;
  notes?: string | null;
  employee_metadata: Record<string, unknown>;
  role_ids: string[];
  role_names: string[];
  location_ids: string[];
  location_names: string[];
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

export type EmployeeDeleteReadiness = {
  business_id: string;
  employee_id: string;
  can_delete: boolean;
  reason?: string | null;
};

export type EmployeeAvailabilityRule = {
  id: string;
  employee_id: string;
  day_of_week: number;
  start_local_time: string;
  end_local_time: string;
  timezone: string;
  availability_type: string;
  valid_from?: string | null;
  valid_until?: string | null;
  priority: number;
  availability_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type SelfEmployeeAvailability = {
  employee_id: string;
  employee_name: string;
  timezone: string;
  rules: EmployeeAvailabilityRule[];
};

export type EmployeeAvailabilityRulePayload = {
  day_of_week: number;
  start_local_time: string;
  end_local_time: string;
  timezone: string;
  availability_type?: string;
  valid_from?: string | null;
  valid_until?: string | null;
  priority?: number;
  availability_metadata?: Record<string, unknown>;
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

export type EmployeeCreatePayload = {
  full_name: string;
  preferred_name?: string | null;
  phone_e164?: string | null;
  email?: string | null;
  external_ref?: string | null;
  employee_number?: string | null;
  employment_type?: string | null;
  primary_location_id?: string | null;
  hire_date?: string | null;
  notes?: string | null;
  employee_metadata?: Record<string, unknown>;
};

export type EmployeeImportError = {
  row_number?: number | null;
  message: string;
};

export type EmployeeBulkImportResponse = {
  created_count: number;
  skipped_count: number;
  employees: EmployeeSummary[];
  errors: EmployeeImportError[];
  default_location_id?: string | null;
  default_location_name?: string | null;
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

export async function createEmployee(
  businessId: string,
  payload: EmployeeCreatePayload,
): Promise<EmployeeSummary> {
  const response = await apiFetchApp(`${API_PREFIX}/businesses/${businessId}/employees`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as EmployeeSummary;
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

export async function getEmployeeDeleteReadiness(
  businessId: string,
  employeeId: string,
): Promise<EmployeeDeleteReadiness> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/employees/${employeeId}/delete-readiness`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as EmployeeDeleteReadiness;
}

export async function deleteEmployee(
  businessId: string,
  employeeId: string,
): Promise<{ deleted: boolean; employee_id: string }> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/employees/${employeeId}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as { deleted: boolean; employee_id: string };
}

export async function getSelfEmployeeAvailability(
  businessId: string,
): Promise<SelfEmployeeAvailability> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/employees/availability-rules/self`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as SelfEmployeeAvailability;
}

export async function replaceSelfEmployeeAvailability(
  businessId: string,
  payload: { rules: EmployeeAvailabilityRulePayload[] },
): Promise<SelfEmployeeAvailability> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/employees/availability-rules/self`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as SelfEmployeeAvailability;
}

export async function importEmployees(
  businessId: string,
  file: File,
): Promise<EmployeeBulkImportResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/employees/import`,
    {
      method: "POST",
      body: formData,
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as EmployeeBulkImportResponse;
}

export async function downloadEmployeeImportTemplate(
  businessId: string,
): Promise<void> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/employees/import/template`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "backfill-employee-roster-template.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
