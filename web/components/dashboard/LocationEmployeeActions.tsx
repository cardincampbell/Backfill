"use client";

import { useEffect, useMemo, useRef, useState, useTransition, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Activity,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Plus,
  Tag,
  Upload,
  UserPlus,
  X,
} from "lucide-react";

import type { BusinessLocation, BusinessRole } from "@/lib/api/businesses";
import {
  createEmployee,
  downloadEmployeeImportTemplate,
  importEmployees,
  updateEmployee,
  type EmployeeBulkImportResponse,
  type EmployeeSummary,
} from "@/lib/api/workforce";

import { getLocationReference } from "./location-role-reference";

type Feedback = {
  tone: "success" | "error";
  message: string;
} | null;

type EnrollmentModalProps = {
  businessId: string;
  businessLocations: BusinessLocation[];
  dark: boolean;
  defaultLocationId?: string | null;
  defaultLocationName?: string | null;
  defaultRoleId?: string | null;
  defaultRoleName?: string | null;
  lockDefaultLocation?: boolean;
  lockDefaultRole?: boolean;
  onClose(): void;
  onCreated(employee: EmployeeSummary): Promise<void> | void;
  roles: BusinessRole[];
};

type BulkUploadModalProps = {
  businessId: string;
  dark: boolean;
  defaultLocationId?: string | null;
  defaultLocationName?: string | null;
  onClose(): void;
  onImported(
    result: EmployeeBulkImportResponse,
    importedEmployees: EmployeeSummary[],
  ): Promise<void> | void;
};

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function locationDisplayName(location: BusinessLocation) {
  return location.display_name || location.name;
}

function buildLocationAssignments(
  selectedLocationIds: string[],
  primaryLocationId: string,
) {
  const nextLocationIds = Array.from(new Set(selectedLocationIds));
  return nextLocationIds.map((locationId) => ({
    location_id: locationId,
    is_primary: locationId === primaryLocationId,
  }));
}

