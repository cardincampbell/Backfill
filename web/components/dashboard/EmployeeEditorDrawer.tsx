"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  AlertCircle,
  Mail,
  Phone,
  Plus,
  Shield as ShieldCheck,
  Tag,
  X,
} from "lucide-react";

import {
  createBusinessRole,
  type BusinessLocation,
  type BusinessRole,
} from "@/lib/api/businesses";
import {
  deleteEmployee,
  getEmployeeDeleteReadiness,
  getEmployeeProfile,
  updateEmployee,
  type EmployeeProfile,
} from "@/lib/api/workforce";

import { getLocationReference } from "./location-role-reference";

type Feedback =
  | {
      tone: "success" | "error";
      message: string;
    }
  | null;

export type EmployeeEditorSeed = {
  id: string;
  full_name: string;
  preferred_name?: string | null;
  email?: string | null;
  phone_e164?: string | null;
  primary_location_id?: string | null;
  primary_role_id?: string | null;
  role_ids: string[];
  role_names: string[];
  location_ids: string[];
  location_names: string[];
  reliability_score?: number | null;
  status: string;
};

type EmployeeAssignmentState = {
  selectedRoleIds: string[];
  primaryRoleId: string;
  selectedLocationIds: string[];
  primaryLocationId: string;
};

function employeeDisplayName(employee: Pick<EmployeeEditorSeed, "full_name" | "preferred_name">) {
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

function buildAssignmentStateFromProfile(profile: EmployeeProfile): EmployeeAssignmentState {
  return {
    selectedRoleIds: profile.roles.map((role) => role.role_id),
    primaryRoleId:
      profile.roles.find((role) => role.is_primary)?.role_id ??
      profile.roles[0]?.role_id ??
      "",
    selectedLocationIds: profile.locations.map((location) => location.location_id),
    primaryLocationId:
      profile.locations.find((location) => location.is_primary)?.location_id ??
      profile.locations[0]?.location_id ??
      "",
  };
}

function buildAssignmentStateFromSeed(
  employee: EmployeeEditorSeed,
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

function countSelectionChanges(initialIds: string[], currentIds: string[]) {
  const initialSet = new Set(initialIds);
  const currentSet = new Set(currentIds);
  let delta = 0;

  initialSet.forEach((id) => {
    if (!currentSet.has(id)) {
      delta += 1;
    }
  });
  currentSet.forEach((id) => {
    if (!initialSet.has(id)) {
      delta += 1;
    }
  });

  return delta;
}

function getReliabilityColor(reliability: number) {
  if (reliability >= 95) {
    return "#00B893";
  }
  if (reliability >= 85) {
    return "#F59E0B";
  }
  return "#E5484D";
}

const statusConfig = {
  active: { label: "Active", color: "#00B893", bg: "#00B893" },
  on_leave: { label: "On Leave", color: "#635BFF", bg: "#635BFF" },
  inactive: { label: "Inactive", color: "#8898AA", bg: "#8898AA" },
  needs_attention: { label: "Needs Attention", color: "#F59E0B", bg: "#F59E0B" },
} as const;

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
          dark ? "text-[#C1CED8] group-hover:text-white" : "text-[#5E6D7A] group-hover:text-[#0A2540]"
        }`}
        style={{ fontWeight: 440 }}
      >
        {label}
      </span>
      <Plus
        className="ml-0.5 text-[#8898AA] transition-colors group-hover:text-[#635BFF]"
        size={11}
      />
    </button>
  );
}

export function EmployeeEditorDrawer({
  businessId,
  dark,
  employee,
  locations,
  onClose,
  onDeleted,
  onRoleCreated,
  onSaved,
  roles,
}: {
  businessId: string;
  dark: boolean;
  employee: EmployeeEditorSeed;
  locations: BusinessLocation[];
  onClose(): void;
  onDeleted?(employeeId: string): Promise<void> | void;
  onRoleCreated?(role: BusinessRole): void;
  onSaved(employee: EmployeeProfile): Promise<void> | void;
  roles: BusinessRole[];
}) {
  const [email, setEmail] = useState(employee.email ?? "");
  const [phone, setPhone] = useState(employee.phone_e164 ?? "");
  const [formData, setFormData] = useState<EmployeeAssignmentState>(() =>
    buildAssignmentStateFromSeed(employee, roles, locations),
  );
  const [roleCatalog, setRoleCatalog] = useState<BusinessRole[]>(roles);
  const [customRole, setCustomRole] = useState("");
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [profile, setProfile] = useState<EmployeeProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleteState, setDeleteState] = useState<{
    canDelete: boolean;
    checking?: boolean;
    deleting?: boolean;
    reason?: string | null;
  }>({ canDelete: false, checking: true });

  useEffect(() => {
    setRoleCatalog(roles);
  }, [roles]);

  useEffect(() => {
    let cancelled = false;

    setEmail(employee.email ?? "");
    setPhone(employee.phone_e164 ?? "");
    setFormData(buildAssignmentStateFromSeed(employee, roles, locations));
    setProfile(null);
    setDeleteState({ canDelete: false, checking: true, reason: null });

    async function loadProfile() {
      try {
        const [nextProfile, readiness] = await Promise.all([
          getEmployeeProfile(businessId, employee.id).catch(() => null),
          getEmployeeDeleteReadiness(businessId, employee.id).catch(() => null),
        ]);
        if (cancelled) {
          return;
        }
        if (nextProfile) {
          setProfile(nextProfile);
          setEmail(nextProfile.email ?? "");
          setPhone(nextProfile.phone_e164 ?? "");
          setFormData(buildAssignmentStateFromProfile(nextProfile));
        }
        setDeleteState(
          readiness
            ? {
                canDelete: readiness.can_delete,
                reason: readiness.reason,
              }
            : {
                canDelete: false,
                reason: "Could not determine whether this employee can be removed.",
              },
        );
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

  useEffect(() => {
    if (!feedback) {
      return;
    }
    const timeoutId = window.setTimeout(() => setFeedback(null), 4000);
    return () => window.clearTimeout(timeoutId);
  }, [feedback]);

  const baselineState = useMemo(
    () =>
      profile
        ? buildAssignmentStateFromProfile(profile)
        : buildAssignmentStateFromSeed(employee, roles, locations),
    [employee, locations, profile, roles],
  );
  const baselineEmail = profile?.email ?? employee.email ?? "";
  const baselinePhone = profile?.phone_e164 ?? employee.phone_e164 ?? "";

  const selectedRoles = roleCatalog.filter((role) => formData.selectedRoleIds.includes(role.id));
  const availableRoles = roleCatalog.filter((role) => !formData.selectedRoleIds.includes(role.id));
  const selectedLocations = useMemo(
    () =>
      locations
        .filter((location) => formData.selectedLocationIds.includes(location.id))
        .sort((left, right) => {
          const leftPrimary = left.id === formData.primaryLocationId ? 1 : 0;
          const rightPrimary = right.id === formData.primaryLocationId ? 1 : 0;
          if (leftPrimary !== rightPrimary) {
            return rightPrimary - leftPrimary;
          }
          return locationDisplayName(left).localeCompare(locationDisplayName(right));
        }),
    [formData.primaryLocationId, formData.selectedLocationIds, locations],
  );
  const availableLocations = locations.filter((location) => !formData.selectedLocationIds.includes(location.id));
  const reliability = Math.round((profile?.reliability_score ?? employee.reliability_score ?? 0.7) * 100);
  const reliabilityColor = getReliabilityColor(reliability);
  const statusKey =
    (profile?.status ?? employee.status) in statusConfig
      ? ((profile?.status ?? employee.status) as keyof typeof statusConfig)
      : "active";
  const status = statusConfig[statusKey];
  const name = employeeDisplayName(employee);
  const theme = {
    textPrimary: dark ? "text-white" : "text-[#0A2540]",
    textSecondary: dark ? "text-[#C1CED8]" : "text-[#8898AA]",
    borderClass: dark ? "border-white/[0.06]" : "border-[#F0F0F5]",
    subtleBorderClass: dark ? "border-white/[0.08]" : "border-[#E5E7EB]",
    subtleSurfaceClass: dark ? "bg-white/[0.04]" : "bg-[#F7F8FA]",
    closeButtonClass: dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]",
    inputClass: dark
      ? "border-white/[0.08] bg-white/[0.04] text-white placeholder-[#8898AA]/60"
      : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder-[#8898AA]/50",
    overlayPanelClass: dark ? "bg-[#0F2E4C] border-white/[0.08]" : "bg-white border-[#E5E7EB]",
    subtleSurfacePanelClass: dark ? "bg-white/[0.02]" : "bg-white",
  };

  const dirtyCount = useMemo(() => {
    let count = 0;

    if (email.trim() !== baselineEmail.trim()) {
      count += 1;
    }
    if (phone.trim() !== baselinePhone.trim()) {
      count += 1;
    }
    count += countSelectionChanges(baselineState.selectedRoleIds, formData.selectedRoleIds);
    if (
      formData.selectedRoleIds.length > 0 &&
      formData.primaryRoleId &&
      formData.primaryRoleId !== baselineState.primaryRoleId
    ) {
      count += 1;
    }
    count += countSelectionChanges(
      baselineState.selectedLocationIds,
      formData.selectedLocationIds,
    );
    if (
      formData.selectedLocationIds.length > 0 &&
      formData.primaryLocationId &&
      formData.primaryLocationId !== baselineState.primaryLocationId
    ) {
      count += 1;
    }

    return count;
  }, [
    baselineEmail,
    baselinePhone,
    baselineState.primaryLocationId,
    baselineState.primaryRoleId,
    baselineState.selectedLocationIds,
    baselineState.selectedRoleIds,
    email,
    formData.primaryLocationId,
    formData.primaryRoleId,
    formData.selectedLocationIds,
    formData.selectedRoleIds,
    phone,
  ]);

  const canSave =
    Boolean(formData.primaryRoleId) &&
    Boolean(formData.primaryLocationId) &&
    dirtyCount > 0;

  useEffect(() => {
    if (!feedback || dirtyCount === 0) {
      return;
    }
    setFeedback(null);
  }, [dirtyCount, feedback]);

  const toggleRole = (roleId: string) => {
    setFormData((current) => {
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
    setFormData((current) => {
      const selectedLocationIds = current.selectedLocationIds.includes(locationId)
        ? current.selectedLocationIds.filter((item) => item !== locationId)
        : [...current.selectedLocationIds, locationId];
      const primaryLocationId = selectedLocationIds.includes(current.primaryLocationId)
        ? current.primaryLocationId
        : selectedLocationIds[0] ?? "";
      return { ...current, selectedLocationIds, primaryLocationId };
    });
  };

  const handleAddCustomRole = async () => {
    const trimmed = customRole.trim();
    if (!trimmed) {
      return;
    }

    const existing = roleCatalog.find(
      (role) => role.name.toLowerCase() === trimmed.toLowerCase(),
    );
    if (existing) {
      setFormData((current) => ({
        ...current,
        selectedRoleIds: current.selectedRoleIds.includes(existing.id)
          ? current.selectedRoleIds
          : [...current.selectedRoleIds, existing.id],
        primaryRoleId: current.primaryRoleId || existing.id,
      }));
      setCustomRole("");
      return;
    }

    try {
      setFeedback(null);
      const createdRole = await createBusinessRole(businessId, { name: trimmed });
      setRoleCatalog((current) => [...current, createdRole]);
      onRoleCreated?.(createdRole);
      setFormData((current) => ({
        ...current,
        selectedRoleIds: [...current.selectedRoleIds, createdRole.id],
        primaryRoleId: current.primaryRoleId || createdRole.id,
      }));
      setCustomRole("");
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "Could not create this role.",
      });
    }
  };

  const handleSave = async () => {
    if (!canSave || isSaving) {
      return;
    }

    const pendingChangeCount = dirtyCount;

    try {
      setIsSaving(true);
      setFeedback(null);
      const nextProfile = await updateEmployee(businessId, employee.id, {
        email: email.trim() || null,
        phone_e164: phone.trim() || null,
        roles: formData.selectedRoleIds.map((roleId) => ({
          role_id: roleId,
          is_primary: roleId === formData.primaryRoleId,
        })),
        locations: formData.selectedLocationIds.map((locationId) => ({
          location_id: locationId,
          is_primary: locationId === formData.primaryLocationId,
        })),
      });
      setProfile(nextProfile);
      setFormData(buildAssignmentStateFromProfile(nextProfile));
      setEmail(nextProfile.email ?? "");
      setPhone(nextProfile.phone_e164 ?? "");
      await onSaved(nextProfile);
      setFeedback({
        tone: "success",
        message: `Saved ${pendingChangeCount} change${pendingChangeCount === 1 ? "" : "s"} for ${name}.`,
      });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "Could not update this employee.",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteState.canDelete || deleteState.deleting || !onDeleted) {
      return;
    }

    const confirmed = window.confirm(
      `Remove ${name}? This only works when they are not tied to scheduled shifts.`,
    );
    if (!confirmed) {
      return;
    }

    try {
      setDeleteState((current) => ({ ...current, deleting: true }));
      setFeedback(null);
      await deleteEmployee(businessId, employee.id);
      await onDeleted(employee.id);
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "Could not remove this employee.",
      });
      setDeleteState((current) => ({ ...current, deleting: false }));
    }
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
        className={`flex h-full w-full flex-col overflow-hidden shadow-2xl sm:w-[460px] ${theme.overlayPanelClass}`}
        exit={{ x: 460 }}
        initial={{ x: 460 }}
        onClick={(event) => event.stopPropagation()}
        transition={{ duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }}
      >
        <div className={`shrink-0 border-b px-6 py-5 ${theme.borderClass}`}>
          <div className="mb-4 flex items-center justify-between">
            <button
              className={`rounded-lg p-1.5 transition-colors ${theme.closeButtonClass}`}
              onClick={onClose}
              type="button"
            >
              <X className="text-[#8898AA]" size={18} />
            </button>
            <button
              className="rounded-full bg-[linear-gradient(135deg,#635BFF,#8B5CF6)] px-4 py-2 text-[12px] text-white transition-all duration-300 hover:shadow-[0_0_16px_rgba(99,91,255,0.25)] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canSave || isSaving}
              onClick={() => {
                void handleSave();
              }}
              style={{ fontWeight: 540 }}
              type="button"
            >
              {isSaving
                ? "Saving..."
                : dirtyCount > 0
                  ? `Save ${dirtyCount} Change${dirtyCount === 1 ? "" : "s"}`
                  : "Save Changes"}
            </button>
          </div>
          <div className="flex items-center gap-4">
            <div
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl text-[16px] text-white"
              style={{
                fontWeight: 600,
                background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
              }}
            >
              {employeeInitials(name)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2.5">
                <h2
                  className={`truncate text-[18px] tracking-[-0.01em] ${theme.textPrimary}`}
                  style={{ fontWeight: 600 }}
                >
                  {name}
                </h2>
                <div
                  className="flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5"
                  style={{ background: `${reliabilityColor}12` }}
                >
                  <ShieldCheck size={12} style={{ color: reliabilityColor }} />
                  <span
                    className="text-[12px] tabular-nums"
                    style={{ color: reliabilityColor, fontWeight: 580 }}
                  >
                    {reliability}%
                  </span>
                </div>
              </div>
              <div className="mt-0.5 flex items-center gap-2">
                <span
                  className="rounded-full px-2 py-0.5 text-[11px]"
                  style={{
                    fontWeight: 480,
                    color: status.color,
                    background: `${status.bg}15`,
                  }}
                >
                  {status.label}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
          {feedback ? (
            <div
              className="rounded-xl px-4 py-3 text-[13px]"
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

          <div>
            <h3
              className="mb-3 text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
              style={{ fontWeight: 500 }}
            >
              Contact
            </h3>
            <div className="space-y-3">
              <div>
                <label
                  className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                  style={{ fontWeight: 500 }}
                >
                  Email
                </label>
                <div className="relative">
                  <div className={`absolute left-3 top-1/2 -translate-y-1/2 flex h-7 w-7 items-center justify-center rounded-md ${theme.subtleSurfaceClass}`}>
                    <Mail className="text-[#8898AA]" size={13} />
                  </div>
                  <input
                    className={`w-full rounded-lg border py-2.5 pl-12 pr-3.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${theme.inputClass}`}
                    onChange={(event) => setEmail(event.target.value)}
                    style={{ fontWeight: 440 }}
                    type="email"
                    value={email}
                  />
                </div>
              </div>
              <div>
                <label
                  className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                  style={{ fontWeight: 500 }}
                >
                  Phone
                </label>
                <div className="relative">
                  <div className={`absolute left-3 top-1/2 -translate-y-1/2 flex h-7 w-7 items-center justify-center rounded-md ${theme.subtleSurfaceClass}`}>
                    <Phone className="text-[#8898AA]" size={13} />
                  </div>
                  <input
                    className={`w-full rounded-lg border py-2.5 pl-12 pr-3.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${theme.inputClass}`}
                    onChange={(event) => setPhone(event.target.value)}
                    style={{ fontWeight: 440 }}
                    type="tel"
                    value={phone}
                  />
                </div>
              </div>
            </div>
          </div>

          <div>
            <div className="mb-3 flex items-center justify-between">
              <h3
                className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                Locations
              </h3>
              <span className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 440 }}>
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
                      onRemove={() => toggleLocation(location.id)}
                      onSetPrimary={() =>
                        setFormData((current) => ({
                          ...current,
                          primaryLocationId: location.id,
                        }))
                      }
                      primary={formData.primaryLocationId === location.id}
                    />
                  );
                })}
              </AnimatePresence>
              {!selectedLocations.length ? (
                <p className={`py-2 text-[12px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                  No locations assigned yet. Add from the list below.
                </p>
              ) : null}
            </div>

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

            {!loading && !locations.length ? (
              <div
                className={`rounded-xl border px-4 py-3 text-[12px] ${
                  dark
                    ? "border-white/[0.08] bg-white/[0.03] text-[#C1CED8]"
                    : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"
                }`}
              >
                Add at least one business location first. Employee location assignment should only use locations from this business.
              </div>
            ) : null}

          </div>

          <div>
            <div className="mb-3 flex items-center justify-between">
              <h3
                className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                Roles
              </h3>
              <span className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 440 }}>
                {selectedRoles.length} roles
              </span>
            </div>
            <div className="mb-4 flex flex-wrap gap-2">
              <AnimatePresence>
                {selectedRoles.map((role) => (
                  <motion.div
                    key={role.id}
                    layout
                    animate={{ opacity: 1, scale: 1 }}
                    className="flex items-center gap-1.5 rounded-lg border border-[#635BFF]/15 bg-[#635BFF]/[0.06] py-1.5 pl-3 pr-2"
                    exit={{ opacity: 0, scale: 0.9 }}
                    initial={{ opacity: 0, scale: 0.9 }}
                  >
                    <Tag className="text-[#635BFF]" size={11} />
                    <span className={`text-[12px] ${theme.textPrimary}`} style={{ fontWeight: 480 }}>
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
                ))}
              </AnimatePresence>
              {!selectedRoles.length ? (
                <p className={`py-2 text-[12px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                  No roles assigned yet. Add from the list below.
                </p>
              ) : null}
            </div>

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
                      onClick={() => availableRoles.forEach((role) => toggleRole(role.id))}
                      style={{ fontWeight: 520 }}
                      type="button"
                    >
                      + Add All
                    </button>
                  ) : null}
                </div>
                <div className="mb-4 flex flex-wrap gap-2">
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

            <div>
              <h3
                className="mb-2 text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                Custom Role
              </h3>
              <div className="flex items-center gap-2">
                <input
                  className={`flex-1 rounded-lg border px-3.5 py-2.5 text-[13px] placeholder-[#8898AA]/50 transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${theme.inputClass}`}
                  onChange={(event) => setCustomRole(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void handleAddCustomRole();
                    }
                  }}
                  placeholder="Type a new role name..."
                  style={{ fontWeight: 440 }}
                  type="text"
                  value={customRole}
                />
                <button
                  className="rounded-lg bg-[linear-gradient(135deg,#635BFF,#8B5CF6)] px-3.5 py-2.5 text-[12px] text-white transition-all duration-200 hover:shadow-[0_0_12px_rgba(99,91,255,0.2)] disabled:cursor-not-allowed disabled:opacity-30"
                  disabled={!customRole.trim()}
                  onClick={() => {
                    void handleAddCustomRole();
                  }}
                  style={{ fontWeight: 520 }}
                  type="button"
                >
                  Add
                </button>
              </div>
            </div>
          </div>

          {onDeleted ? (
            <div className={`border-t pt-4 ${theme.borderClass}`}>
              <div className="group relative inline-flex">
                <button
                  className={`flex items-center gap-2 rounded-lg border px-3.5 py-2.5 text-[12px] transition-all ${
                    deleteState.canDelete
                      ? dark
                        ? "border-[#E5484D]/30 text-[#FF8A8A] hover:bg-[#E5484D]/[0.08]"
                        : "border-[#E5484D]/20 text-[#E5484D] hover:bg-[#E5484D]/[0.04]"
                      : dark
                        ? "border-white/[0.08] text-[#8898AA]"
                        : "border-[#E5E7EB] text-[#8898AA]"
                  } disabled:cursor-not-allowed`}
                  disabled={!deleteState.canDelete || deleteState.checking || deleteState.deleting}
                  onClick={() => {
                    void handleDelete();
                  }}
                  style={{ fontWeight: 500 }}
                  type="button"
                >
                  {deleteState.deleting
                    ? "Removing..."
                    : deleteState.checking
                      ? "Checking..."
                      : "Remove Employee"}
                </button>
                {!deleteState.canDelete && deleteState.reason ? (
                  <div
                    className={`pointer-events-none absolute bottom-full left-0 mb-2 w-64 rounded-lg px-3 py-2 text-[11px] opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100 ${
                      dark
                        ? "border border-white/[0.08] bg-[#102B46] text-[#C1CED8]"
                        : "border border-[#E5E7EB] bg-white text-[#5E6D7A]"
                    }`}
                    style={{ fontWeight: 440 }}
                  >
                    <div className="flex items-start gap-2">
                      <AlertCircle className="mt-0.5 shrink-0 text-[#F59E0B]" size={12} />
                      <span>{deleteState.reason}</span>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </motion.div>
    </motion.div>
  );
}
