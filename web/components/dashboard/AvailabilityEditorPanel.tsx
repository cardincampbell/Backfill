"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Briefcase,
  CalendarClock,
  Check,
  ChevronDown,
  Copy,
  Info,
  Loader2,
  Sparkles,
  Sunrise,
  Sunset,
} from "lucide-react";

import { FloatingDropdown } from "@/components/floating-dropdown";
import type {
  EmployeeAvailabilityRulePayload,
  SelfEmployeeAvailability,
} from "@/lib/api/workforce";

export type AvailabilityEditorFeedback = {
  tone: "success" | "error";
  message: string;
} | null;

export type DayState = {
  enabled: boolean;
  startTime: string;
  endTime: string;
};

export const DAY_ORDER = [
  { index: 0, short: "Mon", label: "Monday" },
  { index: 1, short: "Tue", label: "Tuesday" },
  { index: 2, short: "Wed", label: "Wednesday" },
  { index: 3, short: "Thu", label: "Thursday" },
  { index: 4, short: "Fri", label: "Friday" },
  { index: 5, short: "Sat", label: "Saturday" },
  { index: 6, short: "Sun", label: "Sunday" },
] as const;

const DEFAULT_START_TIME = "7:00 AM";
const DEFAULT_END_TIME = "5:00 PM";

const TIME_OPTIONS = Array.from({ length: 48 }, (_, index) => {
  const hour24 = Math.floor(index / 2);
  const minutes = index % 2 === 0 ? "00" : "30";
  const period = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  const label = `${hour12}:${minutes} ${period}`;
  return {
    value: label,
    label,
  };
});

export function createDefaultDayMap(): Record<number, DayState> {
  return Object.fromEntries(
    DAY_ORDER.map((day) => [
      day.index,
      {
        enabled: false,
        startTime: DEFAULT_START_TIME,
        endTime: DEFAULT_END_TIME,
      },
    ]),
  ) as Record<number, DayState>;
}

function timeLabelToMinutes(label: string): number {
  const [timePart, periodPart] = label.trim().split(" ");
  const [rawHour, rawMinute = "0"] = timePart.split(":");
  let hour = Number(rawHour);
  const minute = Number(rawMinute);

  if (Number.isNaN(hour) || Number.isNaN(minute)) {
    return 0;
  }

  const period = periodPart?.toUpperCase();
  if (period === "PM" && hour !== 12) {
    hour += 12;
  }
  if (period === "AM" && hour === 12) {
    hour = 0;
  }

  return hour * 60 + minute;
}

function parseApiTimeToLabel(value: string, fallback: string): string {
  const [rawHour = "0", rawMinute = "0"] = value.split(":");
  const hour = Number(rawHour);
  const minute = Number(rawMinute);
  if (Number.isNaN(hour) || Number.isNaN(minute)) {
    return fallback;
  }

  let normalizedHour = hour;
  let normalizedMinute = minute;
  if (hour >= 23 && minute >= 45) {
    normalizedHour = 23;
    normalizedMinute = 30;
  } else if (minute >= 45) {
    normalizedHour = Math.min(hour + 1, 23);
    normalizedMinute = 0;
  } else if (minute >= 15 && minute < 45) {
    normalizedMinute = 30;
  } else {
    normalizedMinute = 0;
  }

  const period = normalizedHour >= 12 ? "PM" : "AM";
  const hour12 = normalizedHour % 12 === 0 ? 12 : normalizedHour % 12;
  return `${hour12}:${String(normalizedMinute).padStart(2, "0")} ${period}`;
}

