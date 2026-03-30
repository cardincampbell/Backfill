import { API_BASE_URL, apiFetch } from "./client";

export type PlaceSuggestion = {
  place_id: string;
  provider: string;
  label: string;
  name: string;
  resource_name?: string | null;
  secondary_text?: string | null;
  formatted_address?: string | null;
};

export type PlaceAutocompleteResponse = {
  query: string;
  provider: string;
  suggestions: PlaceSuggestion[];
};

export type PlaceAutocompleteResult =
  | { ok: true; data: PlaceAutocompleteResponse }
  | { ok: false; error: string };

export type PlaceDetailsResponse = {
  provider: string;
  place: PlaceSuggestion | null;
};

export async function autocompletePlaces(
  query: string,
  sessionToken?: string,
): Promise<PlaceAutocompleteResult> {
  const params = new URLSearchParams({ q: query });
  if (sessionToken) {
    params.set("session_token", sessionToken);
  }
  try {
    const response = await apiFetch(`${API_BASE_URL}/api/places/autocomplete?${params.toString()}`, {
      method: "GET",
      cache: "no-store",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      return {
        ok: false,
        error: payload?.detail ?? "Places autocomplete failed",
      };
    }
    return {
      ok: true,
      data: (await response.json()) as PlaceAutocompleteResponse,
    };
  } catch {
    return {
      ok: false,
      error: "Could not reach the places service",
    };
  }
}

export async function getPlaceDetails(
  placeId: string,
  sessionToken?: string,
): Promise<PlaceSuggestion | null> {
  const params = new URLSearchParams({ place_id: placeId });
  if (sessionToken) {
    params.set("session_token", sessionToken);
  }
  try {
    const response = await apiFetch(`${API_BASE_URL}/api/places/details?${params.toString()}`, {
      method: "GET",
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as PlaceDetailsResponse;
    return payload.place ?? null;
  } catch {
    return null;
  }
}
