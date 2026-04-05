import type { PlaceSuggestion } from "@/lib/api/places";

export function inferOrganizationName(place: PlaceSuggestion): string {
  return place.brand_name?.trim() || place.name.trim();
}

export function inferLocationName(place: PlaceSuggestion): string {
  const businessName = inferOrganizationName(place);
  const locationLabel = place.location_label?.trim();
  const rawName = place.name.trim();
  if (locationLabel) {
    const normalizedLabel = locationLabel.toLowerCase();
    if (rawName.toLowerCase().endsWith(normalizedLabel)) {
      return rawName;
    }
    if (businessName.toLowerCase().endsWith(normalizedLabel)) {
      return businessName;
    }
    return `${businessName} · ${locationLabel}`;
  }
  if (rawName && rawName.toLowerCase() !== businessName.toLowerCase()) {
    return rawName;
  }
  return businessName;
}

function firstAddressLine(place: PlaceSuggestion): string | undefined {
  const raw = place.formatted_address?.trim();
  if (!raw) return undefined;
  return raw.split(",")[0]?.trim() || undefined;
}

type LegacyLocationOptions = {
  managerName?: string;
  managerEmail?: string;
  managerPhone?: string;
  organizationId?: number;
  organizationName?: string;
  onboardingInfo?: string;
};

type WorkspaceLocationOptions = {
  timezone?: string;
  settings?: Record<string, unknown>;
};

function isWorkspaceLocationOptions(
  options: LegacyLocationOptions | WorkspaceLocationOptions | undefined,
): options is WorkspaceLocationOptions {
  if (!options) {
    return false;
  }
  return "timezone" in options || "settings" in options;
}

export function buildLocationPayloadFromPlace(
  place: PlaceSuggestion,
  options?: LegacyLocationOptions | WorkspaceLocationOptions,
) {
  const workspaceOptions = isWorkspaceLocationOptions(options) ? options : undefined;
  const basePayload = {
    name: inferLocationName(place),
    address_line_1: firstAddressLine(place),
    locality: place.city ?? undefined,
    region: place.state_region ?? undefined,
    postal_code: place.postal_code ?? undefined,
    country_code: place.country_code ?? "US",
    timezone:
      typeof workspaceOptions?.timezone === "string"
        ? workspaceOptions.timezone
        : "America/Los_Angeles",
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
    settings:
      workspaceOptions?.settings
        ? workspaceOptions.settings
        : {},
  };

  if (!options || workspaceOptions) {
    return basePayload;
  }

  const legacyOptions = options as LegacyLocationOptions;

  return {
    ...basePayload,
    address: place.formatted_address ?? undefined,
    organization_id: legacyOptions.organizationId,
    organization_name: legacyOptions.organizationId ? undefined : legacyOptions.organizationName,
    manager_name: legacyOptions.managerName ?? undefined,
    manager_email: legacyOptions.managerEmail ?? undefined,
    manager_phone: legacyOptions.managerPhone ?? undefined,
    scheduling_platform: "backfill_native",
    operating_mode: "backfill_shifts",
    backfill_shifts_enabled: true,
    backfill_shifts_launch_state: "enabled",
    onboarding_info: legacyOptions.onboardingInfo ?? undefined,
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
    place_international_phone_number: place.international_phone_number ?? undefined,
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