function toApiTime(label: string): string {
  const minutes = timeLabelToMinutes(label);
  const hour = Math.floor(minutes / 60);
  const minute = minutes % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00`;
}

function formatHoursPerWeek(dayStates: Record<number, DayState>): number {
  return DAY_ORDER.reduce((sum, day) => {
    const state = dayStates[day.index];
    if (!state.enabled) {
      return sum;
    }
    const duration =
      (timeLabelToMinutes(state.endTime) - timeLabelToMinutes(state.startTime)) / 60;
    return sum + Math.max(duration, 0.5);
  }, 0);
}

export function buildStateFromRules(
  availability: Pick<SelfEmployeeAvailability, "rules">,
): Record<number, DayState> {
  const nextState = createDefaultDayMap();

  for (const day of DAY_ORDER) {
    const rules = availability.rules
      .filter(
        (rule) =>
          rule.day_of_week === day.index && rule.availability_type === "available",
      )
      .sort((left, right) =>
        left.start_local_time.localeCompare(right.start_local_time),
      );

    if (rules.length === 0) {
      continue;
    }

    nextState[day.index] = {
      enabled: true,
      startTime: parseApiTimeToLabel(
        rules[0].start_local_time,
        DEFAULT_START_TIME,
      ),
      endTime: parseApiTimeToLabel(
        rules[rules.length - 1].end_local_time,
        DEFAULT_END_TIME,
      ),
    };
  }

  return nextState;
}

export function statesEqual(
  left: Record<number, DayState>,
  right: Record<number, DayState>,
): boolean {
  return DAY_ORDER.every((day) => {
    const leftState = left[day.index];
    const rightState = right[day.index];
    return (
      leftState.enabled === rightState.enabled &&
      leftState.startTime === rightState.startTime &&
      leftState.endTime === rightState.endTime
    );
  });
}

export function countDayChanges(
  left: Record<number, DayState>,
  right: Record<number, DayState>,
): number {
  return DAY_ORDER.reduce((count, day) => {
    const leftState = left[day.index];
    const rightState = right[day.index];
    if (
      leftState.enabled !== rightState.enabled ||
      leftState.startTime !== rightState.startTime ||
      leftState.endTime !== rightState.endTime
    ) {
      return count + 1;
    }
    return count;
  }, 0);
}

export function serializeAvailability(
  dayStates: Record<number, DayState>,
  timezone: string,
): { rules: EmployeeAvailabilityRulePayload[] } {
  return {
    rules: DAY_ORDER.filter((day) => dayStates[day.index].enabled).map((day) => {
      const state = dayStates[day.index];
      return {
        day_of_week: day.index,
        start_local_time: toApiTime(state.startTime),
        end_local_time: toApiTime(state.endTime),
        timezone,
        availability_type: "available",
        priority: 0,
        availability_metadata: {
          source: "availability_editor",
        },
      };
    }),
  };
}

export function ensureTimeOrder(state: DayState): DayState {
  const startMinutes = timeLabelToMinutes(state.startTime);
  const endMinutes = timeLabelToMinutes(state.endTime);
  if (endMinutes > startMinutes) {
    return state;
  }

  const startIndex = TIME_OPTIONS.findIndex((option) => option.value === state.startTime);
  const safeEnd =
    TIME_OPTIONS[Math.min(startIndex + 1, TIME_OPTIONS.length - 1)]?.value ??
    DEFAULT_END_TIME;
  return {
    ...state,
    endTime: safeEnd,
  };
}

function AvailabilityTimeSelect({
  dark,
  onChange,
  value,
}: {
  dark: boolean;
  onChange(value: string): void;
  value: string;
}) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((current) => !current)}
        className={`flex h-10 w-full items-center justify-between gap-2 rounded-lg border px-3 text-[12px] transition-all ${
          dark
            ? "border-white/[0.08] bg-white/[0.05] text-white hover:border-[#635BFF]/40"
            : "border-[#E5E7EB] bg-[#F7F8FA] text-[#0A2540] hover:border-[#635BFF]/30"
        }`}
        style={{ fontWeight: 460 }}
      >
        <span>{value}</span>
        <ChevronDown
          size={12}
          className={dark ? "text-[#C1CED8]" : "text-[#8898AA]"}
        />
      </button>

      <FloatingDropdown
        anchorRef={buttonRef}
        className={`overflow-y-auto rounded-xl py-1 ${
          dark
            ? "border border-white/[0.08] bg-[#102B46] shadow-[0_24px_60px_rgba(0,0,0,0.4)]"
            : "border border-[#E5E7EB] bg-white shadow-lg"
        }`}
        maxHeight={240}
        minWidth={180}
        onClose={() => setOpen(false)}
        open={open}
        width={180}
        zIndex={10030}
      >
        {TIME_OPTIONS.map((option) => {
          const isSelected = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] transition-colors ${
                isSelected
                  ? "bg-[#635BFF]/[0.08] text-[#635BFF]"
                  : dark
                    ? "text-white hover:bg-white/[0.06]"
                    : "text-[#0A2540] hover:bg-[#F7F8FA]"
              }`}
              style={{ fontWeight: isSelected ? 520 : 440 }}
            >
              <span className={isSelected ? "" : "ml-4"}>{option.label}</span>
            </button>
          );
        })}
      </FloatingDropdown>
    </div>
  );
}

