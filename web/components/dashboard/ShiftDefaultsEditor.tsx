"use client";

import { useMemo, useRef, useState } from "react";
import { ChevronDown, PenLine } from "lucide-react";
import { motion } from "motion/react";

import { FloatingDropdown } from "@/components/floating-dropdown";
import type { ShiftDefault, ShiftDefaultKey } from "@/lib/api/workspace";

import {
  formatShiftHour,
  getShiftDefaultColor,
  getShiftDefaultIcon,
  getShiftDurationHours,
  normalizeShiftDefaults,
  shiftHourToPercent,
  SHIFT_HOUR_OPTIONS,
} from "./shift-defaults";

function getDefaultShiftLabel(key: ShiftDefaultKey): string {
  switch (key) {
    case "morning":
      return "Morning";
    case "afternoon":
      return "Afternoon";
    case "evening":
      return "Evening";
    case "night":
      return "Night";
    default:
      return key;
  }
}

function formatShiftHourWithMinutes(hour: number): string {
  return formatShiftHour(hour)
    .replace(" AM", ":00 AM")
    .replace(" PM", ":00 PM");
}

function TimeSelect({
  compact = false,
  dark,
  onChange,
  value,
}: {
  compact?: boolean;
  dark: boolean;
  onChange(value: number): void;
  value: number;
}) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const selected = useMemo(
    () => SHIFT_HOUR_OPTIONS.find((option) => Number(option.value) === value),
    [value],
  );

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        className={`flex w-full items-center justify-between gap-2 rounded-lg border px-3 transition-all ${
          compact ? "h-9 text-[11px]" : "h-10 text-[12px]"
        } ${
          dark
            ? "border-white/[0.08] bg-white/[0.05] text-white hover:border-[#635BFF]/40"
            : "border-[#E5E7EB] bg-[#F7F8FA] text-[#0A2540] hover:border-[#635BFF]/30"
        }`}
        onClick={() => setOpen((current) => !current)}
        style={{ fontWeight: 460 }}
        type="button"
      >
        <span>{selected?.label ?? "Select time"}</span>
        <ChevronDown
          size={compact ? 11 : 12}
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
        minWidth={compact ? 168 : 180}
        onClose={() => setOpen(false)}
        open={open}
        width={compact ? 168 : 180}
        zIndex={10030}
      >
        {SHIFT_HOUR_OPTIONS.map((option) => {
          const isSelected = Number(option.value) === value;
          return (
            <button
              key={option.value}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left transition-colors ${
                compact ? "text-[11px]" : "text-[12px]"
              } ${
                isSelected
                  ? "bg-[#635BFF]/[0.08] text-[#635BFF]"
                  : dark
                    ? "text-white hover:bg-white/[0.06]"
                    : "text-[#0A2540] hover:bg-[#F7F8FA]"
              }`}
              onClick={() => {
                onChange(Number(option.value));
                setOpen(false);
              }}
              style={{ fontWeight: isSelected ? 520 : 440 }}
              type="button"
            >
              <span className={isSelected ? "" : "ml-4"}>{option.label}</span>
            </button>
          );
        })}
      </FloatingDropdown>
    </div>
  );
}

function ShiftDefaultCard({
  compact = false,
  dark,
  onChange,
  preset,
}: {
  compact?: boolean;
  dark: boolean;
  onChange(nextPreset: ShiftDefault): void;
  preset: ShiftDefault;
}) {
  const [editing, setEditing] = useState(false);
  const [draftLabel, setDraftLabel] = useState(preset.label);
  const Icon = getShiftDefaultIcon(preset.key);
  const accent = getShiftDefaultColor(preset.key);

  const commitLabel = () => {
    const trimmed = draftLabel.trim();
    onChange({
      ...preset,
      label: trimmed || getDefaultShiftLabel(preset.key),
    });
    setDraftLabel(trimmed || getDefaultShiftLabel(preset.key));
    setEditing(false);
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8, transition: { duration: 0.2 } }}
      className={`group rounded-xl border transition-all duration-300 ${
        dark
          ? "border-white/[0.08] bg-white/[0.03] hover:border-white/[0.14] hover:bg-white/[0.05]"
          : "border-[#E5E7EB] bg-white hover:border-[#D1D5DB] hover:shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
      }`}
    >
      <div className={compact ? "p-3" : "p-4"}>
        <div className={compact ? "flex items-center gap-2.5" : "flex items-center gap-3"}>
          <div
            className={`flex shrink-0 items-center justify-center ${
              compact ? "h-8 w-8 rounded-lg" : "h-10 w-10 rounded-xl"
            }`}
            style={{ background: `${accent}12` }}
          >
            <Icon size={compact ? 16 : 18} style={{ color: accent }} />
          </div>

          <div className="min-w-0 flex-1">
            {editing ? (
              <input
                autoFocus
                className={`w-full rounded-lg border border-[#635BFF]/40 bg-transparent px-2 py-1 outline-none transition-all ${
                  dark ? "text-white" : "text-[#0A2540]"
                } ${compact ? "-ml-2 text-[13px]" : "max-w-[180px] -ml-2 text-[14px]"}`}
                onBlur={commitLabel}
                onChange={(event) => setDraftLabel(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    commitLabel();
                  }
                  if (event.key === "Escape") {
                    setDraftLabel(preset.label);
                    setEditing(false);
                  }
                }}
                style={{
                  fontWeight: 540,
                  boxShadow: "0 0 0 3px rgba(99,91,255,0.1)",
                }}
                value={draftLabel}
              />
            ) : (
              <button
                className="group/name flex items-center gap-1.5"
                onClick={() => {
                  setDraftLabel(preset.label);
                  setEditing(true);
                }}
                type="button"
              >
                <span
                  className={compact ? "text-[13px] text-[#0A2540]" : "text-[14px] text-[#0A2540]"}
                  style={{ fontWeight: 540, color: dark ? "#FFFFFF" : "#0A2540" }}
                >
                  {preset.label}
                </span>
                <PenLine
                  size={compact ? 10 : 11}
                  className="text-[#C1CED8] opacity-0 transition-opacity group-hover/name:opacity-100"
                />
              </button>
            )}

            {!compact ? (
              <p
                className={`mt-0.5 text-[11px] ${dark ? "text-[#C1CED8]" : "text-[#8898AA]"}`}
                style={{ fontWeight: 420 }}
              >
                {formatShiftHourWithMinutes(preset.start_hour)}
                {" – "}
                {formatShiftHourWithMinutes(preset.end_hour)}
                {" · "}
                {getShiftDurationHours(preset.start_hour, preset.end_hour)}h
              </p>
            ) : null}
          </div>

          {!compact ? (
            <div className="hidden shrink-0 items-center gap-2 sm:flex">
              <div className="w-[110px]">
                <TimeSelect
                  dark={dark}
                  onChange={(nextValue) =>
                    onChange({ ...preset, start_hour: nextValue })
                  }
                  value={preset.start_hour}
                />
              </div>
              <span
                className={`text-[10px] ${dark ? "text-[#C1CED8]" : "text-[#C1CED8]"}`}
                style={{ fontWeight: 420 }}
              >
                to
              </span>
              <div className="w-[110px]">
                <TimeSelect
                  dark={dark}
                  onChange={(nextValue) =>
                    onChange({ ...preset, end_hour: nextValue })
                  }
                  value={preset.end_hour}
                />
              </div>
            </div>
          ) : null}
        </div>

        {compact ? (
          <div className="ml-10 mt-2.5 flex items-center gap-2">
            <div className="flex-1">
              <TimeSelect
                compact
                dark={dark}
                onChange={(nextValue) =>
                  onChange({ ...preset, start_hour: nextValue })
                }
                value={preset.start_hour}
              />
            </div>
            <span className="text-[10px] text-[#C1CED8]" style={{ fontWeight: 420 }}>
              to
            </span>
            <div className="flex-1">
              <TimeSelect
                compact
                dark={dark}
                onChange={(nextValue) =>
                  onChange({ ...preset, end_hour: nextValue })
                }
                value={preset.end_hour}
              />
            </div>
          </div>
        ) : (
          <div className="mt-3 ml-[52px] flex items-center gap-2 sm:hidden">
            <div className="flex-1">
              <TimeSelect
                dark={dark}
                onChange={(nextValue) =>
                  onChange({ ...preset, start_hour: nextValue })
                }
                value={preset.start_hour}
              />
            </div>
            <span className="text-[10px] text-[#C1CED8]" style={{ fontWeight: 420 }}>
              to
            </span>
            <div className="flex-1">
              <TimeSelect
                dark={dark}
                onChange={(nextValue) =>
                  onChange({ ...preset, end_hour: nextValue })
                }
                value={preset.end_hour}
              />
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}

export function ShiftCoverageTimeline({
  compact = false,
  dark,
  presets,
}: {
  compact?: boolean;
  dark: boolean;
  presets: ShiftDefault[];
}) {
  const normalizedPresets = normalizeShiftDefaults(presets);
  const timelineBgClass = dark ? "bg-white/[0.04]" : "bg-[#F7F8FA]";
  const timelineBorderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const markerTextClass = dark ? "text-[#8898AA]" : "text-[#C1CED8]";

  return (
    <div>
      <div
        className={`relative h-8 overflow-hidden rounded-lg border ${timelineBgClass} ${timelineBorderClass}`}
      >
        {normalizedPresets.map((preset) => {
          const accent = getShiftDefaultColor(preset.key);
          const startPct = shiftHourToPercent(preset.start_hour);
          const endPct = shiftHourToPercent(preset.end_hour);
          const wraps = endPct <= startPct;

          if (wraps) {
            return (
              <span key={preset.key}>
                <div
                  className="absolute top-0 flex h-full items-center justify-center overflow-hidden"
                  style={{
                    left: `${startPct}%`,
                    width: `${100 - startPct}%`,
                    background: `${accent}20`,
                    borderRight: `1px solid ${accent}30`,
                  }}
                >
                  <span
                    className={`truncate px-1 ${compact ? "text-[8px]" : "text-[9px]"}`}
                    style={{ color: accent, fontWeight: 520 }}
                  >
                    {preset.label}
                  </span>
                </div>
                <div
                  className="absolute top-0 left-0 flex h-full items-center justify-center overflow-hidden"
                  style={{
                    width: `${endPct}%`,
                    background: `${accent}20`,
                    borderRight: `1px solid ${accent}30`,
                  }}
                />
              </span>
            );
          }

          return (
            <div
              key={preset.key}
              className="absolute top-0 flex h-full items-center justify-center overflow-hidden"
              style={{
                left: `${startPct}%`,
                width: `${endPct - startPct}%`,
                background: `${accent}20`,
                borderLeft: `1px solid ${accent}30`,
                borderRight: `1px solid ${accent}30`,
              }}
            >
              <span
                className={`truncate px-1 ${compact ? "text-[8px]" : "text-[9px]"}`}
                style={{ color: accent, fontWeight: 520 }}
              >
                {preset.label}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex items-center">
        {["12a", "3a", "6a", "9a", "12p", "3p", "6p", "9p", "12a"].map(
          (label, index) => (
            <span
              key={`${label}-${index}`}
              className={`${compact ? "text-[8px]" : "text-[9px]"} ${markerTextClass}`}
              style={{ fontWeight: 420, flex: index === 8 ? "0 0 auto" : 1 }}
            >
              {label}
            </span>
          ),
        )}
      </div>
    </div>
  );
}

export function ShiftDefaultsEditor({
  compact = false,
  dark,
  onChange,
  presets,
}: {
  compact?: boolean;
  dark: boolean;
  onChange(presets: ShiftDefault[]): void;
  presets: ShiftDefault[];
}) {
  const normalizedPresets = normalizeShiftDefaults(presets);

  function updatePreset(
    key: ShiftDefaultKey,
    updater: (preset: ShiftDefault) => ShiftDefault,
  ) {
    onChange(
      normalizedPresets.map((preset) =>
        preset.key === key ? updater(preset) : preset,
      ),
    );
  }

  return (
    <div className="space-y-2.5">
      {normalizedPresets.map((preset) => (
        <ShiftDefaultCard
          key={preset.key}
          compact={compact}
          dark={dark}
          onChange={(nextPreset) => updatePreset(preset.key, () => nextPreset)}
          preset={preset}
        />
      ))}
    </div>
  );
}
