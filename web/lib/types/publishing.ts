import type { ScheduleLifecycleState } from "./schedule";

// ── Schedule draft / review types ────────────────────────────────────────

export type DraftOption = {
  type: "template" | "prior_schedule" | "blank";
  id?: number;
  name: string;
  description?: string;
  slot_count?: number;
  week_start_date?: string;
};

export type DraftOptionsResponse = {
  location_id: number;
  target_week_start_date?: string;
  options: DraftOption[];
};

export type CreateFromTemplateResponse = {
  schedule_id: number;
  location_id: number;
  week_start_date: string;
  lifecycle_state: ScheduleLifecycleState;
  created_shift_count: number;
  assigned_shift_count: number;
  open_shift_count: number;
};

export type AiDraftResponse = {
  schedule_id: number;
  location_id: number;
  week_start_date: string;
  lifecycle_state: ScheduleLifecycleState;
  basis_type?: "template" | "prior_schedule" | "derived_schedule" | "blank";
  basis_id?: number | null;
  created_shift_count: number;
  assigned_shift_count: number;
  open_shift_count: number;
};

export type ScheduleReviewChange = {
  type: "shift_added" | "shift_removed" | "role_changed" | "assignment_changed" | "time_changed" | string;
  shift_id?: number;
  role?: string;
  date?: string;
  description: string;
};

export type PublishDiffEntry = {
  type: "added" | "removed" | "changed" | string;
  shift_id?: number;
  role?: string;
  date?: string;
  worker_name?: string;
  description: string;
};

export type WorkerImpactEntry = {
  worker_id: number;
  worker_name: string;
  impact_type: "new_schedule" | "updated" | "removed" | "unchanged" | string;
  change_count?: number;
  description?: string;
};

export type WorkerImpactSummary = {
  total_workers: number;
  new_schedule_count: number;
  updated_count: number;
  removed_count: number;
  unchanged_count: number;
  new_assignment_count?: number;
  changed_shift_count?: number;
  added_shift_only_count?: number;
  removed_shift_only_count?: number;
};

export type PublishDiff = {
  total_changes: number;
  shifts_added: number;
  shifts_removed: number;
  assignments_changed: number;
  roles_changed: number;
  open_shift_impact?: number;
  entries: PublishDiffEntry[];
  worker_impact?: WorkerImpactEntry[];
};

export type DraftRationale = {
  schedule_id: number;
  basis_type?: string;
  basis_id?: number | null;
  basis_name?: string;
  strategy?: string;
  rationale: string;
  highlights?: string[];
};

export type ScheduleReviewResponse = {
  schedule_id: number;
  lifecycle_state: ScheduleLifecycleState;
  review_summary: {
    total_changes: number;
    shifts_added: number;
    shifts_removed: number;
    assignments_changed: number;
    roles_changed: number;
    draft_rationale?: string;
    publish_diff?: PublishDiff;
    publish_highlights?: string[];
    message_preview?: {
      body: string;
      review_link?: string;
      publish_mode?: "initial" | "update" | "republish";
    };
  };
  publish_diff?: PublishDiff;
  publish_impact_summary?: WorkerImpactSummary;
  changes: ScheduleReviewChange[];
};

export type PublishBlocker = {
  code: string;
  message: string;
  severity: "error" | "warning";
};

export type PublishReadinessResponse = {
  schedule_id: number;
  lifecycle_state: ScheduleLifecycleState;
  ready: boolean;
  status: "ready" | "blocked" | "already_published";
  blockers: PublishBlocker[];
  warnings: PublishBlocker[];
};

export type ScheduleVersionEntry = {
  id: number;
  version_number: number;
  version_type: "draft_snapshot" | "publish_snapshot" | "amendment_snapshot";
  shift_count?: number;
  created_at: string;
  change_summary?: string;
  event_label?: string;
  event_narrative?: string;
  default_compare_mode?: "previous" | "previous_publish" | "none" | string;
  diff_summary?: {
    total_changes: number;
    shifts_added: number;
    shifts_removed: number;
    assignments_changed: number;
    roles_changed: number;
  };
  impact_summary?: WorkerImpactSummary;
  highlights?: string[];
  is_current_version?: boolean;
  worker_impact_summary?: WorkerImpactSummary;
  can_compare_to_current?: boolean;
  can_compare_to_previous?: boolean;
};

export type ScheduleVersionsResponse = {
  schedule_id: number;
  versions: ScheduleVersionEntry[];
};

export type ChangeSummaryResponse = {
  schedule_id: number;
  derived_from_schedule_id?: number | null;
  basis_type?: string;
  summary: {
    total_changes: number;
    shifts_added: number;
    shifts_removed: number;
    roles_changed: number;
    assignments_changed: number;
  };
  changes: ScheduleReviewChange[];
  publish_diff?: PublishDiff;
};

export type DeliverySummary = {
  sms_sent?: number;
  sms_removed_sent?: number;
  skipped_unchanged_workers?: number;
};

export type MessagePreviewResponse = {
  schedule_id: number;
  message_body: string;
  review_link?: string;
  publish_diff?: PublishDiff;
  publish_mode?: "initial" | "update" | "republish";
  worker_update_count?: number;
  delivery_summary?: DeliverySummary;
};

export type PublishDiffResponse = {
  schedule_id: number;
  diff: PublishDiff;
};

export type DraftRationaleResponse = DraftRationale;

export type VersionDiffResponse = {
  schedule_id: number;
  version_id: number;
  compare_to_version_id?: number | null;
  compare_mode: "previous" | "previous_publish" | "current" | "explicit" | string;
  diff: PublishDiff;
  worker_impact?: WorkerImpactEntry[];
};

export type PublishImpactResponse = {
  schedule_id: number;
  impact_summary: WorkerImpactSummary;
  worker_impact: WorkerImpactEntry[];
};

export type WorkerMessagePreview = {
  worker_id: number;
  worker_name: string;
  phone?: string;
  delivery_status: "will_send" | "blocked" | "skipped" | string;
  delivery_reason?: string;
  message_type?: "new_schedule" | "updated_schedule" | "removed_from_schedule" | "added_shift" | "time_changed" | string;
  message_body?: string;
};

export type DeliveryEstimate = {
  total_recipients: number;
  will_send: number;
  blocked: number;
  skipped_unchanged: number;
  removal_notices: number;
};

export type PublishPreviewResponse = {
  schedule_id: number;
  message_preview: {
    message_body: string;
    review_link?: string;
    publish_mode?: "initial" | "update" | "republish";
    worker_update_count?: number;
  };
  delivery_estimate: DeliveryEstimate;
  worker_message_previews: WorkerMessagePreview[];
};
