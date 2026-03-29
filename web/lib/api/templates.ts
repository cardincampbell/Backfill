/**
 * Template endpoint functions extracted from shifts-api.ts.
 */
import type {
  ScheduleTemplate,
  ApplyTemplateResponse,
  ApplyTemplateRangeResponse,
  AssignmentStrategy,
  TemplateSlot,
  BulkSlotResponse,
  TemplatePreviewResponse,
  StaffingPlan,
  AutoAssignResponse,
  GenerateDraftResponse,
  SuggestionFeedResponse,
  ApplySuggestionsResponse,
} from "../types";
import { API_BASE_URL, apiFetch, fetchJson } from "./client";

// ── Schedule template endpoints ───────────────────────────────────────────

export async function getScheduleTemplates(
  locationId: number
): Promise<ScheduleTemplate[] | null> {
  return fetchJson<ScheduleTemplate[]>(
    `/api/locations/${locationId}/schedule-templates`
  );
}

export async function saveAsTemplate(
  scheduleId: number,
  payload: { name: string; description?: string; keep_assignees?: boolean }
): Promise<ScheduleTemplate | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedules/${scheduleId}/templates`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as ScheduleTemplate;
  } catch {
    return null;
  }
}

export async function applyTemplate(
  templateId: number,
  weekStartDate: string,
  replace = false,
  dayOfWeekFilter?: number[],
  autoAssign = false,
  strategy?: AssignmentStrategy
): Promise<ApplyTemplateResponse | null> {
  try {
    const body: Record<string, unknown> = { week_start_date: weekStartDate, replace };
    if (dayOfWeekFilter && dayOfWeekFilter.length > 0) body.day_of_week_filter = dayOfWeekFilter;
    if (autoAssign) body.auto_assign_open_shifts = true;
    if (strategy) body.assignment_strategy = strategy;
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/apply`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as ApplyTemplateResponse;
  } catch {
    return null;
  }
}

export async function applyTemplateRange(
  templateId: number,
  weekStartDates: string[],
  replace = false,
  dayOfWeekFilter?: number[],
  autoAssign = false,
  strategy?: AssignmentStrategy
): Promise<ApplyTemplateRangeResponse | null> {
  try {
    const body: Record<string, unknown> = { week_start_dates: weekStartDates, replace };
    if (dayOfWeekFilter && dayOfWeekFilter.length > 0) body.day_of_week_filter = dayOfWeekFilter;
    if (autoAssign) body.auto_assign_open_shifts = true;
    if (strategy) body.assignment_strategy = strategy;
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/apply-range`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as ApplyTemplateRangeResponse;
  } catch {
    return null;
  }
}

export async function updateTemplate(
  templateId: number,
  payload: { name?: string; description?: string }
): Promise<ScheduleTemplate | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as ScheduleTemplate;
  } catch {
    return null;
  }
}

export async function refreshTemplate(
  templateId: number,
  scheduleId: number,
  keepAssignees = false
): Promise<ScheduleTemplate | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/refresh`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schedule_id: scheduleId, keep_assignees: keepAssignees }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as ScheduleTemplate;
  } catch {
    return null;
  }
}

export async function deleteTemplate(templateId: number): Promise<boolean> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}`,
      { method: "DELETE" }
    );
    return res.ok;
  } catch {
    return false;
  }
}

// ── Template authoring endpoints ──────────────────────────────────────────

export async function createEmptyTemplate(
  locationId: number,
  payload: { name: string; description?: string }
): Promise<ScheduleTemplate | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/locations/${locationId}/schedule-templates`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as ScheduleTemplate;
  } catch {
    return null;
  }
}

export async function getTemplate(
  templateId: number
): Promise<ScheduleTemplate | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/schedule-templates/${templateId}`);
    if (!res.ok) return null;
    return (await res.json()) as ScheduleTemplate;
  } catch {
    return null;
  }
}

export async function cloneTemplate(
  templateId: number
): Promise<ScheduleTemplate | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/clone`,
      { method: "POST" }
    );
    if (!res.ok) return null;
    return (await res.json()) as ScheduleTemplate;
  } catch {
    return null;
  }
}

export async function createTemplateSlot(
  templateId: number,
  payload: { role: string; day_of_week: number; start_time: string; end_time: string; worker_id?: number | null; notes?: string }
): Promise<TemplateSlot | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/shifts`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as TemplateSlot;
  } catch {
    return null;
  }
}

export async function editTemplateSlot(
  slotId: number,
  payload: Partial<{ role: string; day_of_week: number; start_time: string; end_time: string; worker_id: number | null; notes: string }>
): Promise<TemplateSlot | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-template-shifts/${slotId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as TemplateSlot;
  } catch {
    return null;
  }
}

export async function duplicateTemplateSlot(
  slotId: number
): Promise<TemplateSlot | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-template-shifts/${slotId}/duplicate`,
      { method: "POST" }
    );
    if (!res.ok) return null;
    return (await res.json()) as TemplateSlot;
  } catch {
    return null;
  }
}

