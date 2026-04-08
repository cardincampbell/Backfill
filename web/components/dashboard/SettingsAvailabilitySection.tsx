"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { motion } from "motion/react";
import { CalendarDays, Copy, Info, Loader2 } from "lucide-react";

import {
  getSelfEmployeeAvailability,
  replaceSelfEmployeeAvailability,
  type SelfEmployeeAvailability,
} from "@/lib/api/workforce";

type Feedback = {
  tone: "success" | "error";
  message: string;
} | null;

type DayState = {
  enabled: boolean;
  startHour: number;
  endHour: number;
};

const DEFAULT_START_HOUR = 9;
const DEFAULT_END_HOUR = 22;
const DAY_ORDER = [
  { index: 0, short: "MON", label: "Monday" },
  { index: 1, short: "TUE", label: "Tuesday" },
  { index: 2, short: "WED", label: "Wednesday" },
  { index: 3, short: "THU", label: "Thursday" },
  { index: 4, short: "FRI", label: "Friday" },
  { index: 5, short: "SAT", label: "Saturday" },
  { index: 6, short: "SUN", label: "Sunday" },
] as const;

function createDefaultDayMap(): Record<number, DayState> {
  return Object.fromEntries(
    DAY_ORDER.map((day) => [
      day.index,
      {
        enabled: false,
        startHour: DEFAULT_START_HOUR,
        endHour: DEFAULT_END_HOUR,
      },
    ]),
  ) as Record<number, DayState>;
}

function parseHour(value: string, { isEnd }: { isEnd: boolean }): number {
  const [rawHour, rawMinute = "0"] = value.split(":");
  const hour = Number(rawHour);
  const minute = Number(rawMinute);
  if (Number.isNaN(hour) || Number.isNaN(minute)) {
    return isEnd ? DEFAULT_END_HOUR : DEFAULT_START_HOUR;
  }
  if (isEnd && hour === 23 && minute >= 30) {
    return 24;
  }
  return Math.max(0, Math.min(24, hour + (minute >= 30 ? 1 : 0)));
}

function formatHour(hour: number): string {
  const normalized = hour === 24 ? 24 : ((hour % 24) + 24) % 24;
  const period = normalized >= 12 && normalized < 24 ? "PM" : "AM";
  const displayHour = normalized % 12 === 0 ? 12 : normalized % 12;
  return `${displayHour} ${period}`;
}

function buildStateFromRules(
  availability: SelfEmployeeAvailability,
): Record<number, DayState> {
  const nextState = createDefaultDayMap();

  for (const day of DAY_ORDER) {
    const rules = availability.rules
      .filter(
        (rule) =>
          rule.day_of_week === day.index && rule.availability_type === "available",
      )
      .sort((left, right) => left.start_local_time.localeCompare(right.start_local_time));
    if (rules.length === 0) {
      continue;
    }
    const startHour = parseHour(rules[0].start_local_time, { isEnd: false });
    const endHour = parseHour(rules[rules.length - 1].end_local_time, { isEnd: true });
    nextState[day.index] = {
      enabled: true,
      startHour: Math.min(startHour, 23),
      endHour: Math.max(Math.min(endHour, 24), Math.min(startHour + 1, 24)),
    };
  }

  return nextState;
}

function statesEqual(
  left: Record<number, DayState>,
  right: Record<number, DayState>,
): boolean {
  return DAY_ORDER.every((day) => {
    const leftState = left[day.index];
    const rightState = right[day.index];
    return (
      leftState.enabled === rightState.enabled &&
      leftState.startHour === rightState.startHour &&
      leftState.endHour === rightState.endHour
    );
  });
}

function serializeAvailability(
  dayStates: Record<number, DayState>,
  timezone: string,
) {
  return {
    rules: DAY_ORDER.filter((day) => dayStates[day.index].enabled).map((day) => {
      const state = dayStates[day.index];
      const endTime = state.endHour >= 24 ? "23:59:00" : `${String(state.endHour).padStart(2, "0")}:00:00`;
      return {
        day_of_week: day.index,
        start_local_time: `${String(state.startHour).padStart(2, "0")}:00:00`,
        end_local_time: endTime,
        timezone,
        availability_type: "available",
        priority: 0,
        availability_metadata: {
          source: "settings_personal_availability",
        },
      };
    }),
  };
}

