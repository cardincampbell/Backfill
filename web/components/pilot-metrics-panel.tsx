"use client";

import { useState, useEffect } from "react";
import type { BackfillShiftsMetricsResponse, BackfillShiftsActivityResponse } from "@/lib/types";
import { getBackfillShiftsMetrics, getBackfillShiftsActivity } from "@/lib/shifts-api";

type PilotMetricsPanelProps = {
  locationId: number;
};

function pct(n: number | undefined): string {
  if (n == null) return "n/a";
  return `${(n * 100).toFixed(1)}%`;
}

export function PilotMetricsPanel({ locationId }: PilotMetricsPanelProps) {
  const [metrics, setMetrics] = useState<BackfillShiftsMetricsResponse | null>(null);
  const [activity, setActivity] = useState<BackfillShiftsActivityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [showActivity, setShowActivity] = useState(false);

  useEffect(() => {
    setLoading(true);
    getBackfillShiftsMetrics(locationId, days).then((r) => {
      setMetrics(r);
      setLoading(false);
    });
  }, [locationId, days]);

  useEffect(() => {
    if (showActivity && !activity) {
      getBackfillShiftsActivity(locationId).then(setActivity);
    }
  }, [showActivity, activity, locationId]);

  if (loading) {
    return (
      <div className="settings-card">
        <div className="settings-card-header">Pilot metrics</div>
        <div className="settings-card-body">
          <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Loading metrics...</div>
        </div>
      </div>
    );
  }

  if (!metrics) {
    return (
      <div className="settings-card">
        <div className="settings-card-header">Pilot metrics</div>
        <div className="settings-card-body">
          <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Metrics unavailable for this location.</div>
        </div>
      </div>
    );
  }

  const { launch_controls, summary, rates, recent_activity } = metrics;

  return (
    <div className="settings-card">
      <div className="settings-card-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Pilot metrics</span>
        <div style={{ display: "flex", gap: 4 }}>
          {[7, 14, 30].map((d) => (
            <button
              key={d}
              className={days === d ? "button button-small" : "button-secondary button-small"}
              onClick={() => setDays(d)}
              style={{ fontSize: "0.68rem", padding: "1px 8px" }}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>
      <div className="settings-card-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Launch state */}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{
            fontSize: "0.72rem",
            fontWeight: 600,
            padding: "2px 8px",
            borderRadius: 999,
            background: launch_controls.backfill_shifts_enabled
              ? launch_controls.backfill_shifts_launch_state === "live" ? "rgba(39, 174, 96, 0.08)" : "rgba(59, 130, 246, 0.08)"
              : "rgba(0,0,0,0.04)",
            color: launch_controls.backfill_shifts_enabled
              ? launch_controls.backfill_shifts_launch_state === "live" ? "#1a7a42" : "#2563eb"
              : "var(--muted)",
          }}>
            {launch_controls.backfill_shifts_enabled
              ? launch_controls.backfill_shifts_launch_state
              : "disabled"}
          </span>
          {launch_controls.backfill_shifts_beta_eligible && (
            <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>Beta eligible</span>
          )}
        </div>

        {/* Summary grid */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          {([
            ["Published", summary.schedules_published],
            ["Amendments", summary.amendments_published],
            ["Enrolled", `${summary.workers_enrolled}/${summary.workers_total}`],
            ["Messages", summary.messages_sent],
            ["Delivered", summary.messages_delivered],
            ["Callouts", summary.callouts_received],
            ["Filled", summary.shifts_filled],
          ] as [string, string | number][]).map(([label, value]) => (
            <div key={label}>
              <div style={{ fontSize: "1.1rem", fontWeight: 600 }}>{value}</div>
              <div style={{ fontSize: "0.68rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</div>
            </div>
          ))}
        </div>

        {/* Rates */}
        <div>
          <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 6 }}>
            Rates
          </div>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: "0.78rem" }}>
            {rates.enrollment_rate != null && <span>Enrollment: <strong>{pct(rates.enrollment_rate)}</strong></span>}
            {rates.delivery_success_rate != null && <span>Delivery: <strong>{pct(rates.delivery_success_rate)}</strong></span>}
            {rates.fill_rate != null && <span>Fill: <strong>{pct(rates.fill_rate)}</strong></span>}
            {rates.publish_rate != null && <span>Publish: <strong>{pct(rates.publish_rate)}</strong></span>}
            {rates.amendment_rate != null && <span>Amendment: <strong>{pct(rates.amendment_rate)}</strong></span>}
          </div>
        </div>

        {/* Activity feed */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
              Activity
            </div>
            <button
              className="button-secondary button-small"
              style={{ fontSize: "0.68rem", padding: "1px 8px" }}
              onClick={() => setShowActivity(!showActivity)}
            >
              {showActivity ? "Summary" : "Full feed"}
            </button>
          </div>

          {!showActivity && recent_activity.length > 0 && (
            <div style={{ fontSize: "0.78rem", maxHeight: 240, overflow: "auto" }}>
              {recent_activity.map((a, i) => (
                <div key={i} style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 12,
                  padding: "3px 0",
                  borderBottom: "1px solid rgba(0,0,0,0.04)",
                }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{
                      fontSize: "0.68rem",
                      padding: "1px 6px",
                      borderRadius: 999,
                      background: "rgba(0,0,0,0.04)",
                      color: "var(--muted)",
                      whiteSpace: "nowrap",
                    }}>
                      {a.event_type.replace(/_/g, " ")}
                    </span>
                    <span>{a.description}</span>
                    {a.count != null && a.count > 1 && (
                      <span style={{ color: "var(--muted)", fontSize: "0.72rem" }}>x{a.count}</span>
                    )}
                  </div>
                  <span style={{ color: "var(--muted)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", fontSize: "0.72rem" }}>
                    {new Date(a.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  </span>
                </div>
              ))}
            </div>
          )}

          {showActivity && !activity && (
            <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Loading activity feed...</div>
          )}

          {showActivity && activity && activity.entries.length === 0 && (
            <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>No activity recorded yet.</div>
          )}

          {showActivity && activity && activity.entries.length > 0 && (
            <div style={{ fontSize: "0.78rem", maxHeight: 360, overflow: "auto" }}>
              {activity.entries.map((entry, i) => (
                <div key={entry.id ?? i} style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 12,
                  padding: "4px 0",
                  borderBottom: "1px solid rgba(0,0,0,0.04)",
                }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{
                      fontSize: "0.68rem",
                      padding: "1px 6px",
                      borderRadius: 999,
                      background: entry.category === "publish" ? "rgba(39, 174, 96, 0.08)" :
                                 entry.category === "delivery" ? "rgba(59, 130, 246, 0.08)" :
                                 entry.category === "callout" || entry.category === "fill" ? "rgba(191, 91, 57, 0.08)" :
                                 "rgba(0,0,0,0.04)",
                      color: entry.category === "publish" ? "#1a7a42" :
                            entry.category === "delivery" ? "#2563eb" :
                            entry.category === "callout" || entry.category === "fill" ? "var(--accent)" :
                            "var(--muted)",
                      whiteSpace: "nowrap",
                    }}>
                      {entry.event_type.replace(/_/g, " ")}
                    </span>
                    <span>{entry.description}</span>
                    {entry.worker_name && (
                      <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>{entry.worker_name}</span>
                    )}
                  </div>
                  <span style={{ color: "var(--muted)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", fontSize: "0.72rem" }}>
                    {new Date(entry.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                  </span>
                </div>
              ))}
              {activity.total_count != null && activity.total_count > activity.entries.length && (
                <div style={{ fontSize: "0.72rem", color: "var(--muted)", padding: "6px 0", textAlign: "center" }}>
                  Showing {activity.entries.length} of {activity.total_count}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
