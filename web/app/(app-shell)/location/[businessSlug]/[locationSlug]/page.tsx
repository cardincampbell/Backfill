import { notFound } from "next/navigation";

import Location from "@/components/dashboard/Location";
import { getWorkspace } from "@/lib/api/workspace";

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

  return (
    <Location
      embeddedInShell
      location={location}
    />
  );
}
