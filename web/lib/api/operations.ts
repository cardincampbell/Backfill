/**
 * Operational API endpoints – imports, coverage, roster, manager actions,
 * location settings, metrics, exceptions, attendance, enrollment, and
 * worker management.
 *
 * Extracted from shifts-api.ts for modularity.
 */
import type {
  CoverageResponse,
  EligibleWorkersResponse,
  ImportCommitResponse,
  ImportErrorCsvResponse,
  ImportJob,
  ImportMappingResponse,
  ImportRowResolveResponse,
  ImportRowsResponse,
  ImportUploadResponse,
  LocationSettings,
  ManagerActionsResponse,
  RosterResponse,
  ScheduleExceptionQueueResponse,
  Worker,
} from "../types";

import { API_BASE_URL, apiFetch, fetchJson, USE_MOCKS } from "./client";

// ── Import endpoints ──────────────────────────────────────────────────────

export async function getImportJob(
  jobId: number
): Promise<ImportJob | null> {
  const live = await fetchJson<ImportJob>(`/api/import-jobs/${jobId}`);
  if (live) return live;
  if (!USE_MOCKS) return null;
  return MOCK_IMPORT_JOB;
}

export async function getImportRows(
  jobId: number
): Promise<ImportRowsResponse | null> {
  const live = await fetchJson<ImportRowsResponse>(
    `/api/import-jobs/${jobId}/rows`
  );
  if (live) return live;
  if (!USE_MOCKS) return null;
  return MOCK_IMPORT_ROWS;
}

export async function createImportJob(
  locationId: number,
  importType: string,
  filename: string
): Promise<ImportJob | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/locations/${locationId}/import-jobs`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ import_type: importType, filename }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as ImportJob;
  } catch {
    return null;
  }
}

export async function uploadImportFile(
  jobId: number,
  file: File
): Promise<ImportUploadResponse | null> {
  try {
    const form = new FormData();
    form.append("file", file);
    const res = await apiFetch(
      `${API_BASE_URL}/api/import-jobs/${jobId}/upload`,
      { method: "POST", body: form }
    );
    if (!res.ok) return null;
    return (await res.json()) as ImportUploadResponse;
  } catch {
    return null;
  }
}

export async function saveImportMapping(
  jobId: number,
  mapping: Record<string, string>
): Promise<ImportMappingResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/import-jobs/${jobId}/mapping`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mapping }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as ImportMappingResponse;
  } catch {
    return null;
  }
}

export async function commitImport(
  jobId: number
): Promise<ImportCommitResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/import-jobs/${jobId}/commit`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    if (!res.ok) return null;
    return (await res.json()) as ImportCommitResponse;
  } catch {
    return null;
  }
}

export async function resolveImportRow(
  rowId: number,
  action: "fix" | "ignore" | "retry",
  normalizedPayload?: Record<string, string>
): Promise<ImportRowResolveResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/import-rows/${rowId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          normalized_payload: normalizedPayload ?? null,
        }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as ImportRowResolveResponse;
  } catch {
    return null;
  }
}

export async function exportImportErrorsCsv(
  jobId: number
): Promise<ImportErrorCsvResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/import-jobs/${jobId}/error-csv`
    );
    if (!res.ok) return null;
    return (await res.json()) as ImportErrorCsvResponse;
  } catch {
    return null;
  }
}

// ── Coverage endpoints ────────────────────────────────────────────────────

export async function getCoverage(
  locationId: number,
  weekStart?: string
): Promise<CoverageResponse | null> {
  const qs = weekStart ? `?week_start=${weekStart}` : "";
  const live = await fetchJson<CoverageResponse>(
    `/api/locations/${locationId}/coverage${qs}`
  );
  if (live) return live;
  if (!USE_MOCKS) return null;
  return MOCK_COVERAGE;
}

// ── Roster endpoints ──────────────────────────────────────────────────────

export async function getLocationRoster(
  locationId: number,
  includeInactive = true
): Promise<RosterResponse | null> {
  return fetchJson<RosterResponse>(
    `/api/locations/${locationId}/roster?include_inactive=${includeInactive}`
  );
}

export async function getEligibleWorkers(
  locationId: number,
  role?: string
): Promise<EligibleWorkersResponse | null> {
  const qs = role ? `?role=${encodeURIComponent(role)}` : "";
  return fetchJson<EligibleWorkersResponse>(
    `/api/locations/${locationId}/eligible-workers${qs}`
  );
}

