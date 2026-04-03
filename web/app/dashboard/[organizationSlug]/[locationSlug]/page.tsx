import { notFound } from "next/navigation";

import { getWorkspace } from "@/lib/api/workspace";
import {
  buildDashboardLocationBasePathFromAny,
  findLocationByDashboardSlugsFromAny,
} from "@/lib/dashboard-paths";
import { renderLocationDetailPage } from "../../location-detail";

type DashboardLocationSlugRouteProps = {
  params: Promise<{ organizationSlug: string; locationSlug: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function DashboardLocationSlugRoute({
  params,
  searchParams,
}: DashboardLocationSlugRouteProps) {
  const { organizationSlug, locationSlug } = await params;
  const query = searchParams ? await searchParams : {};
  const workspace = await getWorkspace();

  if (!workspace?.locations.length) {
    notFound();
  }

  const location = findLocationByDashboardSlugsFromAny(
    workspace.locations,
    organizationSlug,
    locationSlug,
  );

  if (!location) {
    notFound();
  }

  return renderLocationDetailPage({
    workspace: workspace,
    location,
    query,
    basePath: buildDashboardLocationBasePathFromAny(location),
  });
}
