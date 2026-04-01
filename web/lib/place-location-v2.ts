import type { PlaceSuggestion } from "@/lib/api/places";
import { inferLocationName } from "@/lib/place-location";

function firstAddressLine(place: PlaceSuggestion): string | undefined {
  const raw = place.formatted_address?.trim();
  if (!raw) return undefined;
  return raw.split(",")[0]?.trim() || undefined;
}

export function buildV2LocationPayloadFromPlace(
  place: PlaceSuggestion,
  options?: {
    timezone?: string;
    settings?: Record<string, unknown>;
  },
) {
  return {
    name: inferLocationName(place),
    address_line_1: firstAddressLine(place),
    locality: place.city ?? undefined,
    region: place.state_region ?? undefined,
    postal_code: place.postal_code ?? undefined,
    country_code: place.country_code ?? "US",
    timezone: options?.timezone ?? "America/Los_Angeles",
    latitude: place.latitude ?? undefined,
    longitude: place.longitude ?? undefined,
    google_place_id: place.place_id,
    google_place_metadata: {
      provider: place.provider,
      place_id: place.place_id,
      resource_name: place.resource_name ?? null,
      display_name: place.name,
      brand_name: place.brand_name ?? null,
      location_label: place.location_label ?? null,
      formatted_address: place.formatted_address ?? null,
      primary_type: place.primary_type ?? null,
      primary_type_display_name: place.primary_type_display_name ?? null,
      business_status: place.business_status ?? null,
      national_phone_number: place.national_phone_number ?? null,
      international_phone_number: place.international_phone_number ?? null,
      website_uri: place.website_uri ?? null,
      google_maps_uri: place.google_maps_uri ?? null,
      utc_offset_minutes: place.utc_offset_minutes ?? null,
      rating: place.rating ?? null,
      user_rating_count: place.user_rating_count ?? null,
      neighborhood: place.neighborhood ?? null,
      sublocality: place.sublocality ?? null,
      types: place.types ?? [],
      address_components: place.address_components ?? [],
      regular_opening_hours: place.regular_opening_hours ?? {},
      plus_code: place.plus_code ?? {},
      metadata: place.metadata ?? {},
    },
    settings: options?.settings ?? {},
  };
}
