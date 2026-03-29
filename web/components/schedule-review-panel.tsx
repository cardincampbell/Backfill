"use client";

import { useState } from "react";
import type {
  ScheduleReviewResponse,
  PublishReadinessResponse,
  ScheduleVersionsResponse,
  ChangeSummaryResponse,
  MessagePreviewResponse,
  PublishDiffResponse,
  DraftRationaleResponse,
  VersionDiffResponse,
  PublishImpactResponse,
  PublishPreviewResponse,
} from "@/lib/types";
import {
  getScheduleReview,
  getPublishReadiness,
  getScheduleVersions,
  getChangeSummary,
  getMessagePreview,
  getPublishDiff,
  getDraftRationale,
  getVersionDiff,
  getPublishImpact,
  getPublishPreview,
} from "@/lib/shifts-api";

type ScheduleReviewPanelProps = {
  scheduleId: number;
};

function changeIcon(type: string): string {
  switch (type) {
    case "shift_added": return "+";
    case "shift_removed": return "\u2212";
    case "role_changed": return "\u21c4";
    case "assignment_changed": return "\u21bb";
    case "time_changed": return "\u23f0";
    default: return "\u2022";
  }
}

function diffEntryIcon(type: string): { icon: string; color: string } {
  switch (type) {
    case "added": return { icon: "+", color: "#1a7a42" };
    case "removed": return { icon: "\u2212", color: "var(--accent)" };
    default: return { icon: "\u21c4", color: "var(--muted)" };
  }
}

function impactColor(type: string): string {
  switch (type) {
    case "new_schedule": return "#1a7a42";
    case "updated": return "var(--foreground)";
    case "removed": return "var(--accent)";
    case "unchanged": return "var(--muted)";
    default: return "var(--muted)";
  }
}

