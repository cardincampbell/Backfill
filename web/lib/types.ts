export type Restaurant = {
  id: number;
  name: string;
  address?: string | null;
  manager_name?: string | null;
  manager_phone?: string | null;
  manager_email?: string | null;
  scheduling_platform?: string | null;
  scheduling_platform_id?: string | null;
  integration_status?: string | null;
  last_roster_sync_at?: string | null;
  last_roster_sync_status?: string | null;
  last_schedule_sync_at?: string | null;
  last_schedule_sync_status?: string | null;
  last_sync_error?: string | null;
  integration_state?: string | null;
  last_event_sync_at?: string | null;
  last_rolling_sync_at?: string | null;
  last_daily_sync_at?: string | null;
  last_writeback_at?: string | null;
  writeback_enabled?: boolean;
  writeback_subscription_tier?: string | null;
  onboarding_info?: string | null;
  agency_supply_approved?: boolean;
  preferred_agency_partners?: number[];
};

export type Worker = {
  id: number;
  name: string;
  phone: string;
  email?: string | null;
  roles: string[];
  certifications: string[];
  worker_type: string;
  preferred_channel: string;
  priority_rank: number;
  restaurant_id?: number | null;
  source?: string | null;
  source_id?: string | null;
  sms_consent_status: string;
  voice_consent_status: string;
  rating?: number | null;
  show_up_rate?: number | null;
  acceptance_rate?: number | null;
  response_rate?: number | null;
  total_shifts_filled?: number;
};

export type Shift = {
  id: number;
  restaurant_id: number;
  role: string;
  date: string;
  start_time: string;
  end_time: string;
  pay_rate: number;
  requirements: string[];
  status: string;
  called_out_by?: number | null;
  filled_by?: number | null;
  fill_tier?: string | null;
  source_platform?: string | null;
};

export type Cascade = {
  id: number;
  shift_id: number;
  status: string;
  outreach_mode: string;
  current_tier: number;
  current_batch: number;
  current_position: number;
  confirmed_worker_id?: number | null;
  standby_queue: number[];
  manager_approved_tier3: boolean;
};

export type OutreachAttempt = {
  id: number;
  cascade_id: number;
  worker_id: number;
  tier: number;
  channel: string;
  status: string;
  outcome?: string | null;
  standby_position?: number | null;
  promoted_at?: string | null;
  sent_at?: string | null;
  responded_at?: string | null;
  conversation_summary?: string | null;
};

export type AuditLog = {
  id: number;
  timestamp: string;
  actor: string;
  action: string;
  entity_type?: string | null;
  entity_id?: number | null;
  details: Record<string, unknown>;
};

export type DashboardSummary = {
  restaurant_id?: number | null;
  restaurants: number;
  workers: number;
  shifts_total: number;
  shifts_vacant: number;
  shifts_filled: number;
  cascades_active: number;
  broadcast_cascades_active: number;
  workers_on_standby: number;
  active_shift_ids: number[];
  recent_shifts: Shift[];
};

export type IntegrationHealth = {
  restaurant_id: number;
  platform: string;
  mode: string;
  writable: boolean;
  writeback_supported?: boolean;
  writeback_enabled?: boolean;
  writeback_subscription_tier?: string | null;
  platform_id_present?: boolean;
  status: string;
  reason?: string | null;
  last_roster_sync_at?: string | null;
  last_roster_sync_status?: string | null;
  last_schedule_sync_at?: string | null;
  last_schedule_sync_status?: string | null;
  last_sync_error?: string | null;
  integration_state?: string | null;
  last_event_sync_at?: string | null;
  last_rolling_sync_at?: string | null;
  last_daily_sync_at?: string | null;
  last_writeback_at?: string | null;
};

export type SyncJob = {
  id: number;
  platform: string;
  restaurant_id?: number | null;
  integration_event_id?: number | null;
  job_type: string;
  priority: number;
  scope?: string | null;
  scope_ref?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  status: string;
  attempt_count: number;
  max_attempts: number;
  next_run_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  last_error?: string | null;
  idempotency_key?: string | null;
};

export type RestaurantStatusResponse = {
  restaurant: Restaurant;
  integration: IntegrationHealth;
  metrics: {
    workers_total: number;
    workers_sms_ready: number;
    workers_voice_ready: number;
    upcoming_shifts: number;
    shifts_vacant: number;
    shifts_filled: number;
    active_cascades: number;
    workers_on_standby: number;
  };
  worker_preview: Worker[];
  recent_shifts: Shift[];
  active_cascades: Array<{
    id: number;
    shift_id: number;
    shift_role: string;
    shift_date: string;
    shift_start_time: string;
    shift_status: string;
    status: string;
    outreach_mode?: string | null;
    current_tier?: number | null;
    confirmed_worker_id?: number | null;
    confirmed_worker_name?: string | null;
    standby_depth: number;
  }>;
  recent_sync_jobs: SyncJob[];
  recent_audit: AuditLog[];
};

export type ShiftStatusResponse = {
  shift: Shift;
  restaurant?: Restaurant | null;
  cascade?: Cascade | null;
  filled_worker?: Worker | null;
  outreach_attempts: OutreachAttempt[];
};