export async function getLocationWorkers(
  locationId: number
): Promise<Worker[]> {
  const roster = await getLocationRoster(locationId, true);
  if (roster) return roster.workers;
  return (
    (await fetchJson<Worker[]>(`/api/workers?location_id=${locationId}`)) ?? []
  );
}

export async function deactivateWorker(
  workerId: number
): Promise<Worker | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/workers/${workerId}/deactivate`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    if (!res.ok) return null;
    return (await res.json()) as Worker;
  } catch {
    return null;
  }
}

export async function reactivateWorker(
  workerId: number
): Promise<Worker | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/workers/${workerId}/reactivate`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    if (!res.ok) return null;
    return (await res.json()) as Worker;
  } catch {
    return null;
  }
}

export async function transferWorker(
  workerId: number,
  targetLocationId: number,
  roles?: string[],
  priorityRank?: number
): Promise<Worker | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/workers/${workerId}/transfer`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_location_id: targetLocationId,
          roles: roles ?? null,
          priority_rank: priorityRank ?? null,
        }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as Worker;
  } catch {
    return null;
  }
}

// ── Manager action queue endpoints ────────────────────────────────────────

export async function getManagerActions(
  locationId: number,
  weekStart?: string
): Promise<ManagerActionsResponse | null> {
  const qs = weekStart ? `?week_start=${weekStart}` : "";
  return fetchJson<ManagerActionsResponse>(
    `/api/locations/${locationId}/manager-actions${qs}`
  );
}

export async function approveFill(cascadeId: number): Promise<boolean> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/cascades/${cascadeId}/approve-fill`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    return res.ok;
  } catch {
    return false;
  }
}

export async function declineFill(cascadeId: number): Promise<boolean> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/cascades/${cascadeId}/decline-fill`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    return res.ok;
  } catch {
    return false;
  }
}

export async function approveAgency(cascadeId: number): Promise<boolean> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/cascades/${cascadeId}/approve-agency`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    return res.ok;
  } catch {
    return false;
  }
}

// ── Location settings endpoints ───────────────────────────────────────────

export async function getLocationSettings(
  locationId: number
): Promise<LocationSettings | null> {
  return fetchJson<LocationSettings>(
    `/api/locations/${locationId}/settings`
  );
}

export async function updateLocationSettings(
  locationId: number,
  updates: Partial<LocationSettings>
): Promise<LocationSettings | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/locations/${locationId}/settings`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as LocationSettings;
  } catch {
    return null;
  }
}

// ── Backfill Shifts metrics endpoints ─────────────────────────────────────

export async function getBackfillShiftsMetrics(
  locationId: number,
  days = 30
): Promise<import("../types").BackfillShiftsMetricsResponse | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/locations/${locationId}/backfill-shifts-metrics?days=${days}`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").BackfillShiftsMetricsResponse;
  } catch {
    return null;
  }
}

export async function getBackfillShiftsActivity(
  locationId: number,
  limit = 50
): Promise<import("../types").BackfillShiftsActivityResponse | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/locations/${locationId}/backfill-shifts-activity?limit=${limit}`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").BackfillShiftsActivityResponse;
  } catch {
    return null;
  }
}

// ── Schedule exception queue endpoints ────────────────────────────────────

export async function getScheduleExceptions(
  locationId: number,
  actionRequiredOnly = false
): Promise<ScheduleExceptionQueueResponse | null> {
  const qs = actionRequiredOnly ? "?action_required_only=true" : "";
  return fetchJson<ScheduleExceptionQueueResponse>(
    `/api/locations/${locationId}/schedule-exceptions${qs}`
  );
}

export async function executeExceptionAction(
  locationId: number,
  action: { exception_code: string; shift_id: number; action: string; cascade_id?: number }
): Promise<ScheduleExceptionQueueResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/locations/${locationId}/schedule-exceptions/actions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(action),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as ScheduleExceptionQueueResponse;
  } catch {
    return null;
  }
}

// ── Attendance action endpoints ───────────────────────────────────────────

export async function waitForWorker(shiftId: number): Promise<boolean> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/shifts/${shiftId}/attendance/wait`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    return res.ok;
  } catch {
    return false;
  }
}

