"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { API_BASE_URL, apiFetch } from "@/lib/api/client";
import {
  autocompletePlaces,
  getPlaceDetails,
  type PlaceAutocompleteOptions,
  type PlaceSuggestion,
} from "@/lib/api/places";
import {
  completeOnboardingProfile,
  getLocationManagerInvitePreview,
  requestLocationInviteAccess,
  type AuthResponse,
  type LocationManagerInvitePreview,
  verifyAccessCode,
} from "@/lib/api/auth";
import {
  getBrowserSessionToken,
  persistBrowserSessionToken,
} from "@/lib/auth/browser-session";
import {
  clearStoredPreviewPhone,
  getStoredPreviewPhone,
  storePreviewWorkspace,
} from "@/lib/auth/preview";
import { buildDashboardLocationPath } from "@/lib/dashboard-paths";

type StepId = "name" | "email" | "locations" | "phone" | "code";

const STEPS: StepId[] = ["name", "email", "locations"];
const INVITE_STEPS: StepId[] = ["name", "phone", "code"];

type AssignedLocation = {
  id: number;
  name: string;
  organization_name?: string | null;
  place_location_label?: string | null;
  place_formatted_address?: string | null;
  address?: string | null;
};

function newSessionToken(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function firstNameFrom(value: string): string {
  return value.trim().split(/\s+/)[0] || "there";
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function inferOrganizationName(place: PlaceSuggestion): string {
  return place.brand_name?.trim() || place.name.trim();
}

function inferLocationName(place: PlaceSuggestion): string {
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

function buildLocationPayloadFromPlace(
  place: PlaceSuggestion,
  {
    managerName,
    managerEmail,
    managerPhone,
    organizationId,
    organizationName,
    onboardingInfo,
  }: {
    managerName: string;
    managerEmail: string;
    managerPhone?: string;
    organizationId?: number;
    organizationName?: string;
    onboardingInfo: string;
  },
) {
  return {
    name: inferLocationName(place),
    address: place.formatted_address ?? undefined,
    organization_id: organizationId,
    organization_name: organizationId ? undefined : organizationName,
    manager_name: managerName,
    manager_email: managerEmail,
    manager_phone: managerPhone ?? undefined,
    scheduling_platform: "backfill_native",
    operating_mode: "backfill_shifts",
    backfill_shifts_enabled: true,
    backfill_shifts_launch_state: "enabled",
    onboarding_info: onboardingInfo,
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

function normalizeBrand(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function extractCity(place: PlaceSuggestion): string | null {
  if (place.city?.trim()) {
    return place.city.trim();
  }
  const parts = (place.formatted_address ?? "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length >= 2) return parts[1];
  return null;
}

function buildSiblingQuery(place: PlaceSuggestion): string | null {
  const city = extractCity(place);
  const brand = place.brand_name || place.name;
  if (!city) return brand || null;
  return `${brand} ${city}`;
}

function looksLikeSibling(
  primary: PlaceSuggestion,
  suggestion: PlaceSuggestion,
): boolean {
  const base = normalizeBrand(primary.brand_name || primary.name);
  const candidate = normalizeBrand(suggestion.brand_name || suggestion.name);
  if (!base || !candidate) return false;
  return candidate.includes(base) || base.includes(candidate);
}

function OnboardingPageBody() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchWrapRef = useRef<HTMLDivElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const inviteToken = searchParams.get("invite")?.trim() || null;

  const [stepIndex, setStepIndex] = useState(0);
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState("");
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneError, setPhoneError] = useState("");
  const [code, setCode] = useState("");
  const [requestId, setRequestId] = useState<number | null>(null);
  const [destination, setDestination] = useState("");
  const [searchValue, setSearchValue] = useState("");
  const [searchVisible, setSearchVisible] = useState(true);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [selectingPlaceId, setSelectingPlaceId] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<PlaceSuggestion[]>([]);
  const [searchError, setSearchError] = useState("");
  const [confirmedLocations, setConfirmedLocations] = useState<PlaceSuggestion[]>([]);
  const [assignedLocations, setAssignedLocations] = useState<AssignedLocation[]>([]);
  const [siblingSuggestions, setSiblingSuggestions] = useState<PlaceSuggestion[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [sessionToken, setSessionToken] = useState(() => newSessionToken());
  const [geoBias, setGeoBias] = useState<PlaceAutocompleteOptions | null>(null);
  const [sessionResolved, setSessionResolved] = useState(false);
  const [invitePreview, setInvitePreview] = useState<LocationManagerInvitePreview | null>(null);
  const [invitePreviewError, setInvitePreviewError] = useState("");
  const [invitePreviewLoading, setInvitePreviewLoading] = useState(false);

  const isEmailInviteFlow = Boolean(inviteToken);
  const activeSteps = isEmailInviteFlow
    ? INVITE_STEPS
    : assignedLocations.length > 0
      ? (["name", "email"] as StepId[])
      : STEPS;
  const isInviteCompletionFlow = assignedLocations.length > 0;
  const firstName = useMemo(() => firstNameFrom(name), [name]);
  const currentStep = activeSteps[stepIndex];
  const progress = ((stepIndex + 1) / activeSteps.length) * 100;
  const canContinueName = name.trim().length > 0;
  const canContinueEmail = isValidEmail(email);
  const canContinuePhone = phone.trim().length > 0;
  const canLaunch = confirmedLocations.length > 0 && !submitting;
  const addedSiblingIds = new Set(confirmedLocations.map((location) => location.place_id));

  useEffect(() => {
    let cancelled = false;

    async function resolveSession() {
      const token = getBrowserSessionToken();
      if (!token) {
        setSessionResolved(true);
        return;
      }

      try {
        const response = await apiFetch(`${API_BASE_URL}/api/auth/me`, {
          method: "GET",
        });
        if (!response.ok) {
          setSessionResolved(true);
          return;
        }
        const payload = (await response.json()) as AuthResponse;
        if (cancelled) return;
        if (!payload.onboarding_required && payload.locations.length > 0) {
          router.replace("/dashboard");
          return;
        }
        if (payload.onboarding_required && payload.locations.length > 0) {
          setAssignedLocations(
            payload.locations.map((location) => ({
              id: location.id,
              name: location.name,
              organization_name:
                typeof location.organization_name === "string"
                  ? location.organization_name
                  : null,
              place_location_label:
                typeof location.place_location_label === "string"
                  ? location.place_location_label
                  : null,
              place_formatted_address:
                typeof location.place_formatted_address === "string"
                  ? location.place_formatted_address
                  : null,
              address:
                typeof location.address === "string" ? location.address : null,
            })),
          );
        }
      } finally {
        if (!cancelled) {
          setSessionResolved(true);
        }
      }
    }

    void resolveSession();
    return () => {
      cancelled = true;
    };
  }, [router]);

  useEffect(() => {
    if (!inviteToken) {
      setInvitePreview(null);
      setInvitePreviewError("");
      return;
    }

    let cancelled = false;
    setInvitePreviewLoading(true);
    setInvitePreviewError("");

    void getLocationManagerInvitePreview(inviteToken)
      .then((preview) => {
        if (cancelled) return;
        setInvitePreview(preview);
        setEmail(preview.invite_email);
        if (preview.manager_name) {
          setName((current) => (current.trim() ? current : preview.manager_name ?? ""));
        }
      })
      .catch((error) => {
        if (cancelled) return;
        setInvitePreviewError(
          error instanceof Error ? error.message : "Could not load this invite",
        );
      })
      .finally(() => {
        if (!cancelled) {
          setInvitePreviewLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [inviteToken]);

  useEffect(() => {
    if (currentStep !== "locations" || !searchVisible) {
      return;
    }
    const trimmed = searchValue.trim();
    if (trimmed.length < 2) {
      setSearchResults([]);
      setSearchError("");
      setDropdownOpen(false);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      setLoadingSearch(true);
      setSearchError("");
      void autocompletePlaces(trimmed, sessionToken, geoBias ?? undefined).then((result) => {
        if (cancelled) return;
        setLoadingSearch(false);
        if (!result.ok) {
          setSearchResults([]);
          setSearchError(result.error);
          setDropdownOpen(true);
          return;
        }
        setSearchResults(result.data.suggestions.slice(0, 8));
        setDropdownOpen(true);
      });
    }, 200);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [currentStep, searchValue, searchVisible, sessionToken, geoBias]);

  useEffect(() => {
    if (currentStep !== "locations" || geoBias || typeof navigator === "undefined") {
      return;
    }
    if (!("geolocation" in navigator)) {
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setGeoBias({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          radiusMeters: 50000,
        });
      },
      () => {
        // Silent fallback to non-localized search.
      },
      {
        enableHighAccuracy: false,
        timeout: 5000,
        maximumAge: 5 * 60 * 1000,
      },
    );
  }, [currentStep, geoBias]);

  useEffect(() => {
    if (currentStep !== "locations") return;

    function handlePointerDown(event: MouseEvent) {
      if (
        searchWrapRef.current &&
        !searchWrapRef.current.contains(event.target as Node)
      ) {
        setDropdownOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setDropdownOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [currentStep]);

  async function loadSiblingSuggestions(primary: PlaceSuggestion) {
    const query = buildSiblingQuery(primary);
    if (!query) {
      setSiblingSuggestions([]);
      return;
    }
    const siblingToken = newSessionToken();
    const result = await autocompletePlaces(query, siblingToken, geoBias ?? undefined);
    if (!result.ok) {
      setSiblingSuggestions([]);
      return;
    }
    const filtered = result.data.suggestions
      .filter((suggestion) => suggestion.place_id !== primary.place_id)
      .filter((suggestion) => looksLikeSibling(primary, suggestion))
      .slice(0, 6);
    setSiblingSuggestions(filtered);
  }

  async function resolvePlaceSuggestion(suggestion: PlaceSuggestion) {
    const details = await getPlaceDetails(suggestion.place_id, sessionToken);
    return details ?? suggestion;
  }

  async function confirmPlace(suggestion: PlaceSuggestion) {
    setSelectingPlaceId(suggestion.place_id);
    const resolved = await resolvePlaceSuggestion(suggestion);

    setConfirmedLocations((current) => {
      if (current.some((item) => item.place_id === resolved.place_id)) {
        return current;
      }
      return [...current, resolved];
    });

    if (confirmedLocations.length === 0) {
      void loadSiblingSuggestions(resolved);
    }

    setSearchValue("");
    setSearchResults([]);
    setSearchError("");
    setDropdownOpen(false);
    setSearchVisible(false);
    setSelectingPlaceId(null);
    setSessionToken(newSessionToken());
  }

  function removeConfirmedLocation(placeId: string) {
    setConfirmedLocations((current) => {
      const next = current.filter((item) => item.place_id !== placeId);
      if (next.length === 0) {
        setSiblingSuggestions([]);
        setSearchVisible(true);
        setDropdownOpen(false);
      }
      return next;
    });
  }

  async function addSibling(suggestion: PlaceSuggestion) {
    if (addedSiblingIds.has(suggestion.place_id)) {
      return;
    }
    const resolved = await resolvePlaceSuggestion(suggestion);
    setConfirmedLocations((current) => {
      if (current.some((item) => item.place_id === resolved.place_id)) {
        return current;
      }
      return [...current, resolved];
    });
  }

  async function addAllSiblings() {
    const existingIds = new Set(confirmedLocations.map((item) => item.place_id));
    const pending = siblingSuggestions.filter(
      (suggestion) => !existingIds.has(suggestion.place_id),
    );
    if (pending.length === 0) {
      return;
    }
    const resolved = await Promise.all(
      pending.map((suggestion) => resolvePlaceSuggestion(suggestion)),
    );
    setConfirmedLocations((current) => {
      const currentIds = new Set(current.map((item) => item.place_id));
      return [
        ...current,
        ...resolved.filter((place) => !currentIds.has(place.place_id)),
      ];
    });
  }

  function moveToEmail() {
    if (!canContinueName) {
      setNameError("Tell us your name to continue.");
      return;
    }
    setNameError("");
    setStepIndex(1);
  }

  async function handleEmailContinue() {
    if (!canContinueEmail) {
      setEmailError("Enter a valid email to continue.");
      return;
    }
    setEmailError("");
    if (isInviteCompletionFlow) {
      const token = getBrowserSessionToken();
      if (!token) {
        setSubmitError("Your session expired. Sign in again to finish setup.");
        return;
      }
      setSubmitting(true);
      setSubmitError("");
      try {
        await completeOnboardingProfile(token, name.trim(), email.trim());
        router.replace("/dashboard");
      } catch (error) {
        setSubmitError(
          error instanceof Error ? error.message : "Could not finish setup",
        );
        setSubmitting(false);
      }
      return;
    }
    setStepIndex(2);
    window.setTimeout(() => {
      searchInputRef.current?.focus();
    }, 120);
  }

  async function handlePhoneContinue() {
    if (!inviteToken) {
      return;
    }
    if (!phone.trim()) {
      setPhoneError("Enter the phone number you want to use for this location.");
      return;
    }
    if (!name.trim()) {
      setNameError("Tell us your name to continue.");
      setStepIndex(0);
      return;
    }

    setPhoneError("");
    setSubmitting(true);
    setSubmitError("");

    try {
      const result = await requestLocationInviteAccess(
        inviteToken,
        name.trim(),
        phone.trim(),
      );
      setRequestId(result.request_id);
      setDestination(result.destination);
      setCode("");
      setStepIndex(2);
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Could not send verification code",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleInviteCodeVerify() {
    if (!requestId || !code.trim()) {
      setSubmitError("Enter the verification code we texted you.");
      return;
    }

    setSubmitting(true);
    setSubmitError("");

    try {
      const result = await verifyAccessCode(requestId, code.trim());
      if (!result.session_token) {
        throw new Error("No session returned. Please try again.");
      }
      persistBrowserSessionToken(result.session_token);
      clearStoredPreviewPhone();
      router.replace("/dashboard");
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Could not verify this code",
      );
      setSubmitting(false);
    }
  }

  async function launchWorkspace() {
    if (!confirmedLocations.length) {
      setSubmitError("Choose at least one location to continue.");
      return;
    }

    setSubmitting(true);
    setSubmitError("");

    try {
      const previewPhone = getStoredPreviewPhone();
      const onboardingInfo = `${STEPS.length}-step onboarding · ${confirmedLocations.length} confirmed locations`;
      const hydratedLocations = await Promise.all(
        confirmedLocations.map((place) => resolvePlaceSuggestion(place)),
      );
      const primaryLocation = hydratedLocations[0];
      const organizationName = inferOrganizationName(primaryLocation);

      const primaryResponse = await apiFetch(`${API_BASE_URL}/api/locations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          buildLocationPayloadFromPlace(primaryLocation, {
            managerName: name.trim(),
            managerEmail: email.trim(),
            managerPhone: previewPhone ?? undefined,
            organizationName,
            onboardingInfo,
          }),
        ),
      });

      if (!primaryResponse.ok) {
        const payload = await primaryResponse.json().catch(() => null);
        throw new Error(payload?.detail ?? "Could not finish onboarding");
      }

      const location = (await primaryResponse.json()) as {
        id: number;
        name: string;
        organization_id?: number | null;
        organization_name?: string | null;
      };

      const bootstrapResponse = await apiFetch(
        `${API_BASE_URL}/api/locations/${location.id}/preview-bootstrap`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        },
      );

      if (!bootstrapResponse.ok) {
        const payload = await bootstrapResponse.json().catch(() => null);
        throw new Error(
          payload?.detail ?? "Could not prepare the preview workspace",
        );
      }

      const additionalLocations = hydratedLocations.slice(1);
      const createdLocationIds = [location.id];
      if (additionalLocations.length > 0) {
        const results = await Promise.allSettled(
          additionalLocations.map(async (locationChoice) => {
            const response = await apiFetch(`${API_BASE_URL}/api/locations`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(
                buildLocationPayloadFromPlace(locationChoice, {
                  managerName: name.trim(),
                  managerEmail: email.trim(),
                  managerPhone: previewPhone ?? undefined,
                  organizationId: location.organization_id ?? undefined,
                  organizationName,
                  onboardingInfo,
                }),
              ),
            });
            if (!response.ok) {
              return null;
            }
            const created = (await response.json()) as { id: number };
            return created.id;
          }),
        );
        for (const result of results) {
          if (result.status === "fulfilled" && typeof result.value === "number") {
            createdLocationIds.push(result.value);
          }
        }
      }

      storePreviewWorkspace({
        primaryLocationId: location.id,
        locationIds: createdLocationIds,
      });
      clearStoredPreviewPhone();
      router.replace(buildDashboardLocationPath(location, { tab: "schedule" }));
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Could not finish onboarding",
      );
      setSubmitting(false);
    }
  }

  return (
    <main className="lp-onboarding">
      <div className="ob-card">
        <div className="ob-header">
          <a href="/" className="ob-logo">
            Backfill
          </a>
          <span className="ob-step-label">
            {stepIndex + 1} OF {activeSteps.length}
          </span>
        </div>

        <div className="ob-progress-bar">
          <div className="ob-progress-fill" style={{ width: `${progress}%` }} />
        </div>

        <div className="ob-body">
          {currentStep === "name" ? (
            <div className="ob-step-pane">
              <p className="ob-question">What&apos;s your name?</p>
              <p className="ob-sub">
                {isEmailInviteFlow
                  ? "We’ll pair your name with this invite before we verify your phone."
                  : "First name is fine."}
              </p>
              {isEmailInviteFlow ? (
                invitePreviewLoading ? (
                  <p className="ob-sub">Loading your invite…</p>
                ) : invitePreviewError ? (
                  <p className="ob-error">{invitePreviewError}</p>
                ) : invitePreview ? (
                  <div className="ob-confirmed-list">
                    <div className="ob-confirmed-card">
                      <div className="ob-confirmed-check">✉</div>
                      <div className="ob-confirmed-info">
                        <strong>{invitePreview.location_name}</strong>
                        <span>
                          {invitePreview.business_name}
                          {invitePreview.location_address
                            ? ` · ${invitePreview.location_address}`
                            : ""}
                        </span>
                      </div>
                    </div>
                  </div>
                ) : null
              ) : null}
              <input
                className="ob-input ob-input-underline"
                type="text"
                placeholder="Marcus"
                autoFocus
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                  if (nameError) setNameError("");
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    moveToEmail();
                  }
                }}
                autoComplete="name"
              />
              {nameError ? <p className="ob-error">{nameError}</p> : <span />}
              <div className="ob-actions">
                <button
                  className="ob-btn-next"
                  onClick={moveToEmail}
                  disabled={!canContinueName || invitePreviewLoading || Boolean(invitePreviewError)}
                  type="button"
                >
                  Continue →
                </button>
                <span className="ob-btn-hint">or press Enter</span>
              </div>
            </div>
          ) : currentStep === "email" ? (
            <div className="ob-step-pane">
              <p className="ob-question">What&apos;s your email?</p>
              <p className="ob-sub">
                We&apos;ll use this for setup and account follow-up.
              </p>
              <input
                className="ob-input ob-input-underline"
                type="email"
                placeholder="marcus@business.com"
                autoFocus
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value);
                  if (emailError) setEmailError("");
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void handleEmailContinue();
                  }
                }}
                autoComplete="email"
                inputMode="email"
              />
              {emailError || submitError ? (
                <p className="ob-error">{emailError || submitError}</p>
              ) : (
                <span />
              )}
              {isInviteCompletionFlow ? (
                <div className="ob-confirmed-list">
                  {assignedLocations.map((location) => (
                    <div className="ob-confirmed-card" key={location.id}>
                      <div className="ob-confirmed-check">✓</div>
                      <div className="ob-confirmed-info">
                        <strong>
                          {location.place_location_label ?? location.name}
                        </strong>
                        <span>
                          {location.address ??
                            location.place_formatted_address ??
                            location.organization_name ??
                            "Assigned location"}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              <div className="ob-actions">
                <button
                  className="ob-btn-next"
                  onClick={() => {
                    void handleEmailContinue();
                  }}
                  disabled={!canContinueEmail || submitting || !sessionResolved}
                  type="button"
                >
                  {isInviteCompletionFlow
                    ? submitting
                      ? "Finishing…"
                      : "Finish setup →"
                    : "Continue →"}
                </button>
                <span className="ob-btn-hint">
                  {isInviteCompletionFlow
                    ? "We’ll attach your profile to your assigned locations."
                    : "or press Enter"}
                </span>
              </div>
            </div>
          ) : currentStep === "phone" ? (
            <div className="ob-step-pane">
              <p className="ob-question">What&apos;s your phone number?</p>
              <p className="ob-sub">
                We&apos;ll text a one-time code to finish access for
                {invitePreview ? ` ${invitePreview.location_name}` : " this location"}.
              </p>
              {invitePreview ? (
                <div className="ob-confirmed-list">
                  <div className="ob-confirmed-card">
                    <div className="ob-confirmed-check">✓</div>
                    <div className="ob-confirmed-info">
                      <strong>{invitePreview.invite_email}</strong>
                      <span>
                        {invitePreview.business_name}
                        {invitePreview.location_address
                          ? ` · ${invitePreview.location_address}`
                          : ""}
                      </span>
                    </div>
                  </div>
                </div>
              ) : null}
              <input
                className="ob-input ob-input-underline"
                type="tel"
                placeholder="(555) 123-4567"
                autoFocus
                value={phone}
                onChange={(event) => {
                  setPhone(event.target.value);
                  if (phoneError) setPhoneError("");
                  if (submitError) setSubmitError("");
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void handlePhoneContinue();
                  }
                }}
                autoComplete="tel"
                inputMode="tel"
              />
              {phoneError || submitError ? (
                <p className="ob-error">{phoneError || submitError}</p>
              ) : (
                <span />
              )}
              <div className="ob-actions">
                <button
                  className="ob-btn-next"
                  onClick={() => {
                    void handlePhoneContinue();
                  }}
                  disabled={!canContinuePhone || submitting || invitePreviewLoading || Boolean(invitePreviewError)}
                  type="button"
                >
                  {submitting ? "Sending…" : "Send code →"}
                </button>
                <span className="ob-btn-hint">or press Enter</span>
              </div>
            </div>
          ) : currentStep === "code" ? (
            <div className="ob-step-pane">
              <p className="ob-question">Enter your code</p>
              <p className="ob-sub">
                We texted a verification code to{" "}
                <strong>{destination || "your phone"}</strong>.
              </p>
              <input
                className="ob-input ob-input-underline"
                type="text"
                placeholder="123456"
                autoFocus
                value={code}
                onChange={(event) => {
                  setCode(event.target.value.replace(/\D/g, "").slice(0, 10));
                  if (submitError) setSubmitError("");
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void handleInviteCodeVerify();
                  }
                }}
                autoComplete="one-time-code"
                inputMode="numeric"
              />
              {submitError ? <p className="ob-error">{submitError}</p> : <span />}
              <div className="ob-actions">
                <button
                  className="ob-btn-next"
                  onClick={() => {
                    void handleInviteCodeVerify();
                  }}
                  disabled={!code.trim() || submitting || !requestId}
                  type="button"
                >
                  {submitting ? "Verifying…" : "Finish setup →"}
                </button>
                <span className="ob-btn-hint">or press Enter</span>
              </div>
            </div>
          ) : (
            <div className="ob-step-pane">
              <p className="ob-question">Where do you operate, {firstName}?</p>
              <p className="ob-sub">
                Search your first location. We&apos;ll pull in your business
                details, then show you any other locations that look like they
                belong to the same brand.
              </p>

              {confirmedLocations.length > 0 ? (
                <div className="ob-confirmed-list">
                  {confirmedLocations.map((place) => (
                    <div key={place.place_id} className="ob-confirmed-card">
                      <div className="ob-confirmed-check">✓</div>
                      <div className="ob-confirmed-info">
                        <strong>{inferLocationName(place)}</strong>
                        <span>
                          {place.formatted_address ?? "Custom typed location"}
                        </span>
                      </div>
                      <button
                        className="ob-confirmed-remove"
                        type="button"
                        onClick={() => removeConfirmedLocation(place.place_id)}
                        aria-label={`Remove ${place.name}`}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}

              {searchVisible ? (
                <div className="ob-search-wrap" ref={searchWrapRef}>
                  <div className="ob-search-icon">⌕</div>
                  <input
                    ref={searchInputRef}
                    className="ob-search-input"
                    type="text"
                    value={searchValue}
                    placeholder="Search your restaurant or address..."
                    onChange={(event) => {
                      setSearchValue(event.target.value);
                      setDropdownOpen(true);
                    }}
                    onFocus={() => {
                      if (searchValue.trim().length >= 2 || searchError) {
                        setDropdownOpen(true);
                      }
                    }}
                    autoComplete="off"
                    spellCheck={false}
                  />

                  {dropdownOpen &&
                  (loadingSearch || searchResults.length > 0 || searchError) ? (
                    <div className="ob-search-dropdown">
                      {loadingSearch ? (
                        <div className="ob-search-status">Searching locations…</div>
                      ) : searchError ? (
                        <div className="ob-search-status ob-search-status-error">
                          {searchError}
                        </div>
                      ) : (
                        searchResults.map((suggestion) => (
                          <button
                            key={suggestion.place_id}
                            type="button"
                            className="ob-search-option"
                            onMouseDown={(event) => {
                              event.preventDefault();
                              void confirmPlace(suggestion);
                            }}
                            disabled={Boolean(selectingPlaceId)}
                          >
                            <div className="ob-search-option-copy">
                              <strong>
                                {selectingPlaceId === suggestion.place_id
                                  ? "Selecting…"
                                  : inferLocationName(suggestion)}
                              </strong>
                              <span>
                                {suggestion.formatted_address ??
                                  suggestion.secondary_text ??
                                  "Typed location"}
                              </span>
                            </div>
                            {suggestion.primary_type_display_name ? (
                              <span className="ob-search-option-pill">
                                {suggestion.primary_type_display_name}
                              </span>
                            ) : null}
                          </button>
                        ))
                      )}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {siblingSuggestions.length > 0 ? (
                <div className="ob-sibling-block">
                  <div className="ob-sibling-head">
                    <div>
                      We found other locations that might be yours.
                      Add the ones that match.
                    </div>
                    {siblingSuggestions.filter(
                      (suggestion) => !addedSiblingIds.has(suggestion.place_id),
                    ).length >= 2 ? (
                      <button
                        className="ob-sibling-add-all"
                        type="button"
                        onClick={() => void addAllSiblings()}
                      >
                        Add all
                      </button>
                    ) : null}
                  </div>
                  <div className="ob-sibling-list">
                    {siblingSuggestions.map((suggestion) => {
                      const added = addedSiblingIds.has(suggestion.place_id);
                      return (
                        <div
                          key={suggestion.place_id}
                          className={`ob-sibling-row${added ? " added" : ""}`}
                        >
                          <div className="ob-sibling-copy">
                            <strong>{inferLocationName(suggestion)}</strong>
                            <span>
                              {suggestion.formatted_address ??
                                suggestion.secondary_text ??
                                "Suggested location"}
                            </span>
                          </div>
                          <button
                            className={`ob-sibling-add${added ? " done" : ""}`}
                            type="button"
                            onClick={() => void addSibling(suggestion)}
                            disabled={added}
                          >
                            {added ? "✓" : "+"}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                  <button
                    className="ob-sibling-manual"
                    type="button"
                    onClick={() => {
                      setSearchVisible(true);
                      setDropdownOpen(false);
                      setTimeout(() => {
                        searchInputRef.current?.focus();
                      }, 80);
                    }}
                  >
                    Can&apos;t find a location? Add manually →
                  </button>
                </div>
              ) : null}

              {confirmedLocations.length > 0 ? (
                <button
                  className="ob-add-another"
                  type="button"
                  onClick={() => {
                    setSearchVisible(true);
                    setTimeout(() => {
                      searchInputRef.current?.focus();
                    }, 80);
                  }}
                >
                  + Add another location
                </button>
              ) : null}

              <div className="ob-actions">
                <button
                  className="ob-btn-next"
                  onClick={() => void launchWorkspace()}
                  disabled={!canLaunch}
                  type="button"
                >
                  {submitting ? "Getting ready…" : "Let’s go →"}
                </button>
                <span className="ob-btn-hint">
                  Add more locations anytime from your dashboard.
                </span>
              </div>

              {submitError ? <p className="ob-error">{submitError}</p> : null}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

export default function OnboardingPage() {
  return (
    <Suspense
      fallback={
        <main className="lp-onboarding">
          <div className="ob-card">
            <div className="ob-header">
              <a href="/" className="ob-logo">
                Backfill
              </a>
            </div>
            <div className="ob-body">
              <div className="ob-step-pane">
                <p className="ob-question">Loading setup…</p>
              </div>
            </div>
          </div>
        </main>
      }
    >
      <OnboardingPageBody />
    </Suspense>
  );
}
