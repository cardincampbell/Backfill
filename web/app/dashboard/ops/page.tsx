import Link from "next/link";
import { redirect } from "next/navigation";

import { AccountLocationsPanelV2 } from "@/components/account-locations-panel-v2";
import { EmptyState } from "@/components/empty-state";
import { getV2Workspace } from "@/lib/api/v2-workspace";

export const dynamic = "force-dynamic";

export default async function DashboardLocationsPage() {
  const v2Workspace = await getV2Workspace();
  if (!v2Workspace) {
    redirect("/login");
  }

  return (
    <main className="section">
      {!v2Workspace.locations.length ? (
        <>
          <div className="page-head">
            <span className="eyebrow">Your locations</span>
            <h1>No locations yet</h1>
            <p className="muted">
              Add your first location to start the workspace.
            </p>
          </div>
          <EmptyState
            title="Start with one location"
            body="Run onboarding or add a location directly here."
          />
          <section className="section">
            <Link className="button" href="/onboarding">
              Open onboarding
            </Link>
          </section>
        </>
      ) : null}
      <AccountLocationsPanelV2 workspace={v2Workspace} />
    </main>
  );
}