function DayChip({
  dark,
  selected,
  label,
  onClick,
}: {
  dark: boolean;
  selected: boolean;
  label: string;
  onClick(): void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex h-12 min-w-[68px] items-center justify-center rounded-2xl border text-[12px] transition-all duration-200 ${
        selected
          ? "border-[#635BFF] bg-[#635BFF] text-white shadow-[0_8px_20px_rgba(99,91,255,0.22)]"
          : dark
            ? "border-white/[0.08] bg-white/[0.03] text-[#C1CED8] hover:border-white/[0.16] hover:bg-white/[0.05]"
            : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A] hover:border-[#D1D5DB] hover:bg-white"
      }`}
      style={{ fontWeight: 600 }}
    >
      {label}
    </button>
  );
}

function DayAvailabilityCard({
  dark,
  label,
  anchorLabel,
  isAnchor,
  state,
  onCopy,
  onSetEnabled,
  onSetHours,
}: {
  dark: boolean;
  label: string;
  anchorLabel: string | null;
  isAnchor: boolean;
  state: DayState;
  onCopy(): void;
  onSetEnabled(enabled: boolean): void;
  onSetHours(next: Pick<DayState, "startHour" | "endHour">): void;
}) {
  const isAllDay = state.startHour === 0 && state.endHour >= 24;
  const trackLeft = (state.startHour / 24) * 100;
  const trackRight = (state.endHour / 24) * 100;
  const trackWidth = Math.max(trackRight - trackLeft, 4);

  return (
    <div
      className={`rounded-[24px] border p-4 ${
        dark
          ? "border-white/[0.08] bg-white/[0.03]"
          : "border-[#E5E7EB] bg-[#FAFBFC]"
      }`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className={`text-[13px] ${dark ? "text-white" : "text-[#0A2540]"}`} style={{ fontWeight: 600 }}>
            {label}
          </div>
          {!isAnchor && anchorLabel ? (
            <button
              type="button"
              onClick={onCopy}
              className="mt-1 inline-flex items-center gap-1 text-[11px] text-[#635BFF] transition-colors hover:text-[#4B3FD9]"
              style={{ fontWeight: 520 }}
            >
              Same as {anchorLabel}? <Copy size={12} /> Copy
            </button>
          ) : null}
        </div>

        <div
          className={`inline-flex items-center rounded-full border p-1 ${
            dark ? "border-white/[0.08] bg-white/[0.04]" : "border-[#E5E7EB] bg-white"
          }`}
        >
          <button
            type="button"
            onClick={() => {
              onSetEnabled(true);
              onSetHours({ startHour: 0, endHour: 24 });
            }}
            className={`rounded-full px-3 py-1.5 text-[11px] transition-all ${
              isAllDay
                ? "bg-[#635BFF] text-white"
                : dark
                  ? "text-[#C1CED8] hover:bg-white/[0.06]"
                  : "text-[#5E6D7A] hover:bg-[#F7F8FA]"
            }`}
            style={{ fontWeight: 520 }}
          >
            All day
          </button>
          <button
            type="button"
            onClick={() => {
              onSetEnabled(true);
              if (isAllDay) {
                onSetHours({
                  startHour: DEFAULT_START_HOUR,
                  endHour: DEFAULT_END_HOUR,
                });
              }
            }}
            className={`rounded-full px-3 py-1.5 text-[11px] transition-all ${
              !isAllDay
                ? "bg-[#635BFF] text-white"
                : dark
                  ? "text-[#C1CED8] hover:bg-white/[0.06]"
                  : "text-[#5E6D7A] hover:bg-[#F7F8FA]"
            }`}
            style={{ fontWeight: 520 }}
          >
            Custom
          </button>
        </div>
      </div>

      <div className="mt-4">
        <div className="relative h-9">
          <div
            className={`absolute left-0 right-0 top-1/2 h-2 -translate-y-1/2 rounded-full ${
              dark ? "bg-white/[0.08]" : "bg-[#E5E7EB]"
            }`}
          />
          <div
            className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-[#635BFF]"
            style={{
              left: `${trackLeft}%`,
              width: `${trackWidth}%`,
            }}
          />
          <input
            type="range"
            min={0}
            max={23}
            step={1}
            value={state.startHour}
            onChange={(event) => {
              const nextStart = Math.min(Number(event.target.value), state.endHour - 1);
              onSetHours({ startHour: nextStart, endHour: state.endHour });
            }}
            className="availability-range availability-range-start absolute inset-0 h-9 w-full bg-transparent"
            aria-label={`${label} start time`}
          />
          <input
            type="range"
            min={1}
            max={24}
            step={1}
            value={state.endHour}
            onChange={(event) => {
              const nextEnd = Math.max(Number(event.target.value), state.startHour + 1);
              onSetHours({ startHour: state.startHour, endHour: nextEnd });
            }}
            className="availability-range availability-range-end absolute inset-0 h-9 w-full bg-transparent"
            aria-label={`${label} end time`}
          />
        </div>

        <div className={`mt-2 flex items-center justify-between text-[12px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 500 }}>
          <span>{formatHour(state.startHour)}</span>
          <span>{formatHour(state.endHour)}</span>
        </div>
      </div>
    </div>
  );
}

