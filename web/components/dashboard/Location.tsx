"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { ArrowRight, CalendarDays, Check, ChevronLeft, Plus, Tag, X } from "lucide-react";

import { useResolvedAppAppearance } from "@/components/app-session-gate";
import type { WorkspaceLocation } from "@/lib/api/workspace";
import {
  createAndAssignLocationRole,
  getLocationRoles,
  listBusinessRoles,
  replaceLocationRoles,
  type BusinessRole,
  type LocationRoleAssignment,
} from "@/lib/api/businesses";
import DashboardShell from "./DashboardShell";
import {
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
};

const CATEGORY_PRIORITY = ["Healthcare", "Senior Care", "Hospitality"];

function getRoleCategoryLabel(role: BusinessRole): string {
  const category = role.category?.trim();
  return category && category.length > 0 ? category : "Other";
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

export default function Location({
  embeddedInShell = false,
  location,
  backHref = "/dashboard",
}: LocationProps) {
  const router = useRouter();
  const isDark = useResolvedAppAppearance() === "dark";
  const locationDisplayName = location.location_display_name ?? location.location_name;
  const [roles, setRoles] = useState<BusinessRole[]>([]);
  const [assignments, setAssignments] = useState<LocationRoleAssignment[]>([]);
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);
  const [customRole, setCustomRole] = useState("");
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [scheduleStarted, setScheduleStarted] = useState(false);
  const [isCreatingRole, setIsCreatingRole] = useState(false);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setFeedback(null);
        const [nextRoles, nextAssignments] = await Promise.all([
          listBusinessRoles(location.business_id),
          getLocationRoles(location.business_id, location.location_id),
        ]);
        if (cancelled) {
          return;
        }
        setRoles(nextRoles);
        setAssignments(nextAssignments);
        setSelectedRoleIds(nextAssignments.map((assignment) => assignment.role_id));
      } catch (error) {
        if (!cancelled) {
          setFeedback({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Could not load location roles.",
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
      const category = getRoleCategoryLabel(role);
      const existing = grouped.get(category);
      if (existing) {
        existing.push(role);
      } else {
        grouped.set(category, [role]);
      }
    }

    return sortCategoryLabels(Array.from(grouped.keys())).map((category) => ({
      category,
      roles: grouped.get(category) ?? [],
    }));
  }, [availableRoles]);
  const locationReference = getLocationReference({
    name: locationDisplayName,
    slug: location.location_slug,
  });
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
      .filter((role) => getRoleCategoryLabel(role) === category)
      .map((role) => role.id);
    setSelectedRoleIds((current) => Array.from(new Set([...current, ...roleIds])));
  };

  const addAllRoles = () => {
    setSelectedRoleIds(roles.map((role) => role.id));
  };

  const handleCreateRole = async () => {
    const trimmed = customRole.trim();
    if (!trimmed || isCreatingRole) {
      return;
    }

    const existing = roles.find(
      (role) => role.name.trim().toLowerCase() === trimmed.toLowerCase(),
    );

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

  const handleContinue = () => {
    if (!selectedRoleIds.length) {
      return;
    }

    startTransition(async () => {
      try {
        setFeedback(null);
        const nextAssignments = await replaceLocationRoles(
          location.business_id,
          location.location_id,
          selectedRoleIds.map((roleId) => {
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
        setSelectedRoleIds(nextAssignments.map((assignment) => assignment.role_id));
        setScheduleStarted(true);
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
              <span className={`text-[13px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                {locationReference.staffLabel}
              </span>
            </div>
          </div>
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 }}
        className={`rounded-2xl border overflow-hidden ${panelClass}`}
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
                Choose the roles that apply to {locationDisplayName}. Once selected, we'll use them to build your weekly shift schedule and match available staff.
              </p>
              <p className={`mt-3 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                {formatLocationMeta({
                  name: locationDisplayName,
                  slug: location.location_slug,
                  address_line_1: location.address_line_1,
                  locality: location.locality,
                  region: location.region,
                  postal_code: location.postal_code,
                  timezone: location.timezone,
                }) || location.timezone}
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
              key={group.category}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.15 + index * 0.08 }}
            >
              <div className="flex items-center justify-between mb-2.5">
                <h4 className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 500 }}>
                  {group.category}
                </h4>
                <button
                  type="button"
                  onClick={() => addAllInCategory(group.category)}
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
                    <Plus size={11} className="text-[#8898AA] group-hover:text-[#635BFF] transition-colors" />
                    <span className={`text-[12px] transition-colors ${isDark ? "text-[#C1CED8] group-hover:text-white" : "text-[#5E6D7A] group-hover:text-[#0A2540]"}`} style={{ fontWeight: 440 }}>
                      {role.name}
                    </span>
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

          {availableRoles.length === 0 && roles.length > 0 ? (
            <div className={`flex items-center gap-3 p-4 rounded-xl border ${
              isDark
                ? "bg-[#00B893]/[0.08] border-[#00B893]/20"
                : "bg-[#00B893]/[0.04] border-[#00B893]/10"
            }`}>
              <Check size={16} className="text-[#00B893] shrink-0" />
              <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                All available roles have been selected for this location.
              </p>
            </div>
          ) : null}
        </div>

        <div className={`px-5 sm:px-8 py-5 border-t ${borderClass} ${footerSurfaceClass}`}>
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="flex-1">
              <AnimatePresence mode="wait">
                {selectedRoles.length === 0 ? (
                  <motion.p
                    key="empty"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className={`text-[12px] ${textSecondary}`}
                    style={{ fontWeight: 420 }}
                  >
                    Select at least one role to continue
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
                    {selectedRoles.length === 1 ? "role" : "roles"} selected — ready to build your schedule
                  </motion.p>
                )}
              </AnimatePresence>
            </div>
            <motion.button
              type="button"
              onClick={handleContinue}
              disabled={selectedRoles.length === 0 || isPending || loading}
              whileTap={selectedRoles.length > 0 && !isPending ? { scale: 0.97 } : undefined}
              className={`flex items-center justify-center gap-2 px-6 py-3 rounded-full text-[13px] text-white transition-all duration-300 ${
                selectedRoles.length > 0 && !loading && !isPending
                  ? "hover:shadow-[0_0_24px_rgba(99,91,255,0.3)] cursor-pointer"
                  : "opacity-30 cursor-not-allowed"
              }`}
              style={{
                fontWeight: 540,
                background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
              }}
            >
              Continue to Schedule
              <ArrowRight size={15} />
            </motion.button>
          </div>
        </div>
      </motion.div>

      <AnimatePresence>
        {scheduleStarted ? (
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 30 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-6 py-4 rounded-2xl bg-[#0A2540] shadow-2xl border border-[#1A3A5C]"
          >
            <div className="w-8 h-8 rounded-full bg-[#00B893]/20 flex items-center justify-center">
              <Check size={16} className="text-[#00B893]" />
            </div>
            <div>
              <p className="text-[13px] text-white" style={{ fontWeight: 520 }}>
                {selectedRoles.length} roles confirmed for {locationDisplayName}
              </p>
              <p className="text-[11px] text-[#8898AA] mt-0.5" style={{ fontWeight: 420 }}>
                Scheduler coming soon — we'll notify you when it's ready.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setScheduleStarted(false)}
              className="p-1.5 rounded-lg hover:bg-white/10 transition-colors ml-2"
            >
              <X size={14} className="text-[#8898AA]" />
            </button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.div>
  );

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav={locationDisplayName}>{content}</DashboardShell>;
}
