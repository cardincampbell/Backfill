import type {
  CopilotLiveEvent,
  CopilotMessageCreatePayload,
  CopilotSessionCreatePayload,
  CopilotSessionDetail,
  CopilotTool,
  CopilotTurn,
} from "@/lib/types/copilot";
import { apiFetchApp, API_PREFIX } from "./backend-client";
import { API_BASE_URL } from "./client";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function listCopilotTools(
  businessId: string,
): Promise<CopilotTool[]> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/copilot/tools`,
    { next: { revalidate: 0 } },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as CopilotTool[];
}

export async function createCopilotSession(
  businessId: string,
  payload: CopilotSessionCreatePayload,
): Promise<CopilotSessionDetail> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/copilot/sessions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as CopilotSessionDetail;
}

export async function getCopilotSession(
  businessId: string,
  sessionId: string,
): Promise<CopilotSessionDetail> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/copilot/sessions/${sessionId}`,
    { next: { revalidate: 0 } },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as CopilotSessionDetail;
}

export async function createCopilotMessage(
  businessId: string,
  sessionId: string,
  payload: CopilotMessageCreatePayload,
): Promise<CopilotTurn> {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/copilot/sessions/${sessionId}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as CopilotTurn;
}

function copilotSocketBaseUrl(): string {
  const url = new URL(API_BASE_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.origin;
}

export function buildCopilotSessionSocketUrl(
  businessId: string,
  sessionId: string,
): string {
  return `${copilotSocketBaseUrl()}${API_PREFIX}/businesses/${businessId}/copilot/sessions/${sessionId}/live`;
}

export function connectCopilotSessionSocket(options: {
  businessId: string;
  sessionId: string;
  onEvent: (event: CopilotLiveEvent) => void;
  onError?: (message: string) => void;
  onClose?: () => void;
}): WebSocket {
  const socket = new WebSocket(
    buildCopilotSessionSocketUrl(options.businessId, options.sessionId),
  );
  socket.addEventListener("message", (event) => {
    try {
      options.onEvent(JSON.parse(event.data) as CopilotLiveEvent);
    } catch {
      options.onError?.("Copilot returned an invalid realtime event.");
    }
  });
  socket.addEventListener("error", () => {
    options.onError?.("Copilot realtime connection failed.");
  });
  socket.addEventListener("close", () => {
    options.onClose?.();
  });
  return socket;
}

export function sendCopilotSocketMessage(
  socket: WebSocket,
  payload: CopilotMessageCreatePayload & { trace_id?: string },
): void {
  socket.send(
    JSON.stringify({
      type: "user.message",
      text: payload.text,
      location_id: payload.location_id ?? null,
      normalized_channel: payload.normalized_channel ?? "dashboard",
      trace_id: payload.trace_id,
    }),
  );
}

export function cancelCopilotSocketTurn(
  socket: WebSocket,
  traceId?: string | null,
): void {
  socket.send(
    JSON.stringify({
      type: "assistant.cancel",
      trace_id: traceId ?? null,
    }),
  );
}
