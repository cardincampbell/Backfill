"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  updateLocationSettings,
  type LocationSettings,
} from "@/lib/api/workspace";

type LocationSettingsPanelProps = {
  businessId: string;
  locationId: string;
  settings: LocationSettings;
};

const LATE_POLICY_OPTIONS = [
  { value: "wait", label: "Wait for worker" },
  { value: "manager_action", label: "Queue for manager review" },
  { value: "start_coverage", label: "Start coverage immediately" },
] as const;

const MISSED_POLICY_OPTIONS = [
  { value: "manager_action", label: "Queue for manager review" },
  { value: "start_coverage", label: "Start coverage immediately" },
] as const;

export function LocationSettingsPanel({
  businessId,
  locationId,
  settings,
}: LocationSettingsPanelProps) {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const [managerApproval, setManagerApproval] = useState(
    settings.coverage_requires_manager_approval,
  );
  const [latePolicy, setLatePolicy] = useState(settings.late_arrival_policy);
  const [missedPolicy, setMissedPolicy] = useState(settings.missed_check_in_policy);
  const [agencyApproved, setAgencyApproved] = useState(settings.agency_supply_approved);
  const [writebackEnabled, setWritebackEnabled] = useState(settings.writeback_enabled);
  const [shiftsEnabled, setShiftsEnabled] = useState(settings.backfill_shifts_enabled);
  const [launchState, setLaunchState] = useState(settings.backfill_shifts_launch_state);

  const hasChanges =
    managerApproval !== settings.coverage_requires_manager_approval ||
    latePolicy !== settings.late_arrival_policy ||
    missedPolicy !== settings.missed_check_in_policy ||
    agencyApproved !== settings.agency_supply_approved ||
    writebackEnabled !== settings.writeback_enabled ||
    shiftsEnabled !== settings.backfill_shifts_enabled ||
    launchState !== settings.backfill_shifts_launch_state;

  async function handleSave() {
    setSaving(true);
    setFeedback(null);
    try {
      await updateLocationSettings(businessId, locationId, {
        coverage_requires_manager_approval: managerApproval,
        late_arrival_policy: latePolicy,
        missed_check_in_policy: missedPolicy,
        agency_supply_approved: agencyApproved,
        writeback_enabled: writebackEnabled,
        backfill_shifts_enabled: shiftsEnabled,
        backfill_shifts_launch_state: launchState,
      });
      setFeedback({ type: "success", message: "Settings saved." });
      router.refresh();
    } catch (error) {
      setFeedback({
        type: "error",
        message: error instanceof Error ? error.message : "Could not save settings.",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 18 }}>
      <div className="settings-card">
        <div className="settings-card-header">Coverage policies</div>
        <div className="settings-card-body">
          <label className="settings-toggle">
            <div>
              <div className="settings-toggle-label">Require manager approval for fills</div>
              <div className="settings-toggle-desc">
                Accepted offers stay in a review state until a manager confirms them.
              </div>
            </div>
            <input
              checked={managerApproval}
              className="settings-checkbox"
              onChange={(event) => setManagerApproval(event.target.checked)}
              type="checkbox"
            />
          </label>

          <div className="settings-field">
            <div className="settings-toggle-label">Late arrival response</div>
            <div className="settings-toggle-desc">
              Decide whether Backfill waits, surfaces a review item, or starts coverage.
            </div>
            <select
              className="settings-select"
              value={latePolicy}
              onChange={(event) =>
                setLatePolicy(
                  event.target.value as LocationSettings["late_arrival_policy"],
                )
              }
            >
              {LATE_POLICY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="settings-field">
            <div className="settings-toggle-label">Missed check-in response</div>
            <div className="settings-toggle-desc">
              Choose whether no-shows route to the manager or straight into coverage.
            </div>
            <select
              className="settings-select"
              value={missedPolicy}
              onChange={(event) =>
                setMissedPolicy(
                  event.target.value as LocationSettings["missed_check_in_policy"],
                )
              }
            >
              {MISSED_POLICY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="settings-card">
        <div className="settings-card-header">Operational settings</div>
        <div className="settings-card-body">
          <label className="settings-toggle">
            <div>
              <div className="settings-toggle-label">Agency supply approved</div>
              <div className="settings-toggle-desc">
                Let Backfill escalate into agency supply when internal coverage is exhausted.
              </div>
            </div>
            <input
              checked={agencyApproved}
              className="settings-checkbox"
              onChange={(event) => setAgencyApproved(event.target.checked)}
              type="checkbox"
            />
          </label>

          <label className="settings-toggle">
            <div>
              <div className="settings-toggle-label">Write-back enabled</div>
              <div className="settings-toggle-desc">
                Push accepted coverage outcomes back into the connected scheduling system.
              </div>
            </div>
            <input
              checked={writebackEnabled}
              className="settings-checkbox"
              onChange={(event) => setWritebackEnabled(event.target.checked)}
              type="checkbox"
            />
          </label>

          <label className="settings-toggle">
            <div>
              <div className="settings-toggle-label">Enable Backfill Shifts</div>
              <div className="settings-toggle-desc">
                Turn on native scheduling, publishing, and worker notifications for this location.
              </div>
            </div>
            <input
              checked={shiftsEnabled}
              className="settings-checkbox"
              onChange={(event) => setShiftsEnabled(event.target.checked)}
              type="checkbox"
            />
          </label>

          <div className="settings-field">
            <div className="settings-toggle-label">Launch state</div>
            <div className="settings-toggle-desc">
              Control whether this location is off, in beta, or fully live.
            </div>
            <div className="role-chip-row">
              {(["off", "beta", "live"] as const).map((state) => (
                <button
                  key={state}
                  className={
                    launchState === state ? "button button-small" : "button-secondary button-small"
                  }
                  onClick={() => setLaunchState(state)}
                  type="button"
                >
                  {state}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
      {feedback ? (
        <div className="account-locations-feedback" data-tone={feedback.type} role="status">
          {feedback.message}
        </div>
      ) : null}

      {hasChanges ? (
        <div className="manager-panel-actions">
          <span className="muted">These settings update the live location configuration.</span>
          <button className="button button-small" disabled={saving} onClick={handleSave} type="button">
            {saving ? "Saving…" : "Save settings"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
