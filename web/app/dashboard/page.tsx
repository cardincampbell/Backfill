import { EmptyState } from "@/components/empty-state";
import { StatCard } from "@/components/stat-card";
import { getAuditLog, getRestaurants, getShifts, getSupportSnapshot } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const [{ summary, backendReachable }, restaurants, shifts, audits] = await Promise.all([
    getSupportSnapshot(),
    getRestaurants(),
    getShifts(),
    getAuditLog()
  ]);

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
      </div>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Recent shifts</h2>
            <p className="muted">Pulled from the FastAPI `/api/shifts` and `/api/dashboard` endpoints.</p>
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
                    <td>{shift.id}</td>
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
                    <th>Manager</th>
                    <th>Platform</th>
                  </tr>
                </thead>
                <tbody>
                  {restaurants.slice(0, 8).map((restaurant) => (
                    <tr key={restaurant.id}>
                      <td>{restaurant.name}</td>
                      <td>{restaurant.manager_name ?? "Unassigned"}</td>
                      <td>{restaurant.scheduling_platform ?? "backfill_native"}</td>
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
