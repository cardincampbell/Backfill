import type { Shift } from "./core";

// ── Schedule types ────────────────────────────────────────────────────────

export type ScheduleLifecycleState =
  | "draft"
  | "published"
  | "amended"
  | "archived"
  | "recalled";

export type Schedule = {
  id: number;
  location_id: number;
  week_start_date: string;
  week_end_date: string;
  lifecycle_state: ScheduleLifecycleState;
  current_version_id?: number | null;
  derived_from_schedule_id?: number | null;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
  publish_readiness?: {
    ready: boolean;
    status: "ready" | "blocked" | "already_published";
    blocker_count?: number;
    warning_count?: number;
  };
};

export type ScheduleVersion = {
  id: number;
  schedule_id: number;
  version_number: number;
  version_type: "draft_snapshot" | "publish_snapshot" | "amendment_snapshot";
  snapshot_json?: Record<string, unknown>;
  change_summary_json?: Record<string, unknown>;
  published_at?: string | null;
  published_by?: string | null;
  created_at: string;
};

export type AssignmentStatus =
  | "assigned"
  | "open"
  | "claimed"
  | "confirmed"
  | "closed"
  | "removed";

export type AssignmentSource =
  | "import"
  | "copy_last_week"
  | "manual"
  | "claim"
  | "coverage_engine";

export type ShiftAssignment = {
  worker_id?: number | null;
  worker_name?: string | null;
  assignment_status: AssignmentStatus;
  source?: AssignmentSource;
  filled_via_backfill?: boolean;
};

export type ShiftCoverage = {
  is_active: boolean;
  status: "active" | "backfilled" | "awaiting_manager_approval" | "closed" | "none";
  cascade_id?: number | null;
  called_out_by?: string | null;
  filled_by?: string | null;
  manager_action_required?: boolean;
  claimed_by_worker_id?: number | null;
  claimed_by_worker_name?: string | null;
  claimed_at?: string | null;
  pending_action?: string | null;
  current_tier?: string | null;
};

export type ConfirmationStatus =
  | "not_requested"
  | "pending"
  | "confirmed"
  | "declined"
  | "escalated"
  | "not_applicable";

export type AttendanceStatus =
  | "not_requested"
  | "pending"
  | "checked_in"
  | "late"
  | "escalated"
  | "not_applicable";

export type ShiftConfirmation = {
  status: ConfirmationStatus;
};

export type ShiftAttendance = {
  status: AttendanceStatus;
  late_eta_minutes?: number | null;
};

export type ShiftAction =
  | "start_coverage"
  | "cancel_offer"
  | "close_shift"
  | "reopen_shift"
  | "reopen_and_offer"
  | string;

export type ScheduleShift = {
  id: number;
  schedule_id?: number | null;
  role: string;
  date: string;
  start_time: string;
  end_time: string;
  pay_rate?: number;
  status: string;
  published_state?: "draft" | "published" | "amended" | null;
  notes?: string | null;
  assignment?: ShiftAssignment | null;
  coverage?: ShiftCoverage | null;
  confirmation?: ShiftConfirmation | null;
  attendance?: ShiftAttendance | null;
  available_actions?: ShiftAction[];
};

export type BatchShiftActionResponse = {
  processed_count: number;
  success_count: number;
  error_count: number;
  results: { shift_id: number; success: boolean; error?: string }[];
  schedule_view?: WeeklyScheduleResponse;
};

export type ExceptionSeverity = "info" | "warning" | "critical";

export type ScheduleExceptionCode =
  | "open_shift"
  | "open_shift_unassigned"
  | "open_shift_closed"
  | "coverage_fill_approval_required"
  | "coverage_agency_approval_required"
  | "coverage_active"
  | "late_arrival_needs_review"
  | "missed_check_in_needs_review"
  | "missed_check_in_escalated"
  | string;

export type ScheduleException = {
  type: string;
  code?: ScheduleExceptionCode;
  shift_id?: number | null;
  message: string;
  severity?: ExceptionSeverity;
  action_required?: boolean;
  available_actions?: string[];
  vacancy_kind?: "callout" | "open_shift" | "attendance" | null;
  role?: string | null;
  date?: string | null;
  start_time?: string | null;
  worker_id?: number | null;
  worker_name?: string | null;
  cascade_id?: number | null;
  late_eta_minutes?: number | null;
};

export type ScheduleSummary = {
  filled_shifts: number;
  open_shifts: number;
  at_risk_shifts: number;
  warning_count: number;
  action_required_count?: number;
  critical_count?: number;
  attendance_issues?: number;
  late_arrivals?: number;
  late_arrivals_awaiting_decision?: number;
  missed_check_ins?: number;
  missed_check_ins_awaiting_decision?: number;
  missed_check_ins_escalated?: number;
  pending_attendance_reviews?: number;
};

export type WeeklyScheduleResponse = {
  schedule: Schedule | null;
  summary: ScheduleSummary;
  shifts: ScheduleShift[];
  exceptions: ScheduleException[];
};

export type CopyLastWeekResponse = {
  schedule_id: number;
  location_id: number;
  week_start_date: string;
  lifecycle_state: ScheduleLifecycleState;
  copied_shift_count: number;
  open_shift_count: number;
  warning_count: number;
};

export type PublishResponse = {
  schedule_id: number;
  lifecycle_state: "published";
  version_id: number;
  published_at: string;
  delivery_summary: {
    eligible_workers: number;
    sms_sent: number;
    sms_failed: number;
    not_enrolled: number;
  };
};

export type AmendAssignmentResponse = {
  shift_id: number;
  schedule_id: number;
  assignment: ShiftAssignment;
  schedule_lifecycle_state: ScheduleLifecycleState;
};

// ── Schedule lifecycle action types ────────────────────────────────────────

export type ScheduleLifecycleResponse = {
  schedule_id: number;
  lifecycle_state: ScheduleLifecycleState;
  version_id: number;
};

export type CreateShiftResponse = {
  shift: Shift;
  assignment: ShiftAssignment;
  schedule_lifecycle_state: ScheduleLifecycleState;
  version_id: number;
};

export type DeleteShiftResponse = {
  shift_id: number;
  schedule_id: number | null;
  deleted: true;
  schedule_lifecycle_state: ScheduleLifecycleState | null;
  version_id: number | null;
};
