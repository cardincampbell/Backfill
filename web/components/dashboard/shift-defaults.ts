"use client";

import {
  CloudMoon,
  Clock3,
  Sun,
  Sunrise,
  Sunset,
  Zap,
  type LucideIcon,
} from "lucide-react";

import type { ShiftDefault, ShiftDefaultKey } from "@/lib/api/workspace";

export const SHIFT_DEFAULT_ORDER: ShiftDefaultKey[] = [
  "morning",
  "afternoon",
  "evening",
  "night",
];

export const SHIFT_DEFAULT_FALLBACKS: ShiftDefault[] = [
  { key: "morning", label: "Morning", start_hour: 7, end_hour: 15 },
  { key: "afternoon", label: "Afternoon", start_hour: 11, end_hour: 19 },
  { key: "evening", label: "Evening", start_hour: 15, end_hour: 23 },
  { key: "night", label: "Night", start_hour: 23, end_hour: 7 },
];

const SHIFT_ICON_BY_KEY: Record<string, LucideIcon> = {
  morning: Sunrise,
  afternoon: Sun,
  evening: Sunset,
  night: CloudMoon,
};

const SHIFT_COLOR_BY_KEY: Record<string, string> = {
  morning: "#635BFF",
  afternoon: "#3B82F6",
  evening: "#8B5CF6",
  night: "#818CF8",
};

const SHIFT_FALLBACK_ICONS: LucideIcon[] = [
  Sunrise,
  Sun,
  Sunset,
  CloudMoon,
  Clock3,
  Zap,
];

const SHIFT_FALLBACK_COLORS = [
  "#635BFF",
  "#3B82F6",
  "#8B5CF6",
  "#818CF8",
  "#00B893",
  "#F59E0B",
];

function hashKey(key: string) {
  return Array.from(key).reduce((sum, char) => sum + char.charCodeAt(0), 0);
}

export function getShiftDefaultIcon(key: ShiftDefaultKey): LucideIcon {
  return SHIFT_ICON_BY_KEY[key] ?? SHIFT_FALLBACK_ICONS[hashKey(key) % SHIFT_FALLBACK_ICONS.length];
}

export function getShiftDefaultColor(key: ShiftDefaultKey): string {
  return SHIFT_COLOR_BY_KEY[key] ?? SHIFT_FALLBACK_COLORS[hashKey(key) % SHIFT_FALLBACK_COLORS.length];
}

export function formatShiftHour(hour: number): string {
  if (hour === 0 || hour === 24) {
    return "12 AM";
  }
  if (hour === 12) {
    return "12 PM";
  }
  return hour < 12 ? `${hour} AM` : `${hour - 12} PM`;
}

export const SHIFT_HOUR_OPTIONS = Array.from({ length: 24 }, (_, hour) => ({
  label: formatShiftHour(hour),
  value: String(hour),
}));

export function shiftHourToPercent(hour: number): number {
  return ((hour % 24) / 24) * 100;
}

export function getShiftDurationHours(
  startHour: number,
  endHour: number,
): number {
  if (endHour === startHour) {
    return 24;
  }
  if (endHour > startHour) {
    return endHour - startHour;
  }
  return 24 - startHour + endHour;
}

export function getShiftCoverageHours(presets: ShiftDefault[]): number {
  return normalizeShiftDefaults(presets).reduce(
    (total, preset) =>
      total + getShiftDurationHours(preset.start_hour, preset.end_hour),
    0,
  );
}

export function normalizeShiftDefaults(
  presets: ShiftDefault[] | null | undefined,
): ShiftDefault[] {
  if (!presets?.length) {
    return SHIFT_DEFAULT_FALLBACKS.map((preset) => ({ ...preset }));
  }

  const seenKeys = new Set<string>();
  const normalized = presets
    .map((preset) => ({
      key: String(preset.key ?? "").trim(),
      label: String(preset.label ?? "").trim() || "Shift",
      start_hour: Number(preset.start_hour),
      end_hour: Number(preset.end_hour),
    }))
    .filter((preset) => {
      if (!preset.key || seenKeys.has(preset.key)) {
        return false;
      }
      if (
        !Number.isFinite(preset.start_hour) ||
        !Number.isFinite(preset.end_hour) ||
        preset.start_hour < 0 ||
        preset.start_hour > 23 ||
        preset.end_hour < 0 ||
        preset.end_hour > 23
      ) {
        return false;
      }
      seenKeys.add(preset.key);
      return true;
    });

  return normalized.length
    ? normalized
    : SHIFT_DEFAULT_FALLBACKS.map((preset) => ({ ...preset }));
}

export function resolveShiftLabel(
  presets: ShiftDefault[],
  key: ShiftDefaultKey | null | undefined,
  startHour: number,
  endHour: number,
): string {
  if (key) {
    const match = presets.find((preset) => preset.key === key);
    if (match) {
      return match.label;
    }
  }
  const exactMatch = presets.find(
    (preset) =>
      preset.start_hour === startHour && preset.end_hour === endHour,
  );
  if (exactMatch) {
    return exactMatch.label;
  }
  return "";
}
