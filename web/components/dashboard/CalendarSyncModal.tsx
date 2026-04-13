"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { AlertTriangle, Check, Copy, RefreshCw, X } from "lucide-react";

import {
  getCalendarFeed,
  rotateCalendarFeed,
  type CalendarFeed,
} from "@/lib/api/calendar-feed";

interface Props {
  businessId: string;
  locationId: string;
  locationName: string;
  dark?: boolean;
  onClose(): void;
}

type Stage = "loading" | "ready" | "confirm-rotate" | "rotating" | "error";

const PLATFORM_STEPS: {
  name: string;
  icon: string;
  steps: string[];
}[] = [
  {
    name: "Apple Calendar",
    icon: "🍎",
    steps: [
      'Open Calendar → File → "New Calendar Subscription"',
      "Paste the feed URL and click Subscribe",
      'Set "Auto-refresh" to Every hour',
    ],
  },
  {
    name: "Google Calendar",
    icon: "🗓️",
    steps: [
      'Click "+" next to "Other calendars" → "From URL"',
      "Paste the feed URL and click Add Calendar",
      "Changes sync automatically (every 24h)",
    ],
  },
  {
    name: "Outlook",
    icon: "📨",
    steps: [
      "Go to Calendar → Add calendar → Subscribe from web",
      "Paste the feed URL and click Import",
      "Rename if needed and click Save",
    ],
  },
];

