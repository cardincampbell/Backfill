"use client";

import { useEffect, useMemo, useState, useTransition, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { MapPin, Plus, Tag, X } from "lucide-react";

import type { BusinessLocation, BusinessRole } from "@/lib/api/businesses";
import {
  getEmployeeProfile,
  updateEmployee,
  type EmployeeProfile,
  type EmployeeSummary,
} from "@/lib/api/workforce";
import { getLocationReference } from "./location-role-reference";

type Feedback = {
  tone: "success" | "error";
  message: string;
} | null;

type EmployeeAssignmentState = {
  selectedRoleIds: string[];
  primaryRoleId: string;
  selectedLocationIds: string[];
  primaryLocationId: string;
};

type EmployeeAssignmentDrawerProps = {
  businessId: string;
  dark: boolean;
  employee: EmployeeSummary;
  locations: BusinessLocation[];
  onClose(): void;
  onSaved(nextEmployee: EmployeeProfile): Promise<void> | void;
  roles: BusinessRole[];
};

function employeeDisplayName(employee: Pick<EmployeeSummary, "full_name" | "preferred_name">) {
  return employee.preferred_name?.trim() || employee.full_name;
}

function employeeInitials(name: string) {
  return (
    name
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? "")
      .join("") || "BF"
  );
}

function locationDisplayName(location: BusinessLocation) {
  return location.display_name || location.name;
}

function buildAssignmentState(profile: EmployeeProfile): EmployeeAssignmentState {
  const selectedRoleIds = profile.roles.map((role) => role.role_id);
  const selectedLocationIds = profile.locations.map((location) => location.location_id);

  return {
    selectedRoleIds,
    primaryRoleId:
      profile.roles.find((role) => role.is_primary)?.role_id ?? selectedRoleIds[0] ?? "",
    selectedLocationIds,
    primaryLocationId:
      profile.locations.find((location) => location.is_primary)?.location_id ??
      selectedLocationIds[0] ??
      "",
  };
}

function buildAssignmentStateFromSummary(
  employee: EmployeeSummary,
  roles: BusinessRole[],
  locations: BusinessLocation[],
): EmployeeAssignmentState {
  const selectedRoleIds = roles
    .filter((role) => employee.role_ids.includes(role.id) || employee.role_names.includes(role.name))
    .map((role) => role.id);
  const selectedLocationIds = locations
    .filter((location) => employee.location_ids.includes(location.id))
    .map((location) => location.id);

  return {
    selectedRoleIds,
    primaryRoleId:
      roles.find((role) => role.id === employee.primary_role_id)?.id ??
      roles.find((role) => employee.role_names.includes(role.name))?.id ??
      selectedRoleIds[0] ??
      "",
    selectedLocationIds,
    primaryLocationId:
      locations.find((location) => location.id === employee.primary_location_id)?.id ??
      selectedLocationIds[0] ??
      "",
  };
}

function AssignmentPill({
  dark,
  label,
  leading,
  primary,
  onSetPrimary,
  onRemove,
}: {
  dark: boolean;
  label: string;
  leading: ReactNode;
  primary: boolean;
  onSetPrimary(): void;
  onRemove(): void;
}) {
  return (
    <motion.div
      layout
      animate={{ opacity: 1, scale: 1 }}
      className={`flex items-center gap-1.5 rounded-lg border py-1.5 pl-2.5 pr-2 ${
        dark
          ? "border-[#635BFF]/25 bg-[#635BFF]/[0.12]"
          : "border-[#635BFF]/15 bg-[#635BFF]/[0.06]"
      }`}
      exit={{ opacity: 0, scale: 0.9 }}
      initial={{ opacity: 0, scale: 0.9 }}
    >
      <span className="shrink-0">{leading}</span>
      <span
        className={`text-[12px] ${dark ? "text-white" : "text-[#0A2540]"}`}
        style={{ fontWeight: 480 }}
      >
        {label}
      </span>
      <button
        className={`ml-1 rounded-full px-2 py-0.5 text-[10px] transition-colors ${
          primary
            ? "bg-[#635BFF] text-white"
            : dark
              ? "bg-white/[0.06] text-[#C1CED8] hover:bg-white/[0.1]"
              : "bg-white text-[#635BFF] hover:bg-[#635BFF]/10"
        }`}
        onClick={onSetPrimary}
        style={{ fontWeight: primary ? 560 : 500 }}
        type="button"
      >
        {primary ? "Primary" : "Set Primary"}
      </button>
      <button
        className="ml-0.5 rounded p-0.5 transition-colors hover:bg-[#635BFF]/10"
        onClick={onRemove}
        type="button"
      >
        <X className="text-[#8898AA] hover:text-[#E5484D]" size={12} />
      </button>
    </motion.div>
  );
}

