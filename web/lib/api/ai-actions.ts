/**
 * AI action API functions — wired to frozen contract from
 * backfill-shifts-ai-native-pkg section 8.
 */

import type {
  WebAiActionResponse,
  AiWebActionRequest,
  AiClarifyRequest,
  AiActionHistoryResponse,
} from "../types/ai-actions";
import { API_BASE_URL, apiFetch } from "./client";

// ── Submit action ────────────────────────────────────────────────────────

export async function submitAiAction(
  request: AiWebActionRequest
): Promise<WebAiActionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/ai-actions/web`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Failed to process action");
  }
  return (await res.json()) as WebAiActionResponse;
}

// ── Get action detail ────────────────────────────────────────────────────

export async function getAiAction(
  actionId: number
): Promise<WebAiActionResponse | null> {
  const res = await apiFetch(`${API_BASE_URL}/api/ai-actions/${actionId}`);
  if (!res.ok) return null;
  return (await res.json()) as WebAiActionResponse;
}

// ── Confirm action ───────────────────────────────────────────────────────

export async function confirmAiAction(
  actionId: number
): Promise<WebAiActionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/ai-actions/${actionId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Confirmation failed");
  }
  return (await res.json()) as WebAiActionResponse;
}

// ── Clarify action ───────────────────────────────────────────────────────

export async function clarifyAiAction(
  actionId: number,
  request: AiClarifyRequest
): Promise<WebAiActionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/ai-actions/${actionId}/clarify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Clarification failed");
  }
  return (await res.json()) as WebAiActionResponse;
}

// ── Cancel action ────────────────────────────────────────────────────────

export async function cancelAiAction(
  actionId: number
): Promise<WebAiActionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/ai-actions/${actionId}/cancel`, {
    method: "POST",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Cancellation failed");
  }
  return (await res.json()) as WebAiActionResponse;
}

// ── Action history ───────────────────────────────────────────────────────

export async function getAiActionHistory(
  locationId: number,
  limit = 20
): Promise<AiActionHistoryResponse | null> {
  const res = await apiFetch(
    `${API_BASE_URL}/api/locations/${locationId}/ai-action-history?limit=${limit}`
  );
  if (!res.ok) return null;
  return (await res.json()) as AiActionHistoryResponse;
}
