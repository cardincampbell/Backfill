"use client";

import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import type { DraftOptionsResponse, AssignmentStrategy } from "@/lib/types";
import { getDraftOptions, createFromTemplate, createAiDraft } from "@/lib/shifts-api";

const STRATEGY_OPTIONS: { value: AssignmentStrategy; label: string }[] = [
  { value: "priority_first", label: "Priority first" },
  { value: "balance_hours", label: "Balance hours" },
  { value: "minimize_overtime", label: "Minimize overtime" },
];

type DraftLauncherProps = {
  locationId: number;
  weekStart: string;
  basePath?: string;
};

export function DraftLauncher({ locationId, weekStart, basePath }: DraftLauncherProps) {
  const router = useRouter();
  const [options, setOptions] = useState<DraftOptionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [strategy, setStrategy] = useState<AssignmentStrategy>("balance_hours");
  const [autoAssign, setAutoAssign] = useState(true);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const locationBasePath = basePath ?? `/dashboard/locations/${locationId}`;

  useEffect(() => {
    getDraftOptions(locationId, weekStart).then((r) => {
      setOptions(r);
      setLoading(false);
    });
  }, [locationId, weekStart]);

  async function handleCreateFromTemplate(templateId: number) {
    setBusy(true);
    setFeedback(null);
    const result = await createFromTemplate(locationId, {
      template_id: templateId,
      week_start_date: weekStart,
      assignment_strategy: strategy,
      auto_assign_open_shifts: autoAssign,
    });
    if (result) {
      setFeedback({
        type: "success",
        message: `Created schedule: ${result.created_shift_count} shifts (${result.assigned_shift_count} assigned).`,
      });
      router.push(`${locationBasePath}?tab=schedule&week_start=${result.week_start_date}`);
      router.refresh();
    } else {
      setFeedback({ type: "error", message: "Failed to create schedule from template." });
    }
    setBusy(false);
  }

  async function handleAiDraft(basisType?: string, basisId?: number) {
    setBusy(true);
    setFeedback(null);
    const result = await createAiDraft(locationId, {
      week_start_date: weekStart,
      basis_type: basisType,
      basis_id: basisId,
      assignment_strategy: strategy,
    });
    if (result) {
      setFeedback({
        type: "success",
        message: `AI draft created: ${result.created_shift_count} shifts (${result.assigned_shift_count} assigned, ${result.open_shift_count} open).`,
      });
      router.push(`${locationBasePath}?tab=schedule&week_start=${result.week_start_date}`);
      router.refresh();
    } else {
      setFeedback({ type: "error", message: "Failed to create AI draft." });
    }
    setBusy(false);
  }

  if (loading) {
    return (
      <div className="settings-card">
        <div className="settings-card-header">Create a schedule</div>
        <div className="settings-card-body">
          <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Loading options...</div>
        </div>
      </div>
    );
  }

  if (!options || options.options.length === 0) {
    return (
      <div className="settings-card">
        <div className="settings-card-header">Create a schedule</div>
        <div className="settings-card-body">
          <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
            No templates or prior schedules available. Create a template first, or import shifts via CSV.
          </div>
        </div>
      </div>
    );
  }

  const templateOptions = options.options.filter((o) => o.type === "template");
  const scheduleOptions = options.options.filter((o) => o.type === "prior_schedule");

  return (
    <div className="settings-card">
      <div className="settings-card-header">Create a schedule</div>
      <div className="settings-card-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {/* Strategy + auto-assign controls */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>Strategy:</span>
            {STRATEGY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={strategy === opt.value ? "button button-small" : "button-secondary button-small"}
                onClick={() => setStrategy(opt.value)}
                style={{ fontSize: "0.72rem", padding: "2px 8px" }}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.78rem", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={autoAssign}
              onChange={(e) => setAutoAssign(e.target.checked)}
              style={{ accentColor: "var(--brand)" }}
            />
            Auto-assign workers
          </label>
        </div>

        {/* From template */}
        {templateOptions.length > 0 && (
          <div>
            <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 6 }}>
              From template
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {templateOptions.map((opt) => (
                <div key={opt.id} style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "6px 10px",
                  borderRadius: "var(--radius-sm)",
                  background: "rgba(0,0,0,0.02)",
                  fontSize: "0.82rem",
                }}>
                  <div>
                    <span style={{ fontWeight: 500 }}>{opt.name}</span>
                    {opt.slot_count != null && (
                      <span style={{ color: "var(--muted)", marginLeft: 8, fontSize: "0.75rem" }}>
                        {opt.slot_count} slots
                      </span>
                    )}
                    {opt.description && (
                      <span style={{ color: "var(--muted)", marginLeft: 8, fontSize: "0.75rem" }}>
                        {opt.description}
                      </span>
                    )}
                  </div>
                  <button
                    className="button button-small"
                    disabled={busy}
                    onClick={() => handleCreateFromTemplate(opt.id!)}
                  >
                    {busy ? "Creating\u2026" : "Create"}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* From prior schedule / AI draft */}
        {scheduleOptions.length > 0 && (
          <div>
            <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 6 }}>
              AI draft from prior week
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {scheduleOptions.map((opt) => (
                <div key={opt.id} style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "6px 10px",
                  borderRadius: "var(--radius-sm)",
                  background: "rgba(0,0,0,0.02)",
                  fontSize: "0.82rem",
                }}>
                  <div>
                    <span style={{ fontWeight: 500 }}>{opt.name}</span>
                    {opt.week_start_date && (
                      <span style={{ color: "var(--muted)", marginLeft: 8, fontSize: "0.75rem" }}>
                        Week of {opt.week_start_date}
                      </span>
                    )}
                  </div>
                  <button
                    className="button-secondary button-small"
                    disabled={busy}
                    onClick={() => handleAiDraft("prior_schedule", opt.id)}
                  >
                    {busy ? "Creating\u2026" : "AI draft"}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Blank AI draft */}
        <div>
          <button
            className="button-secondary button-small"
            disabled={busy}
            onClick={() => handleAiDraft("blank")}
          >
            {busy ? "Creating\u2026" : "Start blank AI draft"}
          </button>
        </div>

        {feedback && (
          <div style={{
            fontSize: "0.82rem",
            padding: "6px 10px",
            borderRadius: "var(--radius-sm)",
            background: feedback.type === "success" ? "rgba(39, 174, 96, 0.04)" : "rgba(191, 91, 57, 0.04)",
            color: feedback.type === "success" ? "#1a7a42" : "var(--accent)",
          }}>
            {feedback.message}
          </div>
        )}
      </div>
    </div>
  );
}
