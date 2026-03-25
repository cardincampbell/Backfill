export type Restaurant = {
  id: number;
  name: string;
  address?: string | null;
  manager_name?: string | null;
  manager_phone?: string | null;
  manager_email?: string | null;
  scheduling_platform?: string | null;
  agency_supply_approved?: boolean;
};

export type Worker = {
  id: number;
  name: string;
  phone: string;
  roles: string[];
  certifications: string[];
  worker_type: string;
  preferred_channel: string;
  priority_rank: number;
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
  current_tier: number;
  current_position: number;
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
  active_shift_ids: number[];
  recent_shifts: Shift[];
};

export type ShiftStatusResponse = {
  shift: Shift;
  restaurant?: Restaurant | null;
  cascade?: Cascade | null;
  filled_worker?: Worker | null;
  outreach_attempts: OutreachAttempt[];
};
