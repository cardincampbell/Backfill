import {
  CloudMoon,
  Sun,
  Sunrise,
  Sunset,
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

const SHIFT_ICON_BY_KEY: Record<ShiftDefaultKey, LucideIcon> = {
  morning: Sunrise,
  afternoon: Sun,
  evening: Sunset,
  night: CloudMoon,
};

const SHIFT_COLOR_BY_KEY: Record<ShiftDefaultKey, string> = {
  morning: "#635BFF",
  afternoon: "#3B82F6",
  evening: "#8B5CF6",
  night: "#0A2540",
};

export function getShiftDefaultIcon(key: ShiftDefaultKey): LucideIcon {
  return SHIFT_ICON_BY_KEY[key];
}

export function getShiftDefaultColor(key: ShiftDefaultKey): string {
  return SHIFT_COLOR_BY_KEY[key];
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

export function normalizeShiftDefaults(
  presets: ShiftDefault[] | null | undefined,
): ShiftDefault[] {
  const lookup = new Map((presets ?? []).map((preset) => [preset.key, preset]));
  return SHIFT_DEFAULT_ORDER.map((key) => {
    const preset = lookup.get(key);
    if (preset) {
      return {
        key,
        label: preset.label,
        start_hour: preset.start_hour,
        end_hour: preset.end_hour,
      };
    }
    const fallback = SHIFT_DEFAULT_FALLBACKS.find((item) => item.key === key);
    return fallback
      ? { ...fallback }
      : { key, label: key, start_hour: 7, end_hour: 15 };
  });
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
