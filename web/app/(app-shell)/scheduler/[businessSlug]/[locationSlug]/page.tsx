import { notFound } from "next/navigation";

import Scheduler from "@/components/dashboard/Scheduler";
import { getWorkspace } from "@/lib/api/workspace";
import { buildDashboardLocationBasePathFromAny } from "@/lib/dashboard-paths";

export const dynamic = "force-dynamic";

export default async function SchedulerPage({
  params,
}: {
  params: Promise<{ businessSlug: string; locationSlug: string }>;
}) {
  const { businessSlug, locationSlug } = await params;
  const workspace = await getWorkspace();

  if (!workspace) {
    notFound();
  }

  const location = workspace.locations.find(
    (item) =>
      item.business_slug === businessSlug && item.location_slug === locationSlug,
  );

  if (!location) {
    notFound();
  }

  return (
    <Scheduler
      embeddedInShell
      location={location}
      backHref={buildDashboardLocationBasePathFromAny(location)}
    />
  );
}
