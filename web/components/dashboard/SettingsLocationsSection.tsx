"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronRight, MapPin } from "lucide-react";

import { useAppWorkspaceRefresh } from "@/components/app-workspace";
import { useAppWorkspace } from "@/components/app-workspace";
import { useSetLocationEntryMode } from "@/components/location-entry-provider";
import {
  getBusinessLocation,
  getLocationDeleteReadiness,
  getLocationRoles,
  listBusinessLocations,
  replaceLocationRoles,
  type BusinessLocation,
  type LocationRoleAssignment,
} from "@/lib/api/businesses";
import {
  listEmployees,
  updateEmployee,
  type EmployeeSummary,
} from "@/lib/api/workforce";
import {
  getLocationBoard,
  deleteLocation as deleteWorkspaceLocation,
  getLocationShiftDefaults,
  updateLocationSettings,
  updateLocationShiftDefaults,
  type LocationShiftDefaults,
  type ShiftDefault,
  type WorkspaceLocation,
} from "@/lib/api/workspace";
import {
  formatLocationSaveSummary,
  type LocationDeleteState,
  LocationRoleEditor,
  type LocationRoleEditorFeedback as Feedback,
  type LocationRoleEditorSaveSummary,
} from "./LocationRoleEditor";
import {
  formatLocationMeta,
  getLocationReference,
} from "./location-role-reference";
import {
  buildEmployeeLocationAssignments,
  buildInheritedLocationRoleIds,
  employeeAssignedHere,
  mergeUpdatedEmployees,
} from "./location-employee-utils";

const locationsCache = new Map<string, BusinessLocation[]>();
const roleCountCache = new Map<string, Record<string, number>>();

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

