"use client";

import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  Info,
  Plus,
  Upload,
  X,
} from "lucide-react";

import { useResolvedAppAppearance } from "@/components/app-session-gate";
import { useSetLocationEntryMode } from "@/components/location-entry-provider";
import type { WorkspaceLocation } from "@/lib/api/workspace";
import {
  buildDashboardLocationBasePathFromAny,
  buildLocationEmployeeEditPathFromAny,
  buildSchedulerBasePathFromAny,
} from "@/lib/dashboard-paths";
import {
  getLocationRoles,
  listBusinessLocations,
  listBusinessRoles,
  replaceLocationRoles,
  type BusinessLocation,
  type BusinessRole,
  type LocationRoleAssignment,
} from "@/lib/api/businesses";
import {
  listEmployees,
  updateEmployee,
  type EmployeeProfile,
  type EmployeeSummary,
} from "@/lib/api/workforce";
import DashboardShell from "./DashboardShell";
import { EmployeeEditorDrawer } from "./EmployeeEditorDrawer";
import {
  LocationEmployeeBulkUploadModal,
  LocationEmployeeEnrollmentModal,
} from "./LocationEmployeeActions";
import {
  formatLocationMeta,
  getLocationReference,
} from "./location-role-reference";
import {
  buildEmployeeLocationAssignments,
  buildInheritedLocationRoleIds,
  employeeAssignedHere,
  employeeDisplayName,
  employeeEligibilityReason,
  employeeHasAssignedRoles,
  employeeInitials,
  mergeUpdatedEmployees,
} from "./location-employee-utils";

type Feedback = {
  tone: "success" | "error";
  message: string;
} | null;

type LocationProps = {
  embeddedInShell?: boolean;
  location: WorkspaceLocation;
  backHref?: string;
  editingEmployeeId?: string | null;
};

function adaptWorkspaceLocation(location: WorkspaceLocation): BusinessLocation {
  return {
    id: location.location_id,
    business_id: location.business_id,
    name: location.location_name,
    display_name: location.location_display_name ?? location.location_name,
    slug: location.location_slug,
    address_line_1: location.address_line_1 ?? null,
    address_line_2: null,
    locality: location.locality ?? null,
    region: location.region ?? null,
    postal_code: location.postal_code ?? null,
    country_code: location.country_code,
    timezone: location.timezone,
    latitude: null,
    longitude: null,
    google_place_id: location.google_place_id ?? null,
    google_place_metadata: {},
    is_active: true,
    settings: {},
    created_at: "",
    updated_at: "",
  };
}

