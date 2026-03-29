"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createScheduleShift } from "@/lib/shifts-api";
import type { Worker } from "@/lib/types";

type AddShiftFormProps = {
  scheduleId: number;
  weekStartDate: string;
  workers: Worker[];
  roles: string[];
};

function weekDates(weekStart: string): { label: string; value: string }[] {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return days.map((label, i) => {
    const d = new Date(weekStart + "T00:00:00");
    d.setDate(d.getDate() + i);
    return { label: `${label} ${d.toISOString().slice(5, 10)}`, value: d.toISOString().slice(0, 10) };
  });
}

export function AddShiftForm({ scheduleId, weekStartDate, workers, roles }: AddShiftFormProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const dates = weekDates(weekStartDate);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSaving(true);
    setFeedback(null);

    const form = new FormData(e.currentTarget);
    const role = String(form.get("role") ?? "").trim();
    const date = String(form.get("date") ?? "");
    const startTime = String(form.get("start_time") ?? "");
    const endTime = String(form.get("end_time") ?? "");
    const workerIdStr = String(form.get("worker_id") ?? "");
    const workerId = workerIdStr ? Number(workerIdStr) : undefined;
    const notes = String(form.get("notes") ?? "").trim() || undefined;
    const startOffer = form.get("start_open_shift_offer") === "on";

    if (!role || !date || !startTime || !endTime) {
      setFeedback("Role, date, start time, and end time are required.");
      setSaving(false);
      return;
    }

    try {
      const result = await createScheduleShift(scheduleId, {
        role,
        date,
        start_time: startTime,
        end_time: endTime,
        worker_id: workerId ?? null,
        notes,
        start_open_shift_offer: startOffer || undefined,
      });
      if (result) {
        setFeedback(null);
        setOpen(false);
        router.refresh();
      } else {
        setFeedback("Failed to create shift.");
      }
    } catch {
      setFeedback("An error occurred.");
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <button className="button-secondary button-small" onClick={() => setOpen(true)}>
        + Add shift
      </button>
    );
  }

  return (
    <div style={{
      padding: 20,
      borderRadius: "var(--radius-lg)",
      background: "var(--panel)",
      border: "1px solid var(--line)",
      boxShadow: "var(--shadow)",
    }}>
      <div style={{ fontSize: "0.88rem", fontWeight: 600, marginBottom: 16 }}>
        Add a shift
      </div>
      <form onSubmit={handleSubmit}>
        <div className="form-grid">
          <label className="field">
            <span>Role</span>
            <input name="role" list="role-list" placeholder="e.g. server" required />
            <datalist id="role-list">
              {roles.map((r) => (
                <option key={r} value={r} />
              ))}
            </datalist>
          </label>
          <label className="field">
            <span>Date</span>
            <select name="date" required>
              {dates.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Start time</span>
            <input name="start_time" type="time" required />
          </label>
          <label className="field">
            <span>End time</span>
            <input name="end_time" type="time" required />
          </label>
          <label className="field">
            <span>Assign to</span>
            <select name="worker_id">
              <option value="">Open (unassigned)</option>
              {workers.map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Notes</span>
            <input name="notes" placeholder="Optional" />
          </label>
          <label className="settings-toggle" style={{ gridColumn: "1 / -1", padding: "4px 0" }}>
            <div>
              <div className="settings-toggle-label">Start open-shift offer</div>
              <div className="settings-toggle-desc">Immediately offer this shift to eligible workers via SMS.</div>
            </div>
            <input type="checkbox" name="start_open_shift_offer" className="settings-checkbox" />
          </label>
        </div>
        <div className="cta-row" style={{ marginTop: 16 }}>
          <button className="button button-small" type="submit" disabled={saving}>
            {saving ? "Creating\u2026" : "Create shift"}
          </button>
          <button
            className="button-secondary button-small"
            type="button"
            onClick={() => { setOpen(false); setFeedback(null); }}
          >
            Cancel
          </button>
        </div>
        {feedback && (
          <div style={{ fontSize: "0.82rem", marginTop: 10, color: "var(--accent)" }}>
            {feedback}
          </div>
        )}
      </form>
    </div>
  );
}
