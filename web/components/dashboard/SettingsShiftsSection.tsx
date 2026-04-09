"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getBusinessShiftDefaults,
  updateBusinessShiftDefaults,
  type ShiftDefault,
} from "@/lib/api/workspace";

import { ShiftDefaultsEditor } from "./ShiftDefaultsEditor";
import { normalizeShiftDefaults } from "./shift-defaults";

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
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#8898AA]";

  const handleSave = useCallback(async () => {
    if (!isDirty || saving) {
      return;
    }
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
        message: "Business shift defaults updated.",
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
  }, [businessId, isDirty, presets, saving]);

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
      label: saving ? "Saving..." : "Save Changes",
      onClick: () => {
        void handleSave();
      },
    });
    return () => {
      onHeaderActionChange(null);
    };
  }, [handleSave, isDirty, loading, onHeaderActionChange, saving]);

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

      <ShiftDefaultsEditor
        dark={dark}
        onChange={setPresets}
        presets={presets}
      />
    </div>
  );
}
