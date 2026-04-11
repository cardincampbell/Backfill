"use client";

import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CalendarDays,
  Check,
  ChevronLeft,
  Info,
  Plus,
  Tag,
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
  createAndAssignLocationRole,
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
  formatDisplayLabel,
  formatLocationMeta,
  getLocationReference,
} from "./location-role-reference";

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

const CATEGORY_PRIORITY = [
  "management",
  "operations",
  "front_of_house",
  "back_of_house",
  "healthcare",
  "senior_care",
  "hospitality",
];

function getRoleCategoryKey(role: BusinessRole): string {
  const category = role.category?.trim();
  return category && category.length > 0 ? category.toLowerCase() : "other";
}

function getRoleCategoryLabel(categoryKey: string): string {
  return formatDisplayLabel(categoryKey);
}

function sortCategoryLabels(labels: string[]): string[] {
  return [...labels].sort((left, right) => {
    const leftPriority = CATEGORY_PRIORITY.indexOf(left);
    const rightPriority = CATEGORY_PRIORITY.indexOf(right);

    if (leftPriority !== -1 || rightPriority !== -1) {
      if (leftPriority === -1) return 1;
      if (rightPriority === -1) return -1;
      return leftPriority - rightPriority;
    }

    return left.localeCompare(right);
  });
}

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

function employeeHasAssignedRoles(employee: EmployeeSummary) {
  return employee.role_ids.length > 0;
}

function employeeEligibilityReason(employee: EmployeeSummary) {
  const missingRole = employee.role_ids.length === 0;
  const missingLocation = employee.location_ids.length === 0;

  if (missingRole && missingLocation) {
    return "Missing role and location assignment";
  }
  if (missingRole) {
    return "Missing role assignment";
  }
  if (missingLocation) {
    return "Missing location assignment";
  }
  return "Missing scheduling requirements";
}

function employeeAssignedHere(employee: EmployeeSummary, locationId: string) {
  return employee.location_ids.includes(locationId);
}

