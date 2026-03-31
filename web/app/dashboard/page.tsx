import Link from "next/link";
import { redirect } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { getLocations } from "@/lib/api";
import { buildDashboardLocationPath } from "@/lib/dashboard-paths";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const locations = await getLocations();

  if (!locations.length) {
    return (
      <main className="section">
        <div className="workspace-shell-head">
          <div className="workspace-shell-head-copy">
            <h1>No locations yet</h1>
            <p>Create your first location to open the schedule workspace.</p>
          </div>
        </div>
        <EmptyState
          title="Start with one location"
          body="Onboarding creates the first schedule workspace automatically. If you skipped it, run setup to create a location."
        />
        <section className="section">
          <Link className="button" href="/onboarding">
            Open onboarding
          </Link>
        </section>
      </main>
    );
  }

  const latestLocation = locations.reduce((latest, location) =>
    location.id > latest.id ? location : latest,
  );

  redirect(buildDashboardLocationPath(latestLocation, { tab: "schedule" }));
}
