"use client";

import { useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, PenLine } from "lucide-react";
import { motion } from "motion/react";

import { FloatingDropdown } from "@/components/floating-dropdown";
import type { ShiftDefault, ShiftDefaultKey } from "@/lib/api/workspace";

import {
  formatShiftHour,
  getShiftDefaultColor,
  getShiftDefaultIcon,
  normalizeShiftDefaults,
  SHIFT_HOUR_OPTIONS,
} from "./shift-defaults";

const DETAIL_PANEL_WIDTH = 228;

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

function TimeSelect({
  dark,
  onChange,
  value,
}: {
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
        className={`flex h-10 w-full items-center justify-between gap-2 rounded-lg border px-3 text-[12px] transition-all ${
          dark
            ? "border-white/[0.08] bg-white/[0.05] text-white hover:border-[#635BFF]/40"
            : "border-[#E5E7EB] bg-[#F7F8FA] text-[#0A2540] hover:border-[#635BFF]/30"
        }`}
        onClick={() => setOpen((current) => !current)}
        style={{ fontWeight: 460 }}
        type="button"
      >
        <span>{selected?.label ?? "Select time"}</span>
        <ChevronDown size={12} className={dark ? "text-[#C1CED8]" : "text-[#8898AA]"} />
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
        {SHIFT_HOUR_OPTIONS.map((option) => {
          const isSelected = Number(option.value) === value;
          return (
            <button
              key={option.value}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] transition-colors ${
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

function formatShiftHourWithMinutes(hour: number): string {
  return formatShiftHour(hour)
    .replace(" AM", ":00 AM")
    .replace(" PM", ":00 PM");
}

export function ShiftDefaultsEditor({
  dark,
  onChange,
  presets,
}: {
  dark: boolean;
  onChange(presets: ShiftDefault[]): void;
  onReset?: () => void;
  presets: ShiftDefault[];
  resetLabel?: string;
  showReset?: boolean;
}) {
  const normalizedPresets = normalizeShiftDefaults(presets);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#8898AA]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const surfaceClass = dark ? "bg-white/[0.03]" : "bg-white";
  const dividerClass = dark ? "border-white/[0.08]" : "border-[#F0F0F5]";
  const labelInputClass = dark
    ? "text-white placeholder:text-[#C1CED8]/40"
    : "text-[#0A2540] placeholder:text-[#8898AA]/50";

  function updatePreset(
    key: string,
    updater: (preset: ShiftDefault) => ShiftDefault,
  ) {
    onChange(
      normalizedPresets.map((item) =>
        item.key === key ? updater(item) : item,
      ),
    );
  }

  return (
    <div className="space-y-2.5">
      {normalizedPresets.map((preset) => {
        const Icon = getShiftDefaultIcon(preset.key);
        const accent = getShiftDefaultColor(preset.key);
        const isExpanded = expandedKey === preset.key;
        return (
          <div
            key={preset.key}
            className={`overflow-hidden rounded-xl border ${borderClass} ${surfaceClass}`}
          >
            <div className="flex items-stretch">
              <div
                className={`flex min-w-0 flex-1 items-center gap-3 px-3 py-3 ${
                  isExpanded ? `border-r ${dividerClass}` : ""
                }`}
              >
                <div
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                  style={{ background: `${accent}12` }}
                >
                  <Icon size={15} style={{ color: accent }} />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <PenLine
                      size={11}
                      className={dark ? "text-[#C1CED8]" : "text-[#8898AA]"}
                    />
                    <input
                      className={`min-w-0 flex-1 border-0 bg-transparent p-0 text-[12px] tracking-[-0.01em] outline-none ${labelInputClass}`}
                      onBlur={(event) => {
                        const trimmed = event.target.value.trim();
                        if (!trimmed) {
                          updatePreset(preset.key, (item) => ({
                            ...item,
                            label: getDefaultShiftLabel(item.key),
                          }));
                        }
                      }}
                      onChange={(event) =>
                        updatePreset(preset.key, (item) => ({
                          ...item,
                          label: event.target.value,
                        }))
                      }
                      style={{ fontWeight: 560 }}
                      value={preset.label}
                    />
                  </div>
                  <p
                    className={`mt-1 text-[11px] ${textSecondary}`}
                    style={{ fontWeight: 440 }}
                  >
                    {formatShiftHourWithMinutes(preset.start_hour)}
                    {" — "}
                    {formatShiftHourWithMinutes(preset.end_hour)}
                  </p>
                </div>
              </div>

              <motion.div
                animate={{
                  opacity: isExpanded ? 1 : 0,
                  width: isExpanded ? DETAIL_PANEL_WIDTH : 0,
                }}
                className={`overflow-hidden ${dark ? "bg-[#0C243D]" : "bg-[#FAFBFC]"}`}
                initial={false}
                transition={{ duration: 0.28, ease: [0.25, 0.46, 0.45, 0.94] }}
              >
                <div className="grid h-full min-w-[228px] grid-cols-2 gap-2 px-3 py-3">
                  <label className="block">
                    <span
                      className={`mb-1.5 block text-[10px] uppercase tracking-[0.05em] ${textSecondary}`}
                      style={{ fontWeight: 500 }}
                    >
                      Start
                    </span>
                    <TimeSelect
                      dark={dark}
                      onChange={(nextValue) =>
                        updatePreset(preset.key, (item) => ({
                          ...item,
                          start_hour: nextValue,
                        }))
                      }
                      value={preset.start_hour}
                    />
                  </label>

                  <label className="block">
                    <span
                      className={`mb-1.5 block text-[10px] uppercase tracking-[0.05em] ${textSecondary}`}
                      style={{ fontWeight: 500 }}
                    >
                      End
                    </span>
                    <TimeSelect
                      dark={dark}
                      onChange={(nextValue) =>
                        updatePreset(preset.key, (item) => ({
                          ...item,
                          end_hour: nextValue,
                        }))
                      }
                      value={preset.end_hour}
                    />
                  </label>
                </div>
              </motion.div>

              <button
                className={`flex w-11 shrink-0 items-center justify-center transition-colors ${
                  dark ? "hover:bg-white/[0.04]" : "hover:bg-[#F7F8FA]"
                }`}
                onClick={() =>
                  setExpandedKey((current) =>
                    current === preset.key ? null : preset.key,
                  )
                }
                type="button"
              >
                <ChevronRight
                  size={15}
                  className={`transition-transform duration-300 ${
                    dark ? "text-[#C1CED8]" : "text-[#8898AA]"
                  } ${isExpanded ? "rotate-180" : ""}`}
                />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
