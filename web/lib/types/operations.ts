import type { ScheduleException } from "./schedule";
import type { Worker } from "./core";

// ── Import pipeline types ─────────────────────────────────────────────────

export type ImportJobStatus =
  | "uploaded"
  | "mapping"
  | "validating"
  | "action_needed"
  | "completed"
  | "partially_completed"
  | "failed";

export type ImportJobSummary = {
  total_rows: number;
  worker_rows: number;
  shift_rows: number;
  success_rows: number;
  warning_rows: number;
  failed_rows: number;
  skipped_rows?: number;
  committed_rows?: number;
  pending_rows?: number;
};

export type ImportJob = {
  id: number;
  location_id: number;
  import_type: "roster_only" | "shifts_only" | "combined";
  status: ImportJobStatus;
  filename: string;
  summary: ImportJobSummary;
  mapping_json?: Record<string, string> | null;
  created_at?: string;
  updated_at?: string;
};

export type ImportUploadResponse = {
  id: number;
  status: "mapping";
  columns: string[];
  preview_rows: Array<{
    row_number: number;
    values: Record<string, string>;
  }>;
};

export type ImportMappingResponse = {
  id: number;
  status: ImportJobStatus;
  summary: ImportJobSummary;
  action_needed_count: number;
};

export type ImportRowOutcome = "success" | "warning" | "failed" | "skipped";

export type ImportRowResult = {
  id: number;
  row_number: number;
  entity_type: "worker" | "shift";
  outcome: ImportRowOutcome;
  error_code?: string | null;
  error_message?: string | null;
  raw_payload: Record<string, string>;
  normalized_payload?: Record<string, string> | null;
};

export type ImportRowsResponse = {
  job: { id: number; status: ImportJobStatus };
  rows: ImportRowResult[];
};

export type ImportCommitResponse = {
  job_id: number;
  status: ImportJobStatus;
  created_workers: number;
  updated_workers: number;
  created_shifts: number;
  schedule_id?: number | null;
  week_start_date?: string | null;
};

// ── Import row resolution types ───────────────────────────────────────────

export type ImportRowResolveResponse = {
  row: ImportRowResult;
  job: {
    id: number;
    status: ImportJobStatus;
    summary: ImportJobSummary;
  };
  action_needed_count: number;
};

export type ImportErrorCsvResponse = {
  job_id: number;
  csv: string;
  count: number;
};

// ── Coverage types ────────────────────────────────────────────────────────

export type CoverageStatus =
  | "unassigned"
  | "offering"
  | "awaiting_agency_approval"
  | "awaiting_manager_approval"
  | "agency_routing"
  | "unfilled";

export type CoverageShift = {
  shift_id: number;
  role: string;
  date: string;
  start_time: string;
  current_status: string;
  cascade_id?: number | null;
  coverage_status: CoverageStatus;
  current_tier?: string | null;
  outreach_mode?: string | null;
  manager_action_required?: boolean;
  standby_depth?: number | null;
  confirmed_worker_id?: number | null;
  claimed_by_worker_id?: number | null;
  claimed_by_worker_name?: string | null;
  claimed_at?: string | null;
  offered_worker_count?: number | null;
  responded_worker_count?: number | null;
  last_outreach_at?: string | null;
  last_response_at?: string | null;
};

// ── Manager action queue types ────────────────────────────────────────────

export type ManagerActionType =
  | "approve_fill"
  | "approve_agency"
  | "review_late_arrival"
  | "review_missed_check_in";

export type ManagerAction = {
  action_type: ManagerActionType;
  cascade_id: number;
  shift_id: number;
  role: string;
  date: string;
  start_time: string;
  coverage_status: CoverageStatus;
  requested_at: string;
  worker_id?: number | null;
  worker_name?: string | null;
  available_actions: string[];
  late_eta_minutes?: number | null;
};

export type ManagerActionsResponse = {
  location_id: number;
  summary: {
    total: number;
    approve_fill: number;
    approve_agency: number;
    attendance_reviews?: number;
  };
  actions: ManagerAction[];
};

// ── Location settings types ───────────────────────────────────────────────

export type LocationSettings = {
  location_id: number;
  coverage_requires_manager_approval: boolean;
  late_arrival_policy: "wait" | "manager_action" | "start_coverage";
  missed_check_in_policy: "manager_action" | "start_coverage";
  agency_supply_approved: boolean;
  writeback_enabled: boolean;
  timezone?: string | null;
  scheduling_platform?: string | null;
  integration_status?: string | null;
  backfill_shifts_enabled?: boolean;
  backfill_shifts_launch_state?: "off" | "beta" | "live" | string;
  backfill_shifts_beta_eligible?: boolean;
};

export type BackfillShiftsMetricsRates = {
  publish_rate?: number;
  amendment_rate?: number;
  enrollment_rate?: number;
  delivery_success_rate?: number;
  fill_rate?: number;
};

export type BackfillShiftsMetricsActivity = {
  date: string;
  event_type: string;
  description: string;
  count?: number;
};

export type BackfillShiftsMetricsResponse = {
  location_id: number;
  days: number;
  launch_controls: {
    backfill_shifts_enabled: boolean;
    backfill_shifts_launch_state: string;
    backfill_shifts_beta_eligible: boolean;
  };
  summary: {
    schedules_published: number;
    amendments_published: number;
    workers_enrolled: number;
    workers_total: number;
    messages_sent: number;
    messages_delivered: number;
    callouts_received: number;
    shifts_filled: number;
  };
  rates: BackfillShiftsMetricsRates;
  recent_activity: BackfillShiftsMetricsActivity[];
};

// ── Backfill Shifts activity feed types ───────────────────────────────────

export type BackfillShiftsActivityEntry = {
  id?: string;
  timestamp: string;
  event_type: string;
  category?: "publish" | "amendment" | "delivery" | "enrollment" | "callout" | "fill" | "automation" | string;
  description: string;
  schedule_id?: number;
  worker_id?: number;
  worker_name?: string;
  metadata?: Record<string, unknown>;
};

export type BackfillShiftsActivityResponse = {
  location_id: number;
  entries: BackfillShiftsActivityEntry[];
  total_count?: number;
};

// ── Schedule exception queue types ────────────────────────────────────────

export type ScheduleExceptionQueueItem = ScheduleException & {
  id?: string;
};

export type ScheduleExceptionQueueResponse = {
  location_id: number;
  summary: {
    total: number;
    action_required: number;
    critical: number;
  };
  exceptions: ScheduleExceptionQueueItem[];
};

export type CoverageResponse = {
  location_id: number;
  at_risk_shifts: CoverageShift[];
};

// ── Roster types ──────────────────────────────────────────────────────────

export type LocationAssignment = {
  location_id: number;
  priority_rank: number;
  is_active: boolean;
  roles: string[];
};

export type RosterWorker = Worker & {
  enrollment_status: "enrolled" | "not_enrolled";
  is_active_worker: boolean;
  is_active_at_location: boolean;
  active_assignment: LocationAssignment;
};

export type RosterSummary = {
  total_workers: number;
  active_workers: number;
  inactive_workers: number;
  enrolled_workers: number;
};

export type RosterResponse = {
  location_id: number;
  summary: RosterSummary;
  workers: RosterWorker[];
};

export type EligibleWorker = RosterWorker & {
  eligible_roles: string[];
};

export type EligibleWorkersResponse = {
  location_id: number;
  role: string | null;
  workers: EligibleWorker[];
};
