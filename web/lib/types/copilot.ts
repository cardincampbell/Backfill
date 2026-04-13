export type CopilotTool = {
  name: string;
  title: string;
  description: string;
  intent_family: string;
  mutates_state: boolean;
  availability: "available" | "planned";
};

export type CopilotValidationResult = {
  ok: boolean;
  code: string;
  message: string;
};

export type CopilotOpenShiftResultItem = {
  shift_id: string;
  location_id?: string | null;
  location_name?: string | null;
  role_name?: string | null;
  starts_at: string;
  ends_at: string;
  status: string;
};

export type CopilotOpenShiftsResult = {
  kind: "open_shifts";
  total_open_shifts: number;
  location_count?: number;
  items: CopilotOpenShiftResultItem[];
};

export type CopilotCampaignResultItem = {
  campaign_id: string;
  shift_id: string;
  location_name?: string | null;
  role_name?: string | null;
  status: string;
  phase_target?: string | null;
  opened_at?: string | null;
};

export type CopilotCampaignsResult = {
  kind: "campaigns";
  total_active_campaigns: number;
  running_count?: number;
  queued_count?: number;
  items: CopilotCampaignResultItem[];
};

export type CopilotManagerActionResultItem = {
  campaign_id: string;
  shift_id: string;
  location_name?: string | null;
  role_name?: string | null;
  starts_at?: string | null;
  status: string;
};

export type CopilotManagerActionsResult = {
  kind: "manager_actions";
  total_actions: number;
  items: CopilotManagerActionResultItem[];
};

export type CopilotAvailabilityRuleResultItem = {
  day_of_week: number;
  start_local_time: string;
  end_local_time: string;
  timezone: string;
};

export type CopilotAvailabilityUpdateResult = {
  kind: "availability_update";
  employee_id: string;
  employee_name: string;
  timezone: string;
  day_count: number;
  rule_count: number;
  rules: CopilotAvailabilityRuleResultItem[];
};

export type CopilotHelpResult = {
  kind: "help";
  tools: CopilotTool[];
};

export type CopilotToolResultPayload =
  | CopilotOpenShiftsResult
  | CopilotCampaignsResult
  | CopilotManagerActionsResult
  | CopilotAvailabilityUpdateResult
  | CopilotHelpResult
  | Record<string, unknown>;

export type CopilotIntent = {
  family: string;
  tool_name: string;
  reasoning: string;
  confidence: number;
};

export type CopilotSession = {
  id: string;
  business_id: string;
  location_id?: string | null;
  operator_user_id: string;
  channel_last_seen: string;
  intent_family?: string | null;
  state:
    | "active"
    | "awaiting_confirmation"
    | "awaiting_clarification"
    | "completed"
    | "expired";
  context_profile: Record<string, unknown>;
  working_memory: Record<string, unknown>;
  expires_at?: string | null;
  last_message_at?: string | null;
  created_at: string;
};

export type CopilotMessage = {
  id: string;
  copilot_session_id: string;
  direction: "inbound" | "outbound";
  normalized_channel: string;
  raw_text: string;
  normalized_text: string;
  message_metadata: Record<string, unknown>;
  created_at: string;
};

export type CopilotActionRun = {
  id: string;
  copilot_session_id: string;
  tool_name: string;
  status: "planned" | "validated" | "executed" | "failed" | "cancelled";
  input_payload: Record<string, unknown>;
  validation_result: CopilotValidationResult;
  result_payload: CopilotToolResultPayload;
  error_payload: Record<string, unknown>;
  started_at: string;
  finished_at?: string | null;
};

export type CopilotSessionDetail = {
  session: CopilotSession;
  tools: CopilotTool[];
  messages: CopilotMessage[];
  action_runs: CopilotActionRun[];
};

export type CopilotTurn = {
  session: CopilotSession;
  resolved_intent: CopilotIntent;
  inbound_message: CopilotMessage;
  outbound_message: CopilotMessage;
  action_run: CopilotActionRun;
  tools: CopilotTool[];
};

export type CopilotSessionCreatePayload = {
  location_id?: string | null;
  normalized_channel?: string;
  reuse_active?: boolean;
};

export type CopilotMessageCreatePayload = {
  text: string;
  location_id?: string | null;
  normalized_channel?: string;
};

export type CopilotLiveProgressState =
  | "thinking"
  | "planning"
  | "running_tool";

export type CopilotLiveEvent =
  | {
      event_id: string;
      event_type: "session.ready";
      trace_id: string;
      session_id: string;
      occurred_at: string;
      payload: { detail: CopilotSessionDetail };
    }
  | {
      event_id: string;
      event_type: "user.message.accepted";
      trace_id: string;
      session_id: string;
      occurred_at: string;
      payload: { message: CopilotMessage; session: CopilotSession };
    }
  | {
      event_id: string;
      event_type: "assistant.turn.started";
      trace_id: string;
      session_id: string;
      occurred_at: string;
      payload: { session: CopilotSession; message_id: string };
    }
  | {
      event_id: string;
      event_type: "assistant.progress";
      trace_id: string;
      session_id: string;
      occurred_at: string;
      payload: {
        state: CopilotLiveProgressState;
        label: string;
        resolved_intent?: CopilotIntent;
        planner_source?: string;
      };
    }
  | {
      event_id: string;
      event_type: "tool.started";
      trace_id: string;
      session_id: string;
      occurred_at: string;
      payload: {
        tool_name: string;
        input_payload: Record<string, unknown>;
        validation_result: CopilotValidationResult;
      };
    }
  | {
      event_id: string;
      event_type: "tool.finished";
      trace_id: string;
      session_id: string;
      occurred_at: string;
      payload: { action_run: CopilotActionRun };
    }
  | {
      event_id: string;
      event_type: "assistant.message.completed";
      trace_id: string;
      session_id: string;
      occurred_at: string;
      payload: { turn: CopilotTurn };
    }
  | {
      event_id: string;
      event_type: "assistant.turn.failed";
      trace_id: string;
      session_id: string;
      occurred_at: string;
      payload: {
        error: { code: string; message: string };
        turn?: CopilotTurn;
      };
    }
  | {
      event_id: string;
      event_type: "session.error";
      trace_id: string;
      session_id: string;
      occurred_at: string;
      payload: { code: string; message: string };
    };
