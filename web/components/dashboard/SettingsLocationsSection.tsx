"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronRight, MapPin, Plus, Tag, X } from "lucide-react";

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
  formatLocationMeta,
  getLocationReference,
} from "./location-role-reference";

type Feedback = {
  tone: "success" | "error";
  message: string;
} | null;

function RoleTag({
  dark,
  role,
  onRemove,
}: {
  dark: boolean;
  role: BusinessRole;
  onRemove(): void;
}) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      className={`flex items-center gap-1.5 pl-3 pr-2 py-1.5 rounded-lg border ${
        dark
          ? "bg-[#635BFF]/[0.12] border-[#635BFF]/25"
          : "bg-[#635BFF]/[0.06] border-[#635BFF]/15"
      }`}
    >
      <Tag size={11} className="text-[#635BFF]" />
      <span className={`text-[12px] ${dark ? "text-white" : "text-[#0A2540]"}`} style={{ fontWeight: 480 }}>
        {role.name}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="p-0.5 rounded hover:bg-[#635BFF]/10 transition-colors ml-0.5"
      >
        <X size={12} className="text-[#8898AA] hover:text-[#E5484D]" />
      </button>
    </motion.div>
  );
}

function LocationEditSlideOver({
  dark,
  location,
  roles,
  assignments,
  loading,
  saving,
  feedback,
  onClose,
  onSave,
  onCreateRole,
}: {
  dark: boolean;
  location: BusinessLocation;
  roles: BusinessRole[];
  assignments: LocationRoleAssignment[];
  loading: boolean;
  saving: boolean;
  feedback: Feedback;
  onClose(): void;
  onSave(roleIds: string[]): void;
  onCreateRole(name: string): Promise<BusinessRole>;
}) {
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);
  const [customRole, setCustomRole] = useState("");
  const [isCreatingRole, setIsCreatingRole] = useState(false);

  useEffect(() => {
    setSelectedRoleIds(assignments.map((assignment) => assignment.role_id));
  }, [assignments, location.id]);

  const locationReference = getLocationReference(location);
  const selectedRoles = roles.filter((role) => selectedRoleIds.includes(role.id));
  const availableRoles = roles.filter((role) => !selectedRoleIds.includes(role.id));
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#8898AA]";
  const textTertiary = dark ? "text-[#C1CED8]" : "text-[#3E4C59]";
  const borderClass = dark ? "border-white/[0.06]" : "border-[#F0F0F5]";
  const subtleBorderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const subtleSurfaceClass = dark ? "bg-white/[0.04]" : "bg-[#F7F8FA]";

  const addRole = (roleId: string) => {
    setSelectedRoleIds((current) =>
      current.includes(roleId) ? current : [...current, roleId],
    );
  };

  const removeRole = (roleId: string) => {
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
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ x: 460 }}
        animate={{ x: 0 }}
        exit={{ x: 460 }}
        transition={{ duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }}
        className={`w-full sm:w-[460px] h-full shadow-2xl flex flex-col overflow-hidden ${
          dark ? "bg-[#0F2E4C]" : "bg-white"
        }`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className={`px-6 py-5 border-b shrink-0 ${borderClass}`}>
          <div className="flex items-center justify-between mb-4">
            <button
              type="button"
              onClick={onClose}
              className={`p-1.5 rounded-lg transition-colors ${dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"}`}
            >
              <X size={18} className="text-[#8898AA]" />
            </button>
            <button
              type="button"
              onClick={() => onSave(selectedRoleIds)}
              disabled={loading || saving}
              className="px-4 py-2 rounded-full text-[12px] text-white transition-all duration-300 hover:shadow-[0_0_16px_rgba(99,91,255,0.25)] disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                fontWeight: 540,
                background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
              }}
            >
              {saving ? "Saving..." : "Save Changes"}
            </button>
          </div>
          <div className="flex items-center gap-4">
            <div
              className="w-14 h-14 rounded-2xl flex items-center justify-center text-[28px]"
              style={{ background: `${locationReference.color}10` }}
            >
              {locationReference.logo}
            </div>
            <div>
              <h2
                className={`text-[18px] tracking-[-0.01em] ${textPrimary}`}
                style={{ fontWeight: 600 }}
              >
                {location.name}
              </h2>
              <div className="flex items-center gap-2 mt-0.5">
                <span
                  className="text-[12px] px-2 py-0.5 rounded-full"
                  style={{
                    fontWeight: 500,
                    color: locationReference.color,
                    background: `${locationReference.color}10`,
                  }}
                >
                  {locationReference.typeLabel}
                </span>
                <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  {locationReference.staffLabel}
                </span>
              </div>
            </div>
          </div>
          <div className="mt-4 space-y-2">
            <div className="flex items-center gap-3">
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${subtleSurfaceClass}`}>
                <MapPin size={14} className="text-[#8898AA]" />
              </div>
              <span className={`text-[13px] ${textTertiary}`} style={{ fontWeight: 440 }}>
                {formatLocationMeta(location) || location.timezone}
              </span>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
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
                {selectedRoles.map((role) => (
                  <RoleTag
                    key={role.id}
                    dark={dark}
                    role={role}
                    onRemove={() => removeRole(role.id)}
                  />
                ))}
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
                      <Plus
                        size={11}
                        className="text-[#8898AA] group-hover:text-[#635BFF] transition-colors"
                      />
                      <span
                        className={`text-[12px] transition-colors ${dark ? "text-[#C1CED8] group-hover:text-white" : "text-[#5E6D7A] group-hover:text-[#0A2540]"}`}
                        style={{ fontWeight: 440 }}
                      >
                        {role.name}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {!loading && roles.length === 0 ? (
              <div className={`rounded-xl border px-4 py-4 ${subtleBorderClass} ${subtleSurfaceClass}`}>
                <p className={`text-[12px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 440 }}>
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
        </div>
      </motion.div>
    </motion.div>
  );
}

