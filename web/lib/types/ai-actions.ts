/**
 * AI action types — frozen from backfill-shifts-ai-native-pkg section 10.
 *
 * Claude builds against these exact shapes.
 * Do not modify without coordinating with Codex.
 */

import type {
  ScheduleReviewResponse,
  PublishPreviewResponse,
  PublishDiffResponse,
} from "./publishing";
import type {
  ScheduleExceptionQueueResponse,
  ManagerActionsResponse,
  CoverageResponse,
} from "./operations";

// ── Response envelope ────────────────────────────────────────────────────

export type WebAiActionMode =
  | "result"
  | "clarification"
  | "confirmation"
  | "redirect"
  | "error"
  | "cancelled";

export type WebAiActionResponse = {
  action_request_id: number;
  status:
    | "received"
    | "awaiting_clarification"
    | "awaiting_confirmation"
    | "completed"
    | "redirected"
    | "cancelled"
    | "failed";
  mode: WebAiActionMode;
  summary: string;
  risk_class?: "green" | "yellow" | "red";
  requires_confirmation?: boolean;
  clarification?: AiClarification;
  confirmation?: AiConfirmation;
  redirect?: AiRedirect;
  ui_payload?: AiUiPayload | null;
  next_actions?: AiNextAction[];
};

// ── Clarification ────────────────────────────────────────────────────────

export type AiClarificationCandidate = {
  entity_type: "worker" | "shift" | "location" | "schedule" | "date";
  entity_id?: number | null;
  label: string;
  description?: string;
  confidence_score?: number | null;
};

export type AiClarification = {
  prompt: string;
  candidates: AiClarificationCandidate[];
};

// ── Confirmation ─────────────────────────────────────────────────────────

export type AiAffectedEntity = {
  type: string;
  id?: number | null;
  label: string;
};

export type AiConfirmation = {
  prompt: string;
  reason_codes?: string[];
  affected_entities: AiAffectedEntity[];
};

// ── Redirect ─────────────────────────────────────────────────────────────

export type AiRedirect = {
  reason: string;
  url: string;
  label?: string;
};

// ── Next actions ─────────────────────────────────────────────────────────

export type AiNextAction = {
  type: "confirm" | "cancel" | "clarify" | "open_url";
  label: string;
  value?: string;
};

// ── UI payload — reuses existing product payloads ────────────────────────

export type AiUiPayload =
  | { kind: "schedule_review"; data: ScheduleReviewResponse }
  | { kind: "publish_preview"; data: PublishPreviewResponse }
  | { kind: "publish_diff"; data: PublishDiffResponse }
  | { kind: "schedule_exceptions"; data: ScheduleExceptionQueueResponse }
  | { kind: "manager_actions"; data: ManagerActionsResponse }
  | { kind: "coverage_summary"; data: CoverageResponse }
  | {
      kind: "simple_result";
      data: {
        title?: string;
        body?: string;
        metrics?: Record<string, number | string>;
      };
    };

// ── Request types ────────────────────────────────────────────────────────

export type AiWebActionRequest = {
  location_id: number;
  text: string;
  context?: {
    tab?: string;
    schedule_id?: number;
    week_start_date?: string;
    selected_shift_ids?: number[];
    selected_worker_ids?: number[];
    draft_schedule_id?: number;
  } | null;
};

export type AiClarifyRequest = {
  selection: {
    entity_type: string;
    entity_id: number;
  };
};

// ── History ──────────────────────────────────────────────────────────────

export type AiActionHistoryItem = {
  action_request_id: number;
  channel: "web" | "sms" | "voice";
  status: string;
  text: string;
  summary: string;
  created_at: string;
};

export type AiActionHistoryResponse = {
  location_id: number;
  items: AiActionHistoryItem[];
};
