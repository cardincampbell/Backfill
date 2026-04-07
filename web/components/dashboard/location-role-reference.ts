"use client";

import { sourceDashboardLocations } from "./mock-data";

export type LocationReference = {
  color: string;
  logo: string;
  staffLabel: string;
  typeLabel: string;
};

export type LocationReferenceLike = {
  name: string;
  slug?: string | null;
  address_line_1?: string | null;
  locality?: string | null;
  region?: string | null;
  postal_code?: string | null;
  timezone?: string | null;
};

export function formatLocationMeta(location: LocationReferenceLike): string {
  return [
    location.address_line_1,
    location.locality,
    location.region,
    location.postal_code,
  ]
    .filter((value): value is string => Boolean(value))
    .join(", ");
}

export function getLocationReference(
  location: Pick<LocationReferenceLike, "name" | "slug">,
): LocationReference {
  const match =
    sourceDashboardLocations.find((item) => item.slug === location.slug) ??
    sourceDashboardLocations.find((item) => item.name === location.name);

  if (!match) {
    return {
      color: "#635BFF",
      logo: "📍",
      staffLabel: "Team configured in Backfill",
      typeLabel: "Location",
    };
  }

  return {
    color: match.color,
    logo: match.logo,
    staffLabel: `${match.totalStaff} staff`,
    typeLabel: match.type,
  };
}