export default function SettingsAvailabilitySection({
  businessId,
  businessTimezone,
  dark,
}: {
  businessId: string | null;
  businessTimezone: string | null;
  dark: boolean;
}) {
  const [status, setStatus] = useState<"loading" | "ready" | "unlinked" | "error">(
    businessId ? "loading" : "error",
  );
  const [employeeName, setEmployeeName] = useState<string | null>(null);
  const [timezone, setTimezone] = useState<string>(businessTimezone ?? "UTC");
  const [dayStates, setDayStates] = useState<Record<number, DayState>>(createDefaultDayMap);
  const [baseline, setBaseline] = useState<Record<number, DayState>>(createDefaultDayMap);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    if (!businessId) {
      setStatus("error");
      setFeedback({
        tone: "error",
        message: "No business is available for personal availability.",
      });
      return;
    }

    let cancelled = false;
    const resolvedBusinessId: string = businessId;

    async function loadAvailability() {
      try {
        setStatus("loading");
        setFeedback(null);
        const availability = await getSelfEmployeeAvailability(resolvedBusinessId);
        if (cancelled) {
          return;
        }
        const nextState = buildStateFromRules(availability);
        setEmployeeName(availability.employee_name);
        setTimezone(
          availability.rules.length > 0
            ? availability.timezone || businessTimezone || "UTC"
            : businessTimezone || availability.timezone || "UTC",
        );
        setDayStates(nextState);
        setBaseline(nextState);
        setStatus("ready");
      } catch (error) {
        if (cancelled) {
          return;
        }
        const message =
          error instanceof Error
            ? error.message
            : "Could not load your availability right now.";
        if (message === "employee_self_not_found") {
          setStatus("unlinked");
          setFeedback(null);
          setDayStates(createDefaultDayMap());
          setBaseline(createDefaultDayMap());
          return;
        }
        setStatus("error");
        setFeedback({ tone: "error", message });
      }
    }

    void loadAvailability();

    return () => {
      cancelled = true;
    };
  }, [businessId, businessTimezone]);

  const selectedDays = useMemo(
    () => DAY_ORDER.filter((day) => dayStates[day.index].enabled),
    [dayStates],
  );
  const firstSelectedDay = selectedDays[0] ?? null;
  const dirty = !statesEqual(dayStates, baseline);
  const canSave = status === "ready" && dirty && !isPending;

  const updateDayState = (dayIndex: number, next: Partial<DayState>) => {
    setDayStates((current) => ({
      ...current,
      [dayIndex]: {
        ...current[dayIndex],
        ...next,
      },
    }));
  };

  const toggleDay = (dayIndex: number) => {
    setDayStates((current) => ({
      ...current,
      [dayIndex]: current[dayIndex].enabled
        ? { ...current[dayIndex], enabled: false }
        : {
            ...current[dayIndex],
            enabled: true,
          },
    }));
  };

  const handleSave = () => {
    if (!businessId || !canSave) {
      return;
    }
    const resolvedBusinessId = businessId;

    startTransition(async () => {
      try {
        setFeedback(null);
        const payload = serializeAvailability(dayStates, timezone);
        const response = await replaceSelfEmployeeAvailability(resolvedBusinessId, payload);
        const nextState = buildStateFromRules(response);
        setEmployeeName(response.employee_name);
        setTimezone(
          response.rules.length > 0 ? response.timezone || timezone : timezone,
        );
        setDayStates(nextState);
        setBaseline(nextState);
        setFeedback({ tone: "success", message: "Availability updated." });
      } catch (error) {
        setFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not update your availability.",
        });
      }
    });
  };

  if (status === "loading") {
    return (
      <div className={`flex items-center gap-2 py-6 text-[13px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`}>
        <Loader2 size={15} className="animate-spin" />
        Loading availability…
      </div>
    );
  }

  if (status === "unlinked") {
    return (
      <div
        className={`rounded-[24px] border p-5 ${
          dark ? "border-white/[0.08] bg-white/[0.03]" : "border-[#E5E7EB] bg-[#FAFBFC]"
        }`}
      >
        <div className="flex items-start gap-3">
          <Info size={16} className="mt-0.5 shrink-0 text-[#8898AA]" />
          <div>
            <p className={`text-[13px] ${dark ? "text-white" : "text-[#0A2540]"}`} style={{ fontWeight: 560 }}>
              No linked employee profile yet
            </p>
            <p className={`mt-1 text-[12px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 420 }}>
              We could not match this account to an employee in the current business. Add the employee to the roster with the same phone or email, then return here to set general availability.
            </p>
          </div>
        </div>
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
        {feedback?.message ?? "Could not load your availability."}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div
        className={`rounded-[24px] border p-5 ${
          dark ? "border-white/[0.08] bg-white/[0.03]" : "border-[#E5E7EB] bg-[#FAFBFC]"
        }`}
      >
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#635BFF]/10">
            <CalendarDays className="text-[#635BFF]" size={18} />
          </div>
          <div>
            <p className={`text-[14px] ${dark ? "text-white" : "text-[#0A2540]"}`} style={{ fontWeight: 560 }}>
              General availability
            </p>
            <p className={`mt-1 text-[12px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 420 }}>
              Set which days you can work first, then narrow each selected day to a time window. Availability saves in {timezone}.
            </p>
            {employeeName ? (
              <p className="mt-2 text-[11px] text-[#8898AA]" style={{ fontWeight: 500 }}>
                Editing availability for {employeeName}
              </p>
            ) : null}
          </div>
        </div>
      </div>

      {feedback ? (
        <div
          className="rounded-[20px] px-4 py-3 text-[13px]"
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
        <div className="mb-3">
          <h3 className={`text-[11px] uppercase tracking-[0.04em] ${dark ? "text-[#C1CED8]" : "text-[#8898AA]"}`} style={{ fontWeight: 500 }}>
            Step 1 — Select days
          </h3>
        </div>
        <div className="flex flex-wrap gap-2">
          {DAY_ORDER.map((day) => (
            <DayChip
              dark={dark}
              key={day.index}
              label={day.short}
              onClick={() => toggleDay(day.index)}
              selected={dayStates[day.index].enabled}
            />
          ))}
        </div>
      </div>

      {selectedDays.length > 0 ? (
        <div>
          <div className="mb-3">
            <h3 className={`text-[11px] uppercase tracking-[0.04em] ${dark ? "text-[#C1CED8]" : "text-[#8898AA]"}`} style={{ fontWeight: 500 }}>
              Step 2 — Set hours for selected days
            </h3>
          </div>
          <div className="space-y-3">
            {selectedDays.map((day) => (
              <motion.div
                key={day.index}
                animate={{ opacity: 1, y: 0 }}
                initial={{ opacity: 0, y: 8 }}
                transition={{ duration: 0.18 }}
              >
                <DayAvailabilityCard
                  anchorLabel={
                    firstSelectedDay && firstSelectedDay.index !== day.index
                      ? firstSelectedDay.label
                      : null
                  }
                  dark={dark}
                  isAnchor={firstSelectedDay?.index === day.index}
                  label={day.label}
                  onCopy={() => {
                    if (!firstSelectedDay || firstSelectedDay.index === day.index) {
                      return;
                    }
                    const source = dayStates[firstSelectedDay.index];
                    updateDayState(day.index, {
                      enabled: true,
                      startHour: source.startHour,
                      endHour: source.endHour,
                    });
                  }}
                  onSetEnabled={(enabled) => updateDayState(day.index, { enabled })}
                  onSetHours={(next) => updateDayState(day.index, next)}
                  state={dayStates[day.index]}
                />
              </motion.div>
            ))}
          </div>
        </div>
      ) : (
        <div
          className={`rounded-[24px] border px-4 py-4 text-[12px] ${
            dark
              ? "border-white/[0.08] bg-white/[0.03] text-[#C1CED8]"
              : "border-[#E5E7EB] bg-[#FAFBFC] text-[#5E6D7A]"
          }`}
          style={{ fontWeight: 420 }}
        >
          Select at least one day to set your general availability.
        </div>
      )}

      <div className="flex items-center justify-end">
        <button
          type="button"
          onClick={handleSave}
          disabled={!canSave}
          className="rounded-full px-4 py-2.5 text-[13px] text-white transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50"
          style={{
            fontWeight: 540,
            background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
          }}
        >
          {isPending ? "Saving…" : dirty ? "Save Availability" : "Availability Saved"}
        </button>
      </div>
    </div>
  );
}
