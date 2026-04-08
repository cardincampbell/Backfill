"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useResolvedAppAppearance } from "@/components/app-session-gate";
import {
  attachRoleToLocation,
  deriveBusinessRoles,
  type WorkspaceBoard,
  type WorkspaceLocation,
} from "@/lib/api/workspace";
import {
  AlertCircle,
  ArrowRight,
  CalendarDays,
  Check,
  ChevronLeft,
  Clock3,
  RefreshCw,
  ShieldAlert,
  Tag,
  Users,
  X,
} from "lucide-react";

import DashboardShell from "./DashboardShell";
import { Link, useNavigate } from "./router-shim";

type LocationProps = {
  embeddedInShell?: boolean;
  location: WorkspaceLocation;
  board: WorkspaceBoard;
  previousWeekHref: string;
  nextWeekHref: string;
  currentWeekHref: string;
};

type Feedback = {
  tone: "success" | "error";
  message: string;
} | null;

type RoleCoverageItem = {
  label: string;
  covered: number;
  total: number;
  status: "covered" | "filling" | "open";
};

function locationMeta(location: WorkspaceLocation): string {
  return [
    location.address_line_1,
    location.locality,
    location.region,
    location.postal_code,
  ]
    .filter((value): value is string => Boolean(value))
    .join(", ");
}

function formatWeekRange(start: string, end: string): string {
  const startDate = new Date(`${start}T00:00:00`);
  const endDate = new Date(`${end}T00:00:00`);
  const formatter = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  });
  return `${formatter.format(startDate)} - ${formatter.format(endDate)}`;
}

function formatShiftMeta(
  shift: WorkspaceBoard["shifts"][number],
  timezone: string,
): string {
  const start = new Date(shift.starts_at);
  const end = new Date(shift.ends_at);
  const dayLabel = start.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: timezone,
  });
  const startLabel = start.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: timezone,
  });
  const endLabel = end.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: timezone,
  });
  return `${dayLabel} · ${startLabel} - ${endLabel}`;
}

function buildRoleCoverage(board: WorkspaceBoard): RoleCoverageItem[] {
  return board.roles
    .map((role) => {
      const shifts = board.shifts.filter((shift) => shift.role_id === role.role_id);
      if (!shifts.length) {
        return null;
      }
      const covered = shifts.filter(
        (shift) =>
          Boolean(shift.current_assignment) ||
          shift.seats_filled >= shift.seats_requested,
      ).length;
      const filling = shifts.some(
        (shift) =>
          shift.manager_action_required ||
          shift.pending_offer_count > 0 ||
          shift.delivered_offer_count > 0 ||
          shift.status !== "covered",
      );
      return {
        label: role.role_name,
        covered,
        total: shifts.length,
        status:
          covered === shifts.length ? "covered" : filling ? "filling" : "open",
      };
    })
    .filter((item): item is RoleCoverageItem => Boolean(item))
    .slice(0, 4);
}

function shiftWeight(shift: WorkspaceBoard["shifts"][number]): number {
  return (
    Number(shift.manager_action_required) * 100 +
    shift.pending_offer_count * 10 +
    shift.delivered_offer_count * 5 +
    shift.standby_depth
  );
}

function shiftStatusLabel(shift: WorkspaceBoard["shifts"][number]): string {
  if (shift.manager_action_required) {
    return "Needs review";
  }
  if (shift.pending_offer_count > 0) {
    return `${shift.pending_offer_count} pending`;
  }
  if (shift.delivered_offer_count > 0) {
    return `${shift.delivered_offer_count} delivered`;
  }
  if (shift.standby_depth > 0) {
    return `${shift.standby_depth} standby`;
  }
  if (shift.current_assignment?.employee_name) {
    return shift.current_assignment.employee_name;
  }
  return shift.status;
}

