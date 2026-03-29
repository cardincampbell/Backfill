"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { addWorkerToLocation } from "@/lib/shifts-api";

type AddEmployeeFormProps = {
  locationId: number;
  existingRoles: string[];
};

export function AddEmployeeForm({ locationId, existingRoles }: AddEmployeeFormProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSaving(true);
    setFeedback(null);

    const form = new FormData(e.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const phone = String(form.get("phone") ?? "").trim();
    const rolesRaw = String(form.get("roles") ?? "").trim();
    const roles = rolesRaw ? rolesRaw.split(",").map((r) => r.trim()).filter(Boolean) : [];

    if (!name || !phone) {
      setFeedback({ type: "error", message: "Name and phone are required." });
      setSaving(false);
      return;
    }

    try {
      const result = await addWorkerToLocation(locationId, { name, phone, roles });
      if (result) {
        setFeedback({ type: "success", message: `Added ${result.name}.` });
        setOpen(false);
        router.refresh();
      } else {
        setFeedback({ type: "error", message: "Failed to add employee." });
      }
    } catch {
      setFeedback({ type: "error", message: "An error occurred." });
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <div>
        <button className="button button-small" onClick={() => setOpen(true)}>
          Add employee
        </button>
        {feedback && (
          <div style={{
            fontSize: "0.82rem",
            marginTop: 8,
            padding: "8px 12px",
            borderRadius: "var(--radius-sm)",
            background: feedback.type === "success" ? "rgba(39, 174, 96, 0.04)" : "rgba(191, 91, 57, 0.04)",
            color: feedback.type === "success" ? "#1a7a42" : "var(--accent)",
          }}>
            {feedback.message}
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{
      padding: 20,
      borderRadius: "var(--radius-lg)",
      background: "var(--panel)",
      border: "1px solid var(--line)",
      boxShadow: "var(--shadow)",
      maxWidth: 520,
    }}>
      <div style={{ fontSize: "0.88rem", fontWeight: 600, marginBottom: 16 }}>
        Add employee
      </div>
      <form onSubmit={handleSubmit}>
        <div className="form-grid">
          <label className="field">
            <span>Name</span>
            <input name="name" placeholder="Full name" required />
          </label>
          <label className="field">
            <span>Phone</span>
            <input name="phone" type="tel" placeholder="+1 555-555-5555" required />
          </label>
          <label className="field field-span-2">
            <span>Roles</span>
            <input name="roles" list="existing-roles" placeholder="e.g. server, bartender" />
            <datalist id="existing-roles">
              {existingRoles.map((r) => (
                <option key={r} value={r} />
              ))}
            </datalist>
          </label>
        </div>
        <div className="cta-row" style={{ marginTop: 16 }}>
          <button className="button button-small" type="submit" disabled={saving}>
            {saving ? "Adding\u2026" : "Add"}
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
          <div style={{
            fontSize: "0.82rem",
            marginTop: 10,
            color: feedback.type === "error" ? "var(--accent)" : "#1a7a42",
          }}>
            {feedback.message}
          </div>
        )}
      </form>
    </div>
  );
}