export default function SettingsLocationsSection({
  businessId,
  businessType,
  dark,
  editorLocationId,
  onOpenLocationEditor,
  onCloseLocationEditor,
}: {
  businessId: string;
  businessType?: string | null;
  dark: boolean;
  editorLocationId?: string | null;
  onOpenLocationEditor?(locationId: string): void;
  onCloseLocationEditor?(): void;
}) {
  const workspace = useAppWorkspace();
  const refreshWorkspace = useAppWorkspaceRefresh();
  const setLocationEntryMode = useSetLocationEntryMode();
  const workspaceLocations = useMemo(
    () =>
      (workspace?.locations ?? [])
        .filter((location) => location.business_id === businessId)
        .map(adaptWorkspaceLocation),
    [businessId, workspace],
  );
  const [locations, setLocations] = useState<BusinessLocation[]>(
    () => locationsCache.get(businessId) ?? workspaceLocations,
  );
  const [roleCounts, setRoleCounts] = useState<Record<string, number>>(
    () => roleCountCache.get(businessId) ?? {},
  );
  const [selectedLocation, setSelectedLocation] = useState<BusinessLocation | null>(null);
  const [assignments, setAssignments] = useState<LocationRoleAssignment[]>([]);
  const [editorEmployees, setEditorEmployees] = useState<EmployeeSummary[]>([]);
  const [loading, setLoading] = useState(
    () => (locationsCache.get(businessId) ?? workspaceLocations).length === 0,
  );
  const [assignmentLoading, setAssignmentLoading] = useState(false);
  const [shiftDefaults, setShiftDefaults] = useState<LocationShiftDefaults | null>(null);
  const [shiftDefaultsLoading, setShiftDefaultsLoading] = useState(false);
  const [selectedLocationStaffCount, setSelectedLocationStaffCount] = useState<number | null>(
    null,
  );
  const [deleteState, setDeleteState] = useState<LocationDeleteState | undefined>();
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [editorFeedback, setEditorFeedback] = useState<Feedback>(null);
  const [isPending, startTransition] = useTransition();
  const [isDeletingLocation, setIsDeletingLocation] = useState(false);
  const routeControlled = editorLocationId !== undefined;
  const selectedLocationId = routeControlled
    ? (editorLocationId ?? null)
    : (selectedLocation?.id ?? null);
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#8898AA]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const surfaceClass = dark ? "bg-white/[0.03]" : "bg-[#F7F8FA]";

  useEffect(() => {
    const cachedLocations = locationsCache.get(businessId);
    const cachedRoleCounts = roleCountCache.get(businessId);

    setLocations(cachedLocations ?? workspaceLocations);
    setRoleCounts(cachedRoleCounts ?? {});
    setLoading((cachedLocations ?? workspaceLocations).length === 0);
    setSelectedLocation(null);
    setAssignments([]);
    setEditorEmployees([]);
    setShiftDefaults(null);
    setSelectedLocationStaffCount(null);
    setEditorFeedback(null);
  }, [businessId]);

  useEffect(() => {
    if (!routeControlled) {
      return;
    }

    if (!editorLocationId) {
      setSelectedLocation(null);
      return;
    }

    const nextLocation =
      locations.find((location) => location.id === editorLocationId) ?? null;
    if (nextLocation && selectedLocation?.id !== nextLocation.id) {
      setSelectedLocation(nextLocation);
      return;
    }

    if (!loading && !nextLocation) {
      onCloseLocationEditor?.();
    }
  }, [
    editorLocationId,
    loading,
    locations,
    onCloseLocationEditor,
    routeControlled,
    selectedLocation,
  ]);

  useEffect(() => {
    if (workspaceLocations.length === 0) {
      return;
    }
    setLocations((current) => (current.length > 0 ? current : workspaceLocations));
    setLoading(false);
  }, [workspaceLocations]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setFeedback(null);
        const nextLocations = await listBusinessLocations(businessId);
        if (cancelled) {
          return;
        }
        const activeLocations = nextLocations.filter((location) => location.is_active);
        setLocations(activeLocations);
        locationsCache.set(businessId, activeLocations);
        setLoading(false);
        void Promise.allSettled(
          activeLocations.map(async (location) => {
            const nextAssignments = await getLocationRoles(businessId, location.id);
            return [location.id, nextAssignments.length] as const;
          }),
        ).then((results) => {
          if (cancelled) {
            return;
          }
          const nextCounts = Object.fromEntries(
            results.flatMap((result) =>
              result.status === "fulfilled" ? [result.value] : [],
            ),
          );
          roleCountCache.set(businessId, nextCounts);
          setRoleCounts(nextCounts);
        });
      } catch (error) {
        if (!cancelled) {
          setFeedback({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Could not load business locations.",
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
  }, [businessId]);

  useEffect(() => {
    if (!selectedLocationId) {
      setAssignments([]);
      setShiftDefaults(null);
      setSelectedLocationStaffCount(null);
      setDeleteState(undefined);
      setEditorFeedback(null);
      return;
    }

    const activeLocationId = selectedLocationId;
    let cancelled = false;

    async function loadAssignments() {
      try {
        setAssignmentLoading(true);
        setShiftDefaultsLoading(true);
        setDeleteState({ canDelete: false, checking: true });
        setEditorFeedback(null);
        const [
          nextLocation,
          nextAssignments,
          nextShiftDefaults,
          nextDeleteReadiness,
          employees,
        ] = await Promise.all([
          getBusinessLocation(businessId, activeLocationId),
          getLocationRoles(businessId, activeLocationId),
          getLocationShiftDefaults(businessId, activeLocationId),
          getLocationDeleteReadiness(businessId, activeLocationId),
          listEmployees(businessId),
        ]);
        if (cancelled) {
          return;
        }
        setSelectedLocation(nextLocation);
        setAssignments(nextAssignments);
        setEditorEmployees(employees);
        setShiftDefaults(nextShiftDefaults);
        setSelectedLocationStaffCount(
          employees.filter((employee) => employee.location_ids.includes(activeLocationId)).length,
        );
        setDeleteState({
          canDelete: nextDeleteReadiness.can_delete,
          reason: nextDeleteReadiness.reason,
        });
        setRoleCounts((current) => ({
          ...current,
          [activeLocationId]: nextAssignments.length,
        }));
      } catch (error) {
        if (!cancelled) {
          setEditorFeedback({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Could not load location setup.",
          });
          setDeleteState({
            canDelete: false,
            reason: "Could not determine whether this location can be removed.",
          });
        }
      } finally {
        if (!cancelled) {
          setAssignmentLoading(false);
          setShiftDefaultsLoading(false);
        }
      }
    }

    void loadAssignments();

    return () => {
      cancelled = true;
    };
  }, [businessId, selectedLocationId]);

  const assignmentsByRoleId = useMemo(
    () => new Map(assignments.map((assignment) => [assignment.role_id, assignment])),
    [assignments],
  );

  const handleSave = (
    employeeIds: string[],
    locationShiftPresets: ShiftDefault[] | null,
    weekStartDay: string | null,
    saveSummary: LocationRoleEditorSaveSummary,
  ) => {
    if (!selectedLocation) {
      return;
    }

    const activeLocation = selectedLocation;

    startTransition(async () => {
      try {
        const roleIds = buildInheritedLocationRoleIds(
          assignments,
          editorEmployees,
          employeeIds,
        );
        const changedEmployees = editorEmployees.filter((employee) => {
          const currentlyAssigned = employeeAssignedHere(employee, activeLocation.id);
          const shouldBeAssigned = employeeIds.includes(employee.id);
          return currentlyAssigned !== shouldBeAssigned;
        });
        const currentWeekStartDay =
          typeof activeLocation.settings?.week_start_day === "string"
            ? activeLocation.settings.week_start_day
            : null;
        const nextWeekStartDay = weekStartDay || null;
        const [nextAssignments, nextShiftDefaults, _updatedLocationSettings, updatedEmployees] = await Promise.all([
          replaceLocationRoles(
            businessId,
            activeLocation.id,
            roleIds.map((roleId) => {
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
          ),
          updateLocationShiftDefaults(
            businessId,
            activeLocation.id,
            locationShiftPresets,
          ),
          currentWeekStartDay === nextWeekStartDay
            ? Promise.resolve(null)
            : updateLocationSettings(
                businessId,
                activeLocation.id,
                { week_start_day: nextWeekStartDay },
              ),
          Promise.all(
            changedEmployees.map((employee) =>
              updateEmployee(businessId, employee.id, {
                locations: buildEmployeeLocationAssignments(
                  employee,
                  activeLocation.id,
                  employeeIds.includes(employee.id),
                ),
              }),
            ),
          ),
        ]);
        const nextLocationSettings = { ...(activeLocation.settings ?? {}) } as Record<string, unknown>;
        if (nextWeekStartDay) {
          nextLocationSettings.week_start_day = nextWeekStartDay;
        } else {
          delete nextLocationSettings.week_start_day;
        }
        setAssignments(nextAssignments);
        setEditorEmployees((current) => mergeUpdatedEmployees(current, updatedEmployees));
        setShiftDefaults(nextShiftDefaults);
        setSelectedLocation((current) =>
          current && current.id === activeLocation.id
            ? { ...current, settings: nextLocationSettings }
            : current,
        );
        setRoleCounts((current) => ({
          ...current,
          [activeLocation.id]: nextAssignments.length,
        }));
        const board = await getLocationBoard(businessId, activeLocation.id);
        setLocationEntryMode(
          activeLocation.id,
          board?.location_setup_required ? "setup" : "scheduler",
        );
        setEditorFeedback({
          tone: "success",
          message: formatLocationSaveSummary(
            saveSummary,
            activeLocation.display_name ?? activeLocation.name,
          ),
        });
      } catch (error) {
        setEditorFeedback({
          tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Could not update location configuration.",
        });
      }
    });
  };

  const handleDeleteLocation = async () => {
    if (!selectedLocation || isDeletingLocation) {
      return;
    }

    const confirmed = window.confirm(
      `Remove ${selectedLocation.display_name ?? selectedLocation.name}? This will also remove its employee location associations.`,
    );
    if (!confirmed) {
      return;
    }

    setIsDeletingLocation(true);
    setEditorFeedback(null);
    try {
      await deleteWorkspaceLocation(businessId, selectedLocation.id);
      const remainingLocations = locations.filter((location) => location.id !== selectedLocation.id);
      const nextRoleCounts = Object.fromEntries(
        Object.entries(roleCounts).filter(([locationId]) => locationId !== selectedLocation.id),
      );
      locationsCache.set(businessId, remainingLocations);
      roleCountCache.set(businessId, nextRoleCounts);
      setLocations(remainingLocations);
      setRoleCounts(nextRoleCounts);
      if (onCloseLocationEditor) {
        onCloseLocationEditor();
      } else {
        setSelectedLocation(null);
      }
      setAssignments([]);
      setShiftDefaults(null);
      setDeleteState(undefined);
      await refreshWorkspace();
      setFeedback({
        tone: "success",
        message: "Location removed.",
      });
    } catch (error) {
      setEditorFeedback({
        tone: "error",
        message:
          error instanceof Error ? error.message : "Could not remove this location.",
      });
    } finally {
      setIsDeletingLocation(false);
    }
  };

  if (loading) {
    return <div className={`py-10 text-[13px] ${textSecondary}`}>Loading business locations...</div>;
  }

  if (!locations.length) {
    return (
      <div className={`rounded-2xl border px-5 py-6 ${borderClass} ${surfaceClass}`}>
        <div className="flex items-start gap-3">
          <MapPin className="mt-0.5 text-[#8898AA]" size={18} />
          <div>
            <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
              No locations yet
            </p>
            <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
              Add at least one business location before assigning employees here.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        {feedback ? (
          <div
            className="mb-4 rounded-xl px-4 py-3 text-[13px]"
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

        <div className="space-y-3">
          {locations.map((location) => {
            const locationReference = getLocationReference({
              ...location,
              name: location.display_name ?? location.name,
            });
            const locationMeta =
              formatLocationMeta(location) || location.timezone || locationReference.staffLabel;
            const assignedRoleCount = roleCounts[location.id];
            return (
              <button
                key={location.id}
                type="button"
                onClick={() => {
                  if (onOpenLocationEditor) {
                    onOpenLocationEditor(location.id);
                    return;
                  }
                  setSelectedLocation(location);
                }}
                className={`w-full flex items-center gap-4 p-4 rounded-xl border transition-all group text-left cursor-pointer ${
                  dark
                    ? "border-white/[0.08] bg-white/[0.03] hover:border-white/[0.14] hover:bg-white/[0.05]"
                    : "border-[#E5E7EB] hover:border-[#D1D5DB] hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)]"
                }`}
              >
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center text-[18px]"
                  style={{ background: `${locationReference.color}10` }}
                >
                  {locationReference.logo}
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                    {location.display_name ?? location.name}
                  </p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                      {locationReference.typeLabel
                        ? `${locationReference.typeLabel} • ${locationMeta}`
                        : locationMeta}
                    </span>
                    {typeof assignedRoleCount === "number" ? (
                      <>
                        <span className="text-[9px] text-[#8898AA]/40">|</span>
                        <span className="text-[11px] text-[#635BFF]" style={{ fontWeight: 460 }}>
                          {assignedRoleCount} roles
                        </span>
                      </>
                    ) : null}
                  </div>
                </div>
                <ChevronRight
                  size={16}
                  className={`transition-colors shrink-0 ${dark ? "text-[#5E6D7A] group-hover:text-[#C1CED8]" : "text-[#C1CED8] group-hover:text-[#8898AA]"}`}
                />
              </button>
            );
          })}
        </div>
      </motion.div>

      <AnimatePresence>
        {selectedLocation ? (
          <LocationRoleEditor
            assignments={assignments}
            businessTypeLabel={businessType}
            dark={dark}
            deleteState={
              deleteState
                ? {
                    ...deleteState,
                    deleting: isDeletingLocation,
                  }
                : undefined
            }
            feedback={editorFeedback}
            loading={assignmentLoading || shiftDefaultsLoading}
            location={selectedLocation}
            onClose={() => {
              if (onCloseLocationEditor) {
                onCloseLocationEditor();
                return;
              }
              setSelectedLocation(null);
            }}
            onDelete={() => {
              void handleDeleteLocation();
            }}
            onSave={handleSave}
            employees={editorEmployees}
            shiftDefaults={shiftDefaults}
            staffCount={selectedLocationStaffCount}
            saving={isPending}
          />
        ) : null}
      </AnimatePresence>
    </>
  );
}
