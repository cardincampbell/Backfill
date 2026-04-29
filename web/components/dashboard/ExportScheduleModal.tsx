"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { FileDown, X } from "lucide-react";

import {
  getLocationCompliancePayrollExport,
  getLocationComplianceWeek,
  type LocationCompliancePayrollExport,
  type LocationComplianceWeek,
} from "@/lib/api/finance";

export interface ExportModalEmployee {
  id: string;
  name: string;
  role: string;
  roleColor: string;
}

export interface ExportModalShift {
  employeeId: string | null;
  day: number;
  startHour: number;
  endHour: number;
  roleName?: string;
  complianceStatus?: string | null;
  complianceProfileCode?: string | null;
  complianceBlockingRuleCodes?: string[];
  complianceWarningRuleCodes?: string[];
  compliancePremiumRuleCodes?: string[];
  compliancePremiumTotalCents?: number;
  complianceUnresolvedPremiumRuleCodes?: string[];
  complianceOverrideApplied?: boolean;
  complianceOverrideArtifactId?: string | null;
}

interface Props {
  businessId: string;
  locationId: string;
  businessName: string;
  weekLabel: string;
  weekStartDateKey: string;
  locationName: string;
  weekStart: Date;
  employees: ExportModalEmployee[];
  shifts: ExportModalShift[];
  onClose: () => void;
  onExport: () => void;
  dark?: boolean;
}

const FORMATS = [
  { value: 'csv' as const, label: 'CSV', icon: '📄', detail: 'Comma-separated values — opens in Excel or Google Sheets' },
  { value: 'excel' as const, label: 'Excel', icon: '📊', detail: 'Formatted Microsoft Excel workbook (.xlsx)' },
  { value: 'pdf' as const, label: 'PDF', icon: '📕', detail: 'Print-ready landscape document' },
];

