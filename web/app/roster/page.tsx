import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { getLocations } from "@/lib/api";
import { buildDashboardLocationPath } from "@/lib/dashboard-paths";

export const dynamic = "force-dynamic";

export default async function RosterIndexPage() {
  const locations = await getLocations();

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Backfill Shifts</span>
        <h1>Roster</h1>
        <p>Select a location to manage its employee roster and enrollment status.</p>
      </div>

      {locations.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Location</th>
                <th>Employees</th>
                <th>Manager</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {locations.map((location) => (
                <tr key={location.id}>
                  <td style={{ fontWeight: 600 }}>
                    <Link
                      className="text-link"
                      href={buildDashboardLocationPath(location, { tab: "roster" })}
                    >
                      {location.name}
                    </Link>
                    {location.vertical && (
                      <div className="table-meta">
                        <div>{location.vertical}</div>
                      </div>
                    )}
                  </td>
                  <td>{location.employee_count ?? "Unknown"}</td>
                  <td>{location.manager_name ?? "Unassigned"}</td>
                  <td>
                    <div className="cta-row">
                      <Link
                        className="button-secondary button-small"
                        href={buildDashboardLocationPath(location, { tab: "roster" })}
                      >
                        Manage roster
                      </Link>
                      <Link
                        className="button-secondary button-small"
                        href={buildDashboardLocationPath(location, { tab: "imports" })}
                      >
                        Import CSV
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No locations yet"
          body="Create a location through onboarding or the API to start managing rosters."
        />
      )}
    </main>
  );
}
