"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";

import { PlaceAutocomplete } from "@/components/place-autocomplete";
import {
  createLocationFromPlace,
  deleteLocation,
  inviteLocationManager,
  listLocationManagers,
  revokeLocationManager,
  revokeLocationManagerInvite,
  type LocationManagerMembership,
} from "@/lib/api/locations";
import { buildDashboardLocationPath } from "@/lib/dashboard-paths";
import type { PlaceSuggestion } from "@/lib/api/places";
import type { Location } from "@/lib/types";

type AccountLocationsPanelProps = {
  locations: Location[];
};

export function AccountLocationsPanel({ locations }: AccountLocationsPanelProps) {
  const router = useRouter();
  const businessOptions = useMemo(() => {
    const seen = new Map<
      string,
      { key: string; label: string; organization_id?: number | null }
    >();
    for (const location of locations) {
      const label =
        location.organization_name ||
        location.place_brand_name ||
        "Your business";
      const key = location.organization_id ? `id:${location.organization_id}` : `name:${label}`;
      if (!seen.has(key)) {
        seen.set(key, {
          key,
          label,
          organization_id: location.organization_id ?? null,
        });
      }
    }
    return Array.from(seen.values());
  }, [locations]);
  const defaultBusinessKey = businessOptions[0]?.key ?? null;
  const [deletingLocationId, setDeletingLocationId] = useState<number | null>(null);
  const [invitingLocationId, setInvitingLocationId] = useState<number | null>(null);
  const [addingLocation, setAddingLocation] = useState(false);
  const [addLocationValue, setAddLocationValue] = useState("");
  const [addLocationPlace, setAddLocationPlace] = useState<PlaceSuggestion | null>(null);
  const [selectedBusinessKey, setSelectedBusinessKey] = useState<string | null>(
    defaultBusinessKey,
  );
  const [addLocationError, setAddLocationError] = useState("");
  const [expandedInviteLocationId, setExpandedInviteLocationId] = useState<number | null>(
    null,
  );
  const [membershipsByLocation, setMembershipsByLocation] = useState<
    Record<number, LocationManagerMembership[]>
  >({});
  const [loadingMembershipLocationId, setLoadingMembershipLocationId] = useState<number | null>(
    null,
  );
  const [revokingMembershipId, setRevokingMembershipId] = useState<number | null>(null);
  const [inviteDrafts, setInviteDrafts] = useState<
    Record<number, { email: string; manager_name: string }>
  >({});
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);
  const [isPending, startTransition] = useTransition();
  const selectedBusiness = useMemo(
    () =>
      businessOptions.find(
        (option) => option.key === (selectedBusinessKey ?? defaultBusinessKey),
      ) ?? null,
    [businessOptions, defaultBusinessKey, selectedBusinessKey],
  );

  useEffect(() => {
    if (selectedBusinessKey || !defaultBusinessKey) {
      return;
    }
    setSelectedBusinessKey(defaultBusinessKey);
  }, [defaultBusinessKey, selectedBusinessKey]);

  function handleDelete(location: Location) {
    if (deletingLocationId || isPending) return;
    const confirmed = window.confirm(
      `Delete ${location.name}? This only works for locations that do not already have operational data.`,
    );
    if (!confirmed) return;

    setDeletingLocationId(location.id);
    setFeedback(null);

    startTransition(async () => {
      try {
        await deleteLocation(location.id);
        setFeedback({
          type: "success",
          message: `${location.name} was removed from your account.`,
        });
        router.refresh();
      } catch (error) {
        setFeedback({
          type: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not remove this location.",
        });
      } finally {
        setDeletingLocationId(null);
      }
    });
  }

  async function handleAddLocation() {
    if (!addLocationPlace || addingLocation || isPending) {
      if (!addLocationPlace) {
        setAddLocationError("Search and select a real place first.");
      }
      return;
    }

    setAddingLocation(true);
    setAddLocationError("");
    setFeedback(null);

    try {
      const selectedBusinessOption =
        businessOptions.find(
          (option) => option.key === (selectedBusinessKey ?? defaultBusinessKey),
        ) ?? null;
      const createdLocation = await createLocationFromPlace(addLocationPlace, {
        organizationId: selectedBusinessOption?.organization_id ?? undefined,
        organizationName: selectedBusinessOption?.organization_id
          ? undefined
          : selectedBusinessOption?.label,
        onboardingInfo: "Added from logged-in locations page",
      });
      setAddLocationValue("");
      setAddLocationPlace(null);
      setSelectedBusinessKey(defaultBusinessKey);
      setFeedback({
        type: "success",
        message: `${createdLocation.name} was added to your locations.`,
      });
      router.refresh();
    } catch (error) {
      setAddLocationError(
        error instanceof Error ? error.message : "Could not add this location.",
      );
    } finally {
      setAddingLocation(false);
    }
  }

  function handleInviteFieldChange(
    locationId: number,
    field: "email" | "manager_name",
    value: string,
  ) {
    setInviteDrafts((current) => ({
      ...current,
      [locationId]: {
        email: current[locationId]?.email ?? "",
        manager_name: current[locationId]?.manager_name ?? "",
        [field]: value,
      },
    }));
  }

  function toggleInviteForm(locationId: number) {
    setFeedback(null);
    const nextValue = expandedInviteLocationId === locationId ? null : locationId;
    setExpandedInviteLocationId(nextValue);
    if (nextValue === locationId) {
      void loadMemberships(locationId, true);
    }
  }

  async function loadMemberships(locationId: number, force: boolean = false) {
    if (!force && membershipsByLocation[locationId]) {
      return;
    }
    setLoadingMembershipLocationId(locationId);
    try {
      const memberships = await listLocationManagers(locationId);
      setMembershipsByLocation((current) => ({
        ...current,
        [locationId]: memberships,
      }));
    } catch (error) {
      setFeedback({
        type: "error",
        message:
          error instanceof Error
            ? error.message
            : "Could not load manager access for this location.",
      });
    } finally {
      setLoadingMembershipLocationId(null);
    }
  }

  function handleInvite(location: Location) {
    const draft = inviteDrafts[location.id];
    const email = draft?.email?.trim().toLowerCase() ?? "";
    const managerName = draft?.manager_name?.trim() ?? "";

    if (!email || invitingLocationId || isPending) {
      if (!email) {
        setFeedback({
          type: "error",
          message: "Enter the invited manager's email first.",
        });
      }
      return;
    }

    setInvitingLocationId(location.id);
    setFeedback(null);

    startTransition(async () => {
      try {
        const result = await inviteLocationManager(location.id, {
          email,
          manager_name: managerName || undefined,
        });
        const accessLabel = result.created ? "was invited to" : "already has access to";
        setFeedback({
          type: "success",
          message: `${result.membership.manager_email ?? email} ${accessLabel} ${location.name}.`,
        });
        setInviteDrafts((current) => ({
          ...current,
          [location.id]: { email: "", manager_name: "" },
        }));
        await loadMemberships(location.id, true);
        router.refresh();
      } catch (error) {
        setFeedback({
          type: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not invite this manager.",
        });
      } finally {
        setInvitingLocationId(null);
      }
    });
  }

  function handleRevoke(location: Location, membership: LocationManagerMembership) {
    if (!membership.id || membership.role === "owner" || revokingMembershipId || isPending) {
      return;
    }
    const label =
      membership.manager_name ||
      membership.manager_email ||
      membership.phone ||
      "this manager";
    const confirmed = window.confirm(`Remove ${label} from ${location.name}?`);
    if (!confirmed) return;

    setRevokingMembershipId(membership.id);
    setFeedback(null);

    startTransition(async () => {
      try {
        if (membership.entry_kind === "invite") {
          await revokeLocationManagerInvite(location.id, membership.id as number);
        } else {
          await revokeLocationManager(location.id, membership.id as number);
        }
        setFeedback({
          type: "success",
          message: `${label} was removed from ${location.name}.`,
        });
        await loadMemberships(location.id, true);
        router.refresh();
      } catch (error) {
        setFeedback({
          type: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not remove this manager.",
        });
      } finally {
        setRevokingMembershipId(null);
      }
    });
  }

  return (
    <div className="account-locations-shell">
      <header className="account-locations-head">
        <h1>Locations</h1>
      </header>

      <section className="account-location-create">
        <div className="account-location-create-copy">
          <strong>Add location</strong>
          <span>Search a place and add it to one of your businesses.</span>
        </div>
        <div className="account-location-create-grid">
          {businessOptions.length > 1 ? (
            <label className="field account-location-create-business">
              <span>Business</span>
              <select
                value={selectedBusinessKey ?? defaultBusinessKey ?? ""}
                onChange={(event) => setSelectedBusinessKey(event.target.value)}
              >
                {businessOptions.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <div className="account-location-create-business-locked">
              <span className="field-label">Business</span>
              <strong>{selectedBusiness?.label ?? "New business"}</strong>
            </div>
          )}
          <div className="account-location-create-place">
            <span className="field-label">Location</span>
            <PlaceAutocomplete
              value={addLocationValue}
              selectedPlace={addLocationPlace}
              onInputChange={(value) => {
                setAddLocationValue(value);
                setAddLocationError("");
                if (addLocationPlace && value !== addLocationPlace.label) {
                  setAddLocationPlace(null);
                }
              }}
              onSelect={(place) => {
                setAddLocationPlace(place);
                setAddLocationValue(place.label);
                setAddLocationError("");
              }}
              placeholder="Search by business name or street address"
            />
          </div>
          <div className="account-location-create-actions">
            <button
              className="button"
              disabled={!addLocationPlace || addingLocation || isPending}
              onClick={() => {
                void handleAddLocation();
              }}
              type="button"
            >
              {addingLocation ? "Adding…" : "Add location"}
            </button>
          </div>
        </div>
        {addLocationError ? (
          <div className="account-locations-feedback" data-tone="error" role="status">
            {addLocationError}
          </div>
        ) : null}
      </section>

      {feedback ? (
        <div
          className="account-locations-feedback"
          data-tone={feedback.type}
          role="status"
        >
          {feedback.message}
        </div>
      ) : null}

      <div className="account-locations-list">
        {locations.map((location) => {
          const deleting = deletingLocationId === location.id;
          const inviting = invitingLocationId === location.id;
          const loadingMemberships = loadingMembershipLocationId === location.id;
          const inviteDraft = inviteDrafts[location.id] ?? { email: "", manager_name: "" };
          const memberships = membershipsByLocation[location.id] ?? [];
          const pendingMemberships = memberships.filter(
            (membership) => membership.invite_status === "pending",
          );
          const activeMemberships = memberships.filter(
            (membership) => membership.invite_status === "active",
          );
          const businessName =
            location.organization_name ??
            location.place_brand_name ??
            "Independent";

          return (
            <article className="account-location-card" key={location.id}>
              <div className="account-location-card-main">
                <div className="account-location-card-copy">
                  <Link
                    className="account-location-card-link"
                    href={buildDashboardLocationPath(location, { tab: "schedule" })}
                  >
                    <strong>{businessName}</strong>
                  </Link>
                  <span>{location.place_location_label ?? location.name}</span>
                </div>
                <div className="account-location-card-meta">
                  <span>{location.address ?? location.place_formatted_address ?? "No address yet"}</span>
                </div>
              </div>

              <div className="account-location-card-actions">
                <button
                  className="button-secondary button-small"
                  disabled={inviting || isPending}
                  onClick={() => toggleInviteForm(location.id)}
                  type="button"
                >
                  {expandedInviteLocationId === location.id ? "Close" : "Invite manager"}
                </button>
                <button
                  className="button-secondary button-small account-location-delete"
                  disabled={deleting || isPending}
                  onClick={() => handleDelete(location)}
                  type="button"
                >
                  {deleting ? "Removing…" : "Delete"}
                </button>
              </div>

              {expandedInviteLocationId === location.id ? (
                <div className="account-location-invite">
                  <div className="account-location-invite-copy">
                    <strong>Add a manager to this location</strong>
                    <span>
                      Invited managers open the email invite, enter their name and phone,
                      then verify a code before they can access this location.
                    </span>
                  </div>
                  <div className="account-location-membership-groups">
                    <div className="account-location-membership-group">
                      <div className="account-location-membership-head">
                        <strong>Pending invites</strong>
                      </div>
                      {loadingMemberships ? (
                        <span className="account-location-membership-empty">
                          Loading…
                        </span>
                      ) : pendingMemberships.length ? (
                        <div className="account-location-membership-list">
                          {pendingMemberships.map((membership) => (
                            <div
                              className="account-location-membership-row"
                              key={membership.id ?? membership.phone}
                            >
                              <div className="account-location-membership-copy">
                                <strong>
                                  {membership.manager_name || membership.manager_email || "Pending manager"}
                                </strong>
                                <span>
                                  {membership.manager_email ?? membership.phone ?? "Invite pending"}
                                  {membership.phone ? ` · ${membership.phone}` : ""}
                                </span>
                              </div>
                              <div className="account-location-membership-actions">
                                <span
                                  className="account-location-membership-pill"
                                  data-tone="pending"
                                >
                                  Pending
                                </span>
                                {membership.id ? (
                                  <button
                                    className="button-secondary button-small account-location-membership-revoke"
                                    disabled={
                                      revokingMembershipId === membership.id || isPending
                                    }
                                    onClick={() => handleRevoke(location, membership)}
                                    type="button"
                                  >
                                    {revokingMembershipId === membership.id
                                      ? "Removing…"
                                      : "Remove"}
                                  </button>
                                ) : null}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="account-location-membership-empty">
                          No pending invites.
                        </span>
                      )}
                    </div>

                    <div className="account-location-membership-group">
                      <div className="account-location-membership-head">
                        <strong>Accepted managers</strong>
                      </div>
                      {loadingMemberships ? null : activeMemberships.length ? (
                        <div className="account-location-membership-list">
                          {activeMemberships.map((membership) => (
                            <div
                              className="account-location-membership-row"
                              key={membership.id ?? membership.phone}
                            >
                              <div className="account-location-membership-copy">
                                <strong>
                                  {membership.manager_name || membership.manager_email || membership.phone}
                                </strong>
                                <span>
                                  {membership.manager_email || membership.phone}
                                </span>
                              </div>
                              <div className="account-location-membership-actions">
                                <span
                                  className="account-location-membership-pill"
                                  data-tone={membership.role === "owner" ? "owner" : "active"}
                                >
                                  {membership.role === "owner" ? "Owner" : "Manager"}
                                </span>
                                {membership.role !== "owner" && membership.id ? (
                                  <button
                                    className="button-secondary button-small account-location-membership-revoke"
                                    disabled={
                                      revokingMembershipId === membership.id || isPending
                                    }
                                    onClick={() => handleRevoke(location, membership)}
                                    type="button"
                                  >
                                    {revokingMembershipId === membership.id
                                      ? "Removing…"
                                      : "Remove"}
                                  </button>
                                ) : null}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="account-location-membership-empty">
                          No accepted managers yet.
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="account-location-invite-fields">
                    <label className="field">
                      <span>Manager name</span>
                      <input
                        autoComplete="name"
                        onChange={(event) =>
                          handleInviteFieldChange(
                            location.id,
                            "manager_name",
                            event.target.value,
                          )
                        }
                        placeholder="Optional"
                        type="text"
                        value={inviteDraft.manager_name}
                      />
                    </label>
                    <label className="field">
                      <span>Email</span>
                      <input
                        autoComplete="email"
                        onChange={(event) =>
                          handleInviteFieldChange(
                            location.id,
                            "email",
                            event.target.value,
                          )
                        }
                        placeholder="manager@business.com"
                        type="email"
                        value={inviteDraft.email}
                      />
                    </label>
                  </div>
                  <div className="account-location-invite-actions">
                    <button
                      className="button button-small"
                      disabled={inviting || isPending}
                      onClick={() => handleInvite(location)}
                      type="button"
                    >
                      {inviting ? "Inviting…" : "Send invite"}
                    </button>
                  </div>
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}
