import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { getLocations } from "@/lib/api";
import { buildDashboardLocationPath } from "@/lib/dashboard-paths";

export const dynamic = "force-dynamic";

export default async function DashboardLocationsPage() {
  const locations = await getLocations();

  if (!locations.length) {
    return (
      <main className="section">
        <div className="page-head">
          <span className="eyebrow">Your locations</span>
          <h1>No locations yet</h1>
          <p className="muted">
            Once your first location is created, it will appear here and in your schedule workspace.
          </p>
        </div>
        <EmptyState
          title="Start with one location"
          body="Onboarding creates the first schedule workspace automatically. If you skipped it, open onboarding to create your first location."
        />
        <section className="section">
          <Link className="button" href="/onboarding">
            Open onboarding
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="section">
      <section className="page-head">
        <div>
          <span className="eyebrow">Your locations</span>
          <h1>Switch locations</h1>
          <p className="muted">
            Only locations attached to your operator access are shown here.
          </p>
        </div>
      </section>

      <section className="section">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Location</th>
                <th>Business</th>
                <th>Address</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {locations.map((location) => (
                <tr key={location.id}>
                  <td style={{ fontWeight: 600 }}>{location.name}</td>
                  <td>{location.organization_name ?? "Independent"}</td>
                  <td>{location.address ?? location.place_formatted_address ?? "\u2014"}</td>
                  <td style={{ textAlign: "right" }}>
                    <Link
                      className="button-secondary button-small"
                      href={buildDashboardLocationPath(location, { tab: "schedule" })}
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
