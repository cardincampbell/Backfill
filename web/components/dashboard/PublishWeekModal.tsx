"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { Check, X, Zap } from "lucide-react";

import type { ScheduleWeekPublishResponse } from "@/lib/api/workspace";

interface Employee {
  id: string;
  name: string;
  avatar: string;
  role: string;
}

interface Shift {
  id: string;
  employeeId: string | null;
  day: number;
  startHour: number;
  endHour: number;
  role: string;
  color: string;
}

function shiftDuration(shift: Shift) {
  return shift.endHour > shift.startHour
    ? shift.endHour - shift.startHour
    : 24 - shift.startHour + shift.endHour;
}

interface PublishWeekModalProps {
  weekLabel: string;
  shifts: Shift[];
  employees: Employee[];
  isRepublish?: boolean;
  publishedDateLabel?: string | null;
  dark?: boolean;
  onClose: () => void;
  onPublish: () => Promise<ScheduleWeekPublishResponse>;
  onComplete: (result: ScheduleWeekPublishResponse) => void;
}

export function PublishWeekModal({
  weekLabel,
  shifts,
  employees,
  isRepublish = false,
  publishedDateLabel = null,
  dark = false,
  onClose,
  onPublish,
  onComplete,
}: PublishWeekModalProps) {
  const [stage, setStage] = useState<"confirm" | "publishing" | "success">("confirm");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<ScheduleWeekPublishResponse | null>(null);

  const affectedEmployees = Array.from(
    new Set(
      shifts
        .map((shift) => shift.employeeId)
        .filter((employeeId): employeeId is string => Boolean(employeeId)),
    ),
  )
    .map((id) => employees.find((employee) => employee.id === id))
    .filter(Boolean) as Employee[];

  const totalShifts = shifts.length;
  const modalClass = dark
    ? "bg-[#0F2E4C] border border-white/[0.08]"
    : "bg-white border border-[#E5E7EB]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#F0F0F5]";
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#8898AA]";
  const subtleSurfaceClass = dark ? "bg-white/[0.03]" : "bg-[#F7F8FA]/50";
  const rowSurfaceClass = dark
    ? "bg-white/[0.03] border border-white/[0.08]"
    : "bg-white border border-[#E5E7EB]";
  const closeButtonClass = dark
    ? "p-1.5 rounded-lg hover:bg-white/[0.06] transition-colors"
    : "p-1.5 rounded-lg hover:bg-[#F7F8FA] transition-colors";
  const footerButtonClass = dark
    ? "flex-1 py-2.5 rounded-xl border border-white/[0.08] text-[12px] text-[#C1CED8] hover:bg-white/[0.04] transition-colors"
    : "flex-1 py-2.5 rounded-xl border border-[#E5E7EB] text-[12px] text-[#5E6D7A] hover:bg-[#F7F8FA] transition-colors";

  const handlePublish = async () => {
    setErrorMessage(null);
    setStage("publishing");
    try {
      const publishResult = await onPublish();
      setResult(publishResult);
      setStage("success");
      window.setTimeout(() => {
        onComplete(publishResult);
      }, 1200);
    } catch (error) {
      setStage("confirm");
      setErrorMessage(
        error instanceof Error ? error.message : "Could not publish this week. Please try again.",
      );
    }
  };

  const publishedShiftCount = result?.published_shift_count ?? totalShifts;
  const notifiedEmployeeCount =
    result?.notification_enqueued_employee_count ?? affectedEmployees.length;

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.3 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-40 bg-black"
        onClick={stage === "confirm" ? onClose : undefined}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className={`fixed left-1/2 top-1/2 z-50 w-[90vw] max-w-[520px] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl shadow-2xl ${modalClass}`}
      >
        <div className={`flex items-center justify-between border-b px-6 py-5 ${borderClass}`}>
          <div className="flex items-center gap-3">
            <div
              className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all ${
                stage === "success"
                  ? "bg-[#00B893]/10"
                  : "bg-gradient-to-br from-[#635BFF] to-[#8B5CF6]"
              }`}
            >
              {stage === "success" ? (
                <Check size={20} className="text-[#00B893]" />
              ) : (
                <Zap size={20} className="text-white" />
              )}
            </div>
            <div>
              <h3 className={`text-[17px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                {stage === "confirm" && (isRepublish ? "Republish Schedule" : "Publish Schedule")}
                {stage === "publishing" && (isRepublish ? "Republishing..." : "Publishing...")}
                {stage === "success" && (isRepublish ? "Schedule Republished" : "Schedule Published")}
              </h3>
              <p className={`mt-0.5 text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                {stage === "confirm" &&
                  `${weekLabel} · ${totalShifts} Draft Shifts | ${affectedEmployees.length} Employees`}
                {stage === "publishing" && "Publishing draft shifts and queuing notifications"}
                {stage === "success" &&
                  (isRepublish
                    ? "Draft amendments are live and notifications were queued"
                    : "Draft shifts are live and notifications were queued")}
              </p>
            </div>
          </div>
          {stage === "confirm" ? (
            <button onClick={onClose} className={closeButtonClass}>
              <X size={18} className={textSecondary} />
            </button>
          ) : null}
        </div>

        <div className="px-6 py-5">
          {stage === "confirm" ? (
            <>
              {publishedDateLabel ? (
                <div className={`mb-4 rounded-xl border px-3 py-2 text-[12px] ${dark ? "border-[#F59E0B]/25 bg-[#F59E0B]/10 text-[#FDE68A]" : "border-[#FDE68A] bg-[#FFF7D6] text-[#8A6100]"}`}>
                  This schedule was published on {publishedDateLabel}
                </div>
              ) : null}
              {errorMessage ? (
                <div
                  className={`mb-4 rounded-xl border px-3 py-2 text-[12px] ${
                    dark
                      ? "border-[#F87171]/30 bg-[#F87171]/10 text-[#FECACA]"
                      : "border-[#FCA5A5] bg-[#FEF2F2] text-[#B42318]"
                  }`}
                >
                  {errorMessage}
                </div>
              ) : null}
              <div className="mb-5 space-y-3">
                <p
                  className={`text-[11px] uppercase tracking-[0.05em] ${textSecondary}`}
                  style={{ fontWeight: 500 }}
                >
                  What will happen
                </p>
                <div className="space-y-2">
                  {[
                    {
                      icon: "🗓️",
                      text: "Draft shifts move live for this week",
                      detail: `${totalShifts} draft shifts are publishable now`,
                    },
                    {
                      icon: "📨",
                      text: "Assigned staff notifications are queued",
                      detail: "SMS and email are enqueued asynchronously",
                    },
                  ].map((item) => (
                    <div key={item.text} className={`flex items-start gap-3 rounded-lg p-3 ${subtleSurfaceClass}`}>
                      <span className="text-[18px]">{item.icon}</span>
                      <div className="flex-1">
                        <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 500 }}>
                          {item.text}
                        </p>
                        <p className={`mt-0.5 text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                          {item.detail}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <p
                  className={`mb-3 text-[11px] uppercase tracking-[0.05em] ${textSecondary}`}
                  style={{ fontWeight: 500 }}
                >
                  Staff receiving notifications
                </p>
                <div className="max-h-[180px] space-y-1.5 overflow-y-auto pr-1">
                  {affectedEmployees.map((employee) => {
                    const employeeShifts = shifts.filter((shift) => shift.employeeId === employee.id);
                    const employeeHours = employeeShifts.reduce(
                      (sum, shift) => sum + shiftDuration(shift),
                      0,
                    );
                    return (
                      <div
                        key={employee.id}
                        className={`flex items-center gap-3 rounded-lg p-2.5 ${rowSurfaceClass}`}
                      >
                        <img
                          src={employee.avatar}
                          alt={employee.name}
                          className={`h-8 w-8 shrink-0 rounded-full object-cover ring-1 ${
                            dark ? "ring-white/[0.08]" : "ring-[#E5E7EB]"
                          }`}
                        />
                        <div className="min-w-0 flex-1">
                          <p className={`truncate text-[12px] ${textPrimary}`} style={{ fontWeight: 500 }}>
                            {employee.name}
                          </p>
                          <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                            {employee.role}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 540 }}>
                            {employeeShifts.length} shifts
                          </p>
                          <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                            {employeeHours}h
                          </p>
                        </div>
                      </div>
                    );
                  })}
                  {affectedEmployees.length === 0 ? (
                    <div className={`rounded-lg p-3 text-[12px] ${subtleSurfaceClass} ${textSecondary}`}>
                      No assigned employees on the remaining draft shifts. Publish will still move them live.
                    </div>
                  ) : null}
                </div>
              </div>
            </>
          ) : null}

          {stage === "publishing" ? (
            <div className="py-8 text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#635BFF]/10">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-[#635BFF]/30 border-t-[#635BFF]" />
              </div>
              <h4 className={`mb-2 text-[16px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                Publishing this week
              </h4>
              <p className={`text-[12px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                Draft shifts are being published and assigned staff notifications are being queued.
              </p>
            </div>
          ) : null}

          {stage === "success" && result ? (
            <div className="py-8 text-center">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 200, damping: 15 }}
                className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-[#00B893]/10"
              >
                <Check size={32} className="text-[#00B893]" />
              </motion.div>
              <h4 className={`mb-2 text-[16px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                Publish complete
              </h4>
              <p className={`mb-4 text-[12px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                {publishedShiftCount} draft shift{publishedShiftCount === 1 ? "" : "s"} published and{" "}
                {notifiedEmployeeCount} employee notification{notifiedEmployeeCount === 1 ? "" : "s"} queued.
              </p>
            </div>
          ) : null}
        </div>

        {stage === "confirm" ? (
          <div className={`flex gap-2.5 border-t px-6 py-4 ${borderClass}`}>
            <button
              onClick={onClose}
              className={footerButtonClass}
              style={{ fontWeight: 500 }}
            >
              Cancel
            </button>
            <motion.button
              whileTap={{ scale: 0.97 }}
              onClick={() => void handlePublish()}
              className="flex flex-1 items-center justify-center gap-2 rounded-xl py-2.5 text-[12px] text-white transition-all hover:shadow-[0_0_20px_rgba(99,91,255,0.3)]"
              style={{ fontWeight: 540, background: "linear-gradient(135deg, #635BFF, #8B5CF6)" }}
            >
              <Zap size={13} />
              Publish & Notify
            </motion.button>
          </div>
        ) : null}
      </motion.div>
    </>
  );
}