function AvailabilityPresetButton({
  dark,
  icon: Icon,
  label,
  onClick,
}: {
  dark: boolean;
  icon: typeof CalendarClock;
  label: string;
  onClick(): void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-2 rounded-lg border px-3.5 py-2 text-[12px] transition-all duration-200 ${
        dark
          ? "border-white/[0.08] bg-white/[0.03] text-[#C1CED8] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08] hover:text-white"
          : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03] hover:text-[#635BFF]"
      }`}
      style={{ fontWeight: 460 }}
    >
      <Icon size={13} className="opacity-70" />
      {label}
    </button>
  );
}

function DayRow({
  copySuccess,
  dark,
  day,
  onCopyToAll,
  onSetEnabled,
  onSetEndTime,
  onSetStartTime,
  state,
}: {
  copySuccess: boolean;
  dark: boolean;
  day: (typeof DAY_ORDER)[number];
  onCopyToAll(): void;
  onSetEnabled(enabled: boolean): void;
  onSetEndTime(nextValue: string): void;
  onSetStartTime(nextValue: string): void;
  state: DayState;
}) {
  const rowSurfaceClass = state.enabled
    ? dark
      ? "border-white/[0.08] bg-white/[0.03]"
      : "border-[#E5E7EB] bg-white"
    : dark
      ? "border-white/[0.06] bg-white/[0.015]"
      : "border-[#F0F0F5] bg-[#FAFBFC]";

  return (
    <motion.div
      layout
      className={`rounded-xl border transition-all duration-300 ${rowSurfaceClass}`}
    >
      <div className="flex items-center gap-3 p-3 sm:p-4">
        <button
          type="button"
          onClick={() => onSetEnabled(!state.enabled)}
          className={`relative flex h-10 w-10 shrink-0 flex-col overflow-hidden rounded-lg border transition-all duration-300 sm:h-11 sm:w-11 ${
            state.enabled
              ? dark
                ? "border-[#635BFF] bg-[#0F2E4C] shadow-[0_2px_8px_rgba(99,91,255,0.28)]"
                : "border-[#635BFF] bg-white shadow-[0_2px_8px_rgba(99,91,255,0.25)]"
              : dark
                ? "border-white/[0.08] bg-white/[0.04] hover:border-white/[0.16]"
                : "border-[#E5E7EB] bg-[#F0F0F5] hover:border-[#C1CED8] hover:bg-[#E5E7EB]"
          }`}
        >
          <div
            className={`relative h-2.5 w-full transition-colors duration-300 ${
              state.enabled ? "bg-[#635BFF]" : "bg-[#C1CED8]"
            }`}
          >
            <div className="absolute inset-x-0 top-1/2 flex -translate-y-1/2 items-center justify-center gap-3 sm:gap-4">
              <div className={`h-1 w-1 rounded-full ${state.enabled ? "bg-white/40" : "bg-white/30"}`} />
              <div className={`h-1 w-1 rounded-full ${state.enabled ? "bg-white/40" : "bg-white/30"}`} />
            </div>
          </div>
          <div className="flex flex-1 items-center justify-center">
            <span
              className={`text-[11px] transition-colors duration-300 sm:text-[12px] ${
                state.enabled ? "text-[#635BFF]" : dark ? "text-[#8898AA]" : "text-[#C1CED8]"
              }`}
              style={{ fontWeight: 600 }}
            >
              {day.short}
            </span>
          </div>
        </button>

        <div className="hidden min-w-0 flex-1 sm:block">
          <p
            className="text-[13px]"
            style={{
              fontWeight: 500,
              color: state.enabled ? (dark ? "#FFFFFF" : "#0A2540") : dark ? "#8898AA" : "#C1CED8",
            }}
          >
            {day.label}
          </p>
          {state.enabled ? (
            <p className={`mt-0.5 text-[11px] ${dark ? "text-[#C1CED8]" : "text-[#8898AA]"}`} style={{ fontWeight: 420 }}>
              {state.startTime} – {state.endTime}
            </p>
          ) : (
            <p className={`text-[11px] ${dark ? "text-[#8898AA]" : "text-[#C1CED8]"}`} style={{ fontWeight: 420 }}>
              Unavailable
            </p>
          )}
        </div>

        <AnimatePresence>
          {state.enabled ? (
            <motion.div
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: "auto" }}
              exit={{ opacity: 0, width: 0 }}
              className="flex shrink-0 items-center gap-1.5 overflow-hidden sm:gap-2"
            >
              <div className="w-[100px] sm:w-[110px]">
                <AvailabilityTimeSelect dark={dark} onChange={onSetStartTime} value={state.startTime} />
              </div>
              <span className="text-[10px] text-[#C1CED8]" style={{ fontWeight: 420 }}>
                to
              </span>
              <div className="w-[100px] sm:w-[110px]">
                <AvailabilityTimeSelect dark={dark} onChange={onSetEndTime} value={state.endTime} />
              </div>
              <button
                type="button"
                title={`Copy ${day.short}'s hours to all days`}
                onClick={onCopyToAll}
                className="group rounded-lg p-1.5 transition-all hover:bg-[#635BFF]/[0.06]"
              >
                {copySuccess ? (
                  <Check size={13} className="text-[#00B893]" />
                ) : (
                  <Copy size={13} className="text-[#C1CED8] transition-colors group-hover:text-[#635BFF]" />
                )}
              </button>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

export function AvailabilityEditorPanel({
  dark,
  dayStates,
  feedback,
  loadingMessage = "Loading availability…",
  onApplyPreset,
  onCopyToAll,
  onSetDayEnabled,
  onSetEndTime,
  onSetStartTime,
  savedPulse = false,
  showProvisioningHint = false,
  status,
}: {
  dark: boolean;
  dayStates: Record<number, DayState>;
  feedback: AvailabilityEditorFeedback;
  loadingMessage?: string;
  onApplyPreset(dayFilter: "all" | "weekdays" | "weekends", timeFilter: "all" | "mornings" | "evenings"): void;
  onCopyToAll(dayIndex: number): void;
  onSetDayEnabled(dayIndex: number, enabled: boolean): void;
  onSetEndTime(dayIndex: number, nextValue: string): void;
  onSetStartTime(dayIndex: number, nextValue: string): void;
  savedPulse?: boolean;
  showProvisioningHint?: boolean;
  status: "loading" | "ready" | "error";
}) {
  const [copyFrom, setCopyFrom] = useState<number | null>(null);

  useEffect(() => {
    if (copyFrom === null) {
      return;
    }
    const timeoutId = window.setTimeout(() => setCopyFrom(null), 1500);
    return () => window.clearTimeout(timeoutId);
  }, [copyFrom]);

  const enabledCount = useMemo(
    () => DAY_ORDER.filter((day) => dayStates[day.index].enabled).length,
    [dayStates],
  );
  const totalHours = useMemo(() => Math.round(formatHoursPerWeek(dayStates)), [dayStates]);

  if (status === "loading") {
    return (
      <div className={`flex items-center gap-2 py-6 text-[13px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`}>
        <Loader2 size={15} className="animate-spin" />
        {loadingMessage}
      </div>
    );
  }

  if (status === "error") {
    return (
      <div
        className="rounded-[24px] px-4 py-3 text-[13px]"
        role="status"
        style={{
          background: "rgba(229, 72, 77, 0.08)",
          color: "#C13535",
          fontWeight: 500,
        }}
      >
        {feedback?.message ?? "Could not load availability."}
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="space-y-5">
      <div className="flex flex-wrap gap-2">
        <AvailabilityPresetButton dark={dark} icon={CalendarClock} label="All Days" onClick={() => onApplyPreset("all", "all")} />
        <AvailabilityPresetButton dark={dark} icon={Briefcase} label="Weekdays" onClick={() => onApplyPreset("weekdays", "all")} />
        <AvailabilityPresetButton dark={dark} icon={Sparkles} label="Weekends" onClick={() => onApplyPreset("weekends", "all")} />
        <AvailabilityPresetButton dark={dark} icon={Sunrise} label="Mornings" onClick={() => onApplyPreset("all", "mornings")} />
        <AvailabilityPresetButton dark={dark} icon={Sunset} label="Evenings" onClick={() => onApplyPreset("all", "evenings")} />
      </div>

      {showProvisioningHint ? (
        <div className={`rounded-[20px] border px-4 py-3 ${dark ? "border-white/[0.08] bg-white/[0.03]" : "border-[#E5E7EB] bg-[#FAFBFC]"}`} role="status">
          <div className="flex items-start gap-3">
            <Info size={16} className="mt-0.5 shrink-0 text-[#8898AA]" />
            <div>
              <p className={`text-[13px] ${dark ? "text-white" : "text-[#0A2540]"}`} style={{ fontWeight: 560 }}>
                Availability is ready to set up
              </p>
              <p className={`mt-1 text-[12px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 420 }}>
                Save hours here to define when this employee is generally available for scheduling.
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {feedback?.tone === "error" ? (
        <div
          className="rounded-[20px] px-4 py-3 text-[13px]"
          role="status"
          style={{
            background: "rgba(229, 72, 77, 0.08)",
            color: "#C13535",
            fontWeight: 500,
          }}
        >
          {feedback.message}
        </div>
      ) : null}

      <div className="mb-3 flex items-center justify-end">
        <div className="flex items-center gap-2.5">
          <span className={`text-[11px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 500 }}>
            {enabledCount} days
          </span>
          <div className={`h-3 w-px ${dark ? "bg-white/[0.08]" : "bg-[#E5E7EB]"}`} />
          <span className={`text-[11px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 500 }}>
            {totalHours}h / wk
          </span>
          <AnimatePresence>
            {savedPulse ? (
              <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }} className="ml-1 flex items-center gap-1 text-[#00B893]">
                <Check size={12} />
                <span className="text-[11px]" style={{ fontWeight: 500 }}>
                  Saved
                </span>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </div>

      <div className="space-y-2">
        {DAY_ORDER.map((day) => (
          <DayRow
            key={day.index}
            copySuccess={copyFrom === day.index}
            dark={dark}
            day={day}
            onCopyToAll={() => {
              onCopyToAll(day.index);
              setCopyFrom(day.index);
            }}
            onSetEnabled={(enabled) => onSetDayEnabled(day.index, enabled)}
            onSetEndTime={(nextValue) => onSetEndTime(day.index, nextValue)}
            onSetStartTime={(nextValue) => onSetStartTime(day.index, nextValue)}
            state={dayStates[day.index]}
          />
        ))}
      </div>
    </motion.div>
  );
}
