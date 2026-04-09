"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarDays } from "lucide-react";

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

function presetsMatch(left: ShiftDefault[], right: ShiftDefault[]): boolean {
  return JSON.stringify(normalizeShiftDefaults(left)) === JSON.stringify(normalizeShiftDefaults(right));
}

export default function SettingsShiftsSection({
  businessId,
  dark,
}: {
  businessId: string;
  dark: boolean;
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
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#8898AA]";

  async function handleSave() {
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
  }

  if (loading) {
    return <div className={`py-10 text-[13px] ${textSecondary}`}>Loading shift defaults...</div>;
  }

  return (
    <div className="space-y-5">
      <div
        className={`rounded-2xl border p-5 ${
          dark ? "border-white/[0.08] bg-white/[0.03]" : "border-[#E5E7EB] bg-white"
        }`}
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#635BFF]/10">
                <CalendarDays size={18} className="text-[#635BFF]" />
              </div>
              <div>
                <h3
                  className={`text-[16px] tracking-[-0.01em] ${textPrimary}`}
                  style={{ fontWeight: 600 }}
                >
                  Shift Defaults
                </h3>
                <p
                  className={`mt-0.5 text-[12px] ${textSecondary}`}
                  style={{ fontWeight: 420 }}
                >
                  These names and time windows become the default starting point when creating shifts in the scheduler.
                </p>
              </div>
            </div>
            {!isPersisted ? (
              <p
                className={`mt-4 text-[12px] ${textSecondary}`}
                style={{ fontWeight: 440 }}
              >
                Derived from your first location&apos;s operating hours. Save to make them the business default.
              </p>
            ) : null}
          </div>

          <button
            className="rounded-full px-4 py-2 text-[12px] text-white transition-all hover:shadow-[0_0_16px_rgba(99,91,255,0.25)] disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!isDirty || saving}
            onClick={() => {
              void handleSave();
            }}
            style={{
              fontWeight: 540,
              background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
            }}
            type="button"
          >
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>

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
        columnCount={2}
        dark={dark}
        onChange={setPresets}
        presets={presets}
      />
    </div>
  );
}
