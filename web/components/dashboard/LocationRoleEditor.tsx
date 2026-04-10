"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AlertCircle, Lock, MapPin, Phone, Plus, Tag, Trash2, X } from "lucide-react";

import type {
  BusinessLocation,
  BusinessRole,
  LocationRoleAssignment,
} from "@/lib/api/businesses";
import type {
  LocationShiftDefaults,
  ShiftDefault,
} from "@/lib/api/workspace";

import {
  formatDisplayLabel,
  formatLocationMeta,
  getLocationReference,
} from "./location-role-reference";
import { ShiftDefaultsEditor } from "./ShiftDefaultsEditor";
import { normalizeShiftDefaults } from "./shift-defaults";

export type LocationRoleEditorFeedback = {
  tone: "success" | "error";
  message: string;
} | null;

export type LocationDeleteState = {
  canDelete: boolean;
  checking?: boolean;
  deleting?: boolean;
  reason?: string | null;
};

export type LocationRoleEditorSaveSummary = {
  roleChangeCount: number;
  shiftChangeCount: number;
  totalChangeCount: number;
};

export function formatLocationSaveSummary(
  summary: LocationRoleEditorSaveSummary,
  locationName: string,
) {
  const parts: string[] = [];
  if (summary.roleChangeCount > 0) {
    parts.push(`${summary.roleChangeCount} role change${summary.roleChangeCount === 1 ? "" : "s"}`);
  }
  if (summary.shiftChangeCount > 0) {
    parts.push(`${summary.shiftChangeCount} shift change${summary.shiftChangeCount === 1 ? "" : "s"}`);
  }
  if (!parts.length) {
    return `No changes to save for ${locationName}.`;
  }
  return `Saved ${parts.join(" and ")} for ${locationName}.`;
}

function countRoleChanges(initialRoleIds: string[], nextRoleIds: string[]) {
  const initial = new Set(initialRoleIds);
  const next = new Set(nextRoleIds);
  let count = 0;

  initial.forEach((roleId) => {
    if (!next.has(roleId)) {
      count += 1;
    }
  });
  next.forEach((roleId) => {
    if (!initial.has(roleId)) {
      count += 1;
    }
  });

  return count;
}

function countShiftPresetChanges(left: ShiftDefault[], right: ShiftDefault[]) {
  const normalizedLeft = normalizeShiftDefaults(left);
  const normalizedRight = normalizeShiftDefaults(right);
  let count = 0;

  normalizedLeft.forEach((preset, index) => {
    const baselinePreset = normalizedRight[index];
    if (!baselinePreset) {
      count += 1;
      return;
    }
    if (
      preset.label !== baselinePreset.label ||
      preset.start_hour !== baselinePreset.start_hour ||
      preset.end_hour !== baselinePreset.end_hour
    ) {
      count += 1;
    }
  });

  return count;
}

function RoleTag({
  dark,
  role,
  locked = false,
  lockedShiftCount = 0,
  onRemove,
}: {
  dark: boolean;
  role: BusinessRole;
  locked?: boolean;
  lockedShiftCount?: number;
  onRemove(): void;
}) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      className={`flex items-center gap-1.5 pl-3 pr-2 py-1.5 rounded-lg border ${
        locked
          ? dark
            ? "bg-[#FFB800]/[0.1] border-[#FFB800]/25"
            : "bg-[#FFB800]/[0.06] border-[#FFB800]/20"
          : dark
            ? "bg-[#635BFF]/[0.12] border-[#635BFF]/25"
            : "bg-[#635BFF]/[0.06] border-[#635BFF]/15"
      }`}
    >
      <Tag size={11} className={locked ? "text-[#FFB800]" : "text-[#635BFF]"} />
      <span
        className={`text-[12px] ${dark ? "text-white" : "text-[#0A2540]"}`}
        style={{ fontWeight: 480 }}
      >
        {role.name}
      </span>
      {locked ? (
        <div
          className="ml-0.5 p-0.5"
          title={
            lockedShiftCount === 1
              ? "This role has 1 active shift and cannot be removed."
              : `This role has ${lockedShiftCount} active shifts and cannot be removed.`
          }
        >
          <Lock size={12} className="text-[#FFB800]" />
        </div>
      ) : (
        <button
          type="button"
          onClick={onRemove}
          className="p-0.5 rounded hover:bg-[#635BFF]/10 transition-colors ml-0.5"
        >
          <X size={12} className="text-[#8898AA] hover:text-[#E5484D]" />
        </button>
      )}
    </motion.div>
  );
}