function SetupMode({
  board,
  canConfigureRoles,
  currentWeekHref,
  isDark,
  location,
}: {
  board: WorkspaceBoard;
  canConfigureRoles: boolean;
  currentWeekHref: string;
  isDark: boolean;
  location: WorkspaceLocation;
}) {
  const router = useRouter();
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [busyAction, setBusyAction] = useState<"derive" | "attach" | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    setSelectedRoleIds([]);
    setFeedback(null);
  }, [location.location_id, board.location_setup_required]);

  const availableRoles = board.available_roles;
  const selectedRoles = availableRoles.filter((role) =>
    selectedRoleIds.includes(role.role_id),
  );

  const panelClass = isDark
    ? "bg-[#0F2E4C] border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.25)]"
    : "bg-white border-[#E5E7EB] shadow-[0_1px_3px_rgba(0,0,0,0.04)]";
  const borderClass = isDark ? "border-white/[0.06]" : "border-[#F0F0F5]";
  const textPrimary = isDark ? "text-white" : "text-[#0A2540]";
  const textSecondary = isDark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const textMuted = "text-[#8898AA]";

  const toggleRole = (roleId: string) => {
    setSelectedRoleIds((current) =>
      current.includes(roleId)
        ? current.filter((item) => item !== roleId)
        : [...current, roleId],
    );
  };

  function handleDeriveRoles() {
    if (!canConfigureRoles || busyAction || isPending) {
      return;
    }
    setBusyAction("derive");
    setFeedback(null);
    startTransition(async () => {
      try {
        await deriveBusinessRoles(location.business_id);
        setFeedback({
          tone: "success",
          message: "Business roles generated. Choose the ones that belong on this location.",
        });
        router.refresh();
      } catch (error) {
        setFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not generate roles for this business.",
        });
      } finally {
        setBusyAction(null);
      }
    });
  }

  function handleAttachRoles() {
    if (!canConfigureRoles || !selectedRoleIds.length || busyAction || isPending) {
      return;
    }
    setBusyAction("attach");
    setFeedback(null);
    startTransition(async () => {
      try {
        await Promise.all(
          selectedRoleIds.map((roleId) =>
            attachRoleToLocation(location.business_id, location.location_id, roleId),
          ),
        );
        setFeedback({
          tone: "success",
          message: `${selectedRoleIds.length} roles enabled for ${location.location_display_name ?? location.location_name}.`,
        });
        router.refresh();
      } catch (error) {
        setFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not enable these roles for the location.",
        });
      } finally {
        setBusyAction(null);
      }
    });
  }

  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      initial={{ opacity: 0, y: 12 }}
      transition={{ duration: 0.5 }}
    >
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <span
              className="rounded-full bg-[#635BFF]/10 px-2.5 py-1 text-[11px] text-[#635BFF]"
              style={{ fontWeight: 520 }}
            >
              Setup required
            </span>
            <span className={`text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
              Weekly board unlocks after role setup
            </span>
          </div>
          <h1
            className={`text-[24px] sm:text-[28px] md:text-[32px] tracking-[-0.025em] ${textPrimary}`}
            style={{ fontWeight: 620 }}
          >
            {location.location_display_name ?? location.location_name}
          </h1>
          <p
            className={`mt-1 max-w-2xl text-[14px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`}
            style={{ fontWeight: 420 }}
          >
            Select the business roles that should operate at this location. Once enabled,
            Backfill can build the live weekly board, staff shifts, and run coverage.
          </p>
        </div>

        <Link
          to={currentWeekHref}
          className={`inline-flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-[13px] transition-all ${
            isDark
              ? "border border-white/[0.08] bg-white/[0.04] text-[#C1CED8] hover:bg-white/[0.06]"
              : "border border-[#E5E7EB] bg-white text-[#5E6D7A] hover:bg-[#F7F8FA]"
          }`}
          style={{ fontWeight: 480 }}
        >
          <RefreshCw size={14} /> Refresh state
        </Link>
      </div>

      {feedback ? (
        <div
          className="mb-5 rounded-2xl px-4 py-3 text-[13px]"
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

      <motion.div
        animate={{ opacity: 1, y: 0 }}
        className={`${panelClass} overflow-hidden rounded-2xl border`}
        initial={{ opacity: 0, y: 16 }}
        transition={{ duration: 0.5, delay: 0.1 }}
      >
        <div className={`border-b px-5 py-6 sm:px-8 ${borderClass}`}>
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#635BFF]/10">
              <CalendarDays size={20} className="text-[#635BFF]" />
            </div>
            <div className="flex-1">
              <h2
                className={`mb-1 text-[18px] tracking-[-0.01em] ${textPrimary}`}
                style={{ fontWeight: 600 }}
              >
                Enable roles for this location
              </h2>
              <p
                className={`text-[13px] leading-relaxed ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`}
                style={{ fontWeight: 420 }}
              >
                This location does not have any active location roles yet. Attach the
                roles that belong here so shift creation, staffing, and coverage can run
                against the correct role catalog.
              </p>
            </div>
          </div>
        </div>

        <div className={`border-b px-5 py-5 sm:px-8 ${borderClass}`}>
          <div className="mb-3 flex items-center justify-between">
            <h3
              className={`text-[11px] uppercase tracking-[0.04em] ${textMuted}`}
              style={{ fontWeight: 500 }}
            >
              Selected Roles
            </h3>
            <span className={`text-[11px] ${textMuted}`} style={{ fontWeight: 440 }}>
              {selectedRoleIds.length} selected
            </span>
          </div>
          <div className="flex min-h-[36px] flex-wrap gap-2">
            <AnimatePresence>
              {selectedRoles.map((role) => (
                <motion.button
                  key={role.role_id}
                  animate={{ opacity: 1, scale: 1 }}
                  className={`flex items-center gap-1.5 rounded-lg border pl-3 pr-2 py-1.5 ${
                    isDark
                      ? "border-[#635BFF]/25 bg-[#635BFF]/15"
                      : "border-[#635BFF]/15 bg-[#635BFF]/[0.06]"
                  }`}
                  exit={{ opacity: 0, scale: 0.9 }}
                  initial={{ opacity: 0, scale: 0.9 }}
                  layout
                  onClick={() => toggleRole(role.role_id)}
                  type="button"
                >
                  <Tag size={11} className="text-[#635BFF]" />
                  <span className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                    {role.role_name}
                  </span>
                  <X size={12} className="text-[#8898AA]" />
                </motion.button>
              ))}
            </AnimatePresence>
            {selectedRoles.length === 0 ? (
              <p className={`py-1 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
                No roles selected yet. Add roles from the business catalog below.
              </p>
            ) : null}
          </div>
        </div>

        <div className="space-y-6 px-5 py-6 sm:px-8">
          <div className="flex items-center justify-between">
            <h3
              className={`text-[11px] uppercase tracking-[0.04em] ${textMuted}`}
              style={{ fontWeight: 500 }}
            >
              Available Business Roles
            </h3>
            {availableRoles.length > 0 ? (
              <span className={`text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>
                {availableRoles.length} available
              </span>
            ) : null}
          </div>

          {availableRoles.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {availableRoles.map((role) => {
                const active = selectedRoleIds.includes(role.role_id);
                return (
                  <button
                    key={role.role_id}
                    className={`group flex items-center gap-1.5 rounded-lg border px-3 py-1.5 transition-all duration-200 ${
                      active
                        ? isDark
                          ? "border-[#635BFF]/25 bg-[#635BFF]/15 text-white"
                          : "border-[#635BFF]/20 bg-[#635BFF]/[0.08] text-[#0A2540]"
                        : isDark
                          ? "border-white/[0.08] bg-white/[0.04] text-[#C1CED8] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/12"
                          : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]"
                    }`}
                    onClick={() => toggleRole(role.role_id)}
                    type="button"
                  >
                    {active ? (
                      <Check size={11} className="text-[#635BFF]" />
                    ) : (
                      <Tag size={11} className="text-[#8898AA] group-hover:text-[#635BFF]" />
                    )}
                    <span style={{ fontWeight: active ? 520 : 440 }}>{role.role_name}</span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div
              className={`rounded-2xl border px-4 py-4 ${
                isDark
                  ? "border-white/[0.08] bg-white/[0.03]"
                  : "border-[#E5E7EB] bg-[#FAFBFC]"
              }`}
            >
              <div className="flex items-start gap-3">
                <ShieldAlert size={18} className="mt-0.5 shrink-0 text-[#635BFF]" />
                <div>
                  <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                    No business roles are available yet.
                  </p>
                  <p className={`mt-1 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
                    Generate the role catalog first, then come back and attach the roles that
                    belong at {location.location_display_name ?? location.location_name}.
                  </p>
                </div>
              </div>
            </div>
          )}

          {!canConfigureRoles ? (
            <div className="rounded-2xl bg-[rgba(229,72,77,0.08)] px-4 py-3 text-[12px] text-[#C13535]" role="status" style={{ fontWeight: 500 }}>
              Only owners and admins can configure location roles.
            </div>
          ) : null}
        </div>

        <div className={`border-t px-5 py-5 sm:px-8 ${borderClass} ${isDark ? "bg-white/[0.03]" : "bg-[#FAFBFC]"}`}>
          <div className="flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-center">
            <div className="flex-1">
              {selectedRoleIds.length > 0 ? (
                <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 460 }}>
                  <span style={{ color: "#635BFF", fontWeight: 580 }}>
                    {selectedRoleIds.length}
                  </span>{" "}
                  roles selected - once enabled, this location can start building its live board.
                </p>
              ) : (
                <p className={`text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
                  Select at least one role to continue.
                </p>
              )}
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              {availableRoles.length === 0 ? (
                <button
                  className="inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)] disabled:opacity-40"
                  disabled={!canConfigureRoles || busyAction !== null || isPending}
                  onClick={handleDeriveRoles}
                  style={{
                    fontWeight: 540,
                    background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
                  }}
                  type="button"
                >
                  {busyAction === "derive" ? "Generating…" : "Generate roles"}
                </button>
              ) : null}
              <button
                className={`inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-[13px] text-white transition-all duration-300 ${
                  canConfigureRoles && selectedRoleIds.length > 0
                    ? "hover:shadow-[0_0_24px_rgba(99,91,255,0.3)]"
                    : "cursor-not-allowed opacity-30"
                }`}
                disabled={
                  !canConfigureRoles ||
                  selectedRoleIds.length === 0 ||
                  busyAction !== null ||
                  isPending
                }
                onClick={handleAttachRoles}
                style={{
                  fontWeight: 540,
                  background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
                }}
                type="button"
              >
                {busyAction === "attach" ? "Enabling roles…" : "Enable location roles"}
                <ArrowRight size={15} />
              </button>
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function LiveMode({
  board,
  currentWeekHref,
  isDark,
  location,
  nextWeekHref,
  previousWeekHref,
}: {
  board: WorkspaceBoard;
  currentWeekHref: string;
  isDark: boolean;
  location: WorkspaceLocation;
  nextWeekHref: string;
  previousWeekHref: string;
}) {
  const textPrimary = isDark ? "text-white" : "text-[#0A2540]";
  const textSecondary = isDark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const textMuted = "text-[#8898AA]";
  const panelClass = isDark
    ? "bg-[#0F2E4C] border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.25)]"
    : "bg-white border-[#E5E7EB] shadow-[0_1px_3px_rgba(0,0,0,0.04)]";
  const softPanelClass = isDark
    ? "bg-white/[0.03] border-white/[0.08]"
    : "bg-[#FAFBFC] border-[#E5E7EB]";
  const rowHover = isDark ? "hover:bg-white/[0.03]" : "hover:bg-[#FAFBFC]";

  const totalShifts = board.shifts.length;
  const coveredShifts = board.shifts.filter(
    (shift) =>
      Boolean(shift.current_assignment) ||
      shift.seats_filled >= shift.seats_requested,
  ).length;
  const fillRate = totalShifts
    ? Math.round((coveredShifts / totalShifts) * 100)
    : 100;
  const standbyDepth = board.shifts.reduce(
    (sum, shift) => sum + shift.standby_depth,
    0,
  );
  const topWorkers = [...board.workers]
    .sort((left, right) => right.reliability_score - left.reliability_score)
    .slice(0, 4);
  const upcomingShifts = [...board.shifts]
    .sort(
      (left, right) =>
        new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime(),
    )
    .slice(0, 5);
  const hotspotShifts = [...board.shifts]
    .filter(
      (shift) =>
        shift.manager_action_required ||
        shift.pending_offer_count > 0 ||
        shift.delivered_offer_count > 0 ||
        shift.standby_depth > 0 ||
        shift.status !== "covered",
    )
    .sort((left, right) => shiftWeight(right) - shiftWeight(left))
    .slice(0, 4);
  const roleCoverage = buildRoleCoverage(board);
  const metricCards = [
    {
      label: "Fill rate",
      value: `${fillRate}%`,
      detail: `${coveredShifts} of ${totalShifts} shifts staffed`,
    },
    {
      label: "Open shifts",
      value: String(board.action_summary.open_shifts),
      detail: `${board.action_summary.total} items need attention`,
    },
    {
      label: "Active coverage",
      value: String(board.action_summary.active_coverage),
      detail: `${hotspotShifts.length} shifts still in motion`,
    },
    {
      label: "Live team",
      value: String(board.workers.length),
      detail: `${standbyDepth} standby candidates across the week`,
    },
  ];

  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      initial={{ opacity: 0, y: 12 }}
      transition={{ duration: 0.5 }}
    >
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <span className={`text-[12px] uppercase tracking-[0.08em] ${textMuted}`} style={{ fontWeight: 520 }}>
            {location.business_display_name ?? location.business_name}
          </span>
          <h1
            className={`mt-2 text-[24px] sm:text-[28px] md:text-[32px] tracking-[-0.025em] ${textPrimary}`}
            style={{ fontWeight: 620 }}
          >
            {location.location_display_name ?? location.location_name}
          </h1>
          <p className={`mt-1 max-w-2xl text-[14px] ${textSecondary}`} style={{ fontWeight: 420 }}>
            {locationMeta(location) || "Live operating view for this location."}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-1 text-[11px] ${
                isDark ? "bg-white/[0.06] text-[#C1CED8]" : "bg-[#F0F0F5] text-[#5E6D7A]"
              }`}
              style={{ fontWeight: 500 }}
            >
              Week of {board.week_start_date}
            </span>
            <span className={`text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
              {formatWeekRange(board.week_start_date, board.week_end_date)} · {board.timezone}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={previousWeekHref}
            className={`inline-flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-[13px] transition-all ${
              isDark
                ? "border border-white/[0.08] bg-white/[0.04] text-[#C1CED8] hover:bg-white/[0.06]"
                : "border border-[#E5E7EB] bg-white text-[#5E6D7A] hover:bg-[#F7F8FA]"
            }`}
            style={{ fontWeight: 480 }}
          >
            Previous week
          </Link>
          <Link
            to={currentWeekHref}
            className={`inline-flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-[13px] transition-all ${
              isDark
                ? "border border-white/[0.08] bg-white/[0.04] text-[#C1CED8] hover:bg-white/[0.06]"
                : "border border-[#E5E7EB] bg-white text-[#5E6D7A] hover:bg-[#F7F8FA]"
            }`}
            style={{ fontWeight: 480 }}
          >
            This week
          </Link>
          <Link
            to={nextWeekHref}
            className="inline-flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)]"
            style={{
              fontWeight: 540,
              background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
            }}
          >
            Next week
          </Link>
        </div>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 xl:grid-cols-4">
        {metricCards.map((metric, index) => (
          <motion.div
            key={metric.label}
            animate={{ opacity: 1, y: 0 }}
            className={`${panelClass} rounded-2xl border px-4 py-4`}
            initial={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.4, delay: index * 0.05 }}
          >
            <div className="mb-1 flex items-center justify-between">
              <span className={`text-[11px] uppercase tracking-[0.04em] ${textMuted}`} style={{ fontWeight: 480 }}>
                {metric.label}
              </span>
              <div className="h-2 w-2 rounded-full bg-[#635BFF]" />
            </div>
            <span className={`block text-[26px] tracking-[-0.02em] ${textPrimary}`} style={{ fontWeight: 660 }}>
              {metric.value}
            </span>
            <span className={`mt-1 block text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>
              {metric.detail}
            </span>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <div className="space-y-6">
          <section className={`${panelClass} rounded-2xl border p-5 sm:p-6`}>
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <span className={`text-[11px] uppercase tracking-[0.06em] ${textMuted}`} style={{ fontWeight: 500 }}>
                  Coverage snapshot
                </span>
                <h2 className={`mt-1 text-[18px] tracking-[-0.01em] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  Role coverage this week
                </h2>
              </div>
              <div className="text-right">
                <strong className={`block text-[24px] tracking-[-0.02em] ${textPrimary}`} style={{ fontWeight: 640 }}>
                  {fillRate}%
                </strong>
                <span className={`text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>
                  staffed this week
                </span>
              </div>
            </div>

            {roleCoverage.length > 0 ? (
              <div className="space-y-3">
                {roleCoverage.map((item) => (
                  <div
                    key={item.label}
                    className={`flex items-center justify-between gap-3 rounded-2xl border px-4 py-3 ${softPanelClass}`}
                  >
                    <div>
                      <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                        {item.label}
                      </p>
                      <p className={`text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>
                        {item.covered}/{item.total} shifts covered
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-2.5 py-1 text-[11px] ${
                        item.status === "covered"
                          ? "bg-[#00B893]/10 text-[#00B893]"
                          : item.status === "filling"
                            ? "bg-[#635BFF]/10 text-[#635BFF]"
                            : "bg-[#E5484D]/10 text-[#E5484D]"
                      }`}
                      style={{ fontWeight: 520 }}
                    >
                      {item.status === "covered"
                        ? "Covered"
                        : item.status === "filling"
                          ? "Filling"
                          : "Open"}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className={`rounded-2xl border px-4 py-4 ${softPanelClass}`}>
                <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 500 }}>
                  No shifts scheduled yet
                </p>
                <p className={`mt-1 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
                  Once shifts are on the board, coverage by role will show up here.
                </p>
              </div>
            )}

            <div className="mt-5 h-2 overflow-hidden rounded-full bg-[#E5E7EB]/60">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#635BFF] to-[#8B5CF6]"
                style={{ width: `${fillRate}%` }}
              />
            </div>
          </section>

          <section className={`${panelClass} rounded-2xl border p-5 sm:p-6`}>
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <span className={`text-[11px] uppercase tracking-[0.06em] ${textMuted}`} style={{ fontWeight: 500 }}>
                  Upcoming shifts
                </span>
                <h2 className={`mt-1 text-[18px] tracking-[-0.01em] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  Next shifts on the board
                </h2>
              </div>
              <CalendarDays size={18} className="text-[#635BFF]" />
            </div>

            {upcomingShifts.length > 0 ? (
              <div className="space-y-2">
                {upcomingShifts.map((shift) => (
                  <div
                    key={shift.shift_id}
                    className={`flex items-center justify-between gap-3 rounded-2xl border px-4 py-3 transition-colors ${softPanelClass} ${rowHover}`}
                  >
                    <div className="min-w-0 flex-1">
                      <p className={`truncate text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                        {shift.role_name}
                      </p>
                      <p className={`mt-1 text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>
                        {formatShiftMeta(shift, board.timezone)}
                      </p>
                    </div>
                    <span className={`text-[11px] ${textSecondary} text-right`} style={{ fontWeight: 500 }}>
                      {shiftStatusLabel(shift)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className={`rounded-2xl border px-4 py-4 ${softPanelClass}`}>
                <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 500 }}>
                  No upcoming shifts for this week
                </p>
                <p className={`mt-1 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
                  Create or sync shifts to populate the live schedule.
                </p>
              </div>
            )}
          </section>
        </div>

        <div className="space-y-6">
          <section className={`${panelClass} rounded-2xl border p-5 sm:p-6`}>
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <span className={`text-[11px] uppercase tracking-[0.06em] ${textMuted}`} style={{ fontWeight: 500 }}>
                  Reliability
                </span>
                <h2 className={`mt-1 text-[18px] tracking-[-0.01em] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  Top staff
                </h2>
              </div>
              <Users size={18} className="text-[#635BFF]" />
            </div>

            {topWorkers.length > 0 ? (
              <div className="space-y-2">
                {topWorkers.map((worker) => (
                  <div
                    key={worker.employee_id}
                    className={`flex items-center justify-between gap-3 rounded-2xl border px-4 py-3 ${softPanelClass}`}
                  >
                    <div className="min-w-0 flex-1">
                      <p className={`truncate text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                        {worker.preferred_name || worker.full_name}
                      </p>
                      <p className={`mt-1 text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>
                        {worker.role_names.join(" · ") || "No active roles"}
                      </p>
                    </div>
                    <span className="rounded-full bg-[#00B893]/10 px-2.5 py-1 text-[11px] text-[#00B893]" style={{ fontWeight: 520 }}>
                      {worker.reliability_score.toFixed(1)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className={`rounded-2xl border px-4 py-4 ${softPanelClass}`}>
                <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 500 }}>
                  No workers enrolled yet
                </p>
                <p className={`mt-1 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
                  As teammates are assigned to this location, they will appear here.
                </p>
              </div>
            )}
          </section>

          <section className={`${panelClass} rounded-2xl border p-5 sm:p-6`}>
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <span className={`text-[11px] uppercase tracking-[0.06em] ${textMuted}`} style={{ fontWeight: 500 }}>
                  Action queue
                </span>
                <h2 className={`mt-1 text-[18px] tracking-[-0.01em] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  Coverage hotspots
                </h2>
              </div>
              <Clock3 size={18} className="text-[#635BFF]" />
            </div>

            {hotspotShifts.length > 0 ? (
              <div className="space-y-2">
                {hotspotShifts.map((shift) => (
                  <div
                    key={shift.shift_id}
                    className={`rounded-2xl border px-4 py-3 ${softPanelClass}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                        {shift.role_name}
                      </p>
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] ${
                          shift.manager_action_required
                            ? "bg-[#E5484D]/10 text-[#E5484D]"
                            : "bg-[#635BFF]/10 text-[#635BFF]"
                        }`}
                        style={{ fontWeight: 520 }}
                      >
                        {shiftStatusLabel(shift)}
                      </span>
                    </div>
                    <p className={`mt-1 text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>
                      {formatShiftMeta(shift, board.timezone)}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className={`rounded-2xl border px-4 py-4 ${softPanelClass}`}>
                <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 500 }}>
                  No active hotspots
                </p>
                <p className={`mt-1 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
                  This week is currently fully staffed with no active coverage pressure.
                </p>
              </div>
            )}
          </section>
        </div>
      </div>
    </motion.div>
  );
}

export default function Location({
  embeddedInShell = false,
  location,
  board,
  previousWeekHref,
  nextWeekHref,
  currentWeekHref,
}: LocationProps) {
  const navigate = useNavigate();
  const isDark = useResolvedAppAppearance() === "dark";
  const canConfigureRoles = ["owner", "admin"].includes(location.membership_role);

  const content = (
    <>
      <div className="mb-6">
        <button
          className={`flex items-center gap-1.5 text-[12px] text-[#8898AA] transition-colors ${isDark ? "hover:text-[#C1CED8]" : "hover:text-[#5E6D7A]"}`}
          onClick={() => navigate("/dashboard")}
          style={{ fontWeight: 440 }}
          type="button"
        >
          <ChevronLeft size={14} /> Back to Overview
        </button>
      </div>

      {board.location_setup_required ? (
        <SetupMode
          board={board}
          canConfigureRoles={canConfigureRoles}
          currentWeekHref={currentWeekHref}
          isDark={isDark}
          location={location}
        />
      ) : (
        <LiveMode
          board={board}
          currentWeekHref={currentWeekHref}
          isDark={isDark}
          location={location}
          nextWeekHref={nextWeekHref}
          previousWeekHref={previousWeekHref}
        />
      )}
    </>
  );

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav="">{content}</DashboardShell>;
}
