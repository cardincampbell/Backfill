"use client";

import { useMemo, useRef, useState } from "react";
import { ChevronDown, RotateCcw } from "lucide-react";

import { FloatingDropdown } from "@/components/floating-dropdown";
import type { ShiftDefault } from "@/lib/api/workspace";

import {
  getShiftDefaultColor,
  getShiftDefaultIcon,
  normalizeShiftDefaults,
  SHIFT_HOUR_OPTIONS,
} from "./shift-defaults";

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
        className={`flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-[12px] transition-all ${
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

export function ShiftDefaultsEditor({
  columnCount = 2,
  dark,
  onChange,
  onReset,
  presets,
  resetLabel = "Reset",
  showReset = false,
}: {
  columnCount?: 1 | 2;
  dark: boolean;
  onChange(presets: ShiftDefault[]): void;
  onReset?: () => void;
  presets: ShiftDefault[];
  resetLabel?: string;
  showReset?: boolean;
}) {
  const normalizedPresets = normalizeShiftDefaults(presets);

  return (
    <div className="space-y-3">
      {showReset && onReset ? (
        <div className="flex justify-end">
          <button
            className="flex items-center gap-1.5 text-[11px] text-[#635BFF] transition-colors hover:text-[#4B3FD9]"
            onClick={onReset}
            style={{ fontWeight: 520 }}
            type="button"
          >
            <RotateCcw size={12} />
            {resetLabel}
          </button>
        </div>
      ) : null}

      <div
        className={`grid gap-3 ${
          columnCount === 1 ? "grid-cols-1" : "grid-cols-1 xl:grid-cols-2"
        }`}
      >
        {normalizedPresets.map((preset) => {
          const Icon = getShiftDefaultIcon(preset.key);
          const accent = getShiftDefaultColor(preset.key);
          return (
            <div
              key={preset.key}
              className={`rounded-2xl border p-4 ${
                dark
                  ? "border-white/[0.08] bg-white/[0.03]"
                  : "border-[#E5E7EB] bg-white"
              }`}
            >
              <div className="mb-3 flex items-center gap-3">
                <div
                  className="flex h-9 w-9 items-center justify-center rounded-xl"
                  style={{ background: `${accent}12` }}
                >
                  <Icon size={16} style={{ color: accent }} />
                </div>
                <div className="min-w-0 flex-1">
                  <p
                    className={`text-[11px] uppercase tracking-[0.04em] ${
                      dark ? "text-[#C1CED8]" : "text-[#8898AA]"
                    }`}
                    style={{ fontWeight: 500 }}
                  >
                    {preset.key}
                  </p>
                  <input
                    className={`mt-1 w-full border-none bg-transparent p-0 text-[15px] tracking-[-0.01em] focus:outline-none ${
                      dark ? "text-white" : "text-[#0A2540]"
                    }`}
                    onChange={(event) =>
                      onChange(
                        normalizedPresets.map((item) =>
                          item.key === preset.key
                            ? { ...item, label: event.target.value }
                            : item,
                        ),
                      )
                    }
                    style={{ fontWeight: 560 }}
                    value={preset.label}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span
                    className={`mb-1.5 block text-[10px] uppercase tracking-[0.05em] ${
                      dark ? "text-[#C1CED8]" : "text-[#8898AA]"
                    }`}
                    style={{ fontWeight: 500 }}
                  >
                    Start
                  </span>
                  <TimeSelect
                    dark={dark}
                    onChange={(nextValue) =>
                      onChange(
                        normalizedPresets.map((item) =>
                          item.key === preset.key
                            ? { ...item, start_hour: nextValue }
                            : item,
                        ),
                      )
                    }
                    value={preset.start_hour}
                  />
                </label>

                <label className="block">
                  <span
                    className={`mb-1.5 block text-[10px] uppercase tracking-[0.05em] ${
                      dark ? "text-[#C1CED8]" : "text-[#8898AA]"
                    }`}
                    style={{ fontWeight: 500 }}
                  >
                    End
                  </span>
                  <TimeSelect
                    dark={dark}
                    onChange={(nextValue) =>
                      onChange(
                        normalizedPresets.map((item) =>
                          item.key === preset.key
                            ? { ...item, end_hour: nextValue }
                            : item,
                        ),
                      )
                    }
                    value={preset.end_hour}
                  />
                </label>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