export async function deleteTemplateSlot(slotId: number): Promise<boolean> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-template-shifts/${slotId}`,
      { method: "DELETE" }
    );
    return res.ok;
  } catch {
    return false;
  }
}

export async function bulkCreateTemplateSlots(
  templateId: number,
  slots: { role: string; day_of_week: number; start_time: string; end_time: string; worker_id?: number | null; notes?: string }[]
): Promise<BulkSlotResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/shifts/bulk`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shifts: slots }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as BulkSlotResponse;
  } catch {
    return null;
  }
}

export async function bulkUpdateTemplateSlots(
  templateId: number,
  updates: { id: number; role?: string; day_of_week?: number; start_time?: string; end_time?: string; worker_id?: number | null; notes?: string }[]
): Promise<BulkSlotResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/shifts`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shifts: updates }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as BulkSlotResponse;
  } catch {
    return null;
  }
}

export async function bulkDuplicateTemplateSlots(
  templateId: number,
  slotIds: number[]
): Promise<BulkSlotResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/shifts/duplicate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shift_ids: slotIds }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as BulkSlotResponse;
  } catch {
    return null;
  }
}

export async function bulkDeleteTemplateSlots(
  templateId: number,
  slotIds: number[]
): Promise<BulkSlotResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/shifts/delete`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shift_ids: slotIds }),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as BulkSlotResponse;
  } catch {
    return null;
  }
}

export async function previewTemplate(
  templateId: number,
  targetWeekStartDate: string,
  dayOfWeek?: number[]
): Promise<TemplatePreviewResponse | null> {
  try {
    let url = `${API_BASE_URL}/api/schedule-templates/${templateId}/preview?target_week_start_date=${encodeURIComponent(targetWeekStartDate)}`;
    if (dayOfWeek && dayOfWeek.length > 0) {
      url += dayOfWeek.map((d) => `&day_of_week=${d}`).join("");
    }
    const res = await apiFetch(url);
    if (!res.ok) return null;
    return (await res.json()) as TemplatePreviewResponse;
  } catch {
    return null;
  }
}

// ── Template planning endpoints ───────────────────────────────────────────

export async function getStaffingPlan(
  templateId: number,
  strategy?: AssignmentStrategy
): Promise<StaffingPlan | null> {
  try {
    let url = `${API_BASE_URL}/api/schedule-templates/${templateId}/staffing-plan`;
    if (strategy) url += `?strategy=${strategy}`;
    const res = await apiFetch(url);
    if (!res.ok) return null;
    return (await res.json()) as StaffingPlan;
  } catch {
    return null;
  }
}

export async function autoAssignTemplate(
  templateId: number,
  strategy?: AssignmentStrategy
): Promise<AutoAssignResponse | null> {
  try {
    const body: Record<string, unknown> = {};
    if (strategy) body.assignment_strategy = strategy;
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/auto-assign`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as AutoAssignResponse;
  } catch {
    return null;
  }
}

export async function generateDraft(
  templateId: number,
  weekStartDate: string,
  strategy?: AssignmentStrategy
): Promise<GenerateDraftResponse | null> {
  try {
    const body: Record<string, unknown> = { week_start_date: weekStartDate };
    if (strategy) body.assignment_strategy = strategy;
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/generate-draft`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as GenerateDraftResponse;
  } catch {
    return null;
  }
}

// ── Suggestion feed endpoints ────────────────────────────────────────────

export async function getTemplateSuggestions(
  templateId: number,
  strategy?: AssignmentStrategy
): Promise<SuggestionFeedResponse | null> {
  try {
    let url = `${API_BASE_URL}/api/schedule-templates/${templateId}/suggestions`;
    if (strategy) url += `?strategy=${strategy}`;
    const res = await apiFetch(url);
    if (!res.ok) return null;
    return (await res.json()) as SuggestionFeedResponse;
  } catch {
    return null;
  }
}

export async function applySuggestions(
  templateId: number
): Promise<ApplySuggestionsResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/suggestions/apply`,
      { method: "POST" }
    );
    if (!res.ok) return null;
    return (await res.json()) as ApplySuggestionsResponse;
  } catch {
    return null;
  }
}

export async function clearTemplateAssignments(
  templateId: number
): Promise<ScheduleTemplate | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/schedule-templates/${templateId}/assignments/clear`,
      { method: "POST" }
    );
    if (!res.ok) return null;
    return (await res.json()) as ScheduleTemplate;
  } catch {
    return null;
  }
}
