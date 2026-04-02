"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import { PlaceAutocomplete } from "@/components/place-autocomplete";
import type { PlaceSuggestion } from "@/lib/api/places";
import { buildDashboardLocationPathFromAny } from "@/lib/dashboard-paths";
import {
  createV2Business,
  createV2LocationFromPlace,
  deleteV2Location,
  inviteV2LocationManager,
  listV2LocationManagers,
  revokeV2LocationManager,
  revokeV2LocationManagerInvite,
  type V2ManagerAccessEntry,
  type V2Workspace,
  type V2WorkspaceBusiness,
  type V2WorkspaceLocation,
} from "@/lib/api/v2-workspace";

type AccountLocationsPanelV2Props = {
  workspace: V2Workspace;
};

function formatAddress(location: V2WorkspaceLocation): string {
  return [
    location.address_line_1,
    location.locality,
    location.region,
    location.postal_code,
  ]
    .filter(Boolean)
    .join(", ");
}

function roleLabel(role: string): string {
  return role.replace(/_/g, " ");
}

export function AccountLocationsPanelV2({
  workspace,
}: AccountLocationsPanelV2Props) {
  const router = useRouter();
  const businesses = useMemo(
    () =>
      [...workspace.businesses].sort((left, right) =>
        left.business_name.localeCompare(right.business_name),
      ),
    [workspace.businesses],
  );
  const [businessName, setBusinessName] = useState("");
  const [creatingBusiness, setCreatingBusiness] = useState(false);
  const [businessCreateError, setBusinessCreateError] = useState("");
  const [expandedAddLocationBusinessId, setExpandedAddLocationBusinessId] = useState<
    string | null
  >(null);
  const [addLocationValues, setAddLocationValues] = useState<Record<string, string>>({});
  const [addLocationPlaces, setAddLocationPlaces] = useState<
    Record<string, PlaceSuggestion | null>
  >({});
  const [addingLocationBusinessId, setAddingLocationBusinessId] = useState<string | null>(
    null,
  );
  const [addLocationErrors, setAddLocationErrors] = useState<Record<string, string>>({});
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

  async function handleCreateBusiness() {
    const trimmedName = businessName.trim();
    if (!trimmedName || creatingBusiness || isPending) {
      if (!trimmedName) {
        setBusinessCreateError("Enter a business name first.");
      }
      return;
    }

    setCreatingBusiness(true);
    setBusinessCreateError("");
    setFeedback(null);

    try {
      const created = await createV2Business({
        legal_name: trimmedName,
        brand_name: trimmedName,
        primary_email: workspace.user.email ?? undefined,
      });
      setBusinessName("");
      setExpandedAddLocationBusinessId(created.id);
      setFeedback({
        type: "success",
        message: `${created.brand_name ?? created.legal_name} is ready. Add a location to get it live.`,
      });
      router.refresh();
    } catch (error) {
      setBusinessCreateError(
        error instanceof Error ? error.message : "Could not create this business.",
      );
    } finally {
      setCreatingBusiness(false);
    }
  }

  function toggleBusinessLocationComposer(businessId: string) {
    setExpandedAddLocationBusinessId((current) =>
      current === businessId ? null : businessId,
    );
    setAddLocationErrors((current) => ({
      ...current,
      [businessId]: "",
    }));
  }

  async function handleAddLocation(business: V2WorkspaceBusiness) {
    const place = addLocationPlaces[business.business_id] ?? null;
    if (!place || addingLocationBusinessId || isPending) {
      if (!place) {
        setAddLocationErrors((current) => ({
          ...current,
          [business.business_id]: "Search and select a real place first.",
        }));
      }
      return;
    }

    setAddingLocationBusinessId(business.business_id);
    setAddLocationErrors((current) => ({
      ...current,
      [business.business_id]: "",
    }));
    setFeedback(null);

    try {
      const createdLocation = await createV2LocationFromPlace(
        business.business_id,
        place,
        {
          timezone:
            business.locations[0]?.timezone ?? "America/Los_Angeles",
        },
      );
      setAddLocationValues((current) => ({
        ...current,
        [business.business_id]: "",
      }));
      setAddLocationPlaces((current) => ({
        ...current,
        [business.business_id]: null,
      }));
      setExpandedAddLocationBusinessId(null);
      setFeedback({
        type: "success",
        message: `${createdLocation.name} was added to ${business.business_name}.`,
      });
      router.refresh();
    } catch (error) {
      setAddLocationErrors((current) => ({
        ...current,
        [business.business_id]:
          error instanceof Error ? error.message : "Could not add this location.",
      }));
    } finally {
      setAddingLocationBusinessId(null);
    }
  }

  function handleDelete(location: V2WorkspaceLocation) {
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
          message: `${location.location_name} was removed from ${location.business_name}.`,
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

  function toggleInviteForm(location: V2WorkspaceLocation) {
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

  function handleInvite(location: V2WorkspaceLocation) {
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
    location: V2WorkspaceLocation,
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
      <header className="workspace-shell-head account-locations-hero">
        <div className="workspace-shell-head-copy">
          <span className="workspace-shell-brand">Locations</span>
          <h1>Businesses and locations</h1>
          <p>
            One Backfill account can operate multiple businesses. Create a business
            shell, attach locations, then jump straight into schedule, team, or
            location settings from the same control surface.
          </p>
        </div>
        <div className="account-locations-summary">
          <div className="account-locations-summary-item">
            <span>Businesses</span>
            <strong>{businesses.length}</strong>
          </div>
          <div className="account-locations-summary-item">
            <span>Locations</span>
            <strong>{workspace.locations.length}</strong>
          </div>
          <div className="account-locations-summary-item">
            <span>Account</span>
            <strong>{workspace.user.primary_phone_e164 ?? "Phone sign-in"}</strong>
          </div>
        </div>
      </header>

      <section className="account-business-create">
        <div className="account-business-create-copy">
          <strong>Create a business</strong>
          <span>
            Add a new business first, then attach one or many locations beneath it.
          </span>
        </div>
        <div className="account-business-create-form">
          <label className="field">
            <span>Business name</span>
            <input
              onChange={(event) => {
                setBusinessName(event.target.value);
                setBusinessCreateError("");
              }}
              placeholder="Urth Caffe Pasadena"
              type="text"
              value={businessName}
            />
          </label>
          <button
            className="button"
            disabled={!businessName.trim() || creatingBusiness || isPending}
            onClick={() => {
              void handleCreateBusiness();
            }}
            type="button"
          >
            {creatingBusiness ? "Creating…" : "Create business"}
          </button>
        </div>
        {businessCreateError ? (
          <div className="account-locations-feedback" data-tone="error" role="status">
            {businessCreateError}
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

      <div className="account-business-stack">
        {businesses.length ? (
          businesses.map((business) => {
            const businessLocations = [...business.locations].sort((left, right) =>
              left.location_name.localeCompare(right.location_name),
            );
            const addLocationValue = addLocationValues[business.business_id] ?? "";
            const addLocationPlace = addLocationPlaces[business.business_id] ?? null;
            const addLocationError = addLocationErrors[business.business_id] ?? "";
            const showAddLocation = expandedAddLocationBusinessId === business.business_id;

            return (
              <section className="account-business-cluster" key={business.business_id}>
                <div className="account-business-cluster-head">
                  <div className="account-business-cluster-copy">
                    <span className="account-business-kicker">
                      {roleLabel(business.membership_role)} access
                    </span>
                    <h2>{business.business_name}</h2>
                    <p>
                      {business.location_count
                        ? `${business.location_count} ${
                            business.location_count === 1 ? "location" : "locations"
                          } live under this business.`
                        : "No locations yet. Add the first site to start operating this business."}
                    </p>
                  </div>
                  <div className="account-business-cluster-actions">
                    <button
                      className={showAddLocation ? "button button-small" : "button-secondary button-small"}
                      onClick={() => toggleBusinessLocationComposer(business.business_id)}
                      type="button"
                    >
                      {showAddLocation ? "Close" : "Add location"}
                    </button>
                  </div>
                </div>

                {showAddLocation ? (
                  <div className="account-business-location-create">
                    <div className="account-business-location-create-copy">
                      <strong>Add a location to {business.business_name}</strong>
                      <span>
                        Search the real place so we can prefill the address and keep the
                        dashboard URLs clean.
                      </span>
                    </div>
                    <div className="account-business-location-create-form">
                      <div className="account-location-create-place">
                        <span className="field-label">Location</span>
                        <PlaceAutocomplete
                          value={addLocationValue}
                          selectedPlace={addLocationPlace}
                          onInputChange={(value) => {
                            setAddLocationValues((current) => ({
                              ...current,
                              [business.business_id]: value,
                            }));
                            setAddLocationErrors((current) => ({
                              ...current,
                              [business.business_id]: "",
                            }));
                            if (addLocationPlace && value !== addLocationPlace.label) {
                              setAddLocationPlaces((current) => ({
                                ...current,
                                [business.business_id]: null,
                              }));
                            }
                          }}
                          onSelect={(place) => {
                            setAddLocationPlaces((current) => ({
                              ...current,
                              [business.business_id]: place,
                            }));
                            setAddLocationValues((current) => ({
                              ...current,
                              [business.business_id]: place.label,
                            }));
                            setAddLocationErrors((current) => ({
                              ...current,
                              [business.business_id]: "",
                            }));
                          }}
                          placeholder="Search by business name or street address"
                        />
                      </div>
                      <button
                        className="button"
                        disabled={
                          !addLocationPlace ||
                          addingLocationBusinessId === business.business_id ||
                          isPending
                        }
                        onClick={() => {
                          void handleAddLocation(business);
                        }}
                        type="button"
                      >
                        {addingLocationBusinessId === business.business_id
                          ? "Adding…"
                          : "Add location"}
                      </button>
                    </div>
                    {addLocationError ? (
                      <div
                        className="account-locations-feedback"
                        data-tone="error"
                        role="status"
                      >
                        {addLocationError}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {businessLocations.length ? (
                  <div className="account-business-location-grid">
                    {businessLocations.map((location) => {
                      const deleting = deletingLocationId === location.location_id;
                      const memberships = membershipsByLocation[location.location_id] ?? [];
                      const loadingMemberships =
                        loadingMembershipLocationId === location.location_id;
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
                      const scheduleHref = buildDashboardLocationPathFromAny(location, {
                        tab: "schedule",
                      });
                      const teamHref = buildDashboardLocationPathFromAny(location, {
                        tab: "roster",
                      });
                      const settingsHref = buildDashboardLocationPathFromAny(location, {
                        tab: "settings",
                      });

                      return (
                        <article
                          className="account-location-card account-location-card-rich"
                          key={location.location_id}
                        >
                          <div className="account-location-card-main">
                            <div className="account-location-card-copy">
                              <span className="account-location-card-kicker">
                                {location.location_name}
                              </span>
                              <strong>{location.business_name}</strong>
                            </div>
                            <div className="account-location-card-meta">
                              <span>{formatAddress(location) || "No address yet"}</span>
                            </div>
                          </div>

                          <div className="account-location-card-actions">
                            <Link className="button button-small" href={scheduleHref}>
                              Open schedule
                            </Link>
                            <Link className="button-secondary button-small" href={teamHref}>
                              Team
                            </Link>
                            <Link className="button-secondary button-small" href={settingsHref}>
                              Settings
                            </Link>
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
                                  Invited managers open the email invite, verify the phone
                                  number they will use to sign in, and only enter profile
                                  details that are still missing.
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
                                            <span>
                                              {membership.manager_email ?? "Invite pending"}
                                            </span>
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
                                                revokingMembershipId === membership.id ||
                                                isPending
                                              }
                                              onClick={() =>
                                                handleRevoke(location, membership)
                                              }
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
                                              {membership.phone_e164
                                                ? ` · ${membership.phone_e164}`
                                                : ""}
                                            </span>
                                          </div>
                                          <div className="account-location-membership-actions">
                                            <span
                                              className="account-location-membership-pill"
                                              data-tone="active"
                                            >
                                              {membership.role === "owner"
                                                ? "Owner"
                                                : "Manager"}
                                            </span>
                                            {membership.role !== "owner" ? (
                                              <button
                                                className="button-secondary button-small account-location-membership-revoke"
                                                disabled={
                                                  revokingMembershipId === membership.id ||
                                                  isPending
                                                }
                                                onClick={() =>
                                                  handleRevoke(location, membership)
                                                }
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
                                  disabled={
                                    invitingLocationId === location.location_id || isPending
                                  }
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
                ) : (
                  <div className="account-business-empty">
                    <strong>No locations yet</strong>
                    <span>
                      Add the first location for {business.business_name} to activate
                      schedule, coverage, team, and location settings URLs.
                    </span>
                  </div>
                )}
              </section>
            );
          })
        ) : (
          <section className="account-business-empty account-business-empty-root">
            <strong>No businesses yet</strong>
            <span>
              Start by creating your first business above. You can add locations
              immediately after.
            </span>
          </section>
        )}
      </div>
    </div>
  );
}
