"use client";

import { AnimatePresence, motion } from "motion/react";
import { AlertCircle, CheckCircle2 } from "lucide-react";

type DashboardToastProps = {
  tone: "success" | "error";
  message: string | null;
};

export function DashboardToast({ tone, message }: DashboardToastProps) {
  return (
    <AnimatePresence>
      {message ? (
        <motion.div
          key={`${tone}:${message}`}
          initial={{ opacity: 0, scale: 0.9, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.9, y: 8 }}
          transition={{ duration: 0.2 }}
          className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2.5 rounded-full px-4 py-3 shadow-lg"
          style={{
            background: tone === "success" ? "#00B893" : "#E5484D",
          }}
          role="status"
        >
          {tone === "success" ? (
            <CheckCircle2 size={16} className="text-white" />
          ) : (
            <AlertCircle size={16} className="text-white" />
          )}
          <p className="pr-1 text-[13px] text-white" style={{ fontWeight: 500 }}>
            {message}
          </p>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
