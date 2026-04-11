"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { MapPin, Phone, Plus, Trash2, X, Info } from "lucide-react";

import type {
  BusinessLocation,
  LocationRoleAssignment,
} from "@/lib/api/businesses";
import type {
  LocationShiftDefaults,
  ShiftDefault,
} from "@/lib/api/workspace";
import type { EmployeeSummary } from "@/lib/api/workforce";

import {
  formatDisplayLabel,
  formatLocationMeta,
  getLocationReference,
} from "./location-role-reference";
import {
  ShiftCoverageTimeline,
  ShiftDefaultsEditor,
} from "./ShiftDefaultsEditor";
import { getShiftCoverageHours, normalizeShiftDefaults } from "./shift-defaults";
import {
  countEmployeeAssignmentChanges,
  employeeAssignedHere,
  employeeDisplayName,
  employeeEligibilityReason,
  employeeHasAssignedRoles,
  employeeInitials,
} from "./location-employee-utils";

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
  employeeChangeCount: number;
  shiftChangeCount: number;
  totalChangeCount: number;
};

export function formatLocationSaveSummary(
  summary: LocationRoleEditorSaveSummary,
  locationName: string,
) {
  const parts: string[] = [];
  if (summary.employeeChangeCount > 0) {
    parts.push(`${summary.employeeChangeCount} employee change${summary.employeeChangeCount === 1 ? "" : "s"}`);
  }
  if (summary.shiftChangeCount > 0) {
    parts.push(`${summary.shiftChangeCount} shift change${summary.shiftChangeCount === 1 ? "" : "s"}`);
  }
  if (!parts.length) {
    return `No changes to save for ${locationName}.`;
  }
  return `Saved ${parts.join(" and ")} for ${locationName}.`;
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

export function LocationRoleEditor({
  dark,
  location,
  businessTypeLabel,
  staffCount,
  employees,
  assignments,
  shiftDefaults,
  loading,
  saving,
  feedback,
  deleteState,
  onClose,
  onDelete,
  onSave,
}: {
  dark: boolean;
  location: BusinessLocation;
  businessTypeLabel?: string | null;
  staffCount?: number | null;
  employees: EmployeeSummary[];
  assignments: LocationRoleAssignment[];
  shiftDefaults: LocationShiftDefaults | null;
  loading: boolean;
  saving: boolean;
  feedback: LocationRoleEditorFeedback;
  deleteState?: LocationDeleteState;
  onClose(): void;
  onDelete?(): void;
  onSave(
    employeeIds: string[],
    locationShiftPresets: ShiftDefault[] | null,
    summary: LocationRoleEditorSaveSummary,
  ): void;
}) {
  const [selectedEmployeeIds, setSelectedEmployeeIds] = useState<string[]>([]);
  const [useBusinessDefaults, setUseBusinessDefaults] = useState(true);
  const [draftShiftDefaults, setDraftShiftDefaults] = useState<ShiftDefault[]>(() =>
    normalizeShiftDefaults(null),
  );
  const [visibleFeedback, setVisibleFeedback] = useState<LocationRoleEditorFeedback>(feedback);
  const [isClosing, setIsClosing] = useState(false);
  const closeTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    setSelectedEmployeeIds(
      employees
        .filter((employee) => employeeAssignedHere(employee, location.id))
        .map((employee) => employee.id),
    );
  }, [employees, location.id]);

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
  const selectedEmployeeSet = useMemo(
    () => new Set(selectedEmployeeIds),
    [selectedEmployeeIds],
  );
  const sortedEmployees = useMemo(
    () =>
      [...employees].sort((left, right) =>
        employeeDisplayName(left).localeCompare(employeeDisplayName(right)),
      ),
    [employees],
  );
  const assignedEmployees = useMemo(
    () => sortedEmployees.filter((employee) => selectedEmployeeSet.has(employee.id)),
    [selectedEmployeeSet, sortedEmployees],
  );
  const availableReadyEmployees = useMemo(
    () =>
      sortedEmployees.filter(
        (employee) =>
          !selectedEmployeeSet.has(employee.id) && employeeHasAssignedRoles(employee),
      ),
    [selectedEmployeeSet, sortedEmployees],
  );
  const availableUnavailableEmployees = useMemo(
    () =>
      sortedEmployees.filter(
        (employee) =>
          !selectedEmployeeSet.has(employee.id) && !employeeHasAssignedRoles(employee),
      ),
    [selectedEmployeeSet, sortedEmployees],
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
  const baselineEmployeeIds = useMemo(
    () =>
      employees
        .filter((employee) => employeeAssignedHere(employee, location.id))
        .map((employee) => employee.id),
    [employees, location.id],
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
  const employeeChangeCount = useMemo(
    () => countEmployeeAssignmentChanges(baselineEmployeeIds, selectedEmployeeIds),
    [baselineEmployeeIds, selectedEmployeeIds],
  );
  const shiftChangeCount = useMemo(
    () => countShiftPresetChanges(effectiveShiftPresets, baselineShiftPresets),
    [baselineShiftPresets, effectiveShiftPresets],
  );
  const totalChangeCount = employeeChangeCount + shiftChangeCount;
  const totalCoverageHours = useMemo(
    () => Math.round(getShiftCoverageHours(effectiveShiftPresets)),
    [effectiveShiftPresets],
  );

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

  const addEmployee = (employeeId: string) => {
    setSelectedEmployeeIds((current) =>
      current.includes(employeeId) ? current : [...current, employeeId],
    );
  };

  const removeEmployee = (employeeId: string) => {
    setSelectedEmployeeIds((current) => current.filter((item) => item !== employeeId));
  };

  const addAllEmployees = () => {
    setSelectedEmployeeIds((current) =>
      Array.from(
        new Set([
          ...current,
          ...availableReadyEmployees.map((employee) => employee.id),
        ]),
      ),
    );
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
                  selectedEmployeeIds,
                  useBusinessDefaults ? null : normalizeShiftDefaults(draftShiftDefaults),
                  {
                    employeeChangeCount,
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
            <div className={`rounded-xl border px-4 py-4 ${subtleSurfaceClass} ${subtleBorderClass}`}>
              <p className={`text-[13px] leading-relaxed ${textSecondary}`} style={{ fontWeight: 420 }}>
                Assign employees here and we will automatically make their existing roles available for scheduling at this location. Removing an employee later does not remove those location roles.
              </p>
            </div>

            <div className="mt-6">
              <div className="mb-3 flex items-center justify-between">
                <h3
                  className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
                  style={{ fontWeight: 500 }}
                >
                  Assigned Employees
                </h3>
                <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                  {assignedEmployees.length} of {employees.length}
                </span>
              </div>
              <div className="flex min-h-[36px] flex-wrap gap-2">
                <AnimatePresence>
                  {assignedEmployees.map((employee) => {
                    const isReady = employeeHasAssignedRoles(employee);
                    return (
                      <motion.div
                        key={employee.id}
                        layout
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.9 }}
                        className={`group flex items-center gap-2 rounded-lg border py-1.5 pl-2.5 pr-2 ${
                          isReady
                            ? dark
                              ? "bg-[#635BFF]/[0.12] border-[#635BFF]/25"
                              : "bg-[#635BFF]/[0.06] border-[#635BFF]/15"
                            : dark
                              ? "border-[#FFB800]/25 bg-[#FFB800]/[0.1]"
                              : "border-[#FFB800]/20 bg-[#FFB800]/[0.06]"
                        }`}
                      >
                        <span
                          className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${
                            isReady
                              ? "bg-[#635BFF]/10 text-[#635BFF]"
                              : "bg-[#FFB800]/10 text-[#FFB800]"
                          }`}
                        >
                          {employeeInitials(employeeDisplayName(employee))}
                        </span>
                        <span
                          className={`truncate text-[12px] ${textPrimary}`}
                          style={{ fontWeight: 480 }}
                        >
                          {employeeDisplayName(employee)}
                        </span>
                        {!isReady ? (
                          <div className="relative ml-0.5">
                            <Info size={12} className="cursor-default text-[#FFB800]" />
                            <div
                              className={`pointer-events-none absolute bottom-full right-0 z-30 mb-2 w-56 rounded-lg px-3 py-2 text-[11px] opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100 ${
                                dark
                                  ? "border border-white/[0.08] bg-[#102B46] text-[#C1CED8]"
                                  : "border border-[#E5E7EB] bg-white text-[#5E6D7A]"
                              }`}
                              style={{ fontWeight: 440 }}
                            >
                              {employeeEligibilityReason(employee)}
                            </div>
                          </div>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => removeEmployee(employee.id)}
                          className="ml-0.5 rounded p-0.5 transition-colors hover:bg-[#635BFF]/10"
                        >
                          <X size={12} className="text-[#8898AA] hover:text-[#E5484D]" />
                        </button>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
                {!loading && assignedEmployees.length === 0 ? (
                  <p className={`text-[12px] py-2 ${textSecondary}`} style={{ fontWeight: 420 }}>
                    No employees assigned yet. Add from the list below.
                  </p>
                ) : null}
                {loading ? (
                  <p className={`text-[12px] py-2 ${textSecondary}`} style={{ fontWeight: 420 }}>
                    Loading business employees...
                  </p>
                ) : null}
              </div>
            </div>

            <div className="mt-6 border-t pt-6">
              <div className="mb-3 flex items-center justify-between">
                <h3
                  className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
                  style={{ fontWeight: 500 }}
                >
                  Available Employees
                </h3>
                {availableReadyEmployees.length > 1 ? (
                  <button
                    type="button"
                    onClick={addAllEmployees}
                    className="text-[11px] text-[#635BFF] hover:text-[#4B3FD9] transition-colors"
                    style={{ fontWeight: 520 }}
                  >
                    + Add all
                  </button>
                ) : null}
              </div>

              {availableReadyEmployees.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {availableReadyEmployees.map((employee) => (
                    <button
                      key={employee.id}
                      type="button"
                      onClick={() => addEmployee(employee.id)}
                      className={`group flex items-center gap-2 rounded-lg border px-3 py-1.5 transition-all duration-200 ${
                        dark
                          ? "bg-white/[0.03] border-white/[0.08] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08]"
                          : "bg-[#F7F8FA] border-[#E5E7EB] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]"
                      }`}
                    >
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#635BFF]/10 text-[10px] text-[#635BFF]">
                        {employeeInitials(employeeDisplayName(employee))}
                      </span>
                      <span
                        className={`text-[12px] transition-colors ${
                          dark
                            ? "text-[#C1CED8] group-hover:text-white"
                            : "text-[#5E6D7A] group-hover:text-[#0A2540]"
                        }`}
                        style={{ fontWeight: 440 }}
                      >
                        {employeeDisplayName(employee)}
                      </span>
                      <Plus
                        size={11}
                        className="ml-0.5 text-[#8898AA] group-hover:text-[#635BFF] transition-colors"
                      />
                    </button>
                  ))}
                </div>
              ) : !loading ? (
                <p className={`text-[12px] py-2 ${textSecondary}`} style={{ fontWeight: 420 }}>
                  All schedule-ready employees are already assigned to this location.
                </p>
              ) : null}

              {availableUnavailableEmployees.length > 0 ? (
                <div className="mt-5">
                  <div className="mb-2.5">
                    <h4
                      className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
                      style={{ fontWeight: 500 }}
                    >
                      Needs role assignment
                    </h4>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {availableUnavailableEmployees.map((employee) => (
                      <div
                        key={employee.id}
                        className={`group relative z-0 flex items-center gap-2 rounded-lg border px-3 py-1.5 text-left transition-all duration-200 hover:z-20 ${
                          dark
                            ? "border-[#FFB800]/25 bg-[#FFB800]/[0.1] hover:bg-[#FFB800]/[0.14]"
                            : "border-[#FFB800]/20 bg-[#FFB800]/[0.06] hover:bg-[#FFB800]/[0.1]"
                        }`}
                      >
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#FFB800]/10 text-[10px] text-[#FFB800]">
                          {employeeInitials(employeeDisplayName(employee))}
                        </span>
                        <span
                          className={`text-[12px] ${textPrimary}`}
                          style={{ fontWeight: 480 }}
                        >
                          {employeeDisplayName(employee)}
                        </span>
                        <div className="relative ml-0.5">
                          <Info size={12} className="cursor-default text-[#FFB800]" />
                          <div
                            className={`pointer-events-none absolute bottom-full right-0 z-30 mb-2 w-56 rounded-lg px-3 py-2 text-[11px] opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100 ${
                              dark
                                ? "border border-white/[0.08] bg-[#102B46] text-[#C1CED8]"
                                : "border border-[#E5E7EB] bg-white text-[#5E6D7A]"
                            }`}
                            style={{ fontWeight: 440 }}
                          >
                            {employeeEligibilityReason(employee)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <div>
            <div className="mb-3 flex items-center justify-between gap-4">
              <h3
                className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
                style={{ fontWeight: 500 }}
              >
                Shifts
              </h3>
              <div className="flex items-center gap-2.5">
                <span className={`text-[11px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 500 }}>
                  {effectiveShiftPresets.length} shifts
                </span>
                <div className={`h-3 w-px ${dark ? "bg-white/[0.08]" : "bg-[#E5E7EB]"}`} />
                <span className={`text-[11px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 500 }}>
                  ~{totalCoverageHours}h total
                </span>
              </div>
            </div>

            <div className="mb-4">
              <ShiftCoverageTimeline compact dark={dark} presets={effectiveShiftPresets} />
            </div>

            <ShiftDefaultsEditor
              compact
              dark={dark}
              onChange={handleShiftDefaultsChange}
              presets={effectiveShiftPresets}
            />

            {!useBusinessDefaults ? (
              <div className="mt-3 flex justify-end">
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
              </div>
            ) : null}
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
