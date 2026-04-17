"use client";

import { useMemo } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import {
  Calendar,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Circle,
  Clock,
  Loader2,
  MapPin,
  XCircle,
} from "lucide-react";

import {
  getLocationReference,
} from "@/components/dashboard/location-role-reference";
import type { PublicEmployeeSchedule } from "@/lib/api/employee-schedules";

type EmployeeScheduleClientProps = {
  schedule: PublicEmployeeSchedule;
  token: string;
};

function parseDateOnly(value: string): Date {
  const [year, month, day] = value.split("-").map((part) => Number(part));
  return new Date(Date.UTC(year, month - 1, day));
}

function shiftDate(value: string, days: number): string {
  const base = parseDateOnly(value);
  base.setUTCDate(base.getUTCDate() + days);
  return base.toISOString().slice(0, 10);
}

function formatDate(date: Date): string {
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

function formatDateFull(dateValue: string, timezone: string): string {
  return new Date(dateValue).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: timezone,
  });
}

function formatTime(value: string, timezone: string): string {
  return new Date(value).toLocaleTimeString("en-US", {
    timeZone: timezone,
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatWeekLabel(schedule: PublicEmployeeSchedule): string {
  const start = parseDateOnly(schedule.week_start_date);
  const end = parseDateOnly(schedule.week_end_date);
  return `${formatDate(start)} - ${end.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  })}`;
}

function dateKeyInTimezone(value: string, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(value));
  const year = parts.find((part) => part.type === "year")?.value ?? "0000";
  const month = parts.find((part) => part.type === "month")?.value ?? "01";
  const day = parts.find((part) => part.type === "day")?.value ?? "01";
  return `${year}-${month}-${day}`;
}

function durationHours(startsAt: string, endsAt: string): number {
  const hours = (new Date(endsAt).getTime() - new Date(startsAt).getTime()) / 3_600_000;
  return Number.isFinite(hours) ? hours : 0;
}

function employeeInitials(name: string): string {
  return (
    name
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? "")
      .join("") || "BF"
  );
}

function getStatusConfig(status: string) {
  const normalized = (status ?? "scheduled") as string;
  switch (normalized) {
    case "callout":
      return {
        label: "Callout",
        icon: XCircle,
        color: "#DC2626",
        bgColor: "#DC2626",
        textColor: "#DC2626",
      };
    case "no_show":
      return {
        label: "No Show",
        icon: XCircle,
        color: "#DC2626",
        bgColor: "#DC2626",
        textColor: "#DC2626",
      };
    case "scheduled":
      return {
        label: "Scheduled",
        icon: Circle,
        color: "#635BFF",
        bgColor: "#635BFF",
        textColor: "#635BFF",
      };
    case "in_progress":
      return {
        label: "In Progress",
        icon: Loader2,
        color: "#00B893",
        bgColor: "#00B893",
        textColor: "#00B893",
      };
    case "completed":
      return {
        label: "Completed",
        icon: CheckCircle2,
        color: "#8898AA",
        bgColor: "#8898AA",
        textColor: "#8898AA",
      };
    case "cancelled":
      return {
        label: "Cancelled",
        icon: XCircle,
        color: "#DC2626",
        bgColor: "#DC2626",
        textColor: "#DC2626",
      };
    default:
      return {
        label: normalized.replaceAll("_", " "),
        icon: Circle,
        color: "#635BFF",
        bgColor: "#635BFF",
        textColor: "#635BFF",
      };
  }
}

function weekHref(
  token: string,
  options: {
    weekStart: string;
    locationId: string | null;
  },
): string {
  const params = new URLSearchParams({ week_start: options.weekStart });
  if (options.locationId) {
    params.set("location_id", options.locationId);
  }
  return `/schedule/${encodeURIComponent(token)}?${params.toString()}`;
}

export function EmployeeScheduleClient({
  schedule,
  token,
}: EmployeeScheduleClientProps) {
  const previousWeek = shiftDate(schedule.week_start_date, -7);
  const nextWeek = shiftDate(schedule.week_start_date, 7);
  const weekLabel = formatWeekLabel(schedule);
  const employeeRole = useMemo(() => {
    const uniqueRoles = Array.from(
      new Set(schedule.shifts.map((shift) => shift.role_name).filter(Boolean)),
    );
    if (uniqueRoles.length === 1) {
      return uniqueRoles[0];
    }
    if (uniqueRoles.length > 1) {
      return "Multiple roles";
    }
    return "Published schedule";
  }, [schedule.shifts]);

  const weekShifts = useMemo(
    () =>
      [...schedule.shifts].sort(
        (left, right) => new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime(),
      ),
    [schedule.shifts],
  );

  const totalHours = useMemo(
    () =>
      weekShifts.reduce(
        (sum, shift) =>
          shift.historical_display ? sum : sum + durationHours(shift.starts_at, shift.ends_at),
        0,
      ),
    [weekShifts],
  );

  const todayKey = useMemo(() => {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: schedule.timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const year = parts.find((part) => part.type === "year")?.value ?? "0000";
    const month = parts.find((part) => part.type === "month")?.value ?? "01";
    const day = parts.find((part) => part.type === "day")?.value ?? "01";
    return `${year}-${month}-${day}`;
  }, [schedule.timezone]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#FAFBFC] via-[#F7F8FA] to-[#FAFBFC]">
      <div className="border-b border-[#E5E7EB] bg-white">
        <div className="mx-auto max-w-4xl px-4 py-6">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] text-[15px] text-white ring-2 ring-[#635BFF]/20">
              <span style={{ fontWeight: 600 }}>{employeeInitials(schedule.employee_name)}</span>
            </div>
            <div>
              <h1 className="text-[20px] text-[#0A2540]" style={{ fontWeight: 600 }}>
                {schedule.employee_name}
              </h1>
              <p className="text-[13px] text-[#8898AA]" style={{ fontWeight: 440 }}>
                {employeeRole}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-4xl px-4 py-6">
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-4">
          <div className="flex items-center justify-between">
            <Link
              href={weekHref(token, {
                weekStart: previousWeek,
                locationId: schedule.selected_location_id,
              })}
              className="rounded-lg p-2 transition-colors hover:bg-[#F7F8FA]"
            >
              <ChevronLeft size={18} className="text-[#8898AA]" />
            </Link>

            <div className="text-center">
              <div className="mb-1 flex items-center justify-center gap-2">
                <Calendar size={14} className="text-[#8898AA]" />
                <p className="text-[14px] text-[#0A2540]" style={{ fontWeight: 560 }}>
                  {weekLabel}
                </p>
              </div>
              <p className="text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
                {totalHours % 1 === 0 ? totalHours.toFixed(0) : totalHours.toFixed(1)}h scheduled this week
                {schedule.selected_location_name ? ` • ${schedule.selected_location_name}` : ""}
              </p>
            </div>

            <Link
              href={weekHref(token, {
                weekStart: nextWeek,
                locationId: schedule.selected_location_id,
              })}
              className="rounded-lg p-2 transition-colors hover:bg-[#F7F8FA]"
            >
              <ChevronRight size={18} className="text-[#8898AA]" />
            </Link>
          </div>
        </div>

        <div className="mt-6 space-y-3">
          {weekShifts.length === 0 ? (
            <div className="rounded-xl border border-[#E5E7EB] bg-white p-12 text-center">
              <Calendar size={48} className="mx-auto mb-4 text-[#E5E7EB]" />
              <p className="text-[14px] text-[#8898AA]" style={{ fontWeight: 460 }}>
                No shifts scheduled this week
              </p>
            </div>
          ) : (
            weekShifts.map((shift) => {
              const statusConfig = getStatusConfig(shift.display_status || shift.lifecycle_status);
              const StatusIcon = statusConfig.icon;
              const dateKey = dateKeyInTimezone(shift.starts_at, shift.timezone);
              const isToday = dateKey === todayKey;
              const locationReference = getLocationReference({
                name: shift.location_name,
              });
              const hours = durationHours(shift.starts_at, shift.ends_at);
              const isHistorical = shift.historical_display;
              const isHistoricalIncident =
                shift.display_status === "callout" || shift.display_status === "no_show";
              const cardClassName = isHistorical
                ? isHistoricalIncident
                  ? "border-[#FECACA] bg-[#FEF2F2]"
                  : "border-[#D0D7DE] bg-[#F8FAFC]"
                : isToday
                  ? "border-[#635BFF] shadow-lg shadow-[#635BFF]/10"
                  : "border-[#E5E7EB] hover:border-[#635BFF]/30";
              const primaryTextClass = isHistorical ? "line-through text-[#5E6D7A]" : "text-[#0A2540]";
              const secondaryTextClass = isHistorical ? "line-through text-[#8898AA]" : "text-[#8898AA]";

              return (
                <motion.div
                  key={shift.shift_id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`rounded-xl border-2 transition-all ${cardClassName}`}
                >
                  <div className="p-5">
                    <div className="mb-4 flex items-start justify-between">
                      <div>
                        <p className={`mb-1 text-[15px] ${primaryTextClass}`} style={{ fontWeight: 560 }}>
                          {formatDateFull(shift.starts_at, shift.timezone)}
                        </p>
                        {isToday && !isHistorical ? (
                          <span
                            className="inline-block rounded-full bg-[#635BFF] px-2 py-0.5 text-[10px] uppercase tracking-wide text-white"
                            style={{ fontWeight: 600 }}
                          >
                            Today
                          </span>
                        ) : null}
                      </div>
                      <div
                        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5"
                        style={{ background: `${statusConfig.bgColor}10` }}
                      >
                        <StatusIcon
                          size={13}
                          className={shift.lifecycle_status === "in_progress" ? "animate-spin" : ""}
                          style={{ color: statusConfig.color }}
                        />
                        <span
                          className="text-[11px]"
                          style={{ fontWeight: 540, color: statusConfig.textColor }}
                        >
                          {statusConfig.label}
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                      <div className="flex items-start gap-2.5">
                        <div className="shrink-0 rounded-lg bg-[#F7F8FA] p-2">
                          <Clock size={16} className="text-[#635BFF]" />
                        </div>
                        <div>
                          <p
                            className="mb-0.5 text-[11px] uppercase tracking-wide text-[#8898AA]"
                            style={{ fontWeight: 500 }}
                          >
                            Time
                          </p>
                          <p className={`text-[13px] ${primaryTextClass}`} style={{ fontWeight: 520 }}>
                            {formatTime(shift.starts_at, shift.timezone)} - {formatTime(shift.ends_at, shift.timezone)}
                          </p>
                          <p className={`text-[11px] ${secondaryTextClass}`} style={{ fontWeight: 420 }}>
                            {hours % 1 === 0 ? hours.toFixed(0) : hours.toFixed(1)} hours
                          </p>
                        </div>
                      </div>

                      <div className="flex items-start gap-2.5">
                        <div className="shrink-0 rounded-lg bg-[#F7F8FA] p-2">
                          <MapPin size={16} className="text-[#635BFF]" />
                        </div>
                        <div>
                          <p
                            className="mb-0.5 text-[11px] uppercase tracking-wide text-[#8898AA]"
                            style={{ fontWeight: 500 }}
                          >
                            Location
                          </p>
                          <p className={`flex items-center gap-1 text-[13px] ${primaryTextClass}`} style={{ fontWeight: 520 }}>
                            <span>{locationReference.logo}</span>
                            <span>{shift.location_name}</span>
                          </p>
                        </div>
                      </div>

                      <div className="flex items-start gap-2.5">
                        <div className="shrink-0 rounded-lg bg-[#F7F8FA] p-2">
                          <div className="h-4 w-4 rounded-full bg-[#635BFF]" />
                        </div>
                        <div>
                          <p
                            className="mb-0.5 text-[11px] uppercase tracking-wide text-[#8898AA]"
                            style={{ fontWeight: 500 }}
                          >
                            Role
                          </p>
                          <p className={`text-[13px] ${primaryTextClass}`} style={{ fontWeight: 520 }}>
                            {shift.role_name}
                          </p>
                        </div>
                      </div>
                    </div>

                    {shift.notes ? (
                      <div className="mt-4 rounded-lg bg-[#F7F8FA] p-3">
                        <p className="text-[12px] text-[#5E6D7A]" style={{ fontWeight: 440 }}>
                          {shift.notes}
                        </p>
                      </div>
                    ) : null}
                  </div>
                </motion.div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