export function ExportScheduleModal({
  businessId,
  locationId,
  businessName,
  weekLabel,
  weekStartDateKey,
  locationName,
  weekStart,
  employees,
  shifts,
  onClose,
  onExport,
  dark = false,
}: Props) {
  const modalClass = dark ? 'bg-[#0F2E4C] border border-white/[0.08]' : 'bg-white border border-[#E5E7EB]';
  const borderClass = dark ? 'border-white/[0.08]' : 'border-[#F0F0F5]';
  const textPrimary = dark ? 'text-white' : 'text-[#0A2540]';
  const textSecondary = dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]';
  const [selectedFormat, setSelectedFormat] = useState<'csv' | 'pdf' | 'excel'>('csv');
  const [exporting, setExporting] = useState(false);
  const [weekCompliance, setWeekCompliance] = useState<LocationComplianceWeek | null>(null);
  const [payrollExport, setPayrollExport] = useState<LocationCompliancePayrollExport | null>(null);
  const [loadingWeekCompliance, setLoadingWeekCompliance] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoadingWeekCompliance(true);
    void (async () => {
      const [snapshot, payrollSnapshot] = await Promise.all([
        getLocationComplianceWeek(
          businessId,
          locationId,
          weekStartDateKey,
        ),
        getLocationCompliancePayrollExport(
          businessId,
          locationId,
          weekStartDateKey,
        ),
      ]);
      if (!cancelled) {
        setWeekCompliance(snapshot);
        setPayrollExport(payrollSnapshot);
        setLoadingWeekCompliance(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [businessId, locationId, weekStartDateKey]);

  const handleExport = async () => {
    setExporting(true);
    const opts = {
      businessName,
      locationName,
      weekLabel,
      weekStart,
      employees,
      shifts,
      compliancePayrollExport: payrollExport,
    };
    try {
      const { exportCSV, exportExcel, exportPDF } = await import('@/lib/export-schedule');
      if (selectedFormat === 'csv') exportCSV(opts);
      else if (selectedFormat === 'excel') await exportExcel(opts);
      else await exportPDF(opts);
      onExport();
    } catch (err) {
      console.error('Export failed', err);
      setExporting(false);
    }
  };

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 0.3 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black z-40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[90vw] max-w-[480px] rounded-2xl shadow-2xl ${modalClass}`}>
        <div className={`px-6 py-5 border-b flex items-center justify-between ${borderClass}`}>
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${dark ? 'bg-[#635BFF]/20' : 'bg-[#635BFF]/10'}`}>
              <FileDown size={20} className="text-[#635BFF]" />
            </div>
            <div>
              <h3 className={`text-[17px] ${textPrimary}`} style={{ fontWeight: 600 }}>Export Schedule</h3>
              <p className={`text-[11px] mt-0.5 ${textSecondary}`} style={{ fontWeight: 440 }}>{weekLabel}</p>
            </div>
          </div>
          <button onClick={onClose} className={`p-1.5 rounded-lg transition-colors ${dark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]'}`}>
            <X size={18} className={textSecondary} />
          </button>
        </div>

        <div className="px-6 py-5">
          <label className={`block text-[11px] uppercase tracking-[0.04em] mb-3 ${textSecondary}`} style={{ fontWeight: 500 }}>Choose Format</label>
          <div className="space-y-2">
            {FORMATS.map((format) => (
              <button
                key={format.value}
                onClick={() => setSelectedFormat(format.value)}
                className={`w-full flex items-start gap-3 p-3 rounded-lg border transition-all text-left ${
                  selectedFormat === format.value
                    ? 'border-[#635BFF] bg-[#635BFF]/[0.04]'
                    : dark
                      ? 'border-white/[0.08] hover:border-[#635BFF]/30'
                      : 'border-[#E5E7EB] hover:border-[#635BFF]/30'
                }`}>
                <span className="text-[24px] shrink-0">{format.icon}</span>
                <div className="flex-1">
                  <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 500 }}>{format.label}</p>
                  <p className={`text-[10px] mt-0.5 ${textSecondary}`} style={{ fontWeight: 420 }}>{format.detail}</p>
                </div>
                <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 mt-1 transition-all ${
                  selectedFormat === format.value ? 'border-[#635BFF]' : dark ? 'border-white/[0.12]' : 'border-[#E5E7EB]'
                }`}>
                  {selectedFormat === format.value && <div className="w-2 h-2 rounded-full bg-[#635BFF]" />}
                </div>
              </button>
            ))}
          </div>
          <p className={`mt-3 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
            Compliance premiums, unresolved calculations, and recorded artifacts are included automatically when this week has them.
          </p>
          {loadingWeekCompliance ? (
            <div className={`mt-3 rounded-xl border px-3.5 py-3 ${dark ? 'border-white/[0.08] bg-white/[0.03]' : 'border-[#E5E7EB] bg-[#F7F8FA]/70'}`}>
              <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                Compliance Report
              </p>
              <p className={`mt-1 text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                Loading premium and artifact totals for this week…
              </p>
            </div>
          ) : weekCompliance ? (
            <div className={`mt-3 rounded-xl border px-3.5 py-3 ${dark ? 'border-white/[0.08] bg-white/[0.03]' : 'border-[#E5E7EB] bg-[#F7F8FA]/70'}`}>
              <div className="flex items-center justify-between gap-3">
                <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                  Compliance Report
                </p>
                <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                  {weekCompliance.assigned_shift_count} assigned shift{weekCompliance.assigned_shift_count === 1 ? '' : 's'}
                </p>
              </div>
              <div className="mt-2 grid grid-cols-4 gap-2">
                <div>
                  <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>Premiums</p>
                  <p className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                    ${(weekCompliance.premium_total_cents / 100).toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>Unresolved</p>
                  <p className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                    {weekCompliance.unresolved_premium_assignment_count}
                  </p>
                </div>
                <div>
                  <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>Artifacts</p>
                  <p className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                    {payrollExport?.artifact_record_row_count ?? weekCompliance.override_artifacts.length}
                  </p>
                </div>
                <div>
                  <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>Manual Review</p>
                  <p className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                    {payrollExport?.manual_review_row_count ?? weekCompliance.unresolved_premium_assignment_count}
                  </p>
                </div>
              </div>
              {payrollExport ? (
                <>
                  <div className="mt-3 grid grid-cols-3 gap-2">
                    <div>
                      <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>Ready Rows</p>
                      <p className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                        {payrollExport.ready_adjustment_row_count ?? payrollExport.premium_payment_row_count}
                      </p>
                    </div>
                    <div>
                      <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>Missing IDs</p>
                      <p className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                        {payrollExport.missing_employee_identifier_row_count ?? 0}
                      </p>
                    </div>
                    <div>
                      <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>Info Rows</p>
                      <p className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                        {payrollExport.artifact_record_row_count}
                      </p>
                    </div>
                  </div>
                  <p className={`mt-2 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                    Export includes {payrollExport.premium_payment_row_count} premium payment row{payrollExport.premium_payment_row_count === 1 ? '' : 's'} and {payrollExport.manual_review_row_count} manual review row{payrollExport.manual_review_row_count === 1 ? '' : 's'}.
                  </p>
                  {(payrollExport.manual_review_row_count > 0 || (payrollExport.missing_employee_identifier_row_count ?? 0) > 0) ? (
                    <p className={`mt-1 text-[10px] ${dark ? 'text-[#FDE68A]' : 'text-[#9A3412]'}`} style={{ fontWeight: 500 }}>
                      Some payroll consequence rows still require manual handling before direct payroll import.
                    </p>
                  ) : null}
                </>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className={`px-6 py-4 border-t flex gap-2.5 ${borderClass}`}>
          <button onClick={onClose}
            className={`flex-1 py-2.5 rounded-xl border text-[12px] transition-colors ${dark ? 'border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]' : 'border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]'}`}
            style={{ fontWeight: 500 }}>
            Cancel
          </button>
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={() => void handleExport()}
            disabled={exporting}
            className="flex-1 py-2.5 rounded-xl text-[12px] text-white transition-all hover:shadow-[0_0_20px_rgba(99,91,255,0.3)] flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
            {exporting ? (
              <div className="w-3.5 h-3.5 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            ) : (
              <FileDown size={13} />
            )}
            {exporting ? 'Exporting…' : `Export ${selectedFormat.toUpperCase()}`}
          </motion.button>
        </div>
      </motion.div>
    </>
  );
}
