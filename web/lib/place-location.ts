import type { PlaceSuggestion } from "@/lib/api/places";

export function inferOrganizationName(place: PlaceSuggestion): string {
  return place.brand_name?.trim() || place.name.trim();
}

export function inferLocationName(place: PlaceSuggestion): string {
  const businessName = inferOrganizationName(place);
  const locationLabel = place.location_label?.trim();
  const rawName = place.name.trim();
  if (locationLabel) {
    return `${businessName} · ${locationLabel}`;
  }
  if (rawName && rawName.toLowerCase() !== businessName.toLowerCase()) {
    return rawName;
  }
  return businessName;
}

export function buildLocationPayloadFromPlace(
  place: PlaceSuggestion,
  {
    managerName,
    managerEmail,
    managerPhone,
    organizationId,
    organizationName,
    onboardingInfo,
  }: {
    managerName?: string;
    managerEmail?: string;
    managerPhone?: string;
    organizationId?: number;
    organizationName?: string;
    onboardingInfo?: string;
  },
) {
  return {
    name: inferLocationName(place),
    address: place.formatted_address ?? undefined,
    organization_id: organizationId,
    organization_name: organizationId ? undefined : organizationName,
    manager_name: managerName ?? undefined,
    manager_email: managerEmail ?? undefined,
    manager_phone: managerPhone ?? undefined,
    scheduling_platform: "backfill_native",
    operating_mode: "backfill_shifts",
    backfill_shifts_enabled: true,
    backfill_shifts_launch_state: "enabled",
    onboarding_info: onboardingInfo ?? undefined,
    place_provider: place.provider,
    place_id: place.place_id,
    place_resource_name: place.resource_name ?? undefined,
    place_display_name: place.name,
    place_brand_name: place.brand_name ?? inferOrganizationName(place),
    place_location_label: place.location_label ?? undefined,
    place_formatted_address: place.formatted_address ?? undefined,
    place_primary_type: place.primary_type ?? undefined,
    place_primary_type_display_name: place.primary_type_display_name ?? undefined,
    place_business_status: place.business_status ?? undefined,
    place_latitude: place.latitude ?? undefined,
    place_longitude: place.longitude ?? undefined,
    place_google_maps_uri: place.google_maps_uri ?? undefined,
    place_website_uri: place.website_uri ?? undefined,
    place_national_phone_number: place.national_phone_number ?? undefined,
    place_international_phone_number:
      place.international_phone_number ?? undefined,
    place_utc_offset_minutes: place.utc_offset_minutes ?? undefined,
    place_rating: place.rating ?? undefined,
    place_user_rating_count: place.user_rating_count ?? undefined,
    place_city: place.city ?? undefined,
    place_state_region: place.state_region ?? undefined,
    place_postal_code: place.postal_code ?? undefined,
    place_country_code: place.country_code ?? undefined,
    place_neighborhood: place.neighborhood ?? undefined,
    place_sublocality: place.sublocality ?? undefined,
    place_types: place.types ?? [],
    place_address_components: place.address_components ?? [],
    place_regular_opening_hours: place.regular_opening_hours ?? {},
    place_plus_code: place.plus_code ?? {},
    place_metadata: place.metadata ?? {},
  };
}
