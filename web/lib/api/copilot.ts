import type {
  CopilotMessageCreatePayload,
  CopilotSessionCreatePayload,
  CopilotSessionDetail,
  CopilotTool,
  CopilotTurn,
} from "@/lib/types/copilot";
import { apiFetchApp, API_PREFIX } from "./backend-client";

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
