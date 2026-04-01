import Link from "next/link";
import { redirect } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { getV2Workspace } from "@/lib/api/v2-workspace";
import { buildDashboardLocationPathFromAny } from "@/lib/dashboard-paths";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const v2Workspace = await getV2Workspace();
  if (!v2Workspace) {
    redirect("/login");
  }

  if (!v2Workspace.locations.length) {
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
          body="Bootstrap your first business and location through onboarding."
        />
        <section className="section">
          <Link className="button" href="/onboarding">
            Open onboarding
          </Link>
        </section>
      </main>
    );
  }

  redirect(
    buildDashboardLocationPathFromAny(v2Workspace.locations[0], {
      tab: "schedule",
    }),
  );
}
