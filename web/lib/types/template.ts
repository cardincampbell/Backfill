import type { WeeklyScheduleResponse } from "./schedule";

// ── Schedule template types ───────────────────────────────────────────────

export type TemplateSlotWarning = {
  code: string;
  message: string;
};

export type TemplateSlot = {
  id?: number;
  role: string;
  day_of_week: number; // 0=Mon, 6=Sun
  start_time: string;
  end_time: string;
  worker_id?: number | null;
  worker_name?: string | null;
  notes?: string | null;
  warnings?: TemplateSlotWarning[];
  available_actions?: string[];
};

export type TemplateValidationSummary = {
  warning_count: number;
  invalid_assignments: number;
  unassigned_shifts: number;
  overlap_count?: number;
  ready: boolean;
};

export type TemplateWarning = {
  code: string;
  message: string;
  slot_ids?: number[];
};

export type TemplateDaySummary = {
  day_of_week: number;
  slot_count: number;
  total_hours: number;
};

export type TemplateRoleSummary = {
  role: string;
  slot_count: number;
  total_hours: number;
};

export type TemplateWorkerSummary = {
  worker_id: number;
  worker_name: string;
  slot_count: number;
  total_hours: number;
};

export type AssignmentStrategy = "priority_first" | "balance_hours" | "minimize_overtime";

export type StaffingSlotSuggestion = {
  slot_id: number;
  role: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  current_worker_id?: number | null;
  current_worker_name?: string | null;
  recommended_worker_id?: number | null;
  recommended_worker_name?: string | null;
  needs_review?: boolean;
  suggestion_strategy?: AssignmentStrategy;
  suggested_workers: {
    worker_id: number;
    worker_name: string;
    rank?: number;
    score?: number;
    score_breakdown?: Record<string, number>;
    reason?: string;
    reason_codes?: string[];
    confidence?: number;
  }[];
};

export type StaffingWorkerCapacity = {
  worker_id: number;
  worker_name: string;
  max_hours_per_week?: number | null;
  template_hours: number;
  remaining_capacity?: number | null;
  at_capacity: boolean;
  overtime_risk: boolean;
};

export type StaffingPlan = {
  template_id: number;
  eligible_worker_count: number;
  staffing_gap_count: number;
  auto_assignable_shift_count: number;
  overtime_risk_count: number;
  over_capacity_worker_count: number;
  review_required_count?: number;
  recommended_assignment_count?: number;
  coverage_risk_count?: number;
  ready_to_generate?: boolean;
  ready_to_publish?: boolean;
  slot_suggestions: StaffingSlotSuggestion[];
  worker_capacities: StaffingWorkerCapacity[];
};

export type AutoAssignResponse = {
  template_id: number;
  assigned_count: number;
  skipped_count: number;
  assignments: {
    slot_id: number;
    worker_id: number;
    worker_name: string;
  }[];
  template: ScheduleTemplate;
};

export type GenerateDraftResponse = {
  template_id: number;
  schedule_id: number;
  week_start_date: string;
  created_shift_count: number;
  assigned_shift_count: number;
  open_shift_count: number;
  template: ScheduleTemplate;
};

export type ScheduleTemplate = {
  id: number;
  location_id: number;
  name: string;
  description?: string | null;
  source_schedule_id?: number | null;
  source_week_start_date?: string | null;
  keep_assignees: boolean;
  slots: TemplateSlot[];
  slot_count: number;
  created_at: string;
  validation_summary?: TemplateValidationSummary;
  available_actions?: string[];
  template_warnings?: TemplateWarning[];
  daily_summary?: TemplateDaySummary[];
  role_summary?: TemplateRoleSummary[];
  worker_summary?: TemplateWorkerSummary[];
  staffing_plan?: StaffingPlan;
};

export type BulkSlotResponse = {
  processed_count: number;
  success_count: number;
  error_count: number;
  results: { slot_id?: number; success: boolean; error?: string }[];
  template: ScheduleTemplate;
};

export type TemplatePreviewShift = {
  role: string;
  date: string;
  start_time: string;
  end_time: string;
  worker_id?: number | null;
  worker_name?: string | null;
};

export type TemplatePreviewResponse = {
  template_id: number;
  target_week_start_date: string;
  existing_schedule_id?: number | null;
  existing_shift_count?: number;
  replace_required?: boolean;
  summary: {
    total_shifts: number;
    assigned_shifts: number;
    open_shifts: number;
  };
  shifts: TemplatePreviewShift[];
};

export type ApplyTemplateResponse = {
  schedule_id: number;
  location_id: number;
  week_start_date: string;
  created_shift_count: number;
  skipped_count?: number;
  schedule_view?: WeeklyScheduleResponse;
};

export type ApplyTemplateRangeResponse = {
  template_id: number;
  weeks_requested: number;
  weeks_succeeded: number;
  weeks_failed: number;
  results: {
    week_start_date: string;
    success: boolean;
    schedule_id?: number;
    created_shift_count?: number;
    error?: string;
  }[];
};

// ── Suggestion feed types ─────────────────────────────────────────────────

export type SuggestionFeedResponse = {
  template_id: number;
  strategy: AssignmentStrategy;
  suggestions: StaffingSlotSuggestion[];
};

export type ApplySuggestionsResponse = {
  template_id: number;
  applied_count: number;
  skipped_count: number;
  template: ScheduleTemplate;
};
