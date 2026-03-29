import type { RosterResponse, RosterWorker } from "@/lib/types";
import { EmptyState } from "./empty-state";
import { RosterWorkerActions } from "./roster-worker-actions";

type LocationOption = { id: number; name: string };

type RosterPanelProps = {
  roster: RosterResponse;
  locationId: number;
  locations?: LocationOption[];
};

function enrollmentPill(worker: RosterWorker): { label: string; className: string } {
  if (worker.enrollment_status === "enrolled") {
    return { label: "Enrolled", className: "pill pill-success" };
  }
  return { label: "Not enrolled", className: "pill" };
}

function statusPill(worker: RosterWorker): { label: string; className: string } {
  if (!worker.is_active_worker) {
    return { label: worker.employment_status ?? "Inactive", className: "pill pill-failed" };
  }
  if (!worker.is_active_at_location) {
    return { label: "Inactive here", className: "pill pill-warning" };
  }
  return { label: "Active", className: "pill pill-success" };
}

export function RosterPanel({ roster, locationId, locations = [] }: RosterPanelProps) {
  if (roster.workers.length === 0) {
    return (
      <EmptyState
        title="No employees yet"
        body="Import a roster CSV, add employees manually, or wait for the integration sync to populate this list."
      />
    );
  }

  const { summary } = roster;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Summary */}
      <div className="summary-bar">
        <div className="summary-bar-item">
          <strong>{summary.total_workers}</strong>
          <span>Total</span>
        </div>
        <div className="summary-bar-item">
          <strong>{summary.active_workers}</strong>
          <span>Active</span>
        </div>
        <div className="summary-bar-item">
          <strong>{summary.inactive_workers}</strong>
          <span>Inactive</span>
        </div>
        <div className="summary-bar-item">
          <strong>{summary.enrolled_workers}</strong>
          <span>Enrolled</span>
        </div>
      </div>

      {/* Table */}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Phone</th>
              <th>Roles</th>
              <th>Status</th>
              <th>Enrollment</th>
              <th>Priority</th>
              <th style={{ width: 160 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {roster.workers.map((worker) => {
              const enrollment = enrollmentPill(worker);
              const status = statusPill(worker);
              const assignmentRoles = worker.active_assignment?.roles ?? worker.roles ?? [];
              const priority = worker.active_assignment?.priority_rank ?? worker.priority_rank;
              return (
                <tr
                  key={worker.id}
                  style={!worker.is_active_at_location ? { opacity: 0.5 } : undefined}
                >
                  <td style={{ fontWeight: 600 }}>{worker.name}</td>
                  <td style={{ fontVariantNumeric: "tabular-nums" }}>{worker.phone}</td>
                  <td>{assignmentRoles.join(", ") || "\u2014"}</td>
                  <td>
                    <span className={status.className}>{status.label}</span>
                  </td>
                  <td>
                    <span className={enrollment.className}>{enrollment.label}</span>
                  </td>
                  <td style={{ fontVariantNumeric: "tabular-nums" }}>{priority}</td>
                  <td>
                    <RosterWorkerActions
                      workerId={worker.id}
                      isActive={worker.is_active_at_location}
                      locationId={locationId}
                      locations={locations}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
