import { notFound, redirect } from "next/navigation";

import { getLocationStatus } from "@/lib/api";
import { buildDashboardLocationPath } from "@/lib/dashboard-paths";

type LocationDetailPageRouteProps = {
  params: Promise<{ locationId: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function queryValue(value: string | string[] | undefined): string | undefined {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return typeof value[0] === "string" ? value[0] : undefined;
  }
  return undefined;
}

export default async function LocationDetailRoute({
  params,
  searchParams,
}: LocationDetailPageRouteProps) {
  const { locationId } = await params;
  const numericLocationId = Number(locationId);
  const query = searchParams ? await searchParams : {};

  if (!Number.isInteger(numericLocationId) || numericLocationId <= 0) {
    notFound();
  }

  const status = await getLocationStatus(numericLocationId);

  if (!status) {
    notFound();
  }

  const normalizedQuery = Object.fromEntries(
    Object.entries(query)
      .map(([key, value]) => [key, queryValue(value)] as const)
      .filter((entry): entry is [string, string] => Boolean(entry[1])),
  );

  redirect(buildDashboardLocationPath(status.location, normalizedQuery));
}
