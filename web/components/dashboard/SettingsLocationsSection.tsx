"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronRight, MapPin } from "lucide-react";

import { useAppWorkspace } from "@/components/app-workspace";
import { useSetLocationEntryMode } from "@/components/location-entry-provider";
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
  getLocationBoard,
  getLocationShiftDefaults,
  updateLocationShiftDefaults,
  type LocationShiftDefaults,
  type ShiftDefault,
  type WorkspaceLocation,
} from "@/lib/api/workspace";
import {
  LocationRoleEditor,
  type LocationRoleEditorFeedback as Feedback,
} from "./LocationRoleEditor";
import {
  getLocationReference,
} from "./location-role-reference";

const locationsCache = new Map<string, BusinessLocation[]>();
const rolesCache = new Map<string, BusinessRole[]>();
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
  dark,
}: {
  businessId: string;
  dark: boolean;
}) {
  const workspace = useAppWorkspace();
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
  const [roles, setRoles] = useState<BusinessRole[]>(
    () => rolesCache.get(businessId) ?? [],
  );
  const [roleCounts, setRoleCounts] = useState<Record<string, number>>(
    () => roleCountCache.get(businessId) ?? {},
  );
  const [selectedLocation, setSelectedLocation] = useState<BusinessLocation | null>(null);
  const [assignments, setAssignments] = useState<LocationRoleAssignment[]>([]);
  const [loading, setLoading] = useState(
    () => (locationsCache.get(businessId) ?? workspaceLocations).length === 0,
  );
  const [assignmentLoading, setAssignmentLoading] = useState(false);
  const [shiftDefaults, setShiftDefaults] = useState<LocationShiftDefaults | null>(null);
  const [shiftDefaultsLoading, setShiftDefaultsLoading] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [editorFeedback, setEditorFeedback] = useState<Feedback>(null);
  const [isPending, startTransition] = useTransition();
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#8898AA]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const surfaceClass = dark ? "bg-white/[0.03]" : "bg-[#F7F8FA]";

  useEffect(() => {
    const cachedLocations = locationsCache.get(businessId);
    const cachedRoles = rolesCache.get(businessId);
    const cachedRoleCounts = roleCountCache.get(businessId);

    setLocations(cachedLocations ?? workspaceLocations);
    setRoles(cachedRoles ?? []);
    setRoleCounts(cachedRoleCounts ?? {});
    setLoading((cachedLocations ?? workspaceLocations).length === 0);
    setSelectedLocation(null);
    setAssignments([]);
    setShiftDefaults(null);
    setEditorFeedback(null);
  }, [businessId, workspaceLocations]);

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
        const [nextLocations, nextRoles] = await Promise.all([
          listBusinessLocations(businessId),
          listBusinessRoles(businessId),
        ]);
        if (cancelled) {
          return;
        }
        const activeLocations = nextLocations.filter((location) => location.is_active);
        setLocations(activeLocations);
        setRoles(nextRoles);
        locationsCache.set(businessId, activeLocations);
        rolesCache.set(businessId, nextRoles);
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
    if (!selectedLocation) {
      setAssignments([]);
      setShiftDefaults(null);
      setEditorFeedback(null);
      return;
    }

    const activeLocation = selectedLocation;
    let cancelled = false;

    async function loadAssignments() {
      try {
        setAssignmentLoading(true);
        setShiftDefaultsLoading(true);
        setEditorFeedback(null);
        const [nextAssignments, nextShiftDefaults] = await Promise.all([
          getLocationRoles(businessId, activeLocation.id),
          getLocationShiftDefaults(businessId, activeLocation.id),
        ]);
        if (cancelled) {
          return;
        }
        setAssignments(nextAssignments);
        setShiftDefaults(nextShiftDefaults);
        setRoleCounts((current) => ({
          ...current,
          [activeLocation.id]: nextAssignments.length,
        }));
      } catch (error) {
        if (!cancelled) {
          setEditorFeedback({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Could not load location roles.",
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
  }, [businessId, selectedLocation]);

  const assignmentsByRoleId = useMemo(
    () => new Map(assignments.map((assignment) => [assignment.role_id, assignment])),
    [assignments],
  );

  const handleSave = (
    roleIds: string[],
    locationShiftPresets: ShiftDefault[] | null,
  ) => {
    if (!selectedLocation) {
      return;
    }

    const activeLocation = selectedLocation;

    startTransition(async () => {
      try {
        const [nextAssignments, nextShiftDefaults] = await Promise.all([
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
        ]);
        setAssignments(nextAssignments);
        setShiftDefaults(nextShiftDefaults);
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
          message: `${roleIds.length} role${roleIds.length === 1 ? "" : "s"} enabled for ${activeLocation.display_name ?? activeLocation.name}.`,
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

  const handleCreateRole = async (name: string): Promise<BusinessRole> => {
    if (!selectedLocation) {
      throw new Error("No location selected.");
    }

    const activeLocation = selectedLocation;
    const existing = roles.find(
      (role) => role.name.trim().toLowerCase() === name.trim().toLowerCase(),
    );

    try {
      setEditorFeedback(null);
      const created = await createAndAssignLocationRole(
        businessId,
        activeLocation.id,
        { name },
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
      setRoleCounts((current) => ({
        ...current,
        [activeLocation.id]:
          assignments.some(
            (assignment) => assignment.role_id === created.location_role.role_id,
          )
            ? current[activeLocation.id] ?? assignments.length
            : (current[activeLocation.id] ?? assignments.length) + 1,
      }));
      setEditorFeedback({
        tone: "success",
        message: existing
          ? `${created.role.name} was assigned to ${activeLocation.display_name ?? activeLocation.name}.`
          : `${created.role.name} was added to Roles and assigned to ${activeLocation.display_name ?? activeLocation.name}.`,
      });
      return created.role;
    } catch (error) {
      setEditorFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "Could not create role.",
      });
      throw error;
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
              Add at least one business location before assigning roles here.
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
            const assignedRoleCount = roleCounts[location.id];
            return (
              <button
                key={location.id}
                type="button"
                onClick={() => setSelectedLocation(location)}
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
                        ? `${locationReference.typeLabel} • ${locationReference.staffLabel}`
                        : locationReference.staffLabel}
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
            dark={dark}
            feedback={editorFeedback}
            loading={assignmentLoading || shiftDefaultsLoading}
            location={selectedLocation}
            onClose={() => setSelectedLocation(null)}
            onCreateRole={handleCreateRole}
            onSave={handleSave}
            shiftDefaults={shiftDefaults}
            roles={roles}
            saving={isPending}
          />
        ) : null}
      </AnimatePresence>
    </>
  );
}
