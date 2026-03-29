/**
 * Schedule endpoint functions extracted from shifts-api.ts.
 */
import type {
  WeeklyScheduleResponse,
  PublishResponse,
  CopyLastWeekResponse,
  AmendAssignmentResponse,
  ScheduleLifecycleResponse,
  CreateShiftResponse,
  DeleteShiftResponse,
} from "../types";
import type { BatchShiftActionResponse } from "../types";
import { API_BASE_URL, USE_MOCKS, apiFetch, fetchJson } from "./client";

// ── Schedule endpoints ────────────────────────────────────────────────────

export async function getWeeklySchedule(
  locationId: number,
  weekStart?: string
): Promise<WeeklyScheduleResponse | null> {
  const qs = weekStart ? `?week_start=${weekStart}` : "";
  const live = await fetchJson<WeeklyScheduleResponse>(
    `/api/locations/${locationId}/schedules/current${qs}`
  );
  if (live) return live;
  if (!USE_MOCKS) return null;
  return MOCK_WEEKLY_SCHEDULE;
}

export async function publishSchedule(
  scheduleId: number
): Promise<PublishResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedules/${scheduleId}/publish`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    if (!res.ok) return null;
    return (await res.json()) as PublishResponse;
  } catch {
    return null;
  }
}

export async function copyLastWeek(
  locationId: number,
  sourceScheduleId: number,
  targetWeekStart: string
): Promise<CopyLastWeekResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/locations/${locationId}/schedules/copy-last-week`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_schedule_id: sourceScheduleId,
          target_week_start_date: targetWeekStart,
        }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as CopyLastWeekResponse;
  } catch {
    return null;
  }
}

export async function amendAssignment(
  shiftId: number,
  workerId: number,
  notes?: string
): Promise<AmendAssignmentResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/shifts/${shiftId}/assignment`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          worker_id: workerId,
          assignment_status: "assigned",
          notes,
        }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as AmendAssignmentResponse;
  } catch {
    return null;
  }
}

export async function recallSchedule(
  scheduleId: number
): Promise<ScheduleLifecycleResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedules/${scheduleId}/recall`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    if (!res.ok) return null;
    return (await res.json()) as ScheduleLifecycleResponse;
  } catch {
    return null;
  }
}

export async function archiveSchedule(
  scheduleId: number
): Promise<ScheduleLifecycleResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedules/${scheduleId}/archive`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    if (!res.ok) return null;
    return (await res.json()) as ScheduleLifecycleResponse;
  } catch {
    return null;
  }
}

export async function createScheduleShift(
  scheduleId: number,
  payload: {
    role: string;
    date: string;
    start_time: string;
    end_time: string;
    pay_rate?: number;
    worker_id?: number | null;
    notes?: string;
    shift_label?: string;
    start_open_shift_offer?: boolean;
  }
): Promise<CreateShiftResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedules/${scheduleId}/shifts`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as CreateShiftResponse;
  } catch {
    return null;
  }
}

export async function deleteShift(
  shiftId: number
): Promise<DeleteShiftResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/shifts/${shiftId}`,
      { method: "DELETE" }
    );
    if (!res.ok) return null;
    return (await res.json()) as DeleteShiftResponse;
  } catch {
    return null;
  }
}

// ── Open-shift lifecycle endpoints ────────────────────────────────────────

export async function offerOpenShifts(
  scheduleId: number
): Promise<{ offered_count: number; coverage_review_url?: string } | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedules/${scheduleId}/offer-open-shifts`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    if (!res.ok) return null;
    return (await res.json()) as { offered_count: number; coverage_review_url?: string };
  } catch {
    return null;
  }
}

export async function cancelOffer(shiftId: number): Promise<boolean> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/shifts/${shiftId}/coverage/cancel`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    return res.ok;
  } catch {
    return false;
  }
}

export async function closeOpenShift(shiftId: number): Promise<boolean> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/shifts/${shiftId}/open-shift/close`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    return res.ok;
  } catch {
    return false;
  }
}

export type BulkEditFields = {
  role?: string;
  date?: string;
  start_time?: string;
  end_time?: string;
  pay_rate?: number;
  notes?: string;
  shift_label?: string;
  spans_midnight?: boolean;
};

