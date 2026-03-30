import type { Location } from "./types";

export type DashboardLocationRef = Pick<
  Location,
  "id" | "name" | "organization_name"
>;

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
  const organizationSlug = slugifySegment(
    location.organization_name,
    "independent-business",
  );
  const locationSlug = slugifySegment(location.name, `location-${location.id}`);
  return `/dashboard/${organizationSlug}/${locationSlug}`;
}

export function buildDashboardLocationPath(
  location: DashboardLocationRef,
  params?: Record<string, string | number | undefined | null>,
): string {
  const basePath = buildDashboardLocationBasePath(location);
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
  return (
    locations.find((location) => {
      return (
        slugifySegment(location.organization_name, "independent-business") ===
          organizationSlug &&
        slugifySegment(location.name, `location-${location.id}`) === locationSlug
      );
    }) ?? null
  );
}