export async function startCoverageForShift(shiftId: number): Promise<boolean> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/shifts/${shiftId}/coverage/start`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    return res.ok;
  } catch {
    return false;
  }
}

// ── Enrollment invite endpoints ───────────────────────────────────────────

export async function sendEnrollmentInvites(
  locationId: number,
  workerIds?: number[]
): Promise<{ sent_count: number } | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/locations/${locationId}/enrollment-invites`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(workerIds ? { worker_ids: workerIds } : {}),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as { sent_count: number };
  } catch {
    return null;
  }
}

// ── Worker management endpoints ───────────────────────────────────────────

export async function addWorkerToLocation(
  locationId: number,
  payload: { name: string; phone: string; roles: string[] }
): Promise<{ id: number; name: string } | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/workers`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...payload,
          location_id: locationId,
          certifications: [],
          source: "manual",
        }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as { id: number; name: string };
  } catch {
    return null;
  }
}

// ── Mock data (matches contract freeze B payloads exactly) ────────────────

const MOCK_IMPORT_JOB: ImportJob = {
  id: 12,
  location_id: 7,
  import_type: "combined",
  status: "action_needed",
  filename: "week-1.csv",
  summary: {
    total_rows: 40,
    worker_rows: 12,
    shift_rows: 28,
    success_rows: 33,
    warning_rows: 4,
    failed_rows: 3,
  },
};

const MOCK_IMPORT_ROWS: ImportRowsResponse = {
  job: { id: 12, status: "action_needed" },
  rows: [
    {
      id: 81,
      row_number: 7,
      entity_type: "worker",
      outcome: "warning",
      error_code: "phone_malformed",
      error_message: "Phone number could not be normalized",
      raw_payload: { employee_name: "Maria Lopez", mobile: "3105550111" },
      normalized_payload: null,
    },
    {
      id: 82,
      row_number: 15,
      entity_type: "shift",
      outcome: "failed",
      error_code: "missing_date",
      error_message: "Date field is required but empty",
      raw_payload: { employee_name: "Jordan Smith", role: "server", start: "11:00", end: "19:00" },
      normalized_payload: null,
    },
    {
      id: 83,
      row_number: 22,
      entity_type: "worker",
      outcome: "warning",
      error_code: "duplicate_phone",
      error_message: "Phone number matches existing worker #44",
      raw_payload: { employee_name: "Maria L.", mobile: "+13105550111" },
      normalized_payload: null,
    },
    {
      id: 84,
      row_number: 28,
      entity_type: "shift",
      outcome: "failed",
      error_code: "invalid_time",
      error_message: "Start time could not be parsed",
      raw_payload: { employee_name: "Alex Chen", role: "host", date: "2026-04-14", start: "morning", end: "4pm" },
      normalized_payload: null,
    },
    {
      id: 85,
      row_number: 33,
      entity_type: "worker",
      outcome: "warning",
      error_code: "unknown_role",
      error_message: "Role 'barista' not found in location roles",
      raw_payload: { employee_name: "Sam Torres", mobile: "+13105550199", role: "barista" },
      normalized_payload: null,
    },
    {
      id: 86,
      row_number: 36,
      entity_type: "shift",
      outcome: "warning",
      error_code: "no_assignee_match",
      error_message: "Employee 'Chris P.' could not be matched to a roster record",
      raw_payload: { employee_name: "Chris P.", role: "line_cook", date: "2026-04-16", start: "09:00", end: "17:00" },
      normalized_payload: null,
    },
    {
      id: 87,
      row_number: 39,
      entity_type: "shift",
      outcome: "failed",
      error_code: "missing_role",
      error_message: "Role field is required but empty",
      raw_payload: { employee_name: "Jordan Smith", date: "2026-04-17", start: "06:00", end: "14:00" },
      normalized_payload: null,
    },
  ],
};

const MOCK_COVERAGE: CoverageResponse = {
  location_id: 7,
  at_risk_shifts: [
    {
      shift_id: 901,
      role: "line_cook",
      date: "2026-04-13",
      start_time: "09:00:00",
      current_status: "vacant",
      cascade_id: 210,
      coverage_status: "offering",
    },
    {
      shift_id: 905,
      role: "server",
      date: "2026-04-18",
      start_time: "17:00:00",
      current_status: "vacant",
      cascade_id: null,
      coverage_status: "unassigned",
    },
  ],
};
