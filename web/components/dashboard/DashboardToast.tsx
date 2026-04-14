"use client";

import { AnimatePresence, motion } from "motion/react";
import { AlertCircle, CheckCircle2, Info } from "lucide-react";

type DashboardToastProps = {
  tone: "success" | "error" | "info";
  message?: string | null;
  title?: string | null;
  detail?: string | null;
};

export function DashboardToast({
  tone,
  message = null,
  title = null,
  detail = null,
}: DashboardToastProps) {
  const resolvedTitle = title ?? message;

  return (
    <AnimatePresence>
      {resolvedTitle ? (
        <motion.div
          key={`${tone}:${resolvedTitle}:${detail ?? ""}`}
          initial={{ opacity: 0, scale: 0.9, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.9, y: 8 }}
          transition={{ duration: 0.2 }}
          className="fixed bottom-6 left-1/2 z-50 flex min-w-[220px] max-w-[min(92vw,520px)] -translate-x-1/2 items-center gap-2.5 rounded-2xl px-4 py-3 shadow-lg"
          style={{
            background:
              tone === "success" ? "#00B893" : tone === "error" ? "#E5484D" : "#635BFF",
          }}
          role="status"
        >
          {tone === "success" ? (
            <CheckCircle2 size={16} className="text-white" />
          ) : tone === "info" ? (
            <Info size={16} className="text-white" />
          ) : (
            <AlertCircle size={16} className="text-white" />
          )}
          <div className="pr-1">
            <p className="text-[13px] text-white" style={{ fontWeight: 500 }}>
              {resolvedTitle}
            </p>
            {detail ? (
              <p className="mt-0.5 text-[10px] text-white/80" style={{ fontWeight: 420 }}>
                {detail}
              </p>
            ) : null}
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
