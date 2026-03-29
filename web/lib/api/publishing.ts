import { API_BASE_URL, apiFetch, fetchJson } from "./client";

export async function getDraftOptions(
  locationId: number,
  weekStart?: string
): Promise<import("../types").DraftOptionsResponse | null> {
  try {
    let url = `${API_BASE_URL}/api/locations/${locationId}/schedule-draft-options`;
    if (weekStart) url += `?target_week_start_date=${encodeURIComponent(weekStart)}`;
    const res = await apiFetch(url);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").DraftOptionsResponse;
  } catch {
    return null;
  }
}

export async function createFromTemplate(
  locationId: number,
  payload: { template_id: number; week_start_date: string; assignment_strategy?: import("../types").AssignmentStrategy; auto_assign_open_shifts?: boolean }
): Promise<import("../types").CreateFromTemplateResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/locations/${locationId}/schedules/create-from-template`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as import("../types").CreateFromTemplateResponse;
  } catch {
    return null;
  }
}

export async function createAiDraft(
  locationId: number,
  payload: { week_start_date: string; basis_type?: string; basis_id?: number; assignment_strategy?: import("../types").AssignmentStrategy }
): Promise<import("../types").AiDraftResponse | null> {
  try {
    const res = await apiFetch(
      `${API_BASE_URL}/api/locations/${locationId}/schedules/ai-draft`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (!res.ok) return null;
    return (await res.json()) as import("../types").AiDraftResponse;
  } catch {
    return null;
  }
}

export async function getScheduleReview(
  scheduleId: number
): Promise<import("../types").ScheduleReviewResponse | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/schedules/${scheduleId}/review`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").ScheduleReviewResponse;
  } catch {
    return null;
  }
}

export async function getPublishReadiness(
  scheduleId: number
): Promise<import("../types").PublishReadinessResponse | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/schedules/${scheduleId}/publish-readiness`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").PublishReadinessResponse;
  } catch {
    return null;
  }
}

export async function getScheduleVersions(
  scheduleId: number
): Promise<import("../types").ScheduleVersionsResponse | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/schedules/${scheduleId}/versions`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").ScheduleVersionsResponse;
  } catch {
    return null;
  }
}

export async function getChangeSummary(
  scheduleId: number
): Promise<import("../types").ChangeSummaryResponse | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/schedules/${scheduleId}/change-summary`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").ChangeSummaryResponse;
  } catch {
    return null;
  }
}

export async function getMessagePreview(
  scheduleId: number
): Promise<import("../types").MessagePreviewResponse | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/schedules/${scheduleId}/message-preview`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").MessagePreviewResponse;
  } catch {
    return null;
  }
}

// ── Publish-diff & draft-rationale endpoints ─────────────────────────────

export async function getPublishDiff(
  scheduleId: number
): Promise<import("../types").PublishDiffResponse | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/schedules/${scheduleId}/publish-diff`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").PublishDiffResponse;
  } catch {
    return null;
  }
}

export async function getDraftRationale(
  scheduleId: number
): Promise<import("../types").DraftRationaleResponse | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/schedules/${scheduleId}/draft-rationale`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").DraftRationaleResponse;
  } catch {
    return null;
  }
}

// ── Version diff & publish impact endpoints ──────────────────────────────

export async function getVersionDiff(
  scheduleId: number,
  versionId: number,
  compareTo?: "current" | "previous" | "previous_publish" | number
): Promise<import("../types").VersionDiffResponse | null> {
  try {
    const params = new URLSearchParams();
    if (compareTo != null) {
      params.set(typeof compareTo === "number" ? "compare_to_version_id" : "compare_to", String(compareTo));
    }
    const qs = params.toString() ? `?${params.toString()}` : "";
    const res = await apiFetch(`${API_BASE_URL}/api/schedules/${scheduleId}/versions/${versionId}/diff${qs}`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").VersionDiffResponse;
  } catch {
    return null;
  }
}

export async function getPublishImpact(
  scheduleId: number
): Promise<import("../types").PublishImpactResponse | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/schedules/${scheduleId}/publish-impact`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").PublishImpactResponse;
  } catch {
    return null;
  }
}

export async function getPublishPreview(
  scheduleId: number
): Promise<import("../types").PublishPreviewResponse | null> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/api/schedules/${scheduleId}/publish-preview`);
    if (!res.ok) return null;
    return (await res.json()) as import("../types").PublishPreviewResponse;
  } catch {
    return null;
  }
}