export async function bulkEditShifts(
  scheduleId: number,
  shiftIds: number[],
  fields: BulkEditFields
): Promise<BatchShiftActionResponse & { updated_fields?: string[] } | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedules/${scheduleId}/shifts`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shift_ids: shiftIds, ...fields }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as BatchShiftActionResponse & { updated_fields?: string[] };
  } catch {
    return null;
  }
}

export async function bulkAssignShifts(
  scheduleId: number,
  assignments: { shift_id: number; worker_id: number | null; notes?: string }[]
): Promise<BatchShiftActionResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedules/${scheduleId}/shifts/assignments`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assignments }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as BatchShiftActionResponse;
  } catch {
    return null;
  }
}

export async function reopenOpenShift(
  shiftId: number,
  startOffer = false
): Promise<boolean> {
  try {
    const qs = startOffer ? "?start_open_shift_offer=true" : "";
    const res = await apiFetch(
      `${API_BASE_URL}/api/shifts/${shiftId}/open-shift/reopen${qs}`,
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    return res.ok;
  } catch {
    return false;
  }
}

export async function batchShiftActions(
  scheduleId: number,
  shiftIds: number[],
  action: string
): Promise<BatchShiftActionResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedules/${scheduleId}/shifts/actions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shift_ids: shiftIds, action }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as BatchShiftActionResponse;
  } catch {
    return null;
  }
}

// ── Mock data ─────────────────────────────────────────────────────────────

const MOCK_WEEKLY_SCHEDULE: WeeklyScheduleResponse = {
  schedule: {
    id: 55,
    location_id: 7,
    week_start_date: "2026-04-13",
    week_end_date: "2026-04-19",
    lifecycle_state: "draft",
    current_version_id: 102,
    derived_from_schedule_id: null,
    created_at: "2026-04-10T12:00:00Z",
    updated_at: "2026-04-10T12:00:00Z",
  },
  summary: {
    filled_shifts: 18,
    open_shifts: 2,
    at_risk_shifts: 0,
    warning_count: 3,
  },
  shifts: [
    {
      id: 901,
      schedule_id: 55,
      role: "line_cook",
      date: "2026-04-13",
      start_time: "09:00:00",
      end_time: "17:00:00",
      status: "scheduled",
      published_state: "draft",
      notes: null,
      assignment: {
        worker_id: 44,
        worker_name: "Maria Lopez",
        assignment_status: "assigned",
      },
    },
    {
      id: 902,
      schedule_id: 55,
      role: "server",
      date: "2026-04-13",
      start_time: "11:00:00",
      end_time: "19:00:00",
      status: "scheduled",
      published_state: "draft",
      notes: null,
      assignment: {
        worker_id: 45,
        worker_name: "Jordan Smith",
        assignment_status: "assigned",
      },
    },
    {
      id: 903,
      schedule_id: 55,
      role: "host",
      date: "2026-04-14",
      start_time: "10:00:00",
      end_time: "16:00:00",
      status: "scheduled",
      published_state: "draft",
      notes: null,
      assignment: {
        worker_id: 46,
        worker_name: "Alex Chen",
        assignment_status: "assigned",
      },
    },
    {
      id: 904,
      schedule_id: 55,
      role: "line_cook",
      date: "2026-04-15",
      start_time: "06:00:00",
      end_time: "14:00:00",
      status: "scheduled",
      published_state: "draft",
      notes: null,
      assignment: {
        worker_id: 44,
        worker_name: "Maria Lopez",
        assignment_status: "assigned",
      },
    },
    {
      id: 905,
      schedule_id: 55,
      role: "server",
      date: "2026-04-18",
      start_time: "17:00:00",
      end_time: "23:00:00",
      status: "scheduled",
      published_state: "draft",
      notes: null,
      assignment: null,
    },
    {
      id: 906,
      schedule_id: 55,
      role: "dishwasher",
      date: "2026-04-19",
      start_time: "10:00:00",
      end_time: "18:00:00",
      status: "scheduled",
      published_state: "draft",
      notes: null,
      assignment: null,
    },
  ],
  exceptions: [
    {
      type: "open_shift",
      shift_id: 905,
      message: "No assignee found for Fri closing shift",
    },
    {
      type: "open_shift",
      shift_id: 906,
      message: "No assignee found for Sat dishwasher shift",
    },
    {
      type: "warning",
      shift_id: null,
      message: "3 employees still not enrolled for SMS delivery",
    },
  ],
};
