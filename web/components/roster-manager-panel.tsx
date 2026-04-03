"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import {
  enrollEmployeeAtLocation,
  type WorkspaceBoard,
} from "@/lib/api/workspace";

type RoleRow = WorkspaceBoard["roles"][number];
type WorkerRow = WorkspaceBoard["workers"][number];

type RosterManagerPanelProps = {
  businessId: string;
  locationId: string;
  canManageTeam: boolean;
  roles: RoleRow[];
  workers: WorkerRow[];
};

type RosterDraft = {
  full_name: string;
  preferred_name: string;
  phone_e164: string;
  email: string;
  notes: string;
  role_ids: string[];
};

function defaultDraft(roleIds: string[]): RosterDraft {
  return {
    full_name: "",
    preferred_name: "",
    phone_e164: "",
    email: "",
    notes: "",
    role_ids: roleIds.length ? [roleIds[0]] : [],
  };
}

export function RosterManagerPanel({
  businessId,
  locationId,
  canManageTeam,
  roles,
  workers,
}: RosterManagerPanelProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [showCreate, setShowCreate] = useState(false);
  const [feedback, setFeedback] = useState<{
    tone: "success" | "error";
    message: string;
  } | null>(null);
  const [draft, setDraft] = useState<RosterDraft>(
    defaultDraft(roles.map((role) => role.role_id)),
  );

  const sortedWorkers = useMemo(
    () =>
      [...workers].sort((left, right) =>
        (left.preferred_name || left.full_name).localeCompare(
          right.preferred_name || right.full_name,
        ),
      ),
    [workers],
  );

  function toggleRole(roleId: string) {
    setDraft((current) => ({
      ...current,
      role_ids: current.role_ids.includes(roleId)
        ? current.role_ids.filter((item) => item !== roleId)
        : [...current.role_ids, roleId],
    }));
  }

  function resetDraft() {
    setDraft(defaultDraft(roles.map((role) => role.role_id)));
  }

  function handleCreate() {
    if (!draft.full_name.trim()) {
      setFeedback({ tone: "error", message: "Enter the team member’s name first." });
      return;
    }
    if (!draft.role_ids.length) {
      setFeedback({ tone: "error", message: "Assign at least one role." });
      return;
    }

    setFeedback(null);
    startTransition(async () => {
      try {
        const result = await enrollEmployeeAtLocation(businessId, {
          location_id: locationId,
          role_ids: draft.role_ids,
          full_name: draft.full_name.trim(),
          preferred_name: draft.preferred_name.trim() || null,
          phone_e164: draft.phone_e164.trim() || null,
          email: draft.email.trim().toLowerCase() || null,
          notes: draft.notes.trim() || null,
          employee_metadata: { source: "workspace" },
        });
        setFeedback({
          tone: "success",
          message: `${result.employee.full_name} was added to this location team.`,
        });
        setShowCreate(false);
        resetDraft();
        router.refresh();
      } catch (error) {
        setFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not add this team member.",
        });
      }
    });
  }

  return (
    <section className="settings-card manager-panel">
      <div className="settings-card-header">Team</div>
      <div className="settings-card-body">
        <div className="manager-panel-head">
          <div>
            <strong>Location roster</strong>
            <p>
              Build the same-location roster that powers Phase 1 coverage before you
              expand into cross-location supply.
            </p>
          </div>
          {canManageTeam ? (
            <button
              className={showCreate ? "button-secondary button-small" : "button button-small"}
              onClick={() => {
                setFeedback(null);
                setShowCreate((current) => !current);
              }}
              type="button"
            >
              {showCreate ? "Close" : "Add teammate"}
            </button>
          ) : null}
        </div>

        {!canManageTeam ? (
          <div className="account-locations-feedback" data-tone="error" role="status">
            Only owners and admins can add or edit team members right now.
          </div>
        ) : null}

        {showCreate && canManageTeam ? (
          <div className="manager-form-grid">
            <label className="field">
              <span>Full name</span>
              <input
                value={draft.full_name}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, full_name: event.target.value }))
                }
                placeholder="Jamie Rivera"
              />
            </label>
            <label className="field">
              <span>Preferred name</span>
              <input
                value={draft.preferred_name}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, preferred_name: event.target.value }))
                }
                placeholder="Jamie"
              />
            </label>
            <label className="field">
              <span>Phone</span>
              <input
                value={draft.phone_e164}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, phone_e164: event.target.value }))
                }
                placeholder="+15555550123"
              />
            </label>
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                value={draft.email}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, email: event.target.value }))
                }
                placeholder="jamie@example.com"
              />
            </label>
            <label className="field manager-form-span">
              <span>Roles at this location</span>
              <div className="role-chip-row">
                {roles.map((role) => {
                  const active = draft.role_ids.includes(role.role_id);
                  return (
                    <button
                      key={role.role_id}
                      className={active ? "button button-small" : "button-secondary button-small"}
                      onClick={() => toggleRole(role.role_id)}
                      type="button"
                    >
                      {role.role_name}
                    </button>
                  );
                })}
              </div>
            </label>
            <label className="field manager-form-span">
              <span>Notes</span>
              <textarea
                rows={3}
                value={draft.notes}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, notes: event.target.value }))
                }
                placeholder="Optional operator notes for this teammate."
              />
            </label>
            <div className="manager-panel-actions">
              <span className="muted">
                New teammates start with this location as their home location.
              </span>
              <button
                className="button button-small"
                disabled={isPending}
                onClick={handleCreate}
                type="button"
              >
                {isPending ? "Adding…" : "Add teammate"}
              </button>
            </div>
          </div>
        ) : null}

        {feedback ? (
          <div className="account-locations-feedback" data-tone={feedback.tone} role="status">
            {feedback.message}
          </div>
        ) : null}

        <div className="manager-list">
          {sortedWorkers.length ? (
            sortedWorkers.map((worker) => (
              <article key={worker.employee_id} className="account-location-card">
                <div className="account-location-card-main">
                  <div className="account-location-card-copy">
                    <strong>{worker.preferred_name || worker.full_name}</strong>
                    <span>{worker.role_names.join(" · ") || "No roles assigned"}</span>
                  </div>
                  <div className="account-location-card-meta">
                    <span>
                      {worker.email || worker.phone_e164 || "No contact info"}
                      {worker.can_blast_here ? " · blast-ready" : ""}
                    </span>
                  </div>
                </div>
              </article>
            ))
          ) : (
            <div className="empty">
              <div className="empty-mark">+</div>
              <div className="empty-title">No team members yet</div>
              <div className="empty-copy">
                Add the first teammate here so the coverage engine has eligible workers
                to target for this location.
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
