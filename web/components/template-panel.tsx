"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ScheduleTemplate } from "@/lib/types";
import {
  saveAsTemplate,
  applyTemplate,
  applyTemplateRange,
  updateTemplate,
  refreshTemplate,
  deleteTemplate,
  createEmptyTemplate,
  cloneTemplate,
  generateDraft,
} from "@/lib/shifts-api";
import { TemplateEditor } from "@/components/template-editor";

type TemplatePanelProps = {
  locationId: number;
  scheduleId?: number;
  currentWeekStart?: string;
  templates: ScheduleTemplate[];
  basePath?: string;
};

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function formatDate(date: string): string {
  const d = new Date(date + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function futureMondays(count: number): string[] {
  const today = new Date();
  const day = today.getDay();
  const diff = day === 0 ? 1 : 8 - day;
  const result: string[] = [];
  for (let i = 0; i < count; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() + diff + i * 7);
    result.push(d.toISOString().slice(0, 10));
  }
  return result;
}

// ── Feedback banner ──────────────────────────────────────────────────────

function FeedbackBanner({ feedback }: { feedback: { type: "success" | "error"; message: string } }) {
  return (
    <div style={{
      fontSize: "0.82rem",
      marginTop: 10,
      padding: "6px 10px",
      borderRadius: "var(--radius-sm)",
      background: feedback.type === "success" ? "rgba(39, 174, 96, 0.04)" : "rgba(191, 91, 57, 0.04)",
      color: feedback.type === "success" ? "#1a7a42" : "var(--accent)",
    }}>
      {feedback.message}
    </div>
  );
}

// ── Save template form ────────────────────────────────────────────────────

function SaveTemplateForm({
  scheduleId,
  onSaved,
}: {
  scheduleId: number;
  onSaved: (t: ScheduleTemplate) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setFeedback(null);

    const form = new FormData(e.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const keepAssignees = form.get("keep_assignees") === "on";

    if (!name) {
      setFeedback({ type: "error", message: "Template name is required." });
      setBusy(false);
      return;
    }

    const result = await saveAsTemplate(scheduleId, {
      name,
      keep_assignees: keepAssignees,
    });

    if (result) {
      setFeedback({ type: "success", message: `Saved "${result.name}" with ${result.slot_count} slots.` });
      onSaved(result);
    } else {
      setFeedback({ type: "error", message: "Failed to save template." });
    }
    setBusy(false);
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-grid">
        <label className="field">
          <span>Template name</span>
          <input name="name" placeholder="e.g. Standard Week" required />
        </label>
        <label className="settings-toggle" style={{ alignSelf: "end", padding: "8px 0" }}>
          <div>
            <div className="settings-toggle-label">Keep assignees</div>
            <div className="settings-toggle-desc">Include worker assignments in the template.</div>
          </div>
          <input type="checkbox" name="keep_assignees" className="settings-checkbox" />
        </label>
      </div>
      <div className="cta-row" style={{ marginTop: 12 }}>
        <button className="button button-small" type="submit" disabled={busy}>
          {busy ? "Saving\u2026" : "Save as template"}
        </button>
      </div>
      {feedback && <FeedbackBanner feedback={feedback} />}
    </form>
  );
}

// ── Template card ─────────────────────────────────────────────────────────

function TemplateCard({
  template: initialTemplate,
  locationId,
  scheduleId,
  basePath,
  onUpdated,
  onDeleted,
  onCloned,
}: {
  template: ScheduleTemplate;
  locationId: number;
  scheduleId?: number;
  basePath?: string;
  onUpdated: (t: ScheduleTemplate) => void;
  onDeleted: (id: number) => void;
  onCloned: (t: ScheduleTemplate) => void;
}) {
  const router = useRouter();
  const [template, setTemplate] = useState(initialTemplate);
  const [editingSlots, setEditingSlots] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [selectedWeeks, setSelectedWeeks] = useState<Set<string>>(new Set());

  // Day filter and auto-assign for apply
  const [applyDayFilter, setApplyDayFilter] = useState<Set<number>>(new Set());
  const [autoAssignOnApply, setAutoAssignOnApply] = useState(false);

  // Edit state
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(template.name);
  const [editDesc, setEditDesc] = useState(template.description ?? "");
  const locationBasePath = basePath ?? `/dashboard/locations/${locationId}`;

  // Delete confirmation
  const [confirmDelete, setConfirmDelete] = useState(false);

  const weeks = futureMondays(6);
  const roleCount = new Set(template.slots.map((s) => s.role)).size;

  // ── Apply ──

  async function handleApplySingle(weekStart: string) {
    setBusy(true);
    setFeedback(null);
    const dayFilter = applyDayFilter.size > 0 ? [...applyDayFilter].sort() : undefined;
    const result = await applyTemplate(template.id, weekStart, false, dayFilter, autoAssignOnApply);
    if (result) {
      setFeedback({ type: "success", message: `Applied ${result.created_shift_count} shifts to week of ${formatDate(result.week_start_date)}.` });
      router.push(`${locationBasePath}?tab=schedule&week_start=${result.week_start_date}`);
      router.refresh();
    } else {
      setFeedback({ type: "error", message: "Failed to apply template." });
    }
    setBusy(false);
  }

  async function handleApplyRange() {
    if (selectedWeeks.size === 0) return;
    setBusy(true);
    setFeedback(null);
    const dayFilter = applyDayFilter.size > 0 ? [...applyDayFilter].sort() : undefined;
    const result = await applyTemplateRange(template.id, [...selectedWeeks].sort(), false, dayFilter, autoAssignOnApply);
    if (result) {
      setFeedback({
        type: result.weeks_failed > 0 ? "error" : "success",
        message: `${result.weeks_succeeded} of ${result.weeks_requested} weeks applied.${result.weeks_failed > 0 ? ` ${result.weeks_failed} failed.` : ""}`,
      });
      setSelectedWeeks(new Set());
      router.refresh();
    } else {
      setFeedback({ type: "error", message: "Failed to apply template range." });
    }
    setBusy(false);
  }

  function toggleWeek(week: string) {
    setSelectedWeeks((prev) => {
      const next = new Set(prev);
      if (next.has(week)) next.delete(week);
      else next.add(week);
      return next;
    });
  }

  // ── Edit ──

  async function handleSaveEdit() {
    const trimmedName = editName.trim();
    if (!trimmedName) return;
    setBusy(true);
    setFeedback(null);
    const result = await updateTemplate(template.id, {
      name: trimmedName,
      description: editDesc.trim() || undefined,
    });
    if (result) {
      setTemplate(result);
      onUpdated(result);
      setEditing(false);
      setFeedback({ type: "success", message: "Template updated." });
    } else {
      setFeedback({ type: "error", message: "Failed to update template." });
    }
    setBusy(false);
  }

  // ── Refresh ──

  async function handleRefresh() {
    if (!scheduleId) return;
    setBusy(true);
    setFeedback(null);
    const result = await refreshTemplate(template.id, scheduleId, template.keep_assignees);
    if (result) {
      setTemplate(result);
      onUpdated(result);
      setFeedback({ type: "success", message: `Refreshed with ${result.slot_count} slots from current schedule.` });
    } else {
      setFeedback({ type: "error", message: "Failed to refresh template." });
    }
    setBusy(false);
  }

  // ── Generate draft ──

  async function handleGenerateDraft(weekStart: string) {
    setBusy(true);
    setFeedback(null);
    const result = await generateDraft(template.id, weekStart);
    if (result) {
      setFeedback({
        type: "success",
        message: `Draft created: ${result.created_shift_count} shifts (${result.assigned_shift_count} assigned, ${result.open_shift_count} open).`,
      });
      router.push(`${locationBasePath}?tab=schedule&week_start=${result.week_start_date}`);
      router.refresh();
    } else {
      setFeedback({ type: "error", message: "Failed to generate draft." });
    }
    setBusy(false);
  }

  // ── Clone ──

  async function handleClone() {
    setBusy(true);
    setFeedback(null);
    const result = await cloneTemplate(template.id);
    if (result) {
      onCloned(result);
      setFeedback({ type: "success", message: `Cloned as "${result.name}".` });
    } else {
      setFeedback({ type: "error", message: "Failed to clone template." });
    }
    setBusy(false);
  }

  // ── Delete ──

  async function handleDelete() {
    setBusy(true);
    setFeedback(null);
    const ok = await deleteTemplate(template.id);
    if (ok) {
      onDeleted(template.id);
    } else {
      setFeedback({ type: "error", message: "Failed to delete template." });
      setConfirmDelete(false);
    }
    setBusy(false);
  }

  return (
    <div className="settings-card">
      <div
        className="settings-card-header"
        style={{ cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
        onClick={() => setExpanded(!expanded)}
      >
        <span>{template.name}</span>
        <span style={{ fontWeight: 400, textTransform: "none", letterSpacing: 0, fontSize: "0.75rem", display: "flex", alignItems: "center", gap: 8 }}>
          {template.slot_count} slots · {roleCount} role{roleCount !== 1 ? "s" : ""} · {template.keep_assignees ? "with assignees" : "open shifts"}
          {template.validation_summary && (
            <span style={{
              fontSize: "0.68rem",
              fontWeight: 600,
              padding: "1px 6px",
              borderRadius: 999,
              background: template.validation_summary.ready ? "rgba(39, 174, 96, 0.08)" : "rgba(191, 91, 57, 0.08)",
              color: template.validation_summary.ready ? "#1a7a42" : "var(--accent)",
            }}>
              {template.validation_summary.ready ? "Ready" : `${template.validation_summary.warning_count} warnings`}
            </span>
          )}
        </span>
      </div>

      {expanded && (
        <div className="settings-card-body">
          {/* Slot preview */}
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {DAY_LABELS.map((day, i) => {
              const daySlots = template.slots.filter((s) => s.day_of_week === i);
              return (
                <div key={day} style={{ minWidth: 90 }}>
                  <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
                    {day}
                  </div>
                  {daySlots.length === 0 ? (
                    <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>{"\u2014"}</div>
                  ) : (
                    daySlots.map((slot, j) => (
                      <div key={j} style={{ fontSize: "0.78rem", marginBottom: 2 }}>
                        <span style={{ fontWeight: 500 }}>{slot.role}</span>
                        <span style={{ color: "var(--muted)", marginLeft: 4 }}>
                          {slot.start_time.slice(0, 5)}{"\u2013"}{slot.end_time.slice(0, 5)}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              );
            })}
          </div>

          {/* Template management actions */}
          <div style={{ marginTop: 16, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <button
              className="button button-small"
              disabled={busy}
              onClick={() => { setEditingSlots(true); setEditing(false); setConfirmDelete(false); }}
            >
              Edit slots
            </button>
            <button
              className="button-secondary button-small"
              disabled={busy}
              onClick={() => { setEditing(!editing); setConfirmDelete(false); }}
            >
              {editing ? "Cancel rename" : "Rename"}
            </button>
            <button
              className="button-secondary button-small"
              disabled={busy}
              onClick={handleClone}
            >
              {busy ? "Cloning\u2026" : "Clone"}
            </button>
            {scheduleId && (
              <button
                className="button-secondary button-small"
                disabled={busy}
                onClick={handleRefresh}
              >
                {busy ? "Refreshing\u2026" : "Refresh from current week"}
              </button>
            )}
            {!confirmDelete ? (
              <button
                className="button-secondary button-small"
                disabled={busy}
                onClick={() => { setConfirmDelete(true); setEditing(false); }}
                style={{ color: "var(--accent)" }}
              >
                Delete
              </button>
            ) : (
              <>
                <span style={{ fontSize: "0.78rem", color: "var(--accent)" }}>Delete this template?</span>
                <button
                  className="button-secondary button-small"
                  disabled={busy}
                  onClick={handleDelete}
                  style={{ color: "var(--accent)" }}
                >
                  {busy ? "Deleting\u2026" : "Confirm delete"}
                </button>
                <button
                  className="button-secondary button-small"
                  disabled={busy}
                  onClick={() => setConfirmDelete(false)}
                >
                  Cancel
                </button>
              </>
            )}
          </div>

          {/* Inline edit form */}
          {editing && (
            <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              <label className="field">
                <span style={{ fontSize: "0.78rem" }}>Name</span>
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  style={{ fontSize: "0.85rem" }}
                />
              </label>
              <label className="field">
                <span style={{ fontSize: "0.78rem" }}>Description</span>
                <input
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  placeholder="Optional description"
                  style={{ fontSize: "0.85rem" }}
                />
              </label>
              <div>
                <button
                  className="button button-small"
                  disabled={busy || !editName.trim()}
                  onClick={handleSaveEdit}
                >
                  {busy ? "Saving\u2026" : "Save changes"}
                </button>
              </div>
            </div>
          )}

          {/* Day filter for apply */}
          <div style={{ marginTop: 16 }}>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>Apply days:</span>
              {DAY_LABELS.map((day, i) => (
                <button
                  key={day}
                  className={applyDayFilter.has(i) ? "button button-small" : "button-secondary button-small"}
                  onClick={() => {
                    setApplyDayFilter((prev) => {
                      const next = new Set(prev);
                      if (next.has(i)) next.delete(i);
                      else next.add(i);
                      return next;
                    });
                  }}
                  style={{ fontSize: "0.72rem", padding: "2px 8px" }}
                >
                  {day}
                </button>
              ))}
              {applyDayFilter.size > 0 && (
                <button
                  className="button-secondary button-small"
                  onClick={() => setApplyDayFilter(new Set())}
                  style={{ fontSize: "0.72rem", padding: "2px 8px" }}
                >
                  All days
                </button>
              )}
            </div>
          </div>

          {/* Auto-assign toggle */}
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.78rem", cursor: "pointer", marginTop: 8 }}>
            <input
              type="checkbox"
              checked={autoAssignOnApply}
              onChange={(e) => setAutoAssignOnApply(e.target.checked)}
              style={{ accentColor: "var(--brand)" }}
            />
            Auto-assign open shifts when applying
          </label>

          {/* Apply to single week */}
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: "0.78rem", fontWeight: 600, marginBottom: 8 }}>Apply to a week{applyDayFilter.size > 0 ? ` (${[...applyDayFilter].sort().map((d) => DAY_LABELS[d]).join(", ")} only)` : ""}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {weeks.map((week) => (
                <button
                  key={week}
                  className="button-secondary button-small"
                  disabled={busy}
                  onClick={() => handleApplySingle(week)}
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {formatDate(week)}
                </button>
              ))}
            </div>
          </div>

          {/* Multi-week rollout */}
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: "0.78rem", fontWeight: 600, marginBottom: 8 }}>Multi-week rollout</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
              {weeks.map((week) => (
                <label key={week} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.78rem", cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={selectedWeeks.has(week)}
                    onChange={() => toggleWeek(week)}
                    style={{ accentColor: "var(--brand)" }}
                  />
                  {formatDate(week)}
                </label>
              ))}
            </div>
            {selectedWeeks.size > 0 && (
              <button
                className="button button-small"
                disabled={busy}
                onClick={handleApplyRange}
              >
                {busy ? "Applying\u2026" : `Apply to ${selectedWeeks.size} week${selectedWeeks.size !== 1 ? "s" : ""}`}
              </button>
            )}
          </div>

          {/* Generate draft schedule */}
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: "0.78rem", fontWeight: 600, marginBottom: 8 }}>Generate draft schedule</div>
            <p style={{ fontSize: "0.75rem", color: "var(--muted)", margin: "0 0 8px" }}>
              Creates a new draft schedule from this template with auto-assigned workers.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {weeks.map((week) => (
                <button
                  key={week}
                  className="button-secondary button-small"
                  disabled={busy}
                  onClick={() => handleGenerateDraft(week)}
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {formatDate(week)}
                </button>
              ))}
            </div>
          </div>

          {feedback && <FeedbackBanner feedback={feedback} />}

          {template.source_week_start_date && (
            <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginTop: 8 }}>
              Created from week of {formatDate(template.source_week_start_date)}
            </div>
          )}
        </div>
      )}

      {/* Slot editor */}
      {editingSlots && (
        <div style={{ marginTop: 12 }}>
          <TemplateEditor
            template={template}
            onClose={() => setEditingSlots(false)}
            onTemplateChanged={(t) => {
              setTemplate(t);
              onUpdated(t);
            }}
          />
        </div>
      )}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────

function CreateBlankTemplateForm({
  locationId,
  onCreated,
}: {
  locationId: number;
  onCreated: (t: ScheduleTemplate) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setFeedback(null);
    const form = new FormData(e.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    if (!name) {
      setFeedback({ type: "error", message: "Template name is required." });
      setBusy(false);
      return;
    }
    const description = String(form.get("description") ?? "").trim() || undefined;
    const result = await createEmptyTemplate(locationId, { name, description });
    if (result) {
      onCreated(result);
      setOpen(false);
      setFeedback(null);
    } else {
      setFeedback({ type: "error", message: "Failed to create template." });
    }
    setBusy(false);
  }

  if (!open) {
    return (
      <button className="button-secondary button-small" onClick={() => setOpen(true)}>
        Create blank template
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", gap: 6, alignItems: "end", flexWrap: "wrap" }}>
      <label className="field" style={{ flex: "1 1 140px", minWidth: 0 }}>
        <span>Name</span>
        <input name="name" placeholder="e.g. Weekend Pattern" required style={{ fontSize: "0.85rem" }} />
      </label>
      <label className="field" style={{ flex: "1 1 180px", minWidth: 0 }}>
        <span>Description</span>
        <input name="description" placeholder="Optional" style={{ fontSize: "0.85rem" }} />
      </label>
      <div style={{ display: "flex", gap: 4, marginBottom: 1 }}>
        <button className="button button-small" type="submit" disabled={busy}>
          {busy ? "Creating\u2026" : "Create"}
        </button>
        <button className="button-secondary button-small" type="button" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      {feedback && <FeedbackBanner feedback={feedback} />}
    </form>
  );
}

export function TemplatePanel({ locationId, scheduleId, currentWeekStart, templates: initialTemplates, basePath }: TemplatePanelProps) {
  const [templates, setTemplates] = useState(initialTemplates);

  function handleSaved(t: ScheduleTemplate) {
    setTemplates((prev) => [t, ...prev]);
  }

  function handleUpdated(t: ScheduleTemplate) {
    setTemplates((prev) => prev.map((x) => (x.id === t.id ? t : x)));
  }

  function handleDeleted(id: number) {
    setTemplates((prev) => prev.filter((x) => x.id !== id));
  }

  function handleCloned(t: ScheduleTemplate) {
    setTemplates((prev) => [t, ...prev]);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Save current / create blank */}
      <div className="settings-card">
        <div className="settings-card-header">
          {scheduleId ? "Save current schedule as template" : "Create a template"}
        </div>
        <div className="settings-card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {scheduleId && (
            <SaveTemplateForm scheduleId={scheduleId} onSaved={handleSaved} />
          )}
          <CreateBlankTemplateForm locationId={locationId} onCreated={handleSaved} />
        </div>
      </div>

      {/* Existing templates */}
      {templates.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Saved templates ({templates.length})
          </div>
          {templates.map((t) => (
            <TemplateCard
              key={t.id}
              template={t}
              locationId={locationId}
              scheduleId={scheduleId}
              basePath={basePath}
              onUpdated={handleUpdated}
              onDeleted={handleDeleted}
              onCloned={handleCloned}
            />
          ))}
        </div>
      ) : !scheduleId ? (
        <div className="empty">
          <strong>No templates yet</strong>
          <div>Create a blank template and add slots, or save one from an existing schedule week.</div>
        </div>
      ) : null}
    </div>
  );
}
