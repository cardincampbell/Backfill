import { notFound } from "next/navigation";

import { getLocations } from "@/lib/api";
import {
  buildDashboardLocationBasePath,
  findLocationByDashboardSlugs,
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
  const locations = await getLocations();
  const location = findLocationByDashboardSlugs(
    locations,
    organizationSlug,
    locationSlug,
  );

  if (!location) {
    notFound();
  }

  return renderLocationDetailPage({
    locationId: location.id,
    query,
    basePath: buildDashboardLocationBasePath(location),
  });
}
