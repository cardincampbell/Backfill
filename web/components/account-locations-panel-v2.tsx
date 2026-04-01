"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";

import { PlaceAutocomplete } from "@/components/place-autocomplete";
import type { PlaceSuggestion } from "@/lib/api/places";
import {
  createV2LocationFromPlace,
  deleteV2Location,
  inviteV2LocationManager,
  listV2LocationManagers,
  revokeV2LocationManager,
  revokeV2LocationManagerInvite,
  type V2ManagerAccessEntry,
  type V2Workspace,
} from "@/lib/api/v2-workspace";

type AccountLocationsPanelV2Props = {
  workspace: V2Workspace;
};

export function AccountLocationsPanelV2({
  workspace,
}: AccountLocationsPanelV2Props) {
  const router = useRouter();
  const businessOptions = useMemo(
    () =>
      workspace.businesses.map((business) => ({
        business_id: business.business_id,
        label: business.business_name,
        timezone: business.locations[0]?.timezone ?? "America/Los_Angeles",
      })),
    [workspace.businesses],
  );
  const defaultBusinessId = businessOptions[0]?.business_id ?? null;
  const [selectedBusinessId, setSelectedBusinessId] = useState<string | null>(
    defaultBusinessId,
  );
  const [addLocationValue, setAddLocationValue] = useState("");
  const [addLocationPlace, setAddLocationPlace] = useState<PlaceSuggestion | null>(null);
  const [addingLocation, setAddingLocation] = useState(false);
  const [addLocationError, setAddLocationError] = useState("");
  const [deletingLocationId, setDeletingLocationId] = useState<string | null>(null);
  const [expandedInviteLocationId, setExpandedInviteLocationId] = useState<string | null>(
    null,
  );
  const [membershipsByLocation, setMembershipsByLocation] = useState<
    Record<string, V2ManagerAccessEntry[]>
  >({});
  const [loadingMembershipLocationId, setLoadingMembershipLocationId] = useState<
    string | null
  >(null);
  const [revokingMembershipId, setRevokingMembershipId] = useState<string | null>(null);
  const [inviteDrafts, setInviteDrafts] = useState<
    Record<string, { email: string; manager_name: string }>
  >({});
  const [invitingLocationId, setInvitingLocationId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    if (selectedBusinessId || !defaultBusinessId) return;
    setSelectedBusinessId(defaultBusinessId);
  }, [defaultBusinessId, selectedBusinessId]);

  const selectedBusiness =
    businessOptions.find((option) => option.business_id === selectedBusinessId) ?? null;

  const sortedLocations = useMemo(
    () =>
      [...workspace.locations].sort((left, right) =>
        `${left.business_name} ${left.location_name}`.localeCompare(
          `${right.business_name} ${right.location_name}`,
        ),
      ),
    [workspace.locations],
  );

  async function handleAddLocation() {
    if (!selectedBusinessId || !addLocationPlace || addingLocation || isPending) {
      if (!addLocationPlace) {
        setAddLocationError("Search and select a real place first.");
      }
      return;
    }

    setAddingLocation(true);
    setAddLocationError("");
    setFeedback(null);

    try {
      const createdLocation = await createV2LocationFromPlace(
        selectedBusinessId,
        addLocationPlace,
        {
          timezone: selectedBusiness?.timezone,
        },
      );
      setAddLocationValue("");
      setAddLocationPlace(null);
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

  function handleDelete(location: (typeof workspace.locations)[number]) {
    if (deletingLocationId || isPending) return;
    const confirmed = window.confirm(
      `Delete ${location.location_name}? This only works for locations that do not already have operational data.`,
    );
    if (!confirmed) return;

    setDeletingLocationId(location.location_id);
    setFeedback(null);

    startTransition(async () => {
      try {
        await deleteV2Location(location.business_id, location.location_id);
        setFeedback({
          type: "success",
          message: `${location.location_name} was removed from your account.`,
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

  async function loadMemberships(
    businessId: string,
    locationId: string,
    force = false,
  ) {
    if (!force && membershipsByLocation[locationId]) {
      return;
    }
    setLoadingMembershipLocationId(locationId);
    try {
      const memberships = await listV2LocationManagers(businessId, locationId);
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

  function toggleInviteForm(location: (typeof workspace.locations)[number]) {
    setFeedback(null);
    const nextValue =
      expandedInviteLocationId === location.location_id ? null : location.location_id;
    setExpandedInviteLocationId(nextValue);
    if (nextValue === location.location_id) {
      void loadMemberships(location.business_id, location.location_id, true);
    }
  }

  function handleInviteFieldChange(
    locationId: string,
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

  function handleInvite(location: (typeof workspace.locations)[number]) {
    const draft = inviteDrafts[location.location_id];
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

    setInvitingLocationId(location.location_id);
    setFeedback(null);

    startTransition(async () => {
      try {
        const result = await inviteV2LocationManager(
          location.business_id,
          location.location_id,
          {
            email,
            manager_name: managerName || undefined,
          },
        );
        const accessLabel = result.created ? "was invited to" : "already has access to";
        setFeedback({
          type: "success",
          message: `${result.access.manager_email ?? email} ${accessLabel} ${location.location_name}.`,
        });
        setInviteDrafts((current) => ({
          ...current,
          [location.location_id]: { email: "", manager_name: "" },
        }));
        await loadMemberships(location.business_id, location.location_id, true);
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

  function handleRevoke(
    location: (typeof workspace.locations)[number],
    membership: V2ManagerAccessEntry,
  ) {
    if (!membership.id || membership.role === "owner" || revokingMembershipId || isPending) {
      return;
    }
    const label =
      membership.manager_name ||
      membership.manager_email ||
      membership.phone_e164 ||
      "this manager";
    const confirmed = window.confirm(
      `Remove ${label} from ${location.location_name}?`,
    );
    if (!confirmed) return;

    setRevokingMembershipId(membership.id);
    setFeedback(null);

    startTransition(async () => {
      try {
        if (membership.entry_kind === "invite") {
          await revokeV2LocationManagerInvite(
            location.business_id,
            location.location_id,
            membership.id,
          );
        } else {
          await revokeV2LocationManager(
            location.business_id,
            location.location_id,
            membership.id,
          );
        }
        setFeedback({
          type: "success",
          message: `${label} was removed from ${location.location_name}.`,
        });
        await loadMemberships(location.business_id, location.location_id, true);
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
                value={selectedBusinessId ?? defaultBusinessId ?? ""}
                onChange={(event) => setSelectedBusinessId(event.target.value)}
              >
                {businessOptions.map((option) => (
                  <option key={option.business_id} value={option.business_id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
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
              disabled={!selectedBusinessId || !addLocationPlace || addingLocation || isPending}
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
        {sortedLocations.map((location) => {
          const deleting = deletingLocationId === location.location_id;
          const memberships = membershipsByLocation[location.location_id] ?? [];
          const loadingMemberships = loadingMembershipLocationId === location.location_id;
          const pendingMemberships = memberships.filter(
            (membership) => membership.invite_status === "pending",
          );
          const activeMemberships = memberships.filter(
            (membership) => membership.invite_status === "active",
          );
          const inviteDraft = inviteDrafts[location.location_id] ?? {
            email: "",
            manager_name: "",
          };

          return (
            <article className="account-location-card" key={location.location_id}>
              <div className="account-location-card-main">
                <div className="account-location-card-copy">
                  <strong>{location.business_name}</strong>
                  <span>{location.location_name}</span>
                </div>
                <div className="account-location-card-meta">
                  <span>
                    {[
                      location.address_line_1,
                      location.locality,
                      location.region,
                      location.postal_code,
                    ]
                      .filter(Boolean)
                      .join(", ") || "No address yet"}
                  </span>
                </div>
              </div>

              <div className="account-location-card-actions">
                <button
                  className="button-secondary button-small"
                  disabled={invitingLocationId === location.location_id || isPending}
                  onClick={() => toggleInviteForm(location)}
                  type="button"
                >
                  {expandedInviteLocationId === location.location_id
                    ? "Close"
                    : "Invite manager"}
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

              {expandedInviteLocationId === location.location_id ? (
                <div className="account-location-invite">
                  <div className="account-location-invite-copy">
                    <strong>Add a manager to this location</strong>
                    <span>
                      Invited managers open the email invite, verify the phone number they
                      will use to sign in, and only enter profile details that are still
                      missing.
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
                              key={membership.id}
                            >
                              <div className="account-location-membership-copy">
                                <strong>
                                  {membership.manager_name ||
                                    membership.manager_email ||
                                    "Pending manager"}
                                </strong>
                                <span>{membership.manager_email ?? "Invite pending"}</span>
                              </div>
                              <div className="account-location-membership-actions">
                                <span
                                  className="account-location-membership-pill"
                                  data-tone="pending"
                                >
                                  Pending
                                </span>
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
                              key={membership.id}
                            >
                              <div className="account-location-membership-copy">
                                <strong>
                                  {membership.manager_name ||
                                    membership.manager_email ||
                                    membership.phone_e164}
                                </strong>
                                <span>
                                  {membership.manager_email ??
                                    membership.phone_e164 ??
                                    "Accepted manager"}
                                  {membership.phone_e164 ? ` · ${membership.phone_e164}` : ""}
                                </span>
                              </div>
                              <div className="account-location-membership-actions">
                                <span
                                  className="account-location-membership-pill"
                                  data-tone="active"
                                >
                                  {membership.role === "owner" ? "Owner" : "Manager"}
                                </span>
                                {membership.role !== "owner" ? (
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

                  <div className="account-location-invite-form">
                    <label className="field">
                      <span>Manager name (optional)</span>
                      <input
                        value={inviteDraft.manager_name}
                        onChange={(event) =>
                          handleInviteFieldChange(
                            location.location_id,
                            "manager_name",
                            event.target.value,
                          )
                        }
                        placeholder="Jordan Lead"
                      />
                    </label>
                    <label className="field">
                      <span>Email</span>
                      <input
                        type="email"
                        value={inviteDraft.email}
                        onChange={(event) =>
                          handleInviteFieldChange(
                            location.location_id,
                            "email",
                            event.target.value,
                          )
                        }
                        placeholder="manager@example.com"
                      />
                    </label>
                    <button
                      className="button"
                      disabled={invitingLocationId === location.location_id || isPending}
                      onClick={() => handleInvite(location)}
                      type="button"
                    >
                      {invitingLocationId === location.location_id
                        ? "Sending…"
                        : "Invite manager"}
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
