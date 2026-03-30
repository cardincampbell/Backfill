import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { StatCard } from "@/components/stat-card";
import {
  getAuditLog,
  getCascades,
  getLocations,
  getShifts,
  getSupportSnapshot,
  getWorkers,
} from "@/lib/api";
import { buildDashboardLocationPath } from "@/lib/dashboard-paths";

export const dynamic = "force-dynamic";

function cascadeStatusPill(status: string): string {
  if (status === "active") return "pill pill-published";
  if (status === "completed") return "pill pill-success";
  if (status === "failed" || status === "expired") return "pill pill-failed";
  return "pill";
}

function shiftStatusPill(status: string): string {
  if (status === "filled" || status === "confirmed") return "pill pill-success";
  if (status === "vacant" || status === "open") return "pill pill-open";
  return "pill";
}

function syncHealthPill(
  state?: string | null,
): { label: string; className: string } {
  if (state === "healthy" || state === "connected") {
    return { label: state, className: "pill pill-success" };
  }
  if (state === "degraded" || state === "stale") {
    return { label: state, className: "pill pill-warning" };
  }
  if (state === "failed" || state === "disconnected") {
    return { label: state, className: "pill pill-failed" };
  }
  return { label: state ?? "not started", className: "pill" };
}

export default async function DashboardOpsPage() {
  const [{ summary, backendReachable }, locations, shifts, audits, cascades, workers] =
    await Promise.all([
      getSupportSnapshot(),
      getLocations(),
      getShifts(),
      getAuditLog(),
      getCascades(),
      getWorkers(),
    ]);

  const workerNames = new Map(workers.map((worker) => [worker.id, worker.name]));
  const shiftsById = new Map(shifts.map((shift) => [shift.id, shift]));
  const coverageRows = cascades
    .filter(
      (cascade) =>
        cascade.status === "active" ||
        (cascade.standby_queue?.length ?? 0) > 0 ||
        cascade.confirmed_worker_id,
    )
    .slice(0, 10);

  if (!backendReachable || !summary) {
    return (
      <main className="section">
        <div className="page-head">
          <span className="eyebrow">Ops index</span>
          <h1>Operations</h1>
        </div>
        <EmptyState
          title="Backend unavailable"
          body="Configure BACKFILL_API_BASE_URL to connect the dashboard to the API service."
        />
      </main>
    );
  }

  return (
    <main className="section">
      <section className="ops-hero">
        <div className="ops-hero-copy">
          <span className="eyebrow">Ops index</span>
          <h1>Cross-location operations.</h1>
          <p className="lede">
            Internal overview of location health, schedule risk, and live coverage activity.
          </p>
        </div>
        <div className="ops-hero-actions">
          <Link
            className="button"
            href={
              locations[0]
                ? buildDashboardLocationPath(locations[0], { tab: "schedule" })
                : "/setup/choose"
            }
          >
            {locations[0] ? "Open first location" : "Start setup"}
          </Link>
          <Link className="button-secondary" href="/setup/choose">
            Add location
          </Link>
        </div>
      </section>

      <div className="stat-grid stat-grid-wide">
        <StatCard label="Locations" value={summary.locations} hint="Active operating records" />
        <StatCard label="Workers" value={summary.workers} hint="Tracked labor pool" />
        <StatCard
          label="Vacant shifts"
          value={summary.shifts_vacant}
          hint="Unfilled or open coverage needs"
        />
        <StatCard
          label="Active cascades"
          value={summary.cascades_active}
          hint="Coverage runs in progress"
        />
        <StatCard
          label="Broadcasting"
          value={summary.broadcast_cascades_active}
          hint="Concurrent outreach"
        />
        <StatCard
          label="On standby"
          value={summary.workers_on_standby}
          hint="Ready reserve labor"
        />
      </div>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Coverage engine</h2>
            <p className="muted">Active and recent coverage runs.</p>
          </div>
        </div>
        {coverageRows.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Shift</th>
                  <th>Mode</th>
                  <th>Tier</th>
                  <th>Status</th>
                  <th>Confirmed</th>
                  <th>Standby</th>
                </tr>
              </thead>
              <tbody>
                {coverageRows.map((cascade) => {
                  const shift = shiftsById.get(cascade.shift_id);
                  const confirmedName = cascade.confirmed_worker_id
                    ? workerNames.get(cascade.confirmed_worker_id) ??
                      `#${cascade.confirmed_worker_id}`
                    : "\u2014";

                  return (
                    <tr key={cascade.id}>
                      <td style={{ fontWeight: 500 }}>
                        {shift ? (
                          <Link className="text-link" href={`/dashboard/shifts/${shift.id}`}>
                            {shift.role} · {shift.date}
                          </Link>
                        ) : (
                          `Shift #${cascade.shift_id}`
                        )}
                      </td>
                      <td>
                        <span className="pill">{cascade.outreach_mode}</span>
                      </td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>
                        Tier {cascade.current_tier}
                      </td>
                      <td>
                        <span className={cascadeStatusPill(cascade.status)}>
                          {cascade.status}
                        </span>
                      </td>
                      <td style={{ fontWeight: 500 }}>{confirmedName}</td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>
                        {cascade.standby_queue?.length ?? 0}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No coverage runs"
            body="Coverage state will appear here when shifts go vacant."
          />
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Recent shifts</h2>
            <p className="muted">Latest shift records across all locations.</p>
          </div>
        </div>
        {shifts.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Role</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Fill tier</th>
                </tr>
              </thead>
              <tbody>
                {shifts.slice(0, 12).map((shift) => (
                  <tr key={shift.id}>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>
                      <Link className="text-link" href={`/dashboard/shifts/${shift.id}`}>
                        {shift.id}
                      </Link>
                    </td>
                    <td style={{ fontWeight: 500 }}>{shift.role}</td>
                    <td>{shift.date}</td>
                    <td>
                      <span className={shiftStatusPill(shift.status)}>{shift.status}</span>
                    </td>
                    <td>{shift.fill_tier ?? "\u2014"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No shifts yet" body="Shifts appear here once created or synced." />
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Locations</h2>
            <p className="muted">Customer locations and integration health.</p>
          </div>
        </div>
        {locations.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Location</th>
                  <th>Platform</th>
                  <th>Health</th>
                  <th>Write-back</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {locations.slice(0, 10).map((location) => {
                  const health = syncHealthPill(
                    location.integration_state ?? location.integration_status,
                  );
                  return (
                    <tr key={location.id}>
                      <td>
                        <Link
                          className="text-link"
                          href={buildDashboardLocationPath(location, { tab: "schedule" })}
                          style={{ fontWeight: 600 }}
                        >
                          {location.name}
                        </Link>
                        <div
                          style={{
                            fontSize: "0.78rem",
                            color: "var(--muted)",
                            marginTop: 2,
                          }}
                        >
                          {location.manager_name ?? "No primary contact"} ·{" "}
                          {location.vertical ?? "unspecified"}
                        </div>
                      </td>
                      <td>
                        <span className="pill">
                          {location.scheduling_platform ?? "native"}
                        </span>
                      </td>
                      <td>
                        <span className={health.className}>{health.label}</span>
                      </td>
                      <td style={{ color: "var(--muted)" }}>
                        {location.writeback_enabled ? "Enabled" : "Off"}
                      </td>
                      <td>
                        <Link
                          className="button-secondary button-small"
                          href={buildDashboardLocationPath(location, { tab: "schedule" })}
                        >
                          View
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No locations yet"
            body="Create a location to start using Backfill."
          />
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Recent audit trail</h2>
            <p className="muted">Latest operational actions across the system.</p>
          </div>
        </div>
        {audits.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Entity</th>
                  <th>At</th>
                </tr>
              </thead>
              <tbody>
                {audits.slice(0, 12).map((audit) => (
                  <tr key={audit.id}>
                    <td style={{ fontWeight: 500 }}>{audit.action}</td>
                    <td>
                      {audit.entity_type} #{audit.entity_id}
                    </td>
                    <td>{new Date(audit.timestamp).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No audit history yet"
            body="Operational history will appear here once the system starts receiving activity."
          />
        )}
      </section>
    </main>
  );
}