function buildEmployeeLocationAssignments(
  employee: EmployeeSummary,
  locationId: string,
  includeLocation: boolean,
) {
  const nextLocationIds = employee.location_ids.filter((item) => item !== locationId);
  if (includeLocation) {
    nextLocationIds.push(locationId);
  }

  if (!nextLocationIds.length) {
    return [];
  }

  const preservedPrimaryLocationId =
    employee.primary_location_id && nextLocationIds.includes(employee.primary_location_id)
      ? employee.primary_location_id
      : includeLocation
        ? locationId
        : nextLocationIds[0];

  return nextLocationIds.map((item) => ({
    location_id: item,
    is_primary: item === preservedPrimaryLocationId,
  }));
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
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);
  const [selectedEmployeeIds, setSelectedEmployeeIds] = useState<string[]>([]);
  const [customRole, setCustomRole] = useState("");
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isCreatingRole, setIsCreatingRole] = useState(false);
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
        const syncedRoleIds = Array.from(
          new Set([
            ...nextAssignments.map((assignment) => assignment.role_id),
            ...nextEmployees
              .filter((employee) => employeeAssignedHere(employee, location.location_id))
              .flatMap((employee) => employee.role_ids),
          ]),
        );
        setAssignments(nextAssignments);
        setSelectedRoleIds(syncedRoleIds);
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
  const selectedRoles = useMemo(
    () => roles.filter((role) => selectedRoleIds.includes(role.id)),
    [roles, selectedRoleIds],
  );
  const availableRoles = useMemo(
    () => roles.filter((role) => !selectedRoleIds.includes(role.id)),
    [roles, selectedRoleIds],
  );
  const groupedAvailableRoles = useMemo(() => {
    const grouped = new Map<string, BusinessRole[]>();
    for (const role of availableRoles) {
      const categoryKey = getRoleCategoryKey(role);
      const existing = grouped.get(categoryKey);
      if (existing) {
        existing.push(role);
      } else {
        grouped.set(categoryKey, [role]);
      }
    }

    return sortCategoryLabels(Array.from(grouped.keys())).map((categoryKey) => ({
      categoryKey,
      categoryLabel: getRoleCategoryLabel(categoryKey),
      roles: grouped.get(categoryKey) ?? [],
    }));
  }, [availableRoles]);
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
    () =>
      sortedEmployees.filter(
        (employee) =>
          selectedEmployeeSet.has(employee.id) && employeeHasAssignedRoles(employee),
      ),
    [selectedEmployeeSet, sortedEmployees],
  );
  const availableEmployees = useMemo(
    () =>
      sortedEmployees.filter(
        (employee) =>
          !selectedEmployeeSet.has(employee.id) && employeeHasAssignedRoles(employee),
      ),
    [selectedEmployeeSet, sortedEmployees],
  );
  const ineligibleEmployees = useMemo(
    () => sortedEmployees.filter((employee) => !employeeHasAssignedRoles(employee)),
    [sortedEmployees],
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

  const addRole = (roleId: string) => {
    setSelectedRoleIds((current) =>
      current.includes(roleId) ? current : [...current, roleId],
    );
  };

  const removeRole = (roleId: string) => {
    setSelectedRoleIds((current) => current.filter((item) => item !== roleId));
  };

  const addAllInCategory = (category: string) => {
    const roleIds = roles
      .filter((role) => getRoleCategoryKey(role) === category)
      .map((role) => role.id);
    setSelectedRoleIds((current) => Array.from(new Set([...current, ...roleIds])));
  };

  const addAllRoles = () => {
    setSelectedRoleIds(roles.map((role) => role.id));
  };

  const addEmployee = (employeeId: string) => {
    const employee = employees.find((item) => item.id === employeeId);
    setSelectedEmployeeIds((current) =>
      current.includes(employeeId) ? current : [...current, employeeId],
    );
    if (employee) {
      setSelectedRoleIds((current) =>
        Array.from(new Set([...current, ...employee.role_ids])),
      );
    }
  };

  const removeEmployee = (employeeId: string) => {
    setSelectedEmployeeIds((current) => current.filter((item) => item !== employeeId));
  };

  const addAllEmployees = () => {
    setSelectedEmployeeIds((current) =>
      Array.from(new Set([...current, ...availableEmployees.map((employee) => employee.id)])),
    );
  };

  const handleCreateRole = async () => {
    const trimmed = customRole.trim();
    if (!trimmed || isCreatingRole) {
      return;
    }

    const existing = roles.find(
      (role) => role.name.trim().toLowerCase() === trimmed.toLowerCase(),
    );
    if (existing) {
      addRole(existing.id);
      setCustomRole("");
      setFeedback({
        tone: "success",
        message: `${existing.name} is already in Roles and has been selected for ${locationDisplayName}.`,
      });
      return;
    }

    try {
      setIsCreatingRole(true);
      setFeedback(null);
      const created = await createAndAssignLocationRole(
        location.business_id,
        location.location_id,
        { name: trimmed },
      );
      setRoles((current) =>
        current.some((role) => role.id === created.role.id)
          ? current
          : [...current, created.role],
      );
      setAssignments((current) => {
        const next = current.filter(
          (assignment) => assignment.role_id !== created.location_role.role_id,
        );
        next.push(created.location_role);
        return next;
      });
      setSelectedRoleIds((current) =>
        current.includes(created.role.id) ? current : [...current, created.role.id],
      );
      setCustomRole("");
      setFeedback({
        tone: "success",
        message: existing
          ? `${created.role.name} was assigned to ${locationDisplayName}.`
          : `${created.role.name} was added to Roles and assigned to ${locationDisplayName}.`,
      });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "Could not create role.",
      });
    } finally {
      setIsCreatingRole(false);
    }
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
    if (selectedEmployeeSet.has(nextEmployee.id)) {
      setSelectedRoleIds((current) =>
        Array.from(new Set([...current, ...nextEmployee.role_ids])),
      );
    }
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
    setSelectedRoleIds((current) =>
      Array.from(new Set([...current, ...nextEmployee.role_ids])),
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
    if (!selectedRoleIds.length || !selectedEmployees.length) {
      return;
    }

    startTransition(async () => {
      try {
        setFeedback(null);
        const roleIdsToSave = Array.from(
          new Set([
            ...selectedRoleIds,
            ...selectedEmployees.flatMap((employee) => employee.role_ids),
          ]),
        );
        const nextAssignments = await replaceLocationRoles(
          location.business_id,
          location.location_id,
          roleIdsToSave.map((roleId) => {
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
        setSelectedRoleIds(nextAssignments.map((assignment) => assignment.role_id));
        if (updatedEmployees.length > 0) {
          const updatedById = new Map(
            updatedEmployees.map((employee) => [employee.id, employee]),
          );
          setEmployees((current) =>
            current.map((employee) => updatedById.get(employee.id) ?? employee),
          );
        }
        setLocationEntryMode(
          location.location_id,
          nextAssignments.length > 0 && selectedEmployees.length > 0
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
              : "Could not update location roles.",
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
                Select roles for this location
              </h2>
              <p className={`text-[13px] leading-relaxed ${textSecondary}`} style={{ fontWeight: 420 }}>
                Choose the roles that apply to {locationDisplayName}. Once selected, we&apos;ll use them to build your weekly shift schedule and match available staff.
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

        <div className={`px-5 sm:px-8 py-5 border-b ${borderClass}`}>
          <div className="flex items-center justify-between mb-3">
            <h3 className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 500 }}>
              Selected Roles
            </h3>
            <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>
              {selectedRoles.length} of {roles.length}
            </span>
          </div>
          <div className="flex flex-wrap gap-2 min-h-[36px]">
            <AnimatePresence>
              {selectedRoles.map((role) => (
                <motion.div
                  key={role.id}
                  layout
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  className={`flex items-center gap-1.5 pl-3 pr-2 py-1.5 rounded-lg border ${chipClass}`}
                >
                  <Tag size={11} className="text-[#635BFF]" />
                  <span className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                    {role.name}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeRole(role.id)}
                    disabled={loading || isPending}
                    className="p-0.5 rounded hover:bg-[#635BFF]/10 transition-colors ml-0.5 disabled:opacity-50"
                  >
                    <X size={12} className="text-[#8898AA] hover:text-[#E5484D]" />
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
            {!loading && selectedRoles.length === 0 ? (
              <p className={`py-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                No roles selected yet. Add from the list below.
              </p>
            ) : null}
            {loading ? (
              <p className={`py-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                Loading location roles...
              </p>
            ) : null}
          </div>
        </div>

        <div className="px-5 sm:px-8 py-6 space-y-6">
          {availableRoles.length > 0 ? (
            <div className="flex items-center justify-between">
              <h3 className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 500 }}>
                Available Roles
              </h3>
              <button
                type="button"
                onClick={addAllRoles}
                disabled={loading || isPending}
                className="text-[11px] text-[#635BFF] hover:text-[#4B3FD9] transition-colors disabled:opacity-50"
                style={{ fontWeight: 520 }}
              >
                + Add All
              </button>
            </div>
          ) : null}

          {groupedAvailableRoles.map((group, index) => (
            <motion.div
              key={group.categoryKey}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.15 + index * 0.08 }}
            >
              <div className="flex items-center justify-between mb-2.5">
                <h4 className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 500 }}>
                  {group.categoryLabel}
                </h4>
                <button
                  type="button"
                  onClick={() => addAllInCategory(group.categoryKey)}
                  disabled={loading || isPending}
                  className="text-[11px] text-[#635BFF] hover:text-[#4B3FD9] transition-colors disabled:opacity-50"
                  style={{ fontWeight: 520 }}
                >
                  + Add all
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {group.roles.map((role) => (
                  <button
                    key={role.id}
                    type="button"
                    onClick={() => addRole(role.id)}
                    disabled={loading || isPending}
                    className={`group flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all duration-200 disabled:opacity-50 ${
                        isDark
                          ? "border-white/[0.08] bg-white/[0.03] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08]"
                          : "border-[#E5E7EB] bg-[#F7F8FA] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]"
                    }`}
                  >
                    <Tag size={11} className="text-[#635BFF]" />
                    <span className={`text-[12px] transition-colors ${isDark ? "text-[#C1CED8] group-hover:text-white" : "text-[#5E6D7A] group-hover:text-[#0A2540]"}`} style={{ fontWeight: 440 }}>
                      {role.name}
                    </span>
                    <Plus size={11} className="ml-0.5 text-[#8898AA] group-hover:text-[#635BFF] transition-colors" />
                  </button>
                ))}
              </div>
            </motion.div>
          ))}

          {!loading && roles.length === 0 ? (
            <div className={`flex items-center gap-3 p-4 rounded-xl border ${subtleSurfaceClass} ${subtleBorderClass}`}>
              <X size={16} className="text-[#8898AA] shrink-0" />
              <p className={`text-[12px] ${isDark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 440 }}>
                This business does not have any roles yet. Business roles are the source of truth for location assignments.
              </p>
            </div>
          ) : null}

          {availableRoles.length === 0 && roles.length > 0 ? (
            <div
              className={`flex items-center gap-3 rounded-xl border p-4 ${
                isDark
                  ? "border-[#00B893]/20 bg-[#00B893]/[0.08]"
                  : "border-[#00B893]/10 bg-[#00B893]/[0.04]"
              }`}
            >
              <Check size={16} className="shrink-0 text-[#00B893]" />
              <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                All available roles have been selected for this location.
              </p>
            </div>
          ) : null}

          <div>
            <h3
              className={`mb-2 text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
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
                    void handleCreateRole();
                  }
                }}
                placeholder="Type a new role name..."
                spellCheck
                className={`flex-1 px-3.5 py-2.5 rounded-lg border text-[13px] placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${
                  isDark
                    ? "border-white/[0.08] bg-white/[0.04] text-white"
                    : "border-[#E5E7EB] bg-white text-[#0A2540]"
                }`}
                style={{ fontWeight: 440 }}
              />
              <button
                type="button"
                onClick={() => void handleCreateRole()}
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

          <div className={`space-y-6 border-t pt-6 ${borderClass}`}>
            <div className="flex items-center justify-between">
              <h3
                className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
                style={{ fontWeight: 500 }}
              >
                Selected Employees
              </h3>
              <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                {selectedEmployees.length} of {employees.length}
              </span>
            </div>

            <div className="flex min-h-[36px] flex-wrap gap-2">
              <AnimatePresence>
                {selectedEmployees.map((employee) => (
                  <motion.div
                    key={employee.id}
                    layout
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.9 }}
                    className={`flex items-center gap-2 rounded-lg border py-1.5 pl-2.5 pr-2 ${chipClass}`}
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
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#635BFF]/10 text-[10px] text-[#635BFF]">
                        {employeeInitials(employeeDisplayName(employee))}
                      </span>
                      <span
                        className={`truncate text-[12px] ${textPrimary}`}
                        style={{ fontWeight: 480 }}
                      >
                        {employeeDisplayName(employee)}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => removeEmployee(employee.id)}
                      disabled={loading || isPending}
                      className="ml-0.5 rounded p-0.5 transition-colors hover:bg-[#635BFF]/10 disabled:opacity-50"
                    >
                      <X size={12} className="text-[#8898AA] hover:text-[#E5484D]" />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
              {loading ? (
                <p className={`py-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  Loading business employees...
                </p>
              ) : selectedEmployees.length === 0 ? (
                <p className={`py-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  No employees selected yet. Add from the list below.
                </p>
              ) : null}
            </div>

            {availableEmployees.length > 0 ? (
              <div>
                <div className="mb-2.5 flex items-center justify-between">
                  <h4
                    className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
                    style={{ fontWeight: 500 }}
                  >
                    Available Employees
                  </h4>
                  {availableEmployees.length > 1 ? (
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
                <div className="flex flex-wrap gap-2">
                  {availableEmployees.map((employee) => (
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
              </div>
            ) : null}

            {ineligibleEmployees.length > 0 ? (
              <div>
                <div className="mb-2.5">
                  <h4
                    className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
                    style={{ fontWeight: 500 }}
                  >
                    Unavailable Employees
                  </h4>
                </div>
                <div className="flex flex-wrap gap-2">
                  {ineligibleEmployees.map((employee) => {
                    return (
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
                    );
                  })}
                </div>
                <p className={`mt-3 text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                  Click any employee to edit their profile.
                </p>
              </div>
            ) : null}

            {!loading && employees.length === 0 ? (
              <div className={`rounded-xl border px-4 py-3 ${subtleSurfaceClass} ${subtleBorderClass}`}>
                <p className={`text-[12px] ${textTertiary}`} style={{ fontWeight: 440 }}>
                  This business does not have any employees yet. Add at least one employee with a role before opening the scheduler for this location.
                </p>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-2 pt-1">
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
                disabled={roles.length === 0}
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

        <div className={`px-5 sm:px-8 py-5 border-t ${borderClass} ${footerSurfaceClass}`}>
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="flex-1">
              <AnimatePresence mode="wait">
                {selectedRoles.length === 0 || selectedEmployees.length === 0 ? (
                  <motion.p
                    key="requirements"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className={`text-[12px] ${textSecondary}`}
                    style={{ fontWeight: 420 }}
                  >
                    Select at least one role and one employee to continue.
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
                      {selectedRoles.length}
                    </span>{" "}
                    {selectedRoles.length === 1 ? "role" : "roles"} and{" "}
                    <span style={{ fontWeight: 580, color: locationReference.color }}>
                      {selectedEmployees.length}
                    </span>{" "}
                    {selectedEmployees.length === 1 ? "employee" : "employees"} selected — ready to build your schedule
                  </motion.p>
                )}
              </AnimatePresence>
            </div>
            <motion.button
              type="button"
              onClick={handleContinue}
              disabled={selectedRoles.length === 0 || selectedEmployees.length === 0 || isPending || loading}
              whileTap={selectedRoles.length > 0 && selectedEmployees.length > 0 && !isPending ? { scale: 0.97 } : undefined}
              className={`flex items-center justify-center gap-2 px-6 py-3 rounded-full text-[13px] text-white transition-all duration-300 ${
                selectedRoles.length > 0 && selectedEmployees.length > 0 && !loading && !isPending
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