export function CalendarSyncModal({
  businessId,
  locationId,
  locationName,
  dark = false,
  onClose,
}: Props) {
  const [stage, setStage] = useState<Stage>("loading");
  const [feed, setFeed] = useState<CalendarFeed | null>(null);
  const [copied, setCopied] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#8898AA]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const surfaceClass = dark ? "bg-white/[0.03]" : "bg-[#F7F8FA]";
  const modalClass = dark
    ? "bg-[#0F2E4C] border border-white/[0.08]"
    : "bg-white border border-[#E5E7EB]";
  const cancelButtonClass = dark
    ? "flex-1 py-2.5 rounded-xl border border-white/[0.08] text-[12px] text-[#C1CED8] hover:bg-white/[0.04] transition-colors"
    : "flex-1 py-2.5 rounded-xl border border-[#E5E7EB] text-[12px] text-[#5E6D7A] hover:bg-[#F7F8FA] transition-colors";

  const loadFeed = useCallback(async () => {
    setStage("loading");
    setErrorMessage(null);
    try {
      const data = await getCalendarFeed(businessId, locationId);
      setFeed(data);
      setStage("ready");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Could not load calendar feed.");
      setStage("error");
    }
  }, [businessId, locationId]);

  useEffect(() => {
    void loadFeed();
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    };
  }, [loadFeed]);

  const handleCopy = useCallback(() => {
    if (!feed?.feed_url) return;
    void navigator.clipboard.writeText(feed.feed_url).then(() => {
      setCopied(true);
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
      copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000);
    });
  }, [feed?.feed_url]);

  const handleRotate = useCallback(async () => {
    setStage("rotating");
    try {
      const data = await rotateCalendarFeed(businessId, locationId);
      setFeed(data);
      setStage("ready");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Could not rotate feed link.");
      setStage("error");
    }
  }, [businessId, locationId]);

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.4 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black z-40"
        onClick={stage === "ready" || stage === "error" ? onClose : undefined}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 10 }}
        transition={{ duration: 0.18 }}
        className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[90vw] max-w-[500px] rounded-2xl shadow-2xl overflow-hidden ${modalClass}`}
      >
        {/* Header */}
        <div className={`px-6 py-5 border-b flex items-center justify-between ${borderClass}`}>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-[#635BFF]/10">
              <span className="text-[18px]">📅</span>
            </div>
            <div>
              <h3 className={`text-[17px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                Calendar Sync
              </h3>
              <p className={`text-[11px] mt-0.5 ${textSecondary}`} style={{ fontWeight: 440 }}>
                {locationName}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className={`p-1.5 rounded-lg transition-colors ${dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"}`}
            type="button"
          >
            <X size={18} className={textSecondary} />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          {/* Loading */}
          {stage === "loading" && (
            <div className="py-10 flex items-center justify-center">
              <div className="w-5 h-5 rounded-full border-2 border-[#635BFF]/30 border-t-[#635BFF] animate-spin" />
            </div>
          )}

          {/* Error */}
          {stage === "error" && (
            <div className="py-6 text-center">
              <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-[#E5484D]/10 flex items-center justify-center">
                <AlertTriangle size={22} className="text-[#E5484D]" />
              </div>
              <p className={`text-[13px] mb-4 ${textPrimary}`} style={{ fontWeight: 500 }}>
                {errorMessage ?? "Something went wrong."}
              </p>
              <button
                onClick={() => void loadFeed()}
                className="px-4 py-2 rounded-xl text-[12px] text-white"
                style={{ fontWeight: 520, background: "linear-gradient(135deg, #635BFF, #8B5CF6)" }}
                type="button"
              >
                Try again
              </button>
            </div>
          )}

          {/* Confirm rotate */}
          {stage === "confirm-rotate" && (
            <div className="py-4 space-y-4">
              <div
                className="rounded-xl px-4 py-3.5"
                style={{ background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.2)" }}
              >
                <p className="text-[12px] text-[#B45309]" style={{ fontWeight: 500 }}>
                  Rotating the link will invalidate the current feed URL. Any calendar app already
                  subscribed will stop receiving updates until re-subscribed with the new link.
                </p>
              </div>
              <p className={`text-[12px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                Are you sure you want to generate a new calendar feed link?
              </p>
            </div>
          )}

          {/* Rotating */}
          {stage === "rotating" && (
            <div className="py-10 flex flex-col items-center justify-center gap-3">
              <div className="w-5 h-5 rounded-full border-2 border-[#635BFF]/30 border-t-[#635BFF] animate-spin" />
              <p className={`text-[12px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                Generating new link...
              </p>
            </div>
          )}

          {/* Ready */}
          {stage === "ready" && feed && (
            <div className="space-y-5">
              {/* Feed URL */}
              <div>
                <p
                  className={`text-[11px] uppercase tracking-[0.04em] mb-2 ${textSecondary}`}
                  style={{ fontWeight: 500 }}
                >
                  Your calendar feed URL
                </p>
                <div
                  className={`flex items-center gap-2 rounded-xl border p-3 ${borderClass} ${surfaceClass}`}
                >
                  <p
                    className={`flex-1 min-w-0 text-[11px] truncate font-mono ${textPrimary}`}
                    style={{ fontWeight: 440 }}
                  >
                    {feed.feed_url}
                  </p>
                  <button
                    onClick={handleCopy}
                    className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] transition-all ${
                      copied
                        ? "bg-[#00B893]/10 text-[#00B893]"
                        : dark
                          ? "bg-white/[0.06] text-[#C1CED8] hover:bg-white/[0.1]"
                          : "bg-[#E5E7EB] text-[#5E6D7A] hover:bg-[#D1D5DB]"
                    }`}
                    style={{ fontWeight: 520 }}
                    type="button"
                  >
                    {copied ? <Check size={12} /> : <Copy size={12} />}
                    {copied ? "Copied" : "Copy"}
                  </button>
                </div>
                <p className={`mt-1.5 text-[11px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  This is a rolling feed — past 7 days through the next 7 weeks, always current.
                </p>
              </div>

              {/* Platform steps */}
              <div>
                <p
                  className={`text-[11px] uppercase tracking-[0.04em] mb-2.5 ${textSecondary}`}
                  style={{ fontWeight: 500 }}
                >
                  Add to your calendar
                </p>
                <div className="space-y-2">
                  {PLATFORM_STEPS.map((platform) => (
                    <details key={platform.name} className={`rounded-xl border ${borderClass}`}>
                      <summary
                        className={`flex items-center gap-2.5 px-3.5 py-3 cursor-pointer select-none ${textPrimary}`}
                        style={{ fontWeight: 520, fontSize: 12 }}
                      >
                        <span className="text-[15px]">{platform.icon}</span>
                        {platform.name}
                      </summary>
                      <div className={`px-3.5 pb-3 border-t ${borderClass}`}>
                        <ol className="mt-2.5 space-y-1.5">
                          {platform.steps.map((step, i) => (
                            <li key={i} className="flex items-start gap-2">
                              <span
                                className="shrink-0 w-4 h-4 rounded-full bg-[#635BFF]/10 text-[#635BFF] flex items-center justify-center text-[9px] mt-0.5"
                                style={{ fontWeight: 600 }}
                              >
                                {i + 1}
                              </span>
                              <span
                                className={`text-[11px] ${textSecondary}`}
                                style={{ fontWeight: 420 }}
                              >
                                {step}
                              </span>
                            </li>
                          ))}
                        </ol>
                      </div>
                    </details>
                  ))}
                </div>
              </div>

              {/* Rotate link */}
              <div className={`pt-1 border-t ${borderClass}`}>
                <button
                  onClick={() => setStage("confirm-rotate")}
                  className={`flex items-center gap-2 text-[11px] transition-colors ${textSecondary} hover:text-[#E5484D]`}
                  style={{ fontWeight: 480 }}
                  type="button"
                >
                  <RefreshCw size={12} />
                  Rotate feed link
                </button>
                <p className={`mt-1 text-[10px] ${textSecondary}`} style={{ fontWeight: 420, opacity: 0.7 }}>
                  Generates a new private URL and invalidates the old one.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {(stage === "confirm-rotate") && (
          <div className={`px-6 py-4 border-t flex gap-2.5 ${borderClass}`}>
            <button
              onClick={() => setStage("ready")}
              className={cancelButtonClass}
              style={{ fontWeight: 500 }}
              type="button"
            >
              Cancel
            </button>
            <button
              onClick={() => void handleRotate()}
              className="flex-1 py-2.5 rounded-xl text-[12px] text-white flex items-center justify-center gap-1.5 transition-all"
              style={{ fontWeight: 540, background: "linear-gradient(135deg, #E5484D, #C13535)" }}
              type="button"
            >
              <RefreshCw size={12} />
              Rotate Link
            </button>
          </div>
        )}

        {stage === "ready" && (
          <div className={`px-6 py-4 border-t ${borderClass}`}>
            <button
              onClick={onClose}
              className={`w-full py-2.5 rounded-xl text-[12px] transition-colors ${cancelButtonClass}`}
              style={{ fontWeight: 500 }}
              type="button"
            >
              Done
            </button>
          </div>
        )}
      </motion.div>
    </>
  );
}
