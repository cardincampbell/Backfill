import { notFound } from "next/navigation";

import { getV2Workspace } from "@/lib/api/v2-workspace";
import {
  buildDashboardLocationBasePathFromAny,
  findLocationByDashboardSlugsFromAny,
} from "@/lib/dashboard-paths";
import { renderV2LocationDetailPage } from "../../location-detail-v2";

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
  const v2Workspace = await getV2Workspace();

  if (!v2Workspace?.locations.length) {
    notFound();
  }

  const v2Location = findLocationByDashboardSlugsFromAny(
    v2Workspace.locations,
    organizationSlug,
    locationSlug,
  );

  if (!v2Location) {
    notFound();
  }

  return renderV2LocationDetailPage({
    workspace: v2Workspace,
    location: v2Location,
    query,
    basePath: buildDashboardLocationBasePathFromAny(v2Location),
  });
}
