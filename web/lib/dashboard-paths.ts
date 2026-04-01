import type { Location } from "./types";

export type DashboardLocationRef = Pick<
  Location,
  "id" | "name" | "organization_name"
>;

export type DashboardLocationLike = {
  id?: string | number;
  location_id?: string;
  name?: string;
  location_name?: string;
  organization_name?: string | null;
  business_name?: string | null;
};

function getDashboardLocationId(location: DashboardLocationLike): string {
  if (location.location_id) return String(location.location_id);
  return String(location.id ?? "location");
}

function getDashboardLocationName(location: DashboardLocationLike): string {
  return location.location_name ?? location.name ?? "Location";
}

function getDashboardOrganizationName(location: DashboardLocationLike): string | null {
  return location.business_name ?? location.organization_name ?? null;
}

export function slugifySegment(
  value: string | null | undefined,
  fallback: string,
): string {
  const normalized = (value ?? "")
    .toLowerCase()
    .trim()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");
  return normalized || fallback;
}

export function buildDashboardLocationBasePath(
  location: DashboardLocationRef,
): string {
  return buildDashboardLocationBasePathFromAny(location);
}

export function buildDashboardLocationBasePathFromAny(
  location: DashboardLocationLike,
): string {
  const organizationSlug = slugifySegment(
    getDashboardOrganizationName(location),
    "independent-business",
  );
  const locationSlug = slugifySegment(
    getDashboardLocationName(location),
    `location-${getDashboardLocationId(location)}`,
  );
  return `/dashboard/${organizationSlug}/${locationSlug}`;
}

export function buildDashboardLocationPath(
  location: DashboardLocationRef,
  params?: Record<string, string | number | undefined | null>,
): string {
  return buildDashboardLocationPathFromAny(location, params);
}

export function buildDashboardLocationPathFromAny(
  location: DashboardLocationLike,
  params?: Record<string, string | number | undefined | null>,
): string {
  const basePath = buildDashboardLocationBasePathFromAny(location);
  if (!params) return basePath;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value == null || value === "") continue;
    query.set(key, String(value));
  }
  const qs = query.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

export function findLocationByDashboardSlugs(
  locations: DashboardLocationRef[],
  organizationSlug: string,
  locationSlug: string,
): DashboardLocationRef | null {
  return findLocationByDashboardSlugsFromAny(
    locations,
    organizationSlug,
    locationSlug,
  );
}

export function findLocationByDashboardSlugsFromAny<T extends DashboardLocationLike>(
  locations: T[],
  organizationSlug: string,
  locationSlug: string,
): T | null {
  return (
    locations.find((location) => {
      return (
        slugifySegment(
          getDashboardOrganizationName(location),
          "independent-business",
        ) ===
          organizationSlug &&
        slugifySegment(
          getDashboardLocationName(location),
          `location-${getDashboardLocationId(location)}`,
        ) === locationSlug
      );
    }) ?? null
  );
}
