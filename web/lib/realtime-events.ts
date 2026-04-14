import { API_BASE_URL } from "@/lib/api/client";
import { API_PREFIX } from "@/lib/api/backend-client";

export type RealtimePlatformEvent = {
  platform_event_id: string;
  business_id: string | null;
  location_id: string | null;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  trace_id: string;
  occurred_at: string | null;
  source: "platform_event";
};

export function shouldRefreshSchedulerForRealtimeEvent(
  event: RealtimePlatformEvent,
): boolean {
  return (
    event.event_type.startsWith("schedule.") ||
    event.event_type.startsWith("coverage.")
  );
}

export function shouldRefreshActivityFeedForRealtimeEvent(
  event: RealtimePlatformEvent,
): boolean {
  return ![
    "copilot.message.recorded",
    "copilot.intent.resolved",
  ].includes(event.event_type);
}

function realtimeEventsUrl(
  businessId: string,
  options: { locationId?: string | null } = {},
): string {
  const url = new URL(
    `${API_BASE_URL}${API_PREFIX}/businesses/${businessId}/realtime/events`,
  );
  if (options.locationId) {
    url.searchParams.set("location_id", options.locationId);
  }
  return url.toString();
}

function parseRealtimePlatformEvent(raw: string): RealtimePlatformEvent | null {
  try {
    const parsed = JSON.parse(raw) as Partial<RealtimePlatformEvent>;
    if (
      typeof parsed.platform_event_id !== "string" ||
      typeof parsed.business_id !== "string" ||
      typeof parsed.event_type !== "string" ||
      typeof parsed.entity_type !== "string" ||
      typeof parsed.trace_id !== "string"
    ) {
      return null;
    }
    return {
      platform_event_id: parsed.platform_event_id,
      business_id: parsed.business_id,
      location_id:
        typeof parsed.location_id === "string" ? parsed.location_id : null,
      event_type: parsed.event_type,
      entity_type: parsed.entity_type,
      entity_id: typeof parsed.entity_id === "string" ? parsed.entity_id : null,
      trace_id: parsed.trace_id,
      occurred_at:
        typeof parsed.occurred_at === "string" ? parsed.occurred_at : null,
      source: "platform_event",
    };
  } catch {
    return null;
  }
}

export function subscribeToRealtimePlatformEvents(
  businessId: string,
  options: {
    locationId?: string | null;
    onEvent: (event: RealtimePlatformEvent) => void;
    onError?: () => void;
  },
): () => void {
  if (typeof window === "undefined" || typeof EventSource === "undefined") {
    return () => undefined;
  }
  const source = new EventSource(realtimeEventsUrl(businessId, options), {
    withCredentials: true,
  });
  const handleMessage = (message: MessageEvent<string>) => {
    const event = parseRealtimePlatformEvent(message.data);
    if (event) {
      options.onEvent(event);
    }
  };
  source.addEventListener(
    "platform_event",
    handleMessage as EventListener,
  );
  source.onerror = () => {
    options.onError?.();
  };
  return () => {
    source.removeEventListener(
      "platform_event",
      handleMessage as EventListener,
    );
    source.close();
  };
}
