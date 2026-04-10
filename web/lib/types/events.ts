export type PlatformEvent = {
  id: string;
  business_id?: string | null;
  location_id?: string | null;
  schema_version: number;
  event_type: string;
  compatibility_event_name?: string | null;
  entity_type: string;
  entity_id?: string | null;
  actor_type: string;
  actor_user_id?: string | null;
  actor_membership_id?: string | null;
  trace_id: string;
  ip_address?: string | null;
  user_agent?: string | null;
  payload: Record<string, unknown>;
  event_metadata: Record<string, unknown>;
  error_message?: string | null;
  occurred_at: string;
};

export type PlatformEventListQuery = {
  locationId?: string | null;
  entityType?: string | null;
  eventType?: string | null;
  limit?: number;
};
