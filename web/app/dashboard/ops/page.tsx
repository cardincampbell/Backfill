import Link from "next/link";

import { AccountLocationsPanel } from "@/components/account-locations-panel";
import { EmptyState } from "@/components/empty-state";
import { getLocations } from "@/lib/api";

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
      <AccountLocationsPanel locations={locations} />
    </main>
  );
}
