"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { LocationSettings } from "@/lib/types";
import { updateLocationSettings, sendEnrollmentInvites } from "@/lib/shifts-api";

type LocationSettingsPanelProps = {
  settings: LocationSettings;
};

const POLICY_OPTIONS = {
  late_arrival: [
    { value: "wait", label: "Wait for worker" },
    { value: "manager_action", label: "Queue for manager review" },
    { value: "start_coverage", label: "Start coverage immediately" },
  ],
  missed_check_in: [
    { value: "manager_action", label: "Queue for manager review" },
    { value: "start_coverage", label: "Start coverage immediately" },
  ],
};

export function LocationSettingsPanel({ settings }: LocationSettingsPanelProps) {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [sendingInvites, setSendingInvites] = useState(false);

  const [managerApproval, setManagerApproval] = useState(settings.coverage_requires_manager_approval);
  const [latePolicy, setLatePolicy] = useState(settings.late_arrival_policy);
  const [missedPolicy, setMissedPolicy] = useState(settings.missed_check_in_policy);
  const [shiftsEnabled, setShiftsEnabled] = useState(settings.backfill_shifts_enabled ?? false);
  const [launchState, setLaunchState] = useState(settings.backfill_shifts_launch_state ?? "off");

  const hasChanges =
    managerApproval !== settings.coverage_requires_manager_approval ||
    latePolicy !== settings.late_arrival_policy ||
    missedPolicy !== settings.missed_check_in_policy ||
    shiftsEnabled !== (settings.backfill_shifts_enabled ?? false) ||
    launchState !== (settings.backfill_shifts_launch_state ?? "off");

  async function handleSave() {
    setSaving(true);
    setFeedback(null);
    const result = await updateLocationSettings(settings.location_id, {
      coverage_requires_manager_approval: managerApproval,
      late_arrival_policy: latePolicy,
      missed_check_in_policy: missedPolicy,
      backfill_shifts_enabled: shiftsEnabled,
      backfill_shifts_launch_state: launchState,
    });
    if (result) {
      setFeedback({ type: "success", message: "Settings saved." });
      router.refresh();
    } else {
      setFeedback({ type: "error", message: "Failed to save settings." });
    }
    setSaving(false);
  }

  async function handleSendInvites() {
    setSendingInvites(true);
    setFeedback(null);
    const result = await sendEnrollmentInvites(settings.location_id);
    if (result) {
      setFeedback({ type: "success", message: `Sent ${result.sent_count} enrollment invite(s).` });
    } else {
      setFeedback({ type: "error", message: "Failed to send invites." });
    }
    setSendingInvites(false);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Coverage policies */}
      <div className="settings-card">
        <div className="settings-card-header">Coverage policies</div>
        <div className="settings-card-body">
          <label className="settings-toggle">
            <div>
              <div className="settings-toggle-label">Require manager approval for fills</div>
              <div className="settings-toggle-desc">Workers who accept a shift must be approved by a manager before being confirmed.</div>
            </div>
            <input
              type="checkbox"
              checked={managerApproval}
              onChange={(e) => setManagerApproval(e.target.checked)}
              className="settings-checkbox"
            />
          </label>
        </div>
      </div>

      {/* Attendance policies */}
      <div className="settings-card">
        <div className="settings-card-header">Attendance policies</div>
        <div className="settings-card-body">
          <div className="settings-field">
            <div className="settings-toggle-label">Late arrival response</div>
            <div className="settings-toggle-desc">What happens when a worker reports running late.</div>
            <select
              value={latePolicy}
              onChange={(e) => setLatePolicy(e.target.value as LocationSettings["late_arrival_policy"])}
              className="settings-select"
            >
              {POLICY_OPTIONS.late_arrival.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div className="settings-field">
            <div className="settings-toggle-label">Missed check-in response</div>
            <div className="settings-toggle-desc">What happens when a worker doesn't check in at shift start.</div>
            <select
              value={missedPolicy}
              onChange={(e) => setMissedPolicy(e.target.value as LocationSettings["missed_check_in_policy"])}
              className="settings-select"
            >
              {POLICY_OPTIONS.missed_check_in.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Save */}
      {hasChanges && (
        <div className="cta-row">
          <button className="button" disabled={saving} onClick={handleSave}>
            {saving ? "Saving\u2026" : "Save changes"}
          </button>
        </div>
      )}

      {/* Backfill Shifts launch controls */}
      <div className="settings-card">
        <div className="settings-card-header">Backfill Shifts</div>
        <div className="settings-card-body">
          <label className="settings-toggle">
            <div>
              <div className="settings-toggle-label">Enable Backfill Shifts</div>
              <div className="settings-toggle-desc">Activate schedule publishing, worker notifications, and shift management for this location.</div>
            </div>
            <input
              type="checkbox"
              checked={shiftsEnabled}
              onChange={(e) => setShiftsEnabled(e.target.checked)}
              className="settings-checkbox"
            />
          </label>

          {shiftsEnabled && (
            <div className="settings-field" style={{ marginTop: 12 }}>
              <div className="settings-toggle-label">Launch state</div>
              <div className="settings-toggle-desc">Controls whether this location is in beta testing or fully live.</div>
              <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                {(["off", "beta", "live"] as const).map((state) => (
                  <button
                    key={state}
                    className={launchState === state ? "button button-small" : "button-secondary button-small"}
                    onClick={() => setLaunchState(state)}
                    style={{ fontSize: "0.72rem", padding: "2px 10px", textTransform: "capitalize" }}
                  >
                    {state}
                  </button>
                ))}
              </div>
            </div>
          )}

          {settings.backfill_shifts_beta_eligible && !shiftsEnabled && (
            <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginTop: 8 }}>
              This location is eligible for the Backfill Shifts beta.
            </div>
          )}
        </div>
      </div>

      {/* Enrollment */}
      <div className="settings-card">
        <div className="settings-card-header">Enrollment</div>
        <div className="settings-card-body">
          <div className="settings-field">
            <div className="settings-toggle-label">Send enrollment invites</div>
            <div className="settings-toggle-desc">Text SMS enrollment invites to all active, not-yet-enrolled employees at this location.</div>
            <div style={{ marginTop: 8 }}>
              <button className="button-secondary button-small" disabled={sendingInvites} onClick={handleSendInvites}>
                {sendingInvites ? "Sending\u2026" : "Send invites"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Context */}
      <div className="settings-card" style={{ opacity: 0.6 }}>
        <div className="settings-card-header">Platform</div>
        <div className="settings-card-body">
          <div style={{ fontSize: "0.85rem", display: "flex", flexDirection: "column", gap: 4 }}>
            <div>Platform: <strong>{settings.scheduling_platform ?? "backfill_native"}</strong></div>
            <div>Integration: <strong>{settings.integration_status ?? "n/a"}</strong></div>
            <div>Writeback: <strong>{settings.writeback_enabled ? "Enabled" : "Disabled"}</strong></div>
            <div>Agency supply: <strong>{settings.agency_supply_approved ? "Approved" : "Not approved"}</strong></div>
            {settings.timezone && <div>Timezone: <strong>{settings.timezone}</strong></div>}
          </div>
        </div>
      </div>

      {feedback && (
        <div style={{
          fontSize: "0.82rem",
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