export default function SettingsLocationsSection({
  businessId,
  dark,
}: {
  businessId: string;
  dark: boolean;
}) {
  const [locations, setLocations] = useState<BusinessLocation[]>([]);
  const [roles, setRoles] = useState<BusinessRole[]>([]);
  const [roleCounts, setRoleCounts] = useState<Record<string, number>>({});
  const [selectedLocation, setSelectedLocation] = useState<BusinessLocation | null>(null);
  const [assignments, setAssignments] = useState<LocationRoleAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [assignmentLoading, setAssignmentLoading] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [editorFeedback, setEditorFeedback] = useState<Feedback>(null);
  const [isPending, startTransition] = useTransition();
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#8898AA]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const surfaceClass = dark ? "bg-white/[0.03]" : "bg-[#F7F8FA]";

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
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
        const counts = await Promise.all(
          activeLocations.map(async (location) => {
            const nextAssignments = await getLocationRoles(businessId, location.id);
            return [location.id, nextAssignments.length] as const;
          }),
        );
        if (!cancelled) {
          setRoleCounts(Object.fromEntries(counts));
        }
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
      setEditorFeedback(null);
      return;
    }

    const activeLocation = selectedLocation;
    let cancelled = false;

    async function loadAssignments() {
      try {
        setAssignmentLoading(true);
        setEditorFeedback(null);
        const nextAssignments = await getLocationRoles(businessId, activeLocation.id);
        if (cancelled) {
          return;
        }
        setAssignments(nextAssignments);
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

  const handleSave = (roleIds: string[]) => {
    if (!selectedLocation) {
      return;
    }

    const activeLocation = selectedLocation;

    startTransition(async () => {
      try {
        const nextAssignments = await replaceLocationRoles(
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
        );
        setAssignments(nextAssignments);
        setRoleCounts((current) => ({
          ...current,
          [activeLocation.id]: nextAssignments.length,
        }));
        setEditorFeedback({
          tone: "success",
          message: `${roleIds.length} role${roleIds.length === 1 ? "" : "s"} enabled for ${activeLocation.name}.`,
        });
      } catch (error) {
        setEditorFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not update location roles.",
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
          ? `${created.role.name} was assigned to ${activeLocation.name}.`
          : `${created.role.name} was added to Roles and assigned to ${activeLocation.name}.`,
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
            const locationReference = getLocationReference(location);
            const assignedRoleCount = roleCounts[location.id] ?? 0;
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
                    {location.name}
                  </p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                      {locationReference.typeLabel} • {locationReference.staffLabel}
                    </span>
                    <span className="text-[9px] text-[#8898AA]/40">|</span>
                    <span className="text-[11px] text-[#635BFF]" style={{ fontWeight: 460 }}>
                      {assignedRoleCount} roles
                    </span>
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
          <LocationEditSlideOver
            assignments={assignments}
            dark={dark}
            feedback={editorFeedback}
            loading={assignmentLoading}
            location={selectedLocation}
            onClose={() => setSelectedLocation(null)}
            onCreateRole={handleCreateRole}
            onSave={handleSave}
            roles={roles}
            saving={isPending}
          />
        ) : null}
      </AnimatePresence>
    </>
  );
}