function AssignmentPill({
  dark,
  label,
  leading,
  onRemove,
  onSetPrimary,
  primary,
}: {
  dark: boolean;
  label: string;
  leading: ReactNode;
  onRemove(): void;
  onSetPrimary(): void;
  primary: boolean;
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
  trailing,
}: {
  dark: boolean;
  label: string;
  leading: ReactNode;
  onClick(): void;
  trailing?: ReactNode;
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
          dark ? "text-[#C1CED8] group-hover:text-white" : "text-[#5E6D7A] group-hover:text-[#0A2540]"
        }`}
        style={{ fontWeight: 440 }}
      >
        {label}
      </span>
      {trailing ?? (
        <Plus
          className="ml-0.5 text-[#8898AA] transition-colors group-hover:text-[#635BFF]"
          size={11}
        />
      )}
    </button>
  );
}

export function EmployeeEnrollmentModal({
  businessId,
  businessLocations,
  dark,
  defaultLocationId = null,
  defaultLocationName = null,
  defaultRoleId = null,
  defaultRoleName = null,
  lockDefaultLocation = false,
  lockDefaultRole = false,
  onClose,
  onCreated,
  roles,
}: EnrollmentModalProps) {
  const fallbackDefaultLocation =
    defaultLocationId == null && businessLocations.length === 1 ? businessLocations[0] : null;
  const effectiveDefaultLocationId = defaultLocationId ?? fallbackDefaultLocation?.id ?? null;
  const effectiveDefaultLocationName =
    defaultLocationName ??
    (fallbackDefaultLocation ? locationDisplayName(fallbackDefaultLocation) : null);
  const effectiveDefaultRoleId = defaultRoleId ?? null;
  const effectiveDefaultRoleName =
    defaultRoleName ??
    roles.find((role) => role.id === effectiveDefaultRoleId)?.name ??
    null;
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>(
    effectiveDefaultRoleId ? [effectiveDefaultRoleId] : [],
  );
  const [selectedLocationIds, setSelectedLocationIds] = useState<string[]>(
    effectiveDefaultLocationId ? [effectiveDefaultLocationId] : [],
  );
  const [primaryLocationId, setPrimaryLocationId] = useState(effectiveDefaultLocationId ?? "");
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    if (!feedback) {
      return;
    }
    const timeoutId = window.setTimeout(() => setFeedback(null), 4000);
    return () => window.clearTimeout(timeoutId);
  }, [feedback]);

  const selectedRoles = useMemo(
    () => roles.filter((role) => selectedRoleIds.includes(role.id)),
    [roles, selectedRoleIds],
  );
  const availableRoles = useMemo(
    () => roles.filter((role) => !selectedRoleIds.includes(role.id)),
    [roles, selectedRoleIds],
  );
  const selectedLocations = useMemo(
    () =>
      businessLocations
        .filter((location) => selectedLocationIds.includes(location.id))
        .sort((left, right) => {
          const leftPrimary = left.id === primaryLocationId ? 1 : 0;
          const rightPrimary = right.id === primaryLocationId ? 1 : 0;
          if (leftPrimary !== rightPrimary) {
            return rightPrimary - leftPrimary;
          }
          return locationDisplayName(left).localeCompare(locationDisplayName(right));
        }),
    [businessLocations, primaryLocationId, selectedLocationIds],
  );
  const availableLocations = useMemo(
    () =>
      businessLocations.filter((location) => !selectedLocationIds.includes(location.id)),
    [businessLocations, selectedLocationIds],
  );

  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const inputClass = dark
    ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8898AA]"
    : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#8898AA]";

  const hasRequiredLocation =
    !effectiveDefaultLocationId || selectedLocationIds.includes(effectiveDefaultLocationId);
  const hasRequiredRole =
    !effectiveDefaultRoleId || selectedRoleIds.includes(effectiveDefaultRoleId);
  const canSubmit =
    Boolean(firstName.trim()) &&
    Boolean(lastName.trim()) &&
    Boolean(email.trim()) &&
    Boolean(phone.trim()) &&
    selectedRoleIds.length > 0 &&
    selectedLocationIds.length > 0 &&
    Boolean(primaryLocationId) &&
    hasRequiredLocation &&
    hasRequiredRole;

  const toggleRole = (roleId: string) => {
    if (lockDefaultRole && roleId === effectiveDefaultRoleId) {
      return;
    }
    setSelectedRoleIds((current) =>
      current.includes(roleId)
        ? current.filter((item) => item !== roleId)
        : [...current, roleId],
    );
  };

  const toggleLocation = (locationIdToToggle: string) => {
    if (lockDefaultLocation && locationIdToToggle === effectiveDefaultLocationId) {
      return;
    }
    setSelectedLocationIds((current) => {
      const nextLocationIds = current.includes(locationIdToToggle)
        ? current.filter((item) => item !== locationIdToToggle)
        : [...current, locationIdToToggle];

      setPrimaryLocationId((currentPrimary) =>
        nextLocationIds.includes(currentPrimary) ? currentPrimary : nextLocationIds[0] ?? "",
      );

      return nextLocationIds;
    });
  };

  const handleSubmit = () => {
    if (!canSubmit || isPending) {
      return;
    }

    startTransition(async () => {
      try {
        setFeedback(null);
        const fullName = `${firstName.trim()} ${lastName.trim()}`.trim();
        const createdEmployee = await createEmployee(businessId, {
          full_name: fullName,
          email: normalizeOptional(email),
          phone_e164: normalizeOptional(phone),
          primary_location_id: primaryLocationId || null,
          employee_metadata: {
            source: defaultLocationId ? "location_ui" : "team_ui",
            ...(defaultLocationId ? { source_location_id: defaultLocationId } : {}),
          },
        });

        const nextEmployee =
          selectedRoleIds.length || selectedLocationIds.length
            ? await updateEmployee(businessId, createdEmployee.id, {
                roles: selectedRoleIds.map((roleId) => ({
                  role_id: roleId,
                  is_primary: roleId === selectedRoleIds[0],
                })),
                locations: buildLocationAssignments(
                  selectedLocationIds,
                  effectiveDefaultLocationId || primaryLocationId,
                ),
              })
            : createdEmployee;

        await onCreated(nextEmployee);
        onClose();
      } catch (error) {
        setFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not add this employee.",
        });
      }
    });
  };

  return (
    <motion.div
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      exit={{ opacity: 0 }}
      initial={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className={`mx-4 w-full max-w-3xl overflow-hidden rounded-[28px] border ${
          dark ? "border-white/[0.08] bg-[#0F2E4C]" : "border-[#E5E7EB] bg-white"
        }`}
        exit={{ opacity: 0, scale: 0.96, y: 16 }}
        initial={{ opacity: 0, scale: 0.96, y: 16 }}
        onClick={(event) => event.stopPropagation()}
        transition={{ duration: 0.22 }}
      >
        <div className={`border-b px-6 py-5 ${borderClass}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#635BFF]/10">
                <UserPlus className="text-[#635BFF]" size={18} />
              </div>
              <div>
                <h2 className={`text-[18px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  Add Employee
                </h2>
                <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  {effectiveDefaultLocationName && effectiveDefaultRoleName
                    ? `This employee will be added to ${effectiveDefaultLocationName} as ${effectiveDefaultRoleName}.`
                    : effectiveDefaultLocationName
                      ? `This employee will be added to ${effectiveDefaultLocationName} automatically.`
                      : "Add a new team member using this business's live roles and locations."}
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

        <div className="max-h-[70vh] overflow-y-auto px-6 py-5">
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

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label
                className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                First Name
              </label>
              <input
                className={`w-full rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${inputClass}`}
                onChange={(event) => setFirstName(event.target.value)}
                placeholder="Sarah"
                style={{ fontWeight: 440 }}
                type="text"
                value={firstName}
              />
            </div>
            <div>
              <label
                className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                Last Name
              </label>
              <input
                className={`w-full rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${inputClass}`}
                onChange={(event) => setLastName(event.target.value)}
                placeholder="Martinez"
                style={{ fontWeight: 440 }}
                type="text"
                value={lastName}
              />
            </div>
            <div>
              <label
                className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                Email
              </label>
              <input
                className={`w-full rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${inputClass}`}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="sarah.m@company.com"
                style={{ fontWeight: 440 }}
                type="email"
                value={email}
              />
            </div>
            <div>
              <label
                className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                Phone
              </label>
              <input
                className={`w-full rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${inputClass}`}
                onChange={(event) => setPhone(event.target.value)}
                placeholder="(415) 555-0142"
                style={{ fontWeight: 440 }}
                type="tel"
                value={phone}
              />
            </div>
          </div>

          <div className="mt-5">
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

                  if (lockDefaultLocation) {
                    return (
                      <div
                        key={location.id}
                        className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 ${
                          dark
                            ? "border-[#635BFF]/25 bg-[#635BFF]/[0.12]"
                            : "border-[#635BFF]/15 bg-[#635BFF]/[0.06]"
                        }`}
                      >
                        <span className="text-[13px]">{reference.logo}</span>
                        <span className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                          {locationDisplayName(location)}
                        </span>
                      </div>
                    );
                  }

                  return (
                    <AssignmentPill
                      dark={dark}
                      key={location.id}
                      label={locationDisplayName(location)}
                      leading={<span className="text-[13px]">{reference.logo}</span>}
                      onRemove={() => toggleLocation(location.id)}
                      onSetPrimary={() => setPrimaryLocationId(location.id)}
                      primary={primaryLocationId === location.id}
                    />
                  );
                })}
              </AnimatePresence>
              {!selectedLocations.length ? (
                <p className="py-2 text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
                  No locations selected yet. Add from the list below.
                </p>
              ) : null}
            </div>

            {!hasRequiredLocation && defaultLocationName ? (
              <p className="mb-3 text-[12px] text-[#E5484D]" style={{ fontWeight: 460 }}>
                {defaultLocationName} must stay selected to add an employee from this page.
              </p>
            ) : null}

            {!businessLocations.length ? (
              <div
                className={`rounded-xl border px-4 py-3 text-[12px] ${
                  dark
                    ? "border-white/[0.08] bg-white/[0.03] text-[#C1CED8]"
                    : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"
                }`}
              >
                Add at least one business location first. Employee location assignment should only use locations from this business.
              </div>
            ) : !lockDefaultLocation && availableLocations.length ? (
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
                      onClick={() =>
                        availableLocations.forEach((location) => toggleLocation(location.id))
                      }
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
                        onClick={() => toggleLocation(location.id)}
                      />
                    );
                  })}
                </div>
              </div>
            ) : null}
          </div>

          <div className="mt-5">
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
                {selectedRoles.map((role) =>
                  lockDefaultRole ? (
                    <div
                      key={role.id}
                      className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 ${
                        dark
                          ? "border-[#635BFF]/25 bg-[#635BFF]/[0.12]"
                          : "border-[#635BFF]/15 bg-[#635BFF]/[0.06]"
                      }`}
                    >
                      <Tag className="text-[#635BFF]" size={11} />
                      <span className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                        {role.name}
                      </span>
                    </div>
                  ) : (
                    <motion.div
                      key={role.id}
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
                      <Tag className="text-[#635BFF]" size={11} />
                      <span className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                        {role.name}
                      </span>
                      <button
                        className="ml-0.5 rounded p-0.5 transition-colors hover:bg-[#635BFF]/10"
                        onClick={() => toggleRole(role.id)}
                        type="button"
                      >
                        <X className="text-[#8898AA] hover:text-[#E5484D]" size={12} />
                      </button>
                    </motion.div>
                  ),
                )}
              </AnimatePresence>
            {!selectedRoles.length ? (
              <p className="py-2 text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
                No roles selected yet. Add from the list below.
              </p>
            ) : null}
          </div>

            {!hasRequiredRole && effectiveDefaultRoleName ? (
              <p className="mb-3 text-[12px] text-[#E5484D]" style={{ fontWeight: 460 }}>
                {effectiveDefaultRoleName} must stay selected to add an employee from this screen.
              </p>
            ) : null}

            {!lockDefaultRole && availableRoles.length ? (
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
                      onClick={() => availableRoles.forEach((role) => toggleRole(role.id))}
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
                      onClick={() => toggleRole(role.id)}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <div className={`flex items-center justify-between gap-3 border-t px-6 py-4 ${borderClass}`}>
          <p className={`max-w-[420px] text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
            {!canSubmit
              ? "First name, last name, phone, email, at least one role, and at least one location are required."
              : effectiveDefaultLocationName && effectiveDefaultRoleName
                ? `${effectiveDefaultLocationName} and ${effectiveDefaultRoleName} stay selected automatically from this scheduler context.`
                : defaultLocationName
                  ? `${defaultLocationName} stays selected automatically when you add an employee from this screen.`
                  : "Add at least one role and one location to finish creating this employee."}
          </p>
          <div className="flex items-center gap-3">
            <button
              className={`rounded-full border px-4 py-2.5 text-[13px] ${
                dark
                  ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]"
                  : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"
              }`}
              onClick={onClose}
              type="button"
            >
              Cancel
            </button>
            <button
              className="rounded-full px-4 py-2.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canSubmit || isPending}
              onClick={handleSubmit}
              style={{
                fontWeight: 540,
                background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
              }}
              type="button"
            >
              {isPending ? "Adding..." : "Add Employee"}
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

export function EmployeeBulkUploadModal({
  businessId,
  dark,
  defaultLocationId = null,
  defaultLocationName = null,
  onClose,
  onImported,
}: BulkUploadModalProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<EmployeeBulkImportResponse | null>(null);
  const [isPending, startTransition] = useTransition();
  const [isDownloadingTemplate, setIsDownloadingTemplate] = useState(false);
  const [detectedRowCount, setDetectedRowCount] = useState<number | null>(null);

  useEffect(() => {
    if (!feedback) {
      return;
    }
    const timeoutId = window.setTimeout(() => setFeedback(null), 4000);
    return () => window.clearTimeout(timeoutId);
  }, [feedback]);

  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const panelClass = dark ? "border-white/[0.08] bg-[#0F2E4C]" : "border-[#E5E7EB] bg-white";
  const subtleBorderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const subtleSurfaceClass = dark ? "bg-white/[0.04]" : "bg-[#F7F8FA]";
  const secondaryButtonClass = dark
    ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]"
    : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]";

  const handleTemplateDownload = async () => {
    try {
      setFeedback(null);
      setIsDownloadingTemplate(true);
      await downloadEmployeeImportTemplate(businessId);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "Could not download the template.");
    } finally {
      setIsDownloadingTemplate(false);
    }
  };

  const simulateUpload = (file: File) => {
    setSelectedFile(file);
    setUploadProgress(0);
    setImportResult(null);
    setDetectedRowCount(null);
    if (file.name.toLowerCase().endsWith(".csv")) {
      void file.text().then((contents) => {
        const lines = contents
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean);
        setDetectedRowCount(Math.max(lines.length - 1, 0));
      }).catch(() => {
        setDetectedRowCount(null);
      });
    }
    const intervalId = window.setInterval(() => {
      setUploadProgress((current) => {
        if (current >= 100) {
          window.clearInterval(intervalId);
          return 100;
        }
        return current + 20;
      });
    }, 160);
  };

  const handleImport = () => {
    if (!selectedFile || uploadProgress < 100 || isPending) {
      return;
    }

    startTransition(async () => {
      try {
        setFeedback(null);
        const result = await importEmployees(businessId, selectedFile);
        const importedEmployees = defaultLocationId
          ? await Promise.all(
              result.employees.map((employee) =>
                updateEmployee(businessId, employee.id, {
                  locations: buildLocationAssignments([defaultLocationId], defaultLocationId),
                }),
              ),
            )
          : result.employees;

        setImportResult(result);
        await onImported(result, importedEmployees);

        if (!result.errors.length) {
          onClose();
          return;
        }

        setFeedback(
          `Imported ${result.created_count} employee${result.created_count === 1 ? "" : "s"} with ${result.errors.length} row issue${result.errors.length === 1 ? "" : "s"}.`,
        );
      } catch (error) {
        setFeedback(error instanceof Error ? error.message : "Could not import these employees.");
      }
    });
  };

  return (
    <motion.div
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      exit={{ opacity: 0 }}
      initial={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className={`mx-4 w-full max-w-lg overflow-hidden rounded-2xl border shadow-2xl ${panelClass}`}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        onClick={(event) => event.stopPropagation()}
        transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
      >
        <div className={`flex items-center justify-between border-b px-6 py-5 ${borderClass}`}>
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#00B893]/10">
              <Upload size={18} className="text-[#00B893]" />
            </div>
            <div>
              <h2 className={`text-[16px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                Import Employees
              </h2>
              <p className={`text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                {defaultLocationName
                  ? `Import from a CSV or Excel file. New employees are also assigned to ${defaultLocationName}.`
                  : "Import from a CSV or Excel file"}
              </p>
            </div>
          </div>
          <button
            className={`rounded-lg p-2 transition-colors ${
              dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"
            }`}
            onClick={onClose}
            type="button"
          >
            <X size={18} className="text-[#8898AA]" />
          </button>
        </div>

        <div className="px-6 py-6">
          {feedback ? (
            <div
              className="mb-4 rounded-xl px-4 py-3 text-[13px]"
              role="status"
              style={{ background: "rgba(229, 72, 77, 0.08)", color: "#C13535", fontWeight: 500 }}
            >
              {feedback}
            </div>
          ) : null}

          <div
            className={`mb-5 flex items-center gap-3 rounded-xl border p-3.5 ${
              dark
                ? "border-[#635BFF]/20 bg-[#635BFF]/[0.08]"
                : "border-[#635BFF]/10 bg-[#635BFF]/[0.04]"
            }`}
          >
            <FileSpreadsheet size={18} className="shrink-0 text-[#635BFF]" />
            <div className="flex-1">
              <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 500 }}>
                Need a template?
              </p>
              <p className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                Download our CSV template with the required columns.
              </p>
            </div>
            <button
              className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] text-[#635BFF] transition-all ${
                dark
                  ? "border-white/[0.08] bg-white/[0.04] hover:bg-white/[0.06]"
                  : "border-[#E5E7EB] bg-white hover:bg-[#F7F8FA]"
              }`}
              disabled={isDownloadingTemplate}
              onClick={() => {
                void handleTemplateDownload();
              }}
              style={{ fontWeight: 500 }}
              type="button"
            >
              <Download size={12} />
              {isDownloadingTemplate ? "Downloading..." : "Template"}
            </button>
          </div>

          <div
            className={`relative cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-all duration-300 ${
              isDragging
                ? "border-[#635BFF] bg-[#635BFF]/[0.08]"
                : selectedFile
                  ? "border-[#00B893]/40 bg-[#00B893]/[0.06]"
                  : dark
                    ? "border-white/[0.08] hover:border-[#635BFF]/30 hover:bg-white/[0.04]"
                    : "border-[#E5E7EB] hover:border-[#635BFF]/30 hover:bg-[#F7F8FA]"
            }`}
            onClick={() => inputRef.current?.click()}
            onDragLeave={() => setIsDragging(false)}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragging(false);
              const file = event.dataTransfer.files?.[0];
              if (file) {
                simulateUpload(file);
              }
            }}
          >
            <input
              accept=".csv,.xlsx"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  simulateUpload(file);
                }
              }}
              ref={inputRef}
              type="file"
            />

            {selectedFile ? (
              <div>
                <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[#00B893]/10">
                  {uploadProgress >= 100 ? (
                    <CheckCircle2 size={24} className="text-[#00B893]" />
                  ) : (
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                    >
                      <Activity size={20} className="text-[#00B893]" />
                    </motion.div>
                  )}
                </div>
                <p className={`mb-1 text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                  {selectedFile.name}
                </p>
                {uploadProgress < 100 ? (
                  <div className="mx-auto w-48">
                    <div
                      className={`mt-2 h-1.5 overflow-hidden rounded-full ${
                        dark ? "bg-white/[0.08]" : "bg-[#F0F0F5]"
                      }`}
                    >
                      <motion.div
                        className="h-full rounded-full bg-gradient-to-r from-[#00B893] to-[#00D4AA]"
                        animate={{ width: `${Math.min(uploadProgress, 100)}%` }}
                        initial={{ width: 0 }}
                      />
                    </div>
                  <p className={`mt-1.5 text-[11px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                      Processing...
                    </p>
                  </div>
                ) : (
                  <p className="text-[12px] text-[#00B893]" style={{ fontWeight: 480 }}>
                    {detectedRowCount !== null
                      ? `Ready to import • ${detectedRowCount} employee${detectedRowCount === 1 ? "" : "s"} found`
                      : "Ready to import this file"}
                  </p>
                )}
              </div>
            ) : (
              <div>
                <div className={`mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full ${subtleSurfaceClass}`}>
                  <Upload size={20} className="text-[#8898AA]" />
                </div>
                <p className={`mb-1 text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                  Drop your file here, or click to browse
                </p>
                <p className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  Supports CSV, XLS, XLSX • Max 5MB
                </p>
              </div>
            )}
          </div>

          {selectedFile && uploadProgress >= 100 ? (
            <motion.div
              animate={{ opacity: 1, y: 0 }}
              className={`mt-4 rounded-xl border p-4 ${subtleBorderClass} ${subtleSurfaceClass}`}
              initial={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.3, delay: 0.1 }}
            >
              <p className={`mb-3 text-[11px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 500 }}>
                Column Mapping Preview
              </p>
              <div className="space-y-2">
                {[
                  { csv: "first_name", mapped: "First Name" },
                  { csv: "last_name", mapped: "Last Name" },
                  { csv: "phone_number", mapped: "Phone Number" },
                  { csv: "email_address", mapped: "Email Address" },
                ].map((column) => (
                  <div key={column.csv} className="flex items-center gap-3 text-[12px]">
                    <span className="text-[#00B893]">✓</span>
                    <span className={`w-28 truncate ${textSecondary}`} style={{ fontWeight: 420 }}>
                      {column.csv}
                    </span>
                    <span className={textSecondary}>→</span>
                    <span className={textPrimary} style={{ fontWeight: 480 }}>
                      {column.mapped}
                    </span>
                  </div>
                ))}
              </div>
            </motion.div>
          ) : null}

          {importResult?.errors.length ? (
            <div
              className={`mt-4 rounded-2xl border px-4 py-4 ${
                dark ? "border-white/[0.08] bg-white/[0.04]" : "border-[#E5E7EB] bg-[#FAFBFC]"
              }`}
            >
              <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                Import completed with row issues
              </p>
              <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                {importResult.created_count} created, {importResult.skipped_count} skipped.
              </p>
              <div className="mt-3 space-y-2">
                {importResult.errors.map((error, index) => (
                  <div
                    key={`${error.row_number ?? "general"}-${index}`}
                    className={`rounded-xl px-3 py-2 text-[12px] ${
                      dark ? "bg-white/[0.04] text-[#C1CED8]" : "bg-white text-[#5E6D7A]"
                    }`}
                    style={{ fontWeight: 420 }}
                  >
                    Row {error.row_number ?? "?"}: {error.message}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className={`flex items-center justify-end gap-3 border-t px-6 py-4 ${borderClass} ${subtleSurfaceClass}`}>
          <button
            className={`rounded-lg border px-4 py-2.5 text-[13px] transition-all ${secondaryButtonClass}`}
            onClick={onClose}
            style={{ fontWeight: 480 }}
            type="button"
          >
            Cancel
          </button>
          <button
            className={`rounded-lg px-5 py-2.5 text-[13px] text-white transition-all duration-300 ${
              selectedFile && uploadProgress >= 100
                ? "hover:shadow-[0_0_20px_rgba(0,184,147,0.25)]"
                : "cursor-not-allowed opacity-40"
            }`}
            disabled={!selectedFile || uploadProgress < 100 || isPending}
            onClick={handleImport}
            style={{ fontWeight: 540, background: "linear-gradient(135deg, #00B893, #00D4AA)" }}
            type="button"
          >
            {isPending ? "Importing..." : "Import Employees"}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

export function LocationEmployeeEnrollmentModal(
  props: Omit<EnrollmentModalProps, "defaultLocationId" | "defaultLocationName"> & {
    locationId: string;
    locationName: string;
  },
) {
  return (
    <EmployeeEnrollmentModal
      {...props}
      defaultLocationId={props.locationId}
      defaultLocationName={props.locationName}
      lockDefaultLocation
    />
  );
}

export function SchedulerEmployeeEnrollmentModal(
  props: Omit<
    EnrollmentModalProps,
    | "defaultLocationId"
    | "defaultLocationName"
    | "defaultRoleId"
    | "defaultRoleName"
  > & {
    locationId: string;
    locationName: string;
    roleId: string;
    roleName: string;
  },
) {
  return (
    <EmployeeEnrollmentModal
      {...props}
      defaultLocationId={props.locationId}
      defaultLocationName={props.locationName}
      defaultRoleId={props.roleId}
      defaultRoleName={props.roleName}
      lockDefaultLocation
      lockDefaultRole
    />
  );
}

export function LocationEmployeeBulkUploadModal(
  props: Omit<BulkUploadModalProps, "defaultLocationId" | "defaultLocationName" | "onImported"> & {
    locationId: string;
    locationName: string;
    onImported(
      importedEmployees: EmployeeSummary[],
      createdCount: number,
      skippedCount: number,
    ): Promise<void> | void;
  },
) {
  return (
    <EmployeeBulkUploadModal
      businessId={props.businessId}
      dark={props.dark}
      defaultLocationId={props.locationId}
      defaultLocationName={props.locationName}
      onClose={props.onClose}
      onImported={async (result, importedEmployees) => {
        await props.onImported(
          importedEmployees,
          result.created_count,
          result.skipped_count,
        );
      }}
    />
  );
}