export function ScheduleReviewPanel({ scheduleId }: ScheduleReviewPanelProps) {
  const [activeSection, setActiveSection] = useState<
    "review" | "readiness" | "versions" | "changes" | "message" | "diff" | "rationale" | "impact" | "preview" | null
  >(null);
  const [review, setReview] = useState<ScheduleReviewResponse | null>(null);
  const [readiness, setReadiness] = useState<PublishReadinessResponse | null>(null);
  const [versions, setVersions] = useState<ScheduleVersionsResponse | null>(null);
  const [changeSummary, setChangeSummary] = useState<ChangeSummaryResponse | null>(null);
  const [messagePreview, setMessagePreview] = useState<MessagePreviewResponse | null>(null);
  const [publishDiff, setPublishDiff] = useState<PublishDiffResponse | null>(null);
  const [rationale, setRationale] = useState<DraftRationaleResponse | null>(null);
  const [publishImpact, setPublishImpact] = useState<PublishImpactResponse | null>(null);
  const [publishPreview, setPublishPreview] = useState<PublishPreviewResponse | null>(null);
  const [versionDiff, setVersionDiff] = useState<VersionDiffResponse | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadSection(section: typeof activeSection) {
    if (activeSection === section) {
      setActiveSection(null);
      return;
    }
    setBusy(true);
    setActiveSection(section);
    setVersionDiff(null);
    setSelectedVersionId(null);
    switch (section) {
      case "review": {
        const r = await getScheduleReview(scheduleId);
        setReview(r);
        break;
      }
      case "readiness": {
        const r = await getPublishReadiness(scheduleId);
        setReadiness(r);
        break;
      }
      case "versions": {
        const r = await getScheduleVersions(scheduleId);
        setVersions(r);
        break;
      }
      case "changes": {
        const r = await getChangeSummary(scheduleId);
        setChangeSummary(r);
        break;
      }
      case "message": {
        const r = await getMessagePreview(scheduleId);
        setMessagePreview(r);
        break;
      }
      case "diff": {
        const r = await getPublishDiff(scheduleId);
        setPublishDiff(r);
        break;
      }
      case "rationale": {
        const r = await getDraftRationale(scheduleId);
        setRationale(r);
        break;
      }
      case "impact": {
        const r = await getPublishImpact(scheduleId);
        setPublishImpact(r);
        break;
      }
      case "preview": {
        const r = await getPublishPreview(scheduleId);
        setPublishPreview(r);
        break;
      }
    }
    setBusy(false);
  }

  async function loadVersionDiff(versionId: number, compareTo?: "current" | "previous" | "previous_publish") {
    if (selectedVersionId === versionId && versionDiff) {
      setVersionDiff(null);
      setSelectedVersionId(null);
      return;
    }
    setBusy(true);
    setSelectedVersionId(versionId);
    const r = await getVersionDiff(scheduleId, versionId, compareTo);
    setVersionDiff(r);
    setBusy(false);
  }

  return (
    <div className="settings-card" style={{ marginTop: 16 }}>
      <div className="settings-card-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Schedule intelligence</span>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button className={`button-secondary button-small${activeSection === "readiness" ? " active" : ""}`} onClick={() => loadSection("readiness")} disabled={busy}>
            Readiness
          </button>
          <button className={`button-secondary button-small${activeSection === "review" ? " active" : ""}`} onClick={() => loadSection("review")} disabled={busy}>
            Review
          </button>
          <button className={`button-secondary button-small${activeSection === "changes" ? " active" : ""}`} onClick={() => loadSection("changes")} disabled={busy}>
            Changes
          </button>
          <button className={`button-secondary button-small${activeSection === "diff" ? " active" : ""}`} onClick={() => loadSection("diff")} disabled={busy}>
            Publish diff
          </button>
          <button className={`button-secondary button-small${activeSection === "impact" ? " active" : ""}`} onClick={() => loadSection("impact")} disabled={busy}>
            Impact
          </button>
          <button className={`button-secondary button-small${activeSection === "preview" ? " active" : ""}`} onClick={() => loadSection("preview")} disabled={busy}>
            Preview
          </button>
          <button className={`button-secondary button-small${activeSection === "rationale" ? " active" : ""}`} onClick={() => loadSection("rationale")} disabled={busy}>
            Rationale
          </button>
          <button className={`button-secondary button-small${activeSection === "message" ? " active" : ""}`} onClick={() => loadSection("message")} disabled={busy}>
            Message
          </button>
          <button className={`button-secondary button-small${activeSection === "versions" ? " active" : ""}`} onClick={() => loadSection("versions")} disabled={busy}>
            History
          </button>
        </div>
      </div>

      {activeSection && (
        <div className="settings-card-body">
          {busy && !versionDiff && <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Loading...</div>}

          {/* Publish readiness */}
          {activeSection === "readiness" && readiness && !busy && (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <span style={{
                  fontSize: "0.72rem",
                  fontWeight: 600,
                  padding: "2px 8px",
                  borderRadius: 999,
                  background: readiness.ready ? "rgba(39, 174, 96, 0.08)" : "rgba(191, 91, 57, 0.08)",
                  color: readiness.ready ? "#1a7a42" : "var(--accent)",
                }}>
                  {readiness.status === "already_published" ? "Already published" : readiness.ready ? "Ready to publish" : "Blocked"}
                </span>
              </div>
              {readiness.blockers.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>Blockers</div>
                  {readiness.blockers.map((b, i) => (
                    <div key={i} style={{ fontSize: "0.78rem", color: "var(--accent)", padding: "2px 0" }}>{b.message}</div>
                  ))}
                </div>
              )}
              {readiness.warnings.length > 0 && (
                <div>
                  <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>Warnings</div>
                  {readiness.warnings.map((w, i) => (
                    <div key={i} style={{ fontSize: "0.78rem", color: "var(--muted)", padding: "2px 0" }}>{w.message}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Review */}
          {activeSection === "review" && review && !busy && (
            <div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: "0.78rem", marginBottom: 12 }}>
                <span><strong>{review.review_summary.total_changes}</strong> changes</span>
                {review.review_summary.shifts_added > 0 && <span><strong>{review.review_summary.shifts_added}</strong> added</span>}
                {review.review_summary.shifts_removed > 0 && <span><strong>{review.review_summary.shifts_removed}</strong> removed</span>}
                {review.review_summary.assignments_changed > 0 && <span><strong>{review.review_summary.assignments_changed}</strong> reassigned</span>}
                {review.review_summary.roles_changed > 0 && <span><strong>{review.review_summary.roles_changed}</strong> role changes</span>}
              </div>
              {review.publish_impact_summary && (
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: "0.75rem", color: "var(--muted)", marginBottom: 10 }}>
                  <span>{review.publish_impact_summary.total_workers} workers affected</span>
                  {review.publish_impact_summary.new_schedule_count > 0 && (
                    <span style={{ color: "#1a7a42" }}>{review.publish_impact_summary.new_schedule_count} new</span>
                  )}
                  {review.publish_impact_summary.updated_count > 0 && (
                    <span>{review.publish_impact_summary.updated_count} updated</span>
                  )}
                  {review.publish_impact_summary.removed_count > 0 && (
                    <span style={{ color: "var(--accent)" }}>{review.publish_impact_summary.removed_count} removed</span>
                  )}
                  {review.publish_impact_summary.unchanged_count > 0 && (
                    <span>{review.publish_impact_summary.unchanged_count} unchanged</span>
                  )}
                </div>
              )}
              {review.changes.length > 0 && (
                <div style={{ fontSize: "0.78rem", maxHeight: 300, overflow: "auto" }}>
                  {review.changes.map((c, i) => (
                    <div key={i} style={{ display: "flex", gap: 8, padding: "3px 0", borderBottom: "1px solid rgba(0,0,0,0.04)" }}>
                      <span style={{ fontFamily: "monospace", width: 16, textAlign: "center", color: "var(--muted)" }}>{changeIcon(c.type)}</span>
                      <span>{c.description}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Change summary */}
          {activeSection === "changes" && changeSummary && !busy && (
            <div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: "0.78rem", marginBottom: 12 }}>
                <span><strong>{changeSummary.summary.total_changes}</strong> total changes</span>
                {changeSummary.summary.shifts_added > 0 && <span><strong>+{changeSummary.summary.shifts_added}</strong> shifts</span>}
                {changeSummary.summary.shifts_removed > 0 && <span><strong>-{changeSummary.summary.shifts_removed}</strong> shifts</span>}
                {changeSummary.summary.roles_changed > 0 && <span><strong>{changeSummary.summary.roles_changed}</strong> role changes</span>}
                {changeSummary.summary.assignments_changed > 0 && <span><strong>{changeSummary.summary.assignments_changed}</strong> assignment changes</span>}
              </div>
              {changeSummary.basis_type && (
                <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginBottom: 8 }}>
                  Compared to: {changeSummary.basis_type}{changeSummary.derived_from_schedule_id ? ` #${changeSummary.derived_from_schedule_id}` : ""}
                </div>
              )}
              {changeSummary.changes.length > 0 && (
                <div style={{ fontSize: "0.78rem", maxHeight: 300, overflow: "auto" }}>
                  {changeSummary.changes.map((c, i) => (
                    <div key={i} style={{ display: "flex", gap: 8, padding: "3px 0", borderBottom: "1px solid rgba(0,0,0,0.04)" }}>
                      <span style={{ fontFamily: "monospace", width: 16, textAlign: "center", color: "var(--muted)" }}>{changeIcon(c.type)}</span>
                      <span>{c.description}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Publish diff */}
          {activeSection === "diff" && publishDiff && !busy && (
            <div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: "0.78rem", marginBottom: 12 }}>
                <span><strong>{publishDiff.diff.total_changes}</strong> total changes</span>
                {publishDiff.diff.shifts_added > 0 && <span><strong>+{publishDiff.diff.shifts_added}</strong> added</span>}
                {publishDiff.diff.shifts_removed > 0 && <span><strong>-{publishDiff.diff.shifts_removed}</strong> removed</span>}
                {publishDiff.diff.assignments_changed > 0 && <span><strong>{publishDiff.diff.assignments_changed}</strong> reassigned</span>}
                {publishDiff.diff.roles_changed > 0 && <span><strong>{publishDiff.diff.roles_changed}</strong> role changes</span>}
                {publishDiff.diff.open_shift_impact != null && publishDiff.diff.open_shift_impact !== 0 && (
                  <span><strong>{publishDiff.diff.open_shift_impact > 0 ? "+" : ""}{publishDiff.diff.open_shift_impact}</strong> open shifts</span>
                )}
              </div>
              {publishDiff.diff.worker_impact && publishDiff.diff.worker_impact.length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
                    Worker impact
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {publishDiff.diff.worker_impact.map((w) => (
                      <span key={w.worker_id} style={{
                        fontSize: "0.72rem",
                        padding: "2px 8px",
                        borderRadius: 999,
                        background: "rgba(0,0,0,0.03)",
                        color: impactColor(w.impact_type),
                      }}>
                        {w.worker_name} &middot; {w.impact_type.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {publishDiff.diff.entries.length > 0 && (
                <div style={{ fontSize: "0.78rem", maxHeight: 300, overflow: "auto" }}>
                  {publishDiff.diff.entries.map((e, i) => {
                    const { icon, color } = diffEntryIcon(e.type);
                    return (
                      <div key={i} style={{ display: "flex", gap: 8, padding: "3px 0", borderBottom: "1px solid rgba(0,0,0,0.04)" }}>
                        <span style={{ fontFamily: "monospace", width: 16, textAlign: "center", color }}>{icon}</span>
                        <span>{e.description}</span>
                      </div>
                    );
                  })}
                </div>
              )}
              {publishDiff.diff.total_changes === 0 && (
                <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>No changes from the currently published schedule.</div>
              )}
            </div>
          )}

          {/* Publish impact */}
          {activeSection === "impact" && publishImpact && !busy && (
            <div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: "0.78rem", marginBottom: 12 }}>
                <span><strong>{publishImpact.impact_summary.total_workers}</strong> workers total</span>
                {publishImpact.impact_summary.new_schedule_count > 0 && (
                  <span style={{ color: "#1a7a42" }}><strong>{publishImpact.impact_summary.new_schedule_count}</strong> new schedule</span>
                )}
                {publishImpact.impact_summary.updated_count > 0 && (
                  <span><strong>{publishImpact.impact_summary.updated_count}</strong> updated</span>
                )}
                {publishImpact.impact_summary.removed_count > 0 && (
                  <span style={{ color: "var(--accent)" }}><strong>{publishImpact.impact_summary.removed_count}</strong> removed</span>
                )}
                {publishImpact.impact_summary.unchanged_count > 0 && (
                  <span style={{ color: "var(--muted)" }}><strong>{publishImpact.impact_summary.unchanged_count}</strong> unchanged (skipped)</span>
                )}
              </div>
              {/* Granular change-type counts */}
              {(publishImpact.impact_summary.new_assignment_count != null || publishImpact.impact_summary.changed_shift_count != null) && (
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: "0.72rem", color: "var(--muted)", marginBottom: 10 }}>
                  {publishImpact.impact_summary.new_assignment_count != null && publishImpact.impact_summary.new_assignment_count > 0 && (
                    <span>{publishImpact.impact_summary.new_assignment_count} new assignments</span>
                  )}
                  {publishImpact.impact_summary.changed_shift_count != null && publishImpact.impact_summary.changed_shift_count > 0 && (
                    <span>{publishImpact.impact_summary.changed_shift_count} changed shifts</span>
                  )}
                  {publishImpact.impact_summary.added_shift_only_count != null && publishImpact.impact_summary.added_shift_only_count > 0 && (
                    <span>{publishImpact.impact_summary.added_shift_only_count} added-only</span>
                  )}
                  {publishImpact.impact_summary.removed_shift_only_count != null && publishImpact.impact_summary.removed_shift_only_count > 0 && (
                    <span>{publishImpact.impact_summary.removed_shift_only_count} removed-only</span>
                  )}
                </div>
              )}
              {publishImpact.worker_impact.length > 0 && (
                <div style={{ fontSize: "0.78rem", maxHeight: 300, overflow: "auto" }}>
                  {publishImpact.worker_impact.map((w) => (
                    <div key={w.worker_id} style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "4px 0",
                      borderBottom: "1px solid rgba(0,0,0,0.04)",
                    }}>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <span style={{ fontWeight: 500 }}>{w.worker_name}</span>
                        <span style={{
                          fontSize: "0.68rem",
                          padding: "1px 6px",
                          borderRadius: 999,
                          background: w.impact_type === "removed" ? "rgba(191, 91, 57, 0.08)" :
                                     w.impact_type === "new_schedule" ? "rgba(39, 174, 96, 0.08)" :
                                     w.impact_type === "unchanged" ? "rgba(0,0,0,0.03)" : "rgba(0,0,0,0.04)",
                          color: impactColor(w.impact_type),
                        }}>
                          {w.impact_type.replace(/_/g, " ")}
                        </span>
                        {w.change_count != null && w.change_count > 0 && (
                          <span style={{ color: "var(--muted)", fontSize: "0.75rem" }}>{w.change_count} changes</span>
                        )}
                      </div>
                      {w.description && (
                        <span style={{ color: "var(--muted)", fontSize: "0.75rem" }}>{w.description}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Publish preview */}
          {activeSection === "preview" && publishPreview && !busy && (
            <div>
              {/* Delivery estimate */}
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: "0.78rem", marginBottom: 12 }}>
                <span><strong>{publishPreview.delivery_estimate.total_recipients}</strong> recipients</span>
                <span style={{ color: "#1a7a42" }}><strong>{publishPreview.delivery_estimate.will_send}</strong> will send</span>
                {publishPreview.delivery_estimate.blocked > 0 && (
                  <span style={{ color: "var(--accent)" }}><strong>{publishPreview.delivery_estimate.blocked}</strong> blocked</span>
                )}
                {publishPreview.delivery_estimate.skipped_unchanged > 0 && (
                  <span style={{ color: "var(--muted)" }}><strong>{publishPreview.delivery_estimate.skipped_unchanged}</strong> unchanged</span>
                )}
                {publishPreview.delivery_estimate.removal_notices > 0 && (
                  <span style={{ color: "var(--accent)" }}><strong>{publishPreview.delivery_estimate.removal_notices}</strong> removal notices</span>
                )}
              </div>

              {/* Manager preview */}
              <div style={{ marginBottom: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                    Manager message
                  </span>
                  {publishPreview.message_preview.publish_mode && (
                    <span style={{
                      fontSize: "0.68rem",
                      padding: "1px 6px",
                      borderRadius: 999,
                      background: "rgba(0,0,0,0.04)",
                      color: "var(--muted)",
                    }}>
                      {publishPreview.message_preview.publish_mode}
                    </span>
                  )}
                </div>
                <div style={{
                  fontSize: "0.82rem",
                  padding: "10px 14px",
                  borderRadius: "var(--radius-sm)",
                  background: "rgba(0,0,0,0.02)",
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.5,
                }}>
                  {publishPreview.message_preview.message_body}
                </div>
              </div>

              {/* Worker message previews */}
              {publishPreview.worker_message_previews.length > 0 && (
                <div>
                  <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 6 }}>
                    Worker messages ({publishPreview.worker_message_previews.length})
                  </div>
                  <div style={{ fontSize: "0.78rem", maxHeight: 400, overflow: "auto" }}>
                    {publishPreview.worker_message_previews.map((wp) => (
                      <div key={wp.worker_id} style={{
                        padding: "8px 0",
                        borderBottom: "1px solid rgba(0,0,0,0.04)",
                      }}>
                        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                          <span style={{ fontWeight: 500 }}>{wp.worker_name}</span>
                          <span style={{
                            fontSize: "0.68rem",
                            padding: "1px 6px",
                            borderRadius: 999,
                            background: wp.delivery_status === "will_send" ? "rgba(39, 174, 96, 0.08)" :
                                       wp.delivery_status === "blocked" ? "rgba(191, 91, 57, 0.08)" : "rgba(0,0,0,0.03)",
                            color: wp.delivery_status === "will_send" ? "#1a7a42" :
                                  wp.delivery_status === "blocked" ? "var(--accent)" : "var(--muted)",
                          }}>
                            {wp.delivery_status.replace(/_/g, " ")}
                          </span>
                          {wp.message_type && (
                            <span style={{ fontSize: "0.68rem", color: "var(--muted)" }}>
                              {wp.message_type.replace(/_/g, " ")}
                            </span>
                          )}
                          {wp.delivery_reason && wp.delivery_status !== "will_send" && (
                            <span style={{ fontSize: "0.68rem", color: wp.delivery_status === "blocked" ? "var(--accent)" : "var(--muted)" }}>
                              {wp.delivery_reason}
                            </span>
                          )}
                        </div>
                        {wp.message_body && wp.delivery_status === "will_send" && (
                          <div style={{
                            fontSize: "0.75rem",
                            padding: "6px 10px",
                            borderRadius: "var(--radius-sm)",
                            background: "rgba(0,0,0,0.02)",
                            whiteSpace: "pre-wrap",
                            lineHeight: 1.4,
                            color: "var(--muted)",
                          }}>
                            {wp.message_body}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Draft rationale */}
          {activeSection === "rationale" && rationale && !busy && (
            <div>
              {rationale.basis_name && (
                <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginBottom: 8 }}>
                  Based on: {rationale.basis_name}
                  {rationale.strategy && <span> &middot; Strategy: {rationale.strategy.replace(/_/g, " ")}</span>}
                </div>
              )}
              <div style={{
                fontSize: "0.82rem",
                padding: "12px 16px",
                borderRadius: "var(--radius-sm)",
                background: "rgba(0,0,0,0.02)",
                whiteSpace: "pre-wrap",
                lineHeight: 1.5,
              }}>
                {rationale.rationale}
              </div>
              {rationale.highlights && rationale.highlights.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
                    Highlights
                  </div>
                  {rationale.highlights.map((h, i) => (
                    <div key={i} style={{ fontSize: "0.78rem", padding: "2px 0", color: "var(--foreground)" }}>{h}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Message preview */}
          {activeSection === "message" && messagePreview && !busy && (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                  SMS message preview
                </span>
                {messagePreview.publish_mode && (
                  <span style={{
                    fontSize: "0.68rem",
                    padding: "1px 6px",
                    borderRadius: 999,
                    background: "rgba(0,0,0,0.04)",
                    color: "var(--muted)",
                  }}>
                    {messagePreview.publish_mode}
                  </span>
                )}
                {messagePreview.worker_update_count != null && (
                  <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>
                    {messagePreview.worker_update_count} worker{messagePreview.worker_update_count !== 1 ? "s" : ""} notified
                  </span>
                )}
              </div>
              <div style={{
                fontSize: "0.82rem",
                padding: "12px 16px",
                borderRadius: "var(--radius-sm)",
                background: "rgba(0,0,0,0.02)",
                whiteSpace: "pre-wrap",
                lineHeight: 1.5,
              }}>
                {messagePreview.message_body}
              </div>
              {messagePreview.review_link && (
                <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginTop: 6 }}>
                  Review link: {messagePreview.review_link}
                </div>
              )}
              {messagePreview.delivery_summary && (
                <div style={{ display: "flex", gap: 12, fontSize: "0.72rem", color: "var(--muted)", marginTop: 6 }}>
                  {messagePreview.delivery_summary.sms_sent != null && (
                    <span>{messagePreview.delivery_summary.sms_sent} SMS sent</span>
                  )}
                  {messagePreview.delivery_summary.sms_removed_sent != null && messagePreview.delivery_summary.sms_removed_sent > 0 && (
                    <span>{messagePreview.delivery_summary.sms_removed_sent} removal notices</span>
                  )}
                  {messagePreview.delivery_summary.skipped_unchanged_workers != null && messagePreview.delivery_summary.skipped_unchanged_workers > 0 && (
                    <span>{messagePreview.delivery_summary.skipped_unchanged_workers} unchanged skipped</span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Version history */}
          {activeSection === "versions" && versions && !busy && (
            <div>
              {versions.versions.length === 0 ? (
                <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>No versions recorded yet.</div>
              ) : (
                <div style={{ fontSize: "0.78rem" }}>
                  {versions.versions.map((v) => (
                    <div key={v.id}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          gap: 12,
                          padding: "6px 0",
                          borderBottom: selectedVersionId === v.id ? "none" : "1px solid rgba(0,0,0,0.04)",
                          cursor: "pointer",
                          background: v.is_current_version ? "rgba(39, 174, 96, 0.03)" : "transparent",
                        }}
                        onClick={() => loadVersionDiff(v.id, v.default_compare_mode as "current" | "previous" | "previous_publish" | undefined)}
                      >
                        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                          <span style={{ fontWeight: 600 }}>v{v.version_number}</span>
                          <span style={{
                            fontSize: "0.68rem",
                            padding: "1px 6px",
                            borderRadius: 999,
                            background: v.version_type === "publish_snapshot" ? "rgba(39, 174, 96, 0.08)" :
                                       v.version_type === "amendment_snapshot" ? "rgba(59, 130, 246, 0.08)" : "rgba(0,0,0,0.04)",
                            color: v.version_type === "publish_snapshot" ? "#1a7a42" :
                                  v.version_type === "amendment_snapshot" ? "#2563eb" : "var(--muted)",
                          }}>
                            {v.event_label || v.version_type.replace(/_/g, " ")}
                          </span>
                          {v.is_current_version && (
                            <span style={{
                              fontSize: "0.68rem",
                              padding: "1px 6px",
                              borderRadius: 999,
                              background: "rgba(39, 174, 96, 0.08)",
                              color: "#1a7a42",
                            }}>
                              current
                            </span>
                          )}
                          {v.shift_count != null && (
                            <span style={{ color: "var(--muted)" }}>{v.shift_count} shifts</span>
                          )}
                          {v.diff_summary && v.diff_summary.total_changes > 0 && (
                            <span style={{ color: "var(--muted)", fontSize: "0.72rem" }}>
                              {v.diff_summary.total_changes} changes
                            </span>
                          )}
                          {v.worker_impact_summary && v.worker_impact_summary.total_workers > 0 && (
                            <span style={{ color: "var(--muted)", fontSize: "0.72rem" }}>
                              {v.worker_impact_summary.total_workers} workers
                            </span>
                          )}
                        </div>
                        <span style={{ color: "var(--muted)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                          {new Date(v.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                        </span>
                      </div>

                      {v.event_narrative && selectedVersionId !== v.id && (
                        <div style={{ fontSize: "0.72rem", color: "var(--muted)", padding: "0 0 4px 0" }}>
                          {v.event_narrative}
                        </div>
                      )}

                      {/* Version diff drill-in */}
                      {selectedVersionId === v.id && (
                        <div style={{
                          padding: "8px 12px",
                          marginBottom: 4,
                          borderRadius: "var(--radius-sm)",
                          background: "rgba(0,0,0,0.02)",
                          borderBottom: "1px solid rgba(0,0,0,0.04)",
                        }}>
                          {busy && <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>Loading diff...</div>}
                          {versionDiff && !busy && (
                            <div>
                              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6, fontSize: "0.72rem", color: "var(--muted)" }}>
                                <span>Compared: {versionDiff.compare_mode.replace(/_/g, " ")}</span>
                                {versionDiff.compare_to_version_id && <span>vs v{versionDiff.compare_to_version_id}</span>}
                              </div>
                              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: "0.75rem", marginBottom: 8 }}>
                                <span><strong>{versionDiff.diff.total_changes}</strong> changes</span>
                                {versionDiff.diff.shifts_added > 0 && <span>+{versionDiff.diff.shifts_added} added</span>}
                                {versionDiff.diff.shifts_removed > 0 && <span>-{versionDiff.diff.shifts_removed} removed</span>}
                                {versionDiff.diff.assignments_changed > 0 && <span>{versionDiff.diff.assignments_changed} reassigned</span>}
                              </div>
                              {v.highlights && v.highlights.length > 0 && (
                                <div style={{ marginBottom: 6 }}>
                                  {v.highlights.map((h, i) => (
                                    <div key={i} style={{ fontSize: "0.72rem", color: "var(--muted)", padding: "1px 0" }}>{h}</div>
                                  ))}
                                </div>
                              )}
                              {versionDiff.diff.entries.length > 0 && (
                                <div style={{ fontSize: "0.75rem", maxHeight: 200, overflow: "auto" }}>
                                  {versionDiff.diff.entries.map((e, i) => {
                                    const { icon, color } = diffEntryIcon(e.type);
                                    return (
                                      <div key={i} style={{ display: "flex", gap: 6, padding: "2px 0", borderBottom: "1px solid rgba(0,0,0,0.03)" }}>
                                        <span style={{ fontFamily: "monospace", width: 14, textAlign: "center", color }}>{icon}</span>
                                        <span>{e.description}</span>
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                              {versionDiff.worker_impact && versionDiff.worker_impact.length > 0 && (
                                <div style={{ marginTop: 6 }}>
                                  <div style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 2 }}>
                                    Worker impact
                                  </div>
                                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                                    {versionDiff.worker_impact.map((w) => (
                                      <span key={w.worker_id} style={{
                                        fontSize: "0.68rem",
                                        padding: "1px 6px",
                                        borderRadius: 999,
                                        background: "rgba(0,0,0,0.03)",
                                        color: impactColor(w.impact_type),
                                      }}>
                                        {w.worker_name}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}
                              {/* Compare-to-current shortcut */}
                              {v.can_compare_to_current && versionDiff.compare_mode !== "current" && (
                                <button
                                  className="button-secondary button-small"
                                  style={{ marginTop: 8, fontSize: "0.68rem" }}
                                  onClick={(e) => { e.stopPropagation(); loadVersionDiff(v.id, "current"); }}
                                >
                                  Compare to current
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
