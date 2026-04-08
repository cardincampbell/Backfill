import { notFound, redirect } from "next/navigation";

import Location from "@/components/dashboard/Location";
import { getLocationBoard, getWorkspace } from "@/lib/api/workspace";
import { buildSchedulerBasePathFromAny } from "@/lib/dashboard-paths";

export const dynamic = "force-dynamic";

export default async function LocationPage({
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

  const board = await getLocationBoard(location.business_id, location.location_id);
  if (board && !board.location_role_setup_required) {
    redirect(buildSchedulerBasePathFromAny(location));
  }

  return (
    <Location
      embeddedInShell
      location={location}
    />
  );
}