function AvailableAssignmentButton({
  dark,
  label,
  leading,
  onClick,
}: {
  dark: boolean;
  label: string;
  leading: ReactNode;
  onClick(): void;
}) {
  return (
    <button
      className={`group flex items-center gap-1.5 rounded-lg border px-3 py-1.5 transition-all duration-200 ${
        dark
          ? "border-white/[0.08] bg-white/[0.03] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08]"
          : "border-[#E5E7EB] bg-[#F7F8FA] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]"
      }`}
      onClick={onClick}
      type="button"
    >
      <span className="shrink-0">{leading}</span>
      <span
        className={`text-[12px] transition-colors ${
          dark
            ? "text-[#C1CED8] group-hover:text-white"
            : "text-[#5E6D7A] group-hover:text-[#0A2540]"
        }`}
        style={{ fontWeight: 440 }}
      >
        {label}
      </span>
      <Plus
        size={11}
        className="ml-0.5 text-[#8898AA] transition-colors group-hover:text-[#635BFF]"
      />
    </button>
  );
}

function RoleAssignmentPicker({
  dark,
  loading,
  roles,
  selectedRoleIds,
  primaryRoleId,
  onToggleRole,
  onSetPrimaryRole,
}: {
  dark: boolean;
  loading: boolean;
  roles: BusinessRole[];
  selectedRoleIds: string[];
  primaryRoleId: string;
  onToggleRole(roleId: string): void;
  onSetPrimaryRole(roleId: string): void;
}) {
  const selectedRoles = roles.filter((role) => selectedRoleIds.includes(role.id));
  const availableRoles = roles.filter((role) => !selectedRoleIds.includes(role.id));

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3
          className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
          style={{ fontWeight: 500 }}
        >
          Roles
        </h3>
        <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>
          {selectedRoles.length} selected
        </span>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        <AnimatePresence>
          {selectedRoles.map((role) => (
            <AssignmentPill
              dark={dark}
              key={role.id}
              label={role.name}
              leading={<Tag className="text-[#635BFF]" size={11} />}
              onRemove={() => onToggleRole(role.id)}
              onSetPrimary={() => onSetPrimaryRole(role.id)}
              primary={primaryRoleId === role.id}
            />
          ))}
        </AnimatePresence>
        {!selectedRoles.length ? (
          <p className="py-2 text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
            {loading
              ? "Loading business roles..."
              : "Assign at least one role before this employee can be scheduled."}
          </p>
        ) : null}
      </div>

      {!loading && !roles.length ? (
        <div
          className={`rounded-xl border px-4 py-3 text-[12px] ${
            dark
              ? "border-white/[0.08] bg-white/[0.03] text-[#C1CED8]"
              : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"
          }`}
        >
          Create business roles first. Employee role assignment should only use the business role
          catalog.
        </div>
      ) : null}

      {availableRoles.length ? (
        <div>
          <div className="mb-2.5 flex items-center justify-between">
            <h4
              className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
              style={{ fontWeight: 500 }}
            >
              Available Roles
            </h4>
            {availableRoles.length > 1 ? (
              <button
                className="text-[11px] text-[#635BFF] transition-colors hover:text-[#4B3FD9]"
                onClick={() => availableRoles.forEach((role) => onToggleRole(role.id))}
                style={{ fontWeight: 520 }}
                type="button"
              >
                + Add All
              </button>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {availableRoles.map((role) => (
              <AvailableAssignmentButton
                dark={dark}
                key={role.id}
                label={role.name}
                leading={<Tag className="text-[#635BFF]" size={11} />}
                onClick={() => onToggleRole(role.id)}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function LocationAssignmentPicker({
  dark,
  loading,
  locations,
  selectedLocationIds,
  primaryLocationId,
  onToggleLocation,
  onSetPrimaryLocation,
}: {
  dark: boolean;
  loading: boolean;
  locations: BusinessLocation[];
  selectedLocationIds: string[];
  primaryLocationId: string;
  onToggleLocation(locationId: string): void;
  onSetPrimaryLocation(locationId: string): void;
}) {
  const selectedLocations = locations
    .filter((location) => selectedLocationIds.includes(location.id))
    .sort((left, right) => {
      const leftPrimary = left.id === primaryLocationId ? 1 : 0;
      const rightPrimary = right.id === primaryLocationId ? 1 : 0;
      if (leftPrimary !== rightPrimary) {
        return rightPrimary - leftPrimary;
      }
      return locationDisplayName(left).localeCompare(locationDisplayName(right));
    });
  const availableLocations = locations.filter(
    (location) => !selectedLocationIds.includes(location.id),
  );

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3
          className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
          style={{ fontWeight: 500 }}
        >
          Locations
        </h3>
        <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>
          {selectedLocations.length} selected
        </span>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        <AnimatePresence>
          {selectedLocations.map((location) => {
            const reference = getLocationReference({
              name: locationDisplayName(location),
              slug: location.slug,
            });
            return (
              <AssignmentPill
                dark={dark}
                key={location.id}
                label={locationDisplayName(location)}
                leading={<span className="text-[13px]">{reference.logo}</span>}
                onRemove={() => onToggleLocation(location.id)}
                onSetPrimary={() => onSetPrimaryLocation(location.id)}
                primary={primaryLocationId === location.id}
              />
            );
          })}
        </AnimatePresence>
        {!selectedLocations.length ? (
          <p className="py-2 text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
            {loading
              ? "Loading business locations..."
              : "Assign at least one business location before saving."}
          </p>
        ) : null}
      </div>

      {!loading && !locations.length ? (
        <div
          className={`rounded-xl border px-4 py-3 text-[12px] ${
            dark
              ? "border-white/[0.08] bg-white/[0.03] text-[#C1CED8]"
              : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"
          }`}
        >
          Add at least one business location first. Employee location assignment should only use
          locations from this business.
        </div>
      ) : null}

      {availableLocations.length ? (
        <div>
          <div className="mb-2.5 flex items-center justify-between">
            <h4
              className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
              style={{ fontWeight: 500 }}
            >
              Available Locations
            </h4>
            {availableLocations.length > 1 ? (
              <button
                className="text-[11px] text-[#635BFF] transition-colors hover:text-[#4B3FD9]"
                onClick={() => availableLocations.forEach((location) => onToggleLocation(location.id))}
                style={{ fontWeight: 520 }}
                type="button"
              >
                + Add All
              </button>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {availableLocations.map((location) => {
              const reference = getLocationReference({
                name: locationDisplayName(location),
                slug: location.slug,
              });
              return (
                <AvailableAssignmentButton
                  dark={dark}
                  key={location.id}
                  label={locationDisplayName(location)}
                  leading={<span className="text-[13px]">{reference.logo}</span>}
                  onClick={() => onToggleLocation(location.id)}
                />
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function EmployeeAssignmentDrawer({
  businessId,
  dark,
  employee,
  locations,
  onClose,
  onSaved,
  roles,
}: EmployeeAssignmentDrawerProps) {
  const [profile, setProfile] = useState<EmployeeProfile | null>(null);
  const [state, setState] = useState<EmployeeAssignmentState>(() =>
    buildAssignmentStateFromSummary(employee, roles, locations),
  );
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isPending, startTransition] = useTransition();
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const panelSurface = dark ? "bg-white/[0.04]" : "bg-[#F7F8FA]";
  const fallbackPrimaryLocation = useMemo(
    () =>
      locations.find((location) => location.id === employee.primary_location_id) ??
      locations.find((location) =>
        employee.location_ids.includes(location.id),
      ) ??
      null,
    [employee.location_ids, employee.primary_location_id, locations],
  );
  const primaryLocation = useMemo(
    () => locations.find((location) => location.id === state.primaryLocationId) ?? null,
    [locations, state.primaryLocationId],
  );
  const baselineState = useMemo(
    () => (profile ? buildAssignmentState(profile) : buildAssignmentStateFromSummary(employee, roles, locations)),
    [employee, locations, profile, roles],
  );

  useEffect(() => {
    let cancelled = false;
    setProfile(null);
    setState(buildAssignmentStateFromSummary(employee, roles, locations));

    async function loadProfile() {
      try {
        setLoading(true);
        setFeedback(null);
        const nextProfile = await getEmployeeProfile(businessId, employee.id).catch(() => null);
        if (cancelled) {
          return;
        }
        if (nextProfile) {
          setProfile(nextProfile);
          setState(buildAssignmentState(nextProfile));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadProfile();

    return () => {
      cancelled = true;
    };
  }, [businessId, employee, locations, roles]);

  const toggleRole = (roleId: string) => {
    setState((current) => {
      const selectedRoleIds = current.selectedRoleIds.includes(roleId)
        ? current.selectedRoleIds.filter((item) => item !== roleId)
        : [...current.selectedRoleIds, roleId];
      const primaryRoleId = selectedRoleIds.includes(current.primaryRoleId)
        ? current.primaryRoleId
        : selectedRoleIds[0] ?? "";
      return { ...current, selectedRoleIds, primaryRoleId };
    });
  };

  const toggleLocation = (locationId: string) => {
    setState((current) => {
      const selectedLocationIds = current.selectedLocationIds.includes(locationId)
        ? current.selectedLocationIds.filter((item) => item !== locationId)
        : [...current.selectedLocationIds, locationId];
      const primaryLocationId = selectedLocationIds.includes(current.primaryLocationId)
        ? current.primaryLocationId
        : selectedLocationIds[0] ?? "";
      return { ...current, selectedLocationIds, primaryLocationId };
    });
  };

  const hasAssignmentChanges = useMemo(() => {
    const baselineRoleIds = [...baselineState.selectedRoleIds].sort();
    const currentRoleIds = [...state.selectedRoleIds].sort();
    const baselineLocationIds = [...baselineState.selectedLocationIds].sort();
    const currentLocationIds = [...state.selectedLocationIds].sort();

    if (baselineState.primaryRoleId !== state.primaryRoleId) {
      return true;
    }
    if (baselineState.primaryLocationId !== state.primaryLocationId) {
      return true;
    }
    if (
      baselineRoleIds.length !== currentRoleIds.length ||
      baselineRoleIds.some((value, index) => value !== currentRoleIds[index])
    ) {
      return true;
    }
    if (
      baselineLocationIds.length !== currentLocationIds.length ||
      baselineLocationIds.some((value, index) => value !== currentLocationIds[index])
    ) {
      return true;
    }
    return false;
  }, [baselineState, state]);

  const canSave =
    Boolean(state.selectedRoleIds.length) &&
    Boolean(state.primaryRoleId) &&
    Boolean(state.selectedLocationIds.length) &&
    Boolean(state.primaryLocationId) &&
    hasAssignmentChanges;

  const handleSave = () => {
    if (!canSave || isPending) {
      return;
    }

    startTransition(async () => {
      try {
        setFeedback(null);
        const nextProfile = await updateEmployee(businessId, employee.id, {
          roles: state.selectedRoleIds.map((roleId) => ({
            role_id: roleId,
            is_primary: roleId === state.primaryRoleId,
          })),
          locations: state.selectedLocationIds.map((locationId) => ({
            location_id: locationId,
            is_primary: locationId === state.primaryLocationId,
          })),
        });
        setProfile(nextProfile);
        setState(buildAssignmentState(nextProfile));
        await onSaved(nextProfile);
        setFeedback({ tone: "success", message: "Employee updated." });
      } catch (error) {
        setFeedback({
          tone: "error",
          message:
            error instanceof Error ? error.message : "Could not update this employee.",
        });
      }
    });
  };

  return (
    <motion.div
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm"
      exit={{ opacity: 0 }}
      initial={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        animate={{ x: 0 }}
        className={`flex h-full w-full max-w-[520px] flex-col border-l ${
          dark ? "border-white/[0.08] bg-[#0F2E4C]" : "border-[#E5E7EB] bg-white"
        }`}
        exit={{ x: 520 }}
        initial={{ x: 520 }}
        onClick={(event) => event.stopPropagation()}
        transition={{ duration: 0.28, ease: [0.25, 0.46, 0.45, 0.94] }}
      >
        <div className={`border-b px-6 py-5 ${borderClass}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#635BFF]/10 text-[14px] text-[#635BFF]"
                style={{ fontWeight: 600 }}
              >
                {employeeInitials(employeeDisplayName(employee))}
              </div>
              <div>
                <h2 className={`text-[18px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  {employeeDisplayName(employee)}
                </h2>
                <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  Assign the roles and locations that make this employee schedule-ready.
                </p>
              </div>
            </div>
            <button
              className={`rounded-full p-2 ${
                dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"
              }`}
              onClick={onClose}
              type="button"
            >
              <X className="text-[#8898AA]" size={16} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {feedback ? (
            <div
              className="mb-4 rounded-2xl px-4 py-3 text-[13px]"
              role="status"
              style={{
                background:
                  feedback.tone === "success"
                    ? "rgba(0, 184, 147, 0.08)"
                    : "rgba(229, 72, 77, 0.08)",
                color: feedback.tone === "success" ? "#067A64" : "#C13535",
                fontWeight: 500,
              }}
            >
              {feedback.message}
            </div>
          ) : null}

          {loading && !profile ? (
            <div className={`py-12 text-[13px] ${textSecondary}`}>Loading employee profile...</div>
          ) : (
            <div className="space-y-5">
              <div className={`rounded-2xl px-4 py-4 ${panelSurface}`}>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <p
                      className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                      style={{ fontWeight: 500 }}
                    >
                      Contact
                    </p>
                    <p className={`mt-1 text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                      {profile?.email ?? profile?.phone_e164 ?? employee.email ?? employee.phone_e164 ?? "No contact info"}
                    </p>
                  </div>
                  <div>
                    <p
                      className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                      style={{ fontWeight: 500 }}
                    >
                      Primary Location
                    </p>
                    <div className="mt-1 flex items-center gap-2">
                      <MapPin className="text-[#8898AA]" size={13} />
                      <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                        {primaryLocation
                          ? locationDisplayName(primaryLocation)
                          : fallbackPrimaryLocation
                            ? locationDisplayName(fallbackPrimaryLocation)
                            : "Not set"}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <RoleAssignmentPicker
                dark={dark}
                loading={false}
                onSetPrimaryRole={(roleId) =>
                  setState((current) => ({ ...current, primaryRoleId: roleId }))
                }
                onToggleRole={toggleRole}
                primaryRoleId={state.primaryRoleId}
                roles={roles}
                selectedRoleIds={state.selectedRoleIds}
              />

              <LocationAssignmentPicker
                dark={dark}
                loading={false}
                locations={locations}
                onSetPrimaryLocation={(locationId) =>
                  setState((current) => ({ ...current, primaryLocationId: locationId }))
                }
                onToggleLocation={toggleLocation}
                primaryLocationId={state.primaryLocationId}
                selectedLocationIds={state.selectedLocationIds}
              />
            </div>
          )}
        </div>

        <div className={`flex items-center justify-end gap-3 border-t px-6 py-4 ${borderClass}`}>
          <button
            className={`rounded-full border px-4 py-2.5 text-[13px] ${
              dark
                ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]"
                : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"
            }`}
            onClick={onClose}
            type="button"
          >
            Close
          </button>
          <button
            className="rounded-full px-4 py-2.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canSave || isPending || loading}
            onClick={handleSave}
            style={{
              fontWeight: 540,
              background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
            }}
            type="button"
          >
            {isPending ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
