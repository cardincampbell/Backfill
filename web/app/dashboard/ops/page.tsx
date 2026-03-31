import Link from "next/link";

import { AccountLocationsPanel } from "@/components/account-locations-panel";
import { EmptyState } from "@/components/empty-state";
import { getLocations } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DashboardLocationsPage() {
  const locations = await getLocations();

  return (
    <main className="section">
      {!locations.length ? (
        <>
          <div className="page-head">
            <span className="eyebrow">Your locations</span>
            <h1>No locations yet</h1>
            <p className="muted">
              Add a place now or open onboarding to create your first schedule workspace.
            </p>
          </div>
          <EmptyState
            title="Start with one location"
            body="Onboarding creates the first schedule workspace automatically. If you skipped it, add a place here instead."
          />
          <section className="section">
            <Link className="button" href="/onboarding">
              Open onboarding
            </Link>
          </section>
        </>
      ) : null}
      <AccountLocationsPanel locations={locations} />
    </main>
  );
}
