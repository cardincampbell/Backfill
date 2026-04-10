"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getBusinessShiftDefaults,
  updateBusinessShiftDefaults,
  type ShiftDefault,
} from "@/lib/api/workspace";

import {
  ShiftCoverageTimeline,
  ShiftDefaultsEditor,
} from "./ShiftDefaultsEditor";
import { getShiftCoverageHours, normalizeShiftDefaults } from "./shift-defaults";

type Feedback =
  | {
      tone: "success" | "error";
      message: string;
    }
  | null;

export type SettingsSectionHeaderAction = {
  disabled: boolean;
  label: string;
  onClick(): void;
};

function presetsMatch(left: ShiftDefault[], right: ShiftDefault[]): boolean {
  return JSON.stringify(normalizeShiftDefaults(left)) === JSON.stringify(normalizeShiftDefaults(right));
}

function countPresetChanges(left: ShiftDefault[], right: ShiftDefault[]) {
  const normalizedLeft = normalizeShiftDefaults(left);
  const normalizedRight = normalizeShiftDefaults(right);
  let count = 0;

  normalizedLeft.forEach((preset, index) => {
    const baselinePreset = normalizedRight[index];
    if (!baselinePreset) {
      count += 1;
      return;
    }
    if (
      preset.label !== baselinePreset.label ||
      preset.start_hour !== baselinePreset.start_hour ||
      preset.end_hour !== baselinePreset.end_hour
    ) {
      count += 1;
    }
  });

  return count;
}

export default function SettingsShiftsSection({
  businessId,
  dark,
  onHeaderActionChange,
}: {
  businessId: string;
  dark: boolean;
  onHeaderActionChange?(action: SettingsSectionHeaderAction | null): void;
}) {
  const [presets, setPresets] = useState<ShiftDefault[]>(() => normalizeShiftDefaults(null));
  const [baseline, setBaseline] = useState<ShiftDefault[]>(() => normalizeShiftDefaults(null));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isPersisted, setIsPersisted] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setFeedback(null);
        const payload = await getBusinessShiftDefaults(businessId);
        if (cancelled) {
          return;
        }
        const normalized = normalizeShiftDefaults(payload?.presets ?? null);
        setPresets(normalized);
        setBaseline(normalized);
        setIsPersisted(payload?.is_persisted ?? false);
      } catch (error) {
        if (!cancelled) {
          setFeedback({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Could not load business shift defaults.",
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
  }, [businessId]);

  const isDirty = useMemo(() => !presetsMatch(presets, baseline), [baseline, presets]);
  const changeCount = useMemo(() => countPresetChanges(presets, baseline), [baseline, presets]);
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#8898AA]";
  const totalCoverageHours = useMemo(
    () => Math.round(getShiftCoverageHours(presets)),
    [presets],
  );

  useEffect(() => {
    if (!feedback) {
      return;
    }
    const timeoutId = window.setTimeout(() => setFeedback(null), 4000);
    return () => window.clearTimeout(timeoutId);
  }, [feedback]);

  useEffect(() => {
    if (isDirty && feedback) {
      setFeedback(null);
    }
  }, [feedback, isDirty, presets]);

  const handleSave = useCallback(async () => {
    if (!isDirty || saving) {
      return;
    }
    const pendingChangeCount = changeCount;
    try {
      setSaving(true);
      setFeedback(null);
      const payload = await updateBusinessShiftDefaults(businessId, presets);
      const normalized = normalizeShiftDefaults(payload.presets);
      setPresets(normalized);
      setBaseline(normalized);
      setIsPersisted(true);
      setFeedback({
        tone: "success",
        message: `Saved ${pendingChangeCount} shift change${pendingChangeCount === 1 ? "" : "s"}.`,
      });
    } catch (error) {
      setFeedback({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Could not update shift defaults.",
      });
    } finally {
      setSaving(false);
    }
  }, [businessId, changeCount, isDirty, presets, saving]);

  useEffect(() => {
    if (!onHeaderActionChange) {
      return;
    }
    if (loading) {
      onHeaderActionChange(null);
      return;
    }
    onHeaderActionChange({
      disabled: !isDirty || saving,
      label: saving
        ? "Saving..."
        : changeCount > 0
          ? `Save ${changeCount} Change${changeCount === 1 ? "" : "s"}`
          : "Save Changes",
      onClick: () => {
        void handleSave();
      },
    });
    return () => {
      onHeaderActionChange(null);
    };
  }, [changeCount, handleSave, isDirty, loading, onHeaderActionChange, saving]);

  if (loading) {
    return <div className={`py-10 text-[13px] ${textSecondary}`}>Loading shift defaults...</div>;
  }

  return (
    <div className="space-y-5">
      {!isPersisted ? (
        <p className={`text-[12px] ${textSecondary}`} style={{ fontWeight: 440 }}>
          Derived from your first location&apos;s operating hours. Save to make them the business default.
        </p>
      ) : null}

      {feedback ? (
        <div
          className="rounded-xl px-4 py-3 text-[13px]"
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

      <div className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <h4
            className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`}
            style={{ fontWeight: 500 }}
          >
            Coverage Overview
          </h4>
          <div className="flex items-center gap-2.5">
            <span className={`text-[11px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 500 }}>
              {presets.length} shifts
            </span>
            <div className={`h-3 w-px ${dark ? "bg-white/[0.08]" : "bg-[#E5E7EB]"}`} />
            <span className={`text-[11px] ${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"}`} style={{ fontWeight: 500 }}>
              ~{totalCoverageHours}h total
            </span>
          </div>
        </div>
        <ShiftCoverageTimeline dark={dark} presets={presets} />
      </div>

      <ShiftDefaultsEditor dark={dark} onChange={setPresets} presets={presets} />
    </div>
  );
}
