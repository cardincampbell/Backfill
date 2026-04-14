"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { Printer, X, Check } from "lucide-react";
import type { PrintEmployee, PrintShift } from "@/lib/print-schedule";

export type { PrintEmployee, PrintShift };

interface Props {
  businessName: string;
  locationName: string;
  weekLabel: string;
  weekDates: Date[];
  employees: PrintEmployee[];
  shifts: PrintShift[];
  onClose: () => void;
  dark?: boolean;
}

export function PrintScheduleModal({
  businessName,
  locationName,
  weekLabel,
  weekDates,
  employees,
  shifts,
  onClose,
  dark = false,
}: Props) {
  const modalClass   = dark ? 'bg-[#0F2E4C] border border-white/[0.08]' : 'bg-white border border-[#E5E7EB]';
  const borderClass  = dark ? 'border-white/[0.08]' : 'border-[#F0F0F5]';
  const textPrimary  = dark ? 'text-white' : 'text-[#0A2540]';
  const textSecondary = dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]';

  const [includeContactInfo, setIncludeContactInfo] = useState(false);
  const [includeHours,       setIncludeHours]       = useState(true);
  const [includeRoles,       setIncludeRoles]       = useState(true);
  const [printing,           setPrinting]           = useState(false);

  const includes = [
    {
      state: includeRoles,
      toggle: () => setIncludeRoles((v) => !v),
      label: 'Role assignments',
      detail: 'Show each employee\'s role',
    },
    {
      state: includeHours,
      toggle: () => setIncludeHours((v) => !v),
      label: 'Hour totals',
      detail: 'Weekly hours per employee',
    },
    {
      state: includeContactInfo,
      toggle: () => setIncludeContactInfo((v) => !v),
      label: 'Employee contact info',
      detail: 'Email and phone number',
    },
  ];

  const handlePrint = async () => {
    setPrinting(true);
    const { printSchedule } = await import('@/lib/print-schedule');
    printSchedule({
      businessName,
      locationName,
      weekLabel,
      weekDates,
      employees,
      shifts,
      includeContactInfo,
      includeHours,
      includeRoles,
    });
    // Keep the modal open briefly so the print dialog can appear
    setTimeout(() => {
      setPrinting(false);
      onClose();
    }, 800);
  };

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 0.3 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-40 bg-black"
        onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[90vw] max-w-[440px] rounded-2xl shadow-2xl ${modalClass}`}
      >
        {/* Header */}
        <div className={`px-6 py-5 border-b flex items-center justify-between ${borderClass}`}>
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${dark ? 'bg-[#635BFF]/20' : 'bg-[#635BFF]/10'}`}>
              <Printer size={20} className="text-[#635BFF]" />
            </div>
            <div>
              <h3 className={`text-[17px] ${textPrimary}`} style={{ fontWeight: 600 }}>Print Schedule</h3>
              <p className={`text-[11px] mt-0.5 ${textSecondary}`} style={{ fontWeight: 440 }}>{weekLabel}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className={`p-1.5 rounded-lg transition-colors ${dark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]'}`}
            type="button"
          >
            <X size={18} className={textSecondary} />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          <p className={`text-[11px] uppercase tracking-[0.04em] mb-3 ${textSecondary}`} style={{ fontWeight: 500 }}>
            Include
          </p>
          <div className="space-y-2">
            {includes.map((opt) => (
              <button
                key={opt.label}
                onClick={opt.toggle}
                className={`w-full flex items-start gap-3 p-3 rounded-lg border transition-all text-left ${
                  dark ? 'border-white/[0.08] hover:border-[#635BFF]/30' : 'border-[#E5E7EB] hover:border-[#635BFF]/30'
                }`}
                type="button"
              >
                <div className={`w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 mt-0.5 transition-all ${
                  opt.state
                    ? 'border-[#635BFF] bg-[#635BFF]'
                    : dark ? 'border-white/[0.12]' : 'border-[#E5E7EB]'
                }`}>
                  {opt.state && <Check size={10} className="text-white" />}
                </div>
                <div className="flex-1">
                  <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 500 }}>{opt.label}</p>
                  <p className={`text-[10px] mt-0.5 ${textSecondary}`} style={{ fontWeight: 420 }}>{opt.detail}</p>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className={`flex gap-2.5 border-t px-6 py-4 ${borderClass}`}>
          <button
            onClick={onClose}
            className={`flex-1 rounded-xl border py-2.5 text-[12px] transition-colors ${
              dark ? 'border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]' : 'border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]'
            }`}
            style={{ fontWeight: 500 }}
            type="button"
          >
            Cancel
          </button>
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={() => void handlePrint()}
            disabled={printing}
            className="flex-1 py-2.5 rounded-xl text-[12px] text-white transition-all hover:shadow-[0_0_20px_rgba(99,91,255,0.3)] flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}
            type="button"
          >
            {printing ? (
              <div className="w-3.5 h-3.5 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            ) : (
              <Printer size={13} />
            )}
            {printing ? 'Opening…' : 'Print Schedule'}
          </motion.button>
        </div>
      </motion.div>
    </>
  );
}