export default function Location({
  embeddedInShell = false,
  location,
  backHref = "/dashboard",
  editingEmployeeId = null,
}: LocationProps) {
  const router = useRouter();
  const isDark = useResolvedAppAppearance() === "dark";
  const setLocationEntryMode = useSetLocationEntryMode();
  const locationDisplayName = location.location_display_name ?? location.location_name;
  const [roles, setRoles] = useState<BusinessRole[]>([]);
  const [businessLocations, setBusinessLocations] = useState<BusinessLocation[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [assignments, setAssignments] = useState<LocationRoleAssignment[]>([]);
  const [selectedEmployeeIds, setSelectedEmployeeIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [editingEmployee, setEditingEmployee] = useState<EmployeeSummary | null>(null);
  const [showAddEmployeeModal, setShowAddEmployeeModal] = useState(false);
  const [showBulkUploadModal, setShowBulkUploadModal] = useState(false);
  const [isPending, startTransition] = useTransition();

  const closeEmployeeEditor = useCallback(() => {
    setEditingEmployee(null);
    router.replace(buildDashboardLocationBasePathFromAny(location), {
      scroll: false,
    });
  }, [location, router]);

  useEffect(() => {
    if (!feedback) {
      return;
    }
    const timeoutId = window.setTimeout(() => setFeedback(null), 4000);
    return () => window.clearTimeout(timeoutId);
  }, [feedback]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setFeedback(null);
        const [nextRoles, nextLocations, nextEmployees, nextAssignments] = await Promise.all([
          listBusinessRoles(location.business_id),
          listBusinessLocations(location.business_id),
          listEmployees(location.business_id),
          getLocationRoles(location.business_id, location.location_id),
        ]);
        if (cancelled) {
          return;
        }
        setRoles(nextRoles);
        setBusinessLocations(nextLocations.filter((item) => item.is_active));
        setEmployees(nextEmployees);
        setAssignments(nextAssignments);
        setSelectedEmployeeIds(
          nextEmployees
            .filter((employee) => employeeAssignedHere(employee, location.location_id))
            .map((employee) => employee.id),
        );
      } catch (error) {
        if (!cancelled) {
          setFeedback({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Could not load the location setup.",
          });
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [location.business_id, location.location_id]);

  useEffect(() => {
    if (!editingEmployeeId) {
      setEditingEmployee(null);
      return;
    }

    const nextEmployee =
      employees.find((employee) => employee.id === editingEmployeeId) ?? null;

    if (nextEmployee) {
      setEditingEmployee((current) =>
        current?.id === nextEmployee.id ? current : nextEmployee,
      );
      return;
    }

    if (!loading) {
      setEditingEmployee(null);
      router.replace(buildDashboardLocationBasePathFromAny(location), {
        scroll: false,
      });
    }
  }, [editingEmployeeId, employees, loading, location, router]);

  useEffect(() => {
    setSelectedEmployeeIds((current) =>
      current.filter((employeeId) =>
        employees.some((employee) => employee.id === employeeId),
      ),
    );
  }, [employees]);

  const assignmentsByRoleId = useMemo(
    () => new Map(assignments.map((assignment) => [assignment.role_id, assignment])),
    [assignments],
  );
  const selectedEmployeeSet = useMemo(
    () => new Set(selectedEmployeeIds),
    [selectedEmployeeIds],
  );
  const effectiveBusinessLocations = useMemo(
    () =>
      businessLocations.length > 0
        ? businessLocations
        : [adaptWorkspaceLocation(location)],
    [businessLocations, location],
  );
  const sortedEmployees = useMemo(
    () =>
      [...employees].sort((left, right) =>
        employeeDisplayName(left).localeCompare(employeeDisplayName(right)),
      ),
    [employees],
  );
  const selectedEmployees = useMemo(
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
  const inheritedRoleIds = useMemo(
    () => buildInheritedLocationRoleIds(assignments, employees, selectedEmployeeIds),
    [assignments, employees, selectedEmployeeIds],
  );
  const locationReference = getLocationReference({
    name: locationDisplayName,
    slug: location.location_slug,
  });
  const locationMeta =
    formatLocationMeta({ ...location, name: locationDisplayName }) ||
    location.timezone ||
    locationReference.staffLabel;
  const textPrimary = isDark ? "text-white" : "text-[#0A2540]";
  const textSecondary = isDark ? "text-[#C1CED8]" : "text-[#8898AA]";
  const textTertiary = isDark ? "text-[#C1CED8]" : "text-[#3E4C59]";
  const panelClass = isDark
    ? "bg-[#0F2E4C] border-white/[0.06] shadow-[0_18px_48px_rgba(0,0,0,0.28)]"
    : "bg-white border-[#E5E7EB] shadow-[0_1px_3px_rgba(0,0,0,0.04)]";
  const borderClass = isDark ? "border-white/[0.06]" : "border-[#F0F0F5]";
  const subtleBorderClass = isDark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const subtleSurfaceClass = isDark ? "bg-white/[0.04]" : "bg-[#F7F8FA]";
  const footerSurfaceClass = isDark ? "bg-white/[0.03]" : "bg-[#FAFBFC]";
  const chipClass = isDark
    ? "bg-[#635BFF]/[0.12] border-[#635BFF]/25"
    : "bg-[#635BFF]/[0.06] border-[#635BFF]/15";

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

  const handleEmployeeSaved = async (nextEmployee: EmployeeProfile) => {
    setEmployees((current) =>
      current.map((employee) =>
        employee.id === nextEmployee.id ? nextEmployee : employee,
      ),
    );
    setSelectedEmployeeIds((current) => {
      const assignedToLocation = employeeAssignedHere(nextEmployee, location.location_id);
      if (assignedToLocation) {
        return current.includes(nextEmployee.id)
          ? current
          : [...current, nextEmployee.id];
      }
      return current.filter((item) => item !== nextEmployee.id);
    });
    setEditingEmployee(nextEmployee);
  };

  const handleEmployeeDeleted = async (employeeId: string) => {
    setEmployees((current) => current.filter((employee) => employee.id !== employeeId));
    setSelectedEmployeeIds((current) => current.filter((item) => item !== employeeId));
    closeEmployeeEditor();
    setFeedback({
      tone: "success",
      message: "Employee removed from the roster.",
    });
  };

  const handleBusinessRoleCreated = (role: BusinessRole) => {
    setRoles((current) =>
      current.some((item) => item.id === role.id) ? current : [...current, role],
    );
  };

  const handleEmployeeCreated = async (nextEmployee: EmployeeSummary) => {
    setEmployees((current) => {
      const existing = current.some((employee) => employee.id === nextEmployee.id);
      if (existing) {
        return current.map((employee) =>
          employee.id === nextEmployee.id ? nextEmployee : employee,
        );
      }
      return [nextEmployee, ...current];
    });
    setSelectedEmployeeIds((current) =>
      current.includes(nextEmployee.id)
        ? current
        : [...current, nextEmployee.id],
    );
    setFeedback({
      tone: "success",
      message: `${nextEmployee.full_name} was added to ${locationDisplayName}.`,
    });
  };

  const handleEmployeesImported = async (
    importedEmployees: EmployeeSummary[],
    createdCount: number,
    skippedCount: number,
  ) => {
    const importedById = new Map(
      importedEmployees.map((employee) => [employee.id, employee]),
    );
    setEmployees((current) => {
      const next = current.map(
        (employee) => importedById.get(employee.id) ?? employee,
      );
      const missing = importedEmployees.filter(
        (employee) => !current.some((existing) => existing.id === employee.id),
      );
      return [...missing, ...next];
    });
    setSelectedEmployeeIds((current) =>
      Array.from(new Set([...current, ...importedEmployees.map((employee) => employee.id)])),
    );
    setFeedback({
      tone: "success",
      message: `Imported ${createdCount} employee${createdCount === 1 ? "" : "s"} into ${locationDisplayName}${skippedCount ? `, skipped ${skippedCount}` : ""}.`,
    });
  };

  const handleContinue = () => {
    if (!selectedEmployeeIds.length || inheritedRoleIds.length === 0) {
      return;
    }

    startTransition(async () => {
      try {
        setFeedback(null);
        const nextAssignments = await replaceLocationRoles(
          location.business_id,
          location.location_id,
          inheritedRoleIds.map((roleId) => {
            const existing = assignmentsByRoleId.get(roleId);
            return existing
              ? {
                  role_id: roleId,
                  min_headcount: existing.min_headcount,
                  max_headcount: existing.max_headcount,
                  premium_rules: existing.premium_rules,
                  coverage_settings: existing.coverage_settings,
                }
              : { role_id: roleId };
          }),
        );
        const changedEmployees = employees.filter((employee) => {
          const currentlyAssigned = employeeAssignedHere(employee, location.location_id);
          const shouldBeAssigned = selectedEmployeeIds.includes(employee.id);
          return currentlyAssigned !== shouldBeAssigned;
        });
        const updatedEmployees = await Promise.all(
          changedEmployees.map((employee) =>
            updateEmployee(location.business_id, employee.id, {
              locations: buildEmployeeLocationAssignments(
                employee,
                location.location_id,
                selectedEmployeeIds.includes(employee.id),
              ),
            }),
          ),
        );
        setAssignments(nextAssignments);
        setEmployees((current) => mergeUpdatedEmployees(current, updatedEmployees));
        setLocationEntryMode(
          location.location_id,
          nextAssignments.length > 0 && selectedEmployeeIds.length > 0
            ? "scheduler"
            : "setup",
        );
        router.push(buildSchedulerBasePathFromAny(location));
      } catch (error) {
        setFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not update this location.",
        });
      }
    });
  };

  const content = (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className="mb-8">
        <button
          type="button"
          onClick={() => router.push(backHref)}
          className={`mb-4 flex items-center gap-1.5 text-[12px] transition-colors ${textSecondary} ${isDark ? "hover:text-white" : "hover:text-[#5E6D7A]"}`}
          style={{ fontWeight: 440 }}
        >
          <ChevronLeft size={14} />
          Back to Overview
        </button>

        <div className="flex items-center gap-4 mb-2">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center text-[28px]"
            style={{ background: `${locationReference.color}10` }}
          >
            {locationReference.logo}
          </div>
          <div>
            <h1
              className={`text-[24px] sm:text-[28px] md:text-[32px] tracking-[-0.025em] ${textPrimary}`}
              style={{ fontWeight: 620 }}
            >
              {locationDisplayName}
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              {locationReference.typeLabel ? (
                <span
                  className="text-[12px] px-2.5 py-0.5 rounded-full"
                  style={{
                    fontWeight: 500,
                    color: locationReference.color,
                    background: `${locationReference.color}10`,
                  }}
                >
                  {locationReference.typeLabel}
                </span>
              ) : null}
              <span className={`text-[13px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                {locationMeta}
              </span>
            </div>
          </div>
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 }}
        className={`rounded-2xl border overflow-visible ${panelClass}`}
      >
        <div className={`px-5 sm:px-8 py-6 border-b ${borderClass}`}>
          <div className="flex items-start gap-4">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
              style={{ background: `${locationReference.color}10` }}
            >
              <CalendarDays size={20} style={{ color: locationReference.color }} />
            </div>
            <div className="flex-1">
              <h2
                className={`mb-1 text-[18px] tracking-[-0.01em] ${textPrimary}`}
                style={{ fontWeight: 600 }}
              >
                Assign employees to this location
              </h2>
              <p className={`text-[13px] leading-relaxed ${textSecondary}`} style={{ fontWeight: 420 }}>
                Assign employees here and we&apos;ll automatically make their existing roles available for scheduling at {locationDisplayName}. Removing an employee later does not remove those location roles.
              </p>
            </div>
          </div>
        </div>

        {feedback ? (
          <div
            className="mx-5 mt-5 sm:mx-8 rounded-xl px-4 py-3 text-[13px]"
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

        <div className="px-5 sm:px-8 py-6 space-y-6">
          <div className={`space-y-6 ${borderClass}`}>
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h3
                  className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
                  style={{ fontWeight: 500 }}
                >
                  Assigned Employees
                </h3>
                <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                  {selectedEmployees.length} of {employees.length}
                </span>
              </div>
              <div className="flex min-h-[36px] flex-wrap gap-2">
                <AnimatePresence>
                  {selectedEmployees.map((employee) => {
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
                            ? chipClass
                            : isDark
                              ? "border-[#FFB800]/25 bg-[#FFB800]/[0.1]"
                              : "border-[#FFB800]/20 bg-[#FFB800]/[0.06]"
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() =>
                            router.push(
                              buildLocationEmployeeEditPathFromAny(location, employee.id),
                              { scroll: false },
                            )
                          }
                          className="flex min-w-0 items-center gap-2 text-left"
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
                        </button>
                        {!isReady ? (
                          <div className="relative ml-0.5">
                            <Info size={12} className="cursor-default text-[#FFB800]" />
                            <div
                              className={`pointer-events-none absolute bottom-full right-0 z-30 mb-2 w-56 rounded-lg px-3 py-2 text-[11px] opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100 ${
                                isDark
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
                          disabled={loading || isPending}
                          className="ml-0.5 rounded p-0.5 transition-colors hover:bg-[#635BFF]/10 disabled:opacity-50"
                        >
                          <X size={12} className="text-[#8898AA] hover:text-[#E5484D]" />
                        </button>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
                {loading ? (
                  <p className={`py-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                    Loading business employees...
                  </p>
                ) : selectedEmployees.length === 0 ? (
                  <p className={`py-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                    No employees assigned yet. Add from the list below.
                  </p>
                ) : null}
              </div>
            </div>

            <div className={`border-t pt-6 ${borderClass}`}>
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
                    disabled={loading || isPending}
                    className="text-[11px] text-[#635BFF] transition-colors hover:text-[#4B3FD9] disabled:opacity-50"
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
                      disabled={loading || isPending}
                      className={`group flex items-center gap-2 rounded-lg border px-3 py-1.5 transition-all duration-200 disabled:opacity-50 ${
                        isDark
                          ? "border-white/[0.08] bg-white/[0.03] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08]"
                          : "border-[#E5E7EB] bg-[#F7F8FA] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]"
                      }`}
                    >
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#635BFF]/10 text-[10px] text-[#635BFF]">
                        {employeeInitials(employeeDisplayName(employee))}
                      </span>
                      <span
                        className={`text-[12px] transition-colors ${
                          isDark
                            ? "text-[#C1CED8] group-hover:text-white"
                            : "text-[#5E6D7A] group-hover:text-[#0A2540]"
                        }`}
                        style={{ fontWeight: 440 }}
                      >
                        {employeeDisplayName(employee)}
                      </span>
                      <Plus
                        size={11}
                        className="ml-0.5 text-[#8898AA] transition-colors group-hover:text-[#635BFF]"
                      />
                    </button>
                  ))}
                </div>
              ) : !loading ? (
                <p className={`text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
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
                          isDark
                            ? "border-[#FFB800]/25 bg-[#FFB800]/[0.1] hover:bg-[#FFB800]/[0.14]"
                            : "border-[#FFB800]/20 bg-[#FFB800]/[0.06] hover:bg-[#FFB800]/[0.1]"
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() =>
                            router.push(
                              buildLocationEmployeeEditPathFromAny(location, employee.id),
                              { scroll: false },
                            )
                          }
                          className="flex min-w-0 items-center gap-2 text-left"
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
                        </button>
                        <div className="relative ml-0.5">
                          <Info size={12} className="cursor-default text-[#FFB800]" />
                          <div
                            className={`pointer-events-none absolute bottom-full right-0 z-30 mb-2 w-56 rounded-lg px-3 py-2 text-[11px] opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100 ${
                              isDark
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
                  <p className={`mt-3 text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                    Click any employee to edit their profile.
                  </p>
                </div>
              ) : null}

              {!loading && employees.length === 0 ? (
                <div className={`mt-5 rounded-xl border px-4 py-3 ${subtleSurfaceClass} ${subtleBorderClass}`}>
                  <p className={`text-[12px] ${textTertiary}`} style={{ fontWeight: 440 }}>
                    This business does not have any employees yet. Add at least one employee with a role before opening the scheduler for this location.
                  </p>
                </div>
              ) : null}

              <div className="mt-5 flex flex-wrap items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowBulkUploadModal(true)}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-2 text-[12px] transition-all ${
                    isDark
                      ? "border-white/[0.08] bg-white/[0.04] text-[#C1CED8] hover:bg-white/[0.06]"
                      : "border-[#E5E7EB] bg-white text-[#5E6D7A] hover:bg-[#F7F8FA]"
                  }`}
                  style={{ fontWeight: 500 }}
                >
                  <Upload size={13} /> Bulk Upload
                </button>
                <button
                  type="button"
                  onClick={() => setShowAddEmployeeModal(true)}
                  disabled={!roles.length}
                  className="inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-[12px] text-white transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50"
                  style={{
                    fontWeight: 520,
                    background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
                  }}
                >
                  <Plus size={13} /> Add Employee
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className={`px-5 sm:px-8 py-5 border-t ${borderClass} ${footerSurfaceClass}`}>
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="flex-1">
              <AnimatePresence mode="wait">
                {selectedEmployeeIds.length === 0 ? (
                  <motion.p
                    key="requirements"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className={`text-[12px] ${textSecondary}`}
                    style={{ fontWeight: 420 }}
                  >
                    Assign at least one employee to continue.
                  </motion.p>
                ) : inheritedRoleIds.length === 0 ? (
                  <motion.p
                    key="needs-role"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className={`text-[12px] ${textSecondary}`}
                    style={{ fontWeight: 420 }}
                  >
                    Assigned employees need at least one role before scheduling can start.
                  </motion.p>
                ) : (
                  <motion.p
                    key="count"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className={`text-[12px] ${textPrimary}`}
                    style={{ fontWeight: 460 }}
                  >
                    <span style={{ fontWeight: 580, color: locationReference.color }}>
                      {selectedEmployeeIds.length}
                    </span>{" "}
                    {selectedEmployeeIds.length === 1 ? "employee" : "employees"} assigned —{" "}
                    <span style={{ fontWeight: 580, color: locationReference.color }}>
                      {inheritedRoleIds.length}
                    </span>{" "}
                    {inheritedRoleIds.length === 1 ? "role" : "roles"} ready for scheduling
                  </motion.p>
                )}
              </AnimatePresence>
            </div>
            <motion.button
              type="button"
              onClick={handleContinue}
              disabled={selectedEmployeeIds.length === 0 || inheritedRoleIds.length === 0 || isPending || loading}
              whileTap={selectedEmployeeIds.length > 0 && inheritedRoleIds.length > 0 && !isPending ? { scale: 0.97 } : undefined}
              className={`flex items-center justify-center gap-2 px-6 py-3 rounded-full text-[13px] text-white transition-all duration-300 ${
                selectedEmployeeIds.length > 0 && inheritedRoleIds.length > 0 && !loading && !isPending
                  ? "hover:shadow-[0_0_24px_rgba(99,91,255,0.3)] cursor-pointer"
                  : "opacity-30 cursor-not-allowed"
              }`}
              style={{
                fontWeight: 540,
                background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
              }}
            >
              Continue to Scheduler
              <ArrowRight size={15} />
            </motion.button>
          </div>
        </div>
      </motion.div>

      <AnimatePresence>
        {editingEmployee ? (
          <EmployeeEditorDrawer
            businessId={location.business_id}
            dark={isDark}
            employee={editingEmployee}
            locations={effectiveBusinessLocations}
            onClose={closeEmployeeEditor}
            onDeleted={handleEmployeeDeleted}
            onRoleCreated={handleBusinessRoleCreated}
            onSaved={handleEmployeeSaved}
            roles={roles}
          />
        ) : null}
      </AnimatePresence>
      <AnimatePresence>
        {showAddEmployeeModal ? (
          <LocationEmployeeEnrollmentModal
            businessLocations={effectiveBusinessLocations}
            businessId={location.business_id}
            dark={isDark}
            locationId={location.location_id}
            locationName={locationDisplayName}
            onClose={() => setShowAddEmployeeModal(false)}
            onCreated={handleEmployeeCreated}
            roles={roles}
          />
        ) : null}
      </AnimatePresence>
      <AnimatePresence>
        {showBulkUploadModal ? (
          <LocationEmployeeBulkUploadModal
            businessId={location.business_id}
            dark={isDark}
            locationId={location.location_id}
            locationName={locationDisplayName}
            onClose={() => setShowBulkUploadModal(false)}
            onImported={handleEmployeesImported}
          />
        ) : null}
      </AnimatePresence>

    </motion.div>
  );

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav={locationDisplayName}>{content}</DashboardShell>;
}
