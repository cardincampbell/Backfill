import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { StatCard } from "@/components/stat-card";
import { getAuditLog, getCascades, getRestaurants, getShifts, getSupportSnapshot, getWorkers } from "@/lib/api";

export const dynamic = "force-dynamic";

type DashboardPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function DashboardPage({ searchParams }: DashboardPageProps) {
  if (searchParams) {
    await searchParams;
  }

  const [{ summary, backendReachable }, restaurants, shifts, audits, cascades, workers] = await Promise.all([
    getSupportSnapshot(),
    getRestaurants(),
    getShifts(),
    getAuditLog(),
    getCascades(),
    getWorkers()
  ]);

  const workerNames = new Map(workers.map((worker) => [worker.id, worker.name]));
  const shiftsById = new Map(shifts.map((shift) => [shift.id, shift]));
  const coverageRows = cascades
    .filter((cascade) => cascade.status === "active" || (cascade.standby_queue?.length ?? 0) > 0 || cascade.confirmed_worker_id)
    .slice(0, 10);

  if (!backendReachable || !summary) {
    return (
      <main className="section">
        <div className="page-head">
          <h1>Restaurant dashboard</h1>
          <p>Support-layer visibility for Native Lite operators.</p>
        </div>
        <EmptyState
          title="No backend connection"
          body="This page expects a reachable FastAPI backend. Configure BACKFILL_API_BASE_URL for local or Vercel deployments."
        />
      </main>
    );
  }

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Native Lite</span>
        <h1>Restaurant dashboard</h1>
        <p>Active vacancies, cascade status, roster visibility, and recent operations.</p>
      </div>
      <div className="stat-grid">
        <StatCard label="Restaurants" value={summary.restaurants} />
        <StatCard label="Workers" value={summary.workers} />
        <StatCard label="Vacant shifts" value={summary.shifts_vacant} />
        <StatCard label="Active cascades" value={summary.cascades_active} />
        <StatCard label="Broadcast live" value={summary.broadcast_cascades_active} />
        <StatCard label="Workers on standby" value={summary.workers_on_standby} />
      </div>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Coverage engine</h2>
            <p className="muted">Mode, tier, confirmed worker, and standby depth for the most recent coverage runs.</p>
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
                    ? workerNames.get(cascade.confirmed_worker_id) ?? `Worker #${cascade.confirmed_worker_id}`
                    : "None yet";

                  return (
                    <tr key={cascade.id}>
                      <td>
                        {shift ? (
                          <Link className="text-link" href={`/dashboard/shifts/${shift.id}`}>
                            {shift.role} · {shift.date}
                          </Link>
                        ) : (
                          `Shift #${cascade.shift_id}`
                        )}
                      </td>
                      <td>{cascade.outreach_mode}</td>
                      <td>Tier {cascade.current_tier}</td>
                      <td><span className="pill">{cascade.status}</span></td>
                      <td>{confirmedName}</td>
                      <td>{cascade.standby_queue?.length ?? 0}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No coverage runs yet" body="Once a shift goes vacant, broadcast and standby state will appear here." />
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Recent shifts</h2>
            <p className="muted">Pulled from the FastAPI shift and dashboard endpoints.</p>
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
                    <td>
                      <Link className="text-link" href={`/dashboard/shifts/${shift.id}`}>
                        {shift.id}
                      </Link>
                    </td>
                    <td>{shift.role}</td>
                    <td>{shift.date}</td>
                    <td><span className="pill">{shift.status}</span></td>
                    <td>{shift.fill_tier ?? "Not filled yet"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No shifts yet" body="Create shifts through the API or phone flow and they will appear here." />
        )}
      </section>

      <section className="section">
        <div className="two-up">
          <div className="panel">
            <h3>Restaurants</h3>
            {restaurants.length ? (
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Platform</th>
                    <th>Sync health</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {restaurants.slice(0, 8).map((restaurant) => (
                    <tr key={restaurant.id}>
                      <td>
                        <Link className="text-link" href={`/dashboard/restaurants/${restaurant.id}`}>
                          {restaurant.name}
                        </Link>
                        <div className="table-meta">
                          <div>{restaurant.manager_name ?? "Unassigned manager"}</div>
                        </div>
                      </td>
                      <td>{restaurant.scheduling_platform ?? "backfill_native"}</td>
                      <td>
                          <span className="pill">{restaurant.integration_state ?? restaurant.integration_status ?? "not_started"}</span>
                        <div className="table-meta">
                          <div>Roster: {restaurant.last_roster_sync_status ?? "never"}</div>
                          <div>Schedule: {restaurant.last_schedule_sync_status ?? "never"}</div>
                          <div>Event reconcile: {restaurant.last_event_sync_at ?? "never"}</div>
                          <div>Write-back: {restaurant.writeback_enabled ? "enabled" : "core read-only"}</div>
                          {restaurant.last_sync_error ? <div>Error: {restaurant.last_sync_error}</div> : null}
                        </div>
                      </td>
                      <td>
                        <div className="action-stack">
                          <Link className="button-secondary button-small" href={`/dashboard/restaurants/${restaurant.id}`}>
                            View details
                          </Link>
                          <span className="muted">
                            {restaurant.scheduling_platform === "backfill_native"
                              ? "Native Lite only"
                              : "Auto-sync + queued reconcile"}
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState title="No restaurants" body="Add a restaurant in Native Lite to begin using the dashboard." />
            )}
          </div>

          <div className="panel">
            <h3>Recent audit log</h3>
            {audits.length ? (
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Action</th>
                    <th>Entity</th>
                  </tr>
                </thead>
                <tbody>
                  {audits.slice(0, 8).map((audit) => (
                    <tr key={audit.id}>
                      <td>{audit.timestamp}</td>
                      <td>{audit.action}</td>
                      <td>{audit.entity_type ?? "system"} #{audit.entity_id ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState title="No audit history" body="Audit rows appear here as shifts, vacancies, and outreach attempts occur." />
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