export function LocationRoleEditor({
  dark,
  location,
  businessTypeLabel,
  staffCount,
  roles,
  assignments,
  shiftDefaults,
  loading,
  saving,
  feedback,
  deleteState,
  onClose,
  onDelete,
  onSave,
  onCreateRole,
}: {
  dark: boolean;
  location: BusinessLocation;
  businessTypeLabel?: string | null;
  staffCount?: number | null;
  roles: BusinessRole[];
  assignments: LocationRoleAssignment[];
  shiftDefaults: LocationShiftDefaults | null;
  loading: boolean;
  saving: boolean;
  feedback: LocationRoleEditorFeedback;
  deleteState?: LocationDeleteState;
  onClose(): void;
  onDelete?(): void;
  onSave(
    roleIds: string[],
    locationShiftPresets: ShiftDefault[] | null,
    summary: LocationRoleEditorSaveSummary,
  ): void;
  onCreateRole(name: string): Promise<BusinessRole>;
}) {
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);
  const [customRole, setCustomRole] = useState("");
  const [isCreatingRole, setIsCreatingRole] = useState(false);
  const [useBusinessDefaults, setUseBusinessDefaults] = useState(true);
  const [draftShiftDefaults, setDraftShiftDefaults] = useState<ShiftDefault[]>(() =>
    normalizeShiftDefaults(null),
  );
  const [visibleFeedback, setVisibleFeedback] = useState<LocationRoleEditorFeedback>(feedback);
  const [isClosing, setIsClosing] = useState(false);
  const closeTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    setSelectedRoleIds(assignments.map((assignment) => assignment.role_id));
  }, [assignments, location.id]);

  useEffect(() => {
    if (!shiftDefaults) {
      setUseBusinessDefaults(true);
      setDraftShiftDefaults(normalizeShiftDefaults(null));
      return;
    }
    setUseBusinessDefaults(!shiftDefaults.has_overrides);
    setDraftShiftDefaults(
      normalizeShiftDefaults(
        shiftDefaults.override_presets ?? shiftDefaults.business_presets,
      ),
    );
  }, [location.id, shiftDefaults]);

  useEffect(() => {
    setVisibleFeedback(feedback);
  }, [feedback]);

  useEffect(() => {
    setIsClosing(false);
  }, [location.id]);

  useEffect(
    () => () => {
      if (closeTimeoutRef.current !== null) {
        window.clearTimeout(closeTimeoutRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    if (!visibleFeedback) {
      return;
    }
    const timeoutId = window.setTimeout(() => setVisibleFeedback(null), 4000);
    return () => window.clearTimeout(timeoutId);
  }, [visibleFeedback]);

  const locationReference = getLocationReference({
    ...location,
    name: location.display_name ?? location.name,
  });
  const locationAddress = formatLocationMeta(location) || null;
  const googlePlaceMetadata =
    location.google_place_metadata && typeof location.google_place_metadata === "object"
      ? (location.google_place_metadata as Record<string, unknown>)
      : null;
  const locationPhone =
    (typeof googlePlaceMetadata?.international_phone_number === "string"
      ? googlePlaceMetadata.international_phone_number
      : null) ??
    (typeof googlePlaceMetadata?.national_phone_number === "string"
      ? googlePlaceMetadata.national_phone_number
      : null);
  const placeTypeLabel =
    typeof googlePlaceMetadata?.primary_type_display_name === "string"
      ? googlePlaceMetadata.primary_type_display_name
      : null;
  const resolvedTypeLabel = businessTypeLabel
    ? formatDisplayLabel(businessTypeLabel)
    : placeTypeLabel;
  const resolvedStaffLabel =
    typeof staffCount === "number" ? `${staffCount} staff` : null;
  const assignmentsByRoleId = useMemo(
    () => new Map(assignments.map((assignment) => [assignment.role_id, assignment])),
    [assignments],
  );
  const selectedRoles = roles.filter((role) => selectedRoleIds.includes(role.id));
  const availableRoles = roles.filter((role) => !selectedRoleIds.includes(role.id));
  const lockedRoles = selectedRoles.filter(
    (role) => assignmentsByRoleId.get(role.id)?.is_locked,
  );
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#8898AA]";
  const textTertiary = dark ? "text-[#C1CED8]" : "text-[#3E4C59]";
  const borderClass = dark ? "border-white/[0.06]" : "border-[#F0F0F5]";
  const subtleBorderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const subtleSurfaceClass = dark ? "bg-white/[0.04]" : "bg-[#F7F8FA]";
  const deleteTooltip = deleteState?.canDelete
    ? null
    : deleteState?.reason ?? "This location cannot be removed right now.";
  const baselineRoleIds = useMemo(
    () => assignments.map((assignment) => assignment.role_id),
    [assignments],
  );
  const baselineShiftPresets = useMemo(
    () =>
      normalizeShiftDefaults(
        shiftDefaults?.has_overrides
          ? shiftDefaults.override_presets ?? shiftDefaults.business_presets
          : shiftDefaults?.business_presets ?? null,
      ),
    [shiftDefaults],
  );
  const effectiveShiftPresets = useMemo(
    () =>
      normalizeShiftDefaults(
        useBusinessDefaults
          ? shiftDefaults?.business_presets ?? baselineShiftPresets
          : draftShiftDefaults,
      ),
    [baselineShiftPresets, draftShiftDefaults, shiftDefaults, useBusinessDefaults],
  );
  const roleChangeCount = useMemo(
    () => countRoleChanges(baselineRoleIds, selectedRoleIds),
    [baselineRoleIds, selectedRoleIds],
  );
  const shiftChangeCount = useMemo(
    () => countShiftPresetChanges(effectiveShiftPresets, baselineShiftPresets),
    [baselineShiftPresets, effectiveShiftPresets],
  );
  const totalChangeCount = roleChangeCount + shiftChangeCount;

  useEffect(() => {
    if (totalChangeCount > 0 && visibleFeedback) {
      setVisibleFeedback(null);
    }
  }, [totalChangeCount, visibleFeedback]);

  const handleDismiss = useCallback(() => {
    if (isClosing) {
      return;
    }
    setIsClosing(true);
    closeTimeoutRef.current = window.setTimeout(() => {
      closeTimeoutRef.current = null;
      onClose();
    }, 210);
  }, [isClosing, onClose]);

  const handleShiftDefaultsChange = (nextPresets: ShiftDefault[]) => {
    setUseBusinessDefaults(false);
    setDraftShiftDefaults(normalizeShiftDefaults(nextPresets));
  };

  const addRole = (roleId: string) => {
    setSelectedRoleIds((current) =>
      current.includes(roleId) ? current : [...current, roleId],
    );
  };

  const removeRole = (roleId: string) => {
    if (assignmentsByRoleId.get(roleId)?.is_locked) {
      return;
    }
    setSelectedRoleIds((current) => current.filter((item) => item !== roleId));
  };

  const addAllRoles = () => {
    setSelectedRoleIds(roles.map((role) => role.id));
  };

  const addCustomRole = async () => {
    const trimmed = customRole.trim();
    if (!trimmed) {
      return;
    }

    try {
      setIsCreatingRole(true);
      const createdRole = await onCreateRole(trimmed);
      addRole(createdRole.id);
      setCustomRole("");
    } finally {
      setIsCreatingRole(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: isClosing ? 0 : 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18, ease: [0.4, 0, 0.2, 1] }}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm"
      onClick={handleDismiss}
    >
      <motion.div
        initial={{ x: 460 }}
        animate={{ x: isClosing ? 460 : 0 }}
        exit={{ x: 460 }}
        transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
        className={`w-full sm:w-[460px] h-full shadow-2xl flex flex-col overflow-hidden ${
          dark ? "bg-[#0F2E4C]" : "bg-white"
        } ${isClosing ? "pointer-events-none" : ""}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className={`px-6 py-5 border-b shrink-0 ${borderClass}`}>
          <div className="flex items-center justify-between mb-4">
            <button
              type="button"
              onClick={handleDismiss}
              className={`p-1.5 rounded-lg transition-colors ${
                dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"
              }`}
            >
              <X size={18} className="text-[#8898AA]" />
            </button>
            <button
              type="button"
              onClick={() =>
                onSave(
                  selectedRoleIds,
                  useBusinessDefaults ? null : normalizeShiftDefaults(draftShiftDefaults),
                  {
                    roleChangeCount,
                    shiftChangeCount,
                    totalChangeCount,
                  },
                )
              }
              disabled={loading || saving || totalChangeCount === 0}
              className="px-4 py-2 rounded-full text-[12px] text-white transition-all duration-300 hover:shadow-[0_0_16px_rgba(99,91,255,0.25)] disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                fontWeight: 540,
                background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
              }}
            >
              {saving
                ? "Saving..."
                : totalChangeCount > 0
                  ? `Save ${totalChangeCount} Change${totalChangeCount === 1 ? "" : "s"}`
                  : "Save Changes"}
            </button>
          </div>
          <div className="flex items-center gap-4">
            <div
              className="w-14 h-14 rounded-2xl flex items-center justify-center text-[28px]"
              style={{ background: `${locationReference.color}10` }}
            >
              {locationReference.logo}
            </div>
            <div className="min-w-0">
              <h2
                className={`text-[18px] tracking-[-0.01em] ${textPrimary}`}
                style={{ fontWeight: 600 }}
              >
                {location.display_name ?? location.name}
              </h2>
              <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                {resolvedTypeLabel ? (
                  <span
                    className="text-[12px] px-2 py-0.5 rounded-full"
                    style={{
                      fontWeight: 500,
                      color: locationReference.color,
                      background: `${locationReference.color}10`,
                    }}
                  >
                    {resolvedTypeLabel}
                  </span>
                ) : null}
                {resolvedStaffLabel ? (
                  <span
                    className={`text-[11px] ${textSecondary}`}
                    style={{ fontWeight: 420 }}
                  >
                    {resolvedStaffLabel}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          <div className="mt-4 space-y-2">
            {locationAddress ? (
              <div className="flex items-center gap-3">
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center ${subtleSurfaceClass}`}
                >
                  <MapPin size={14} className="text-[#8898AA]" />
                </div>
                <span className={`text-[13px] ${textTertiary}`} style={{ fontWeight: 440 }}>
                  {locationAddress}
                </span>
              </div>
            ) : null}
            {locationPhone ? (
              <div className="flex items-center gap-3">
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center ${subtleSurfaceClass}`}
                >
                  <Phone size={14} className="text-[#8898AA]" />
                </div>
                <span className={`text-[13px] ${textTertiary}`} style={{ fontWeight: 440 }}>
                  {locationPhone}
                </span>
              </div>
            ) : null}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {visibleFeedback ? (
            <div
              className="rounded-xl px-4 py-3 text-[13px]"
              role="status"
              style={{
                background:
                  visibleFeedback.tone === "success"
                    ? "rgba(0, 184, 147, 0.08)"
                    : "rgba(229, 72, 77, 0.08)",
                color: visibleFeedback.tone === "success" ? "#067A64" : "#C13535",
                fontWeight: 500,
              }}
            >
              {visibleFeedback.message}
            </div>
          ) : null}

          <div>
            <div className="flex items-center justify-between mb-3">
              <h3
                className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
                style={{ fontWeight: 500 }}
              >
                Active Roles
              </h3>
              <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                {selectedRoles.length} roles
              </span>
            </div>
            <div className="flex flex-wrap gap-2 mb-4">
              <AnimatePresence>
                {selectedRoles.map((role) => {
                  const assignment = assignmentsByRoleId.get(role.id);
                  return (
                    <RoleTag
                      key={role.id}
                      dark={dark}
                      role={role}
                      locked={assignment?.is_locked ?? false}
                      lockedShiftCount={assignment?.assigned_shift_count ?? 0}
                      onRemove={() => removeRole(role.id)}
                    />
                  );
                })}
              </AnimatePresence>
              {!loading && selectedRoles.length === 0 ? (
                <p className={`text-[12px] py-2 ${textSecondary}`} style={{ fontWeight: 420 }}>
                  No roles assigned yet. Add from the list below.
                </p>
              ) : null}
              {loading ? (
                <p className={`text-[12px] py-2 ${textSecondary}`} style={{ fontWeight: 420 }}>
                  Loading location roles...
                </p>
              ) : null}
            </div>

            {lockedRoles.length > 0 ? (
              <div
                className={`mb-4 rounded-lg border px-3 py-3 ${
                  dark
                    ? "border-[#FFB800]/20 bg-[#FFB800]/[0.08]"
                    : "border-[#FFB800]/15 bg-[#FFB800]/[0.04]"
                }`}
              >
                <div className="flex items-start gap-2.5">
                  <AlertCircle size={14} className="mt-0.5 shrink-0 text-[#FFB800]" />
                  <div>
                    <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                      Protected roles
                    </p>
                    <p className={`mt-0.5 text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                      {lockedRoles.length === 1
                        ? "1 role has active shifts and cannot be removed until those shifts are reassigned or deleted."
                        : `${lockedRoles.length} roles have active shifts and cannot be removed until those shifts are reassigned or deleted.`}
                    </p>
                  </div>
                </div>
              </div>
            ) : null}

            {availableRoles.length > 0 ? (
              <div>
                <div className="flex items-center justify-between mb-2.5">
                  <h3
                    className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
                    style={{ fontWeight: 500 }}
                  >
                    Available Roles
                  </h3>
                  <button
                    type="button"
                    onClick={addAllRoles}
                    className="text-[11px] text-[#635BFF] hover:text-[#4B3FD9] transition-colors"
                    style={{ fontWeight: 520 }}
                  >
                    + Add All
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {availableRoles.map((role) => (
                    <button
                      key={role.id}
                      type="button"
                      onClick={() => addRole(role.id)}
                      className={`group flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all duration-200 ${
                        dark
                          ? "bg-white/[0.03] border-white/[0.08] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08]"
                          : "bg-[#F7F8FA] border-[#E5E7EB] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]"
                      }`}
                    >
                      <Tag size={11} className="text-[#635BFF]" />
                      <span
                        className={`text-[12px] transition-colors ${
                          dark
                            ? "text-[#C1CED8] group-hover:text-white"
                            : "text-[#5E6D7A] group-hover:text-[#0A2540]"
                        }`}
                        style={{ fontWeight: 440 }}
                      >
                        {role.name}
                      </span>
                      <Plus
                        size={11}
                        className="ml-0.5 text-[#8898AA] group-hover:text-[#635BFF] transition-colors"
                      />
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {!loading && roles.length === 0 ? (
              <div className={`rounded-xl border px-4 py-4 ${subtleBorderClass} ${subtleSurfaceClass}`}>
                <p
                  className={`text-[12px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`}
                  style={{ fontWeight: 440 }}
                >
                  This business does not have any roles yet. Business roles are the source of truth for location assignments.
                </p>
              </div>
            ) : null}

            <div>
              <h3
                className={`text-[11px] uppercase tracking-[0.04em] mb-2 ${textSecondary}`}
                style={{ fontWeight: 500 }}
              >
                Custom Role
              </h3>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={customRole}
                  onChange={(event) => setCustomRole(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void addCustomRole();
                    }
                  }}
                  placeholder="Type a new role name..."
                  className={`flex-1 px-3.5 py-2.5 rounded-lg border text-[13px] placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${
                    dark
                      ? "border-white/[0.08] bg-white/[0.04] text-white"
                      : "border-[#E5E7EB] bg-white text-[#0A2540]"
                  }`}
                  style={{ fontWeight: 440 }}
                />
                <button
                  type="button"
                  onClick={() => void addCustomRole()}
                  disabled={!customRole.trim() || isCreatingRole}
                  className="px-3.5 py-2.5 rounded-lg text-[12px] text-white transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed hover:shadow-[0_0_12px_rgba(99,91,255,0.2)]"
                  style={{
                    fontWeight: 520,
                    background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
                  }}
                >
                  {isCreatingRole ? "Adding..." : "Add"}
                </button>
              </div>
            </div>
          </div>

          <div>
            <div className="mb-3 flex items-start justify-between gap-4">
              <div>
                <h3
                  className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
                  style={{ fontWeight: 500 }}
                >
                  Shift Overrides
                </h3>
                <p
                  className={`mt-1 text-[12px] ${textSecondary}`}
                  style={{ fontWeight: 420 }}
                >
                  This location uses the business defaults unless you customize them here. Changes only affect future shifts created for this location.
                </p>
              </div>
              {!useBusinessDefaults ? (
                <button
                  type="button"
                  onClick={() => {
                    setUseBusinessDefaults(true);
                    setDraftShiftDefaults(
                      normalizeShiftDefaults(shiftDefaults?.business_presets ?? null),
                    );
                  }}
                  className="shrink-0 text-[11px] text-[#635BFF] transition-colors hover:text-[#4B3FD9]"
                  style={{ fontWeight: 520 }}
                >
                  Reset to business defaults
                </button>
              ) : null}
            </div>

            <div
              className={`rounded-xl border p-3 ${
                dark ? "border-white/[0.08] bg-white/[0.03]" : "border-[#E5E7EB] bg-[#F7F8FA]"
              }`}
            >
              <div className="mb-3 flex items-center justify-between gap-4">
                <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                  {useBusinessDefaults
                    ? "Using business defaults"
                    : "Location-specific overrides"}
                </p>
                <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                  {useBusinessDefaults ? "Inheriting" : "Override enabled"}
                </span>
              </div>

              <ShiftDefaultsEditor
                dark={dark}
                onChange={handleShiftDefaultsChange}
                presets={
                  useBusinessDefaults
                    ? shiftDefaults?.business_presets ?? draftShiftDefaults
                    : draftShiftDefaults
                }
              />
            </div>
          </div>

          <div className={`border-t pt-4 ${borderClass}`}>
            <div className="relative inline-flex group">
              <button
                type="button"
                disabled={!deleteState?.canDelete || deleteState?.checking || deleteState?.deleting}
                onClick={onDelete}
                className={`flex items-center gap-2 rounded-lg border px-3.5 py-2.5 text-[12px] transition-all ${
                  deleteState?.canDelete
                    ? dark
                      ? "border-[#E5484D]/30 text-[#FF8A8A] hover:bg-[#E5484D]/[0.08]"
                      : "border-[#E5484D]/20 text-[#E5484D] hover:bg-[#E5484D]/[0.04]"
                    : dark
                      ? "border-white/[0.08] text-[#8898AA]"
                      : "border-[#E5E7EB] text-[#8898AA]"
                } disabled:cursor-not-allowed`}
                style={{ fontWeight: 500 }}
              >
                <Trash2 size={13} />
                {deleteState?.deleting
                  ? "Removing..."
                  : deleteState?.checking
                    ? "Checking..."
                    : "Remove Location"}
              </button>

              {!deleteState?.canDelete && deleteTooltip ? (
                <div
                  className={`pointer-events-none absolute bottom-full left-0 mb-2 w-64 rounded-lg px-3 py-2 text-[11px] opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100 ${
                    dark
                      ? "border border-white/[0.08] bg-[#102B46] text-[#C1CED8]"
                      : "border border-[#E5E7EB] bg-white text-[#5E6D7A]"
                  }`}
                  style={{ fontWeight: 440 }}
                >
                  {deleteTooltip}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
