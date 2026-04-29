"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { AlertTriangle, Check, FileDown, ReceiptText, X } from "lucide-react";

import {
  applySimulatedBusinessCompliancePolicy,
  applySimulatedLocationCompliancePolicy,
  getBusinessComplianceScheduledPolicyDrift,
  getLocationComplianceScheduledPolicyDrift,
  simulateBusinessCompliancePolicy,
  getLocationComplianceTrend,
  getLocationCompliancePayrollExport,
  getLocationComplianceWeek,
  simulateLocationCompliancePolicy,
  type BusinessComplianceScheduledPolicyDrift,
  type BusinessCompliancePolicySimulation,
  type CompliancePolicyActivation,
  type ComplianceOverrideArtifactSummary,
  type ComplianceTrendRuleCount,
  type ComplianceWeekEmployee,
  type ComplianceWeekShift,
  type LocationComplianceScheduledPolicyDrift,
  type LocationCompliancePolicySimulation,
  type LocationComplianceTrend,
  type LocationComplianceWeek,
} from "@/lib/api/finance";
import { exportCompliancePayrollCsv } from "@/lib/export-compliance-payroll";
import { humanizeComplianceCode } from "./compliance-review";

interface Props {
  businessId: string;
  locationId: string;
  locationName: string;
  weekLabel: string;
  weekStartDateKey: string;
  onClose: () => void;
  onOpenExport: () => void;
  dark?: boolean;
}

const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

function formatMoney(cents: number) {
  return USD_FORMATTER.format(cents / 100);
}

function formatSignedMoney(cents: number) {
  const prefix = cents > 0 ? "+" : cents < 0 ? "-" : "";
  return `${prefix}${formatMoney(Math.abs(cents))}`;
}

function formatSignedCount(value: number) {
  if (value > 0) {
    return `+${value}`;
  }
  return String(value);
}

function formatRuleCodes(ruleCodes: string[]) {
  if (!ruleCodes.length) {
    return "None";
  }
  return ruleCodes.map((code) => humanizeComplianceCode(code)).join(", ");
}

function formatShiftLabel(shift: ComplianceWeekShift) {
  const startsAt = new Date(shift.starts_at);
  const endsAt = new Date(shift.ends_at);
  const weekday = startsAt.toLocaleDateString("en-US", { weekday: "short" });
  const startTime = startsAt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const endTime = endsAt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  return `${weekday} ${startTime}-${endTime}`;
}

function formatWeekRangeLabel(weekStartDate: string, weekEndDate: string) {
  const startsAt = new Date(`${weekStartDate}T12:00:00Z`);
  const endsAt = new Date(`${weekEndDate}T12:00:00Z`);
  const startLabel = startsAt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const endLabel = endsAt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `${startLabel}-${endLabel}`;
}

function formatPolicyActivationLabel(activation: CompliancePolicyActivation) {
  const effectiveAt = new Date(activation.effective_at);
  const timeLabel = Number.isNaN(effectiveAt.getTime())
    ? activation.effective_at
    : effectiveAt.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  const scopeLabel = activation.policy_scope === "business" ? "Business default" : (activation.location_name ?? "Location policy");
  return `${scopeLabel} · ${timeLabel}`;
}

function employeeExposureRank(employee: ComplianceWeekEmployee) {
  return (
    employee.premium_total_cents * 100
    + employee.unresolved_premium_rule_codes.length * 10
    + employee.override_applied_count
  );
}

function shiftAttentionRank(shift: ComplianceWeekShift) {
  const statusRank = shift.compliance_status === "block" ? 300 : shift.compliance_status === "warning" ? 200 : 100;
  return (
    statusRank
    + shift.unresolved_premium_rule_codes.length * 10
    + Math.min(shift.premium_total_cents, 9999)
  );
}

export function ComplianceFinanceModal({
  businessId,
  locationId,
  locationName,
  weekLabel,
  weekStartDateKey,
  onClose,
  onOpenExport,
  dark = false,
}: Props) {
  const [report, setReport] = useState<LocationComplianceWeek | null>(null);
  const [trendReport, setTrendReport] = useState<LocationComplianceTrend | null>(null);
  const [locationDrift, setLocationDrift] = useState<LocationComplianceScheduledPolicyDrift | null>(null);
  const [businessDrift, setBusinessDrift] = useState<BusinessComplianceScheduledPolicyDrift | null>(null);
  const [locationSimulation, setLocationSimulation] = useState<LocationCompliancePolicySimulation | null>(null);
  const [businessSimulation, setBusinessSimulation] = useState<BusinessCompliancePolicySimulation | null>(null);
  const [loading, setLoading] = useState(true);
  const [exportingPayroll, setExportingPayroll] = useState(false);
  const [simulatingPolicy, setSimulatingPolicy] = useState(false);
  const [applyingSimulation, setApplyingSimulation] = useState(false);
  const [simulationMessage, setSimulationMessage] = useState<string | null>(null);
  const [policyScope, setPolicyScope] = useState<"location" | "business">("location");
  const [stalePreviewPolicy, setStalePreviewPolicy] = useState<{
    currentCompliancePolicyHash: string;
    currentComplianceSettings: LocationCompliancePolicySimulation["baseline_location_compliance_settings"];
  } | null>(null);
  const [staleBusinessPreviewPolicy, setStaleBusinessPreviewPolicy] = useState<{
    currentCompliancePolicyHash: string;
    currentComplianceSettings: BusinessCompliancePolicySimulation["baseline_business_compliance_settings"];
  } | null>(null);
  const [policyDraft, setPolicyDraft] = useState({
    minimumRestHours: "",
    maxDailyMinutes: "",
    maxWeeklyMinutes: "",
    requireStructuredBreakPlans: false,
    blockUnresolvedPremiums: false,
    disableWrittenConsent: false,
    disableMealWaivers: false,
  });

  async function loadReports(options?: { resetSimulation?: boolean }) {
    setLoading(true);
    if (options?.resetSimulation !== false) {
      setLocationSimulation(null);
      setBusinessSimulation(null);
    }
    const [payload, trendPayload, locationDriftPayload, businessDriftPayload] = await Promise.all([
      getLocationComplianceWeek(
        businessId,
        locationId,
        weekStartDateKey,
      ),
      getLocationComplianceTrend(
        businessId,
        locationId,
        weekStartDateKey,
        6,
      ),
      getLocationComplianceScheduledPolicyDrift(
        businessId,
        locationId,
        weekStartDateKey,
        6,
      ),
      getBusinessComplianceScheduledPolicyDrift(
        businessId,
        weekStartDateKey,
        6,
      ),
    ]);
    setReport(payload);
    setTrendReport(trendPayload);
    setLocationDrift(locationDriftPayload);
    setBusinessDrift(businessDriftPayload);
    setLoading(false);
  }

  useEffect(() => {
    let cancelled = false;
    const loadInitialReports = async () => {
      setLoading(true);
      setLocationSimulation(null);
      setBusinessSimulation(null);
      const [payload, trendPayload, locationDriftPayload, businessDriftPayload] = await Promise.all([
        getLocationComplianceWeek(
          businessId,
          locationId,
          weekStartDateKey,
        ),
        getLocationComplianceTrend(
          businessId,
          locationId,
          weekStartDateKey,
          6,
        ),
        getLocationComplianceScheduledPolicyDrift(
          businessId,
          locationId,
          weekStartDateKey,
          6,
        ),
        getBusinessComplianceScheduledPolicyDrift(
          businessId,
          weekStartDateKey,
          6,
        ),
      ]);
      if (!cancelled) {
        setReport(payload);
        setTrendReport(trendPayload);
        setLocationDrift(locationDriftPayload);
        setBusinessDrift(businessDriftPayload);
        setLoading(false);
      }
    };
    void loadInitialReports();
    return () => {
      cancelled = true;
    };
  }, [businessId, locationId, weekStartDateKey]);

  const topEmployees = useMemo(
    () =>
      [...(report?.employees ?? [])]
        .sort((left, right) => employeeExposureRank(right) - employeeExposureRank(left))
        .slice(0, 6),
    [report],
  );

  const attentionShifts = useMemo(
    () =>
      [...(report?.shifts ?? [])]
        .filter(
          (shift) =>
            shift.compliance_status !== "clear"
            || shift.premium_total_cents > 0
            || shift.unresolved_premium_rule_codes.length > 0,
        )
        .sort((left, right) => shiftAttentionRank(right) - shiftAttentionRank(left))
        .slice(0, 8),
    [report],
  );

  const recentArtifacts = useMemo(
    () =>
      [...(report?.override_artifacts ?? [])]
        .sort((left, right) => right.approved_at.localeCompare(left.approved_at))
        .slice(0, 6),
    [report],
  );

  const trendPeakPremium = useMemo(
    () => Math.max(1, ...(trendReport?.weeks ?? []).map((week) => week.premium_total_cents)),
    [trendReport],
  );

  const recurringRiskGroups = useMemo(
    () => (
      [
        {
          title: "Warning Hotspots",
          rows: trendReport?.top_warning_rule_codes ?? [],
        },
        {
          title: "Premium Drivers",
          rows: trendReport?.top_premium_rule_codes ?? [],
        },
        {
          title: "Unresolved Drivers",
          rows: trendReport?.top_unresolved_premium_rule_codes ?? [],
        },
      ] satisfies { title: string; rows: ComplianceTrendRuleCount[] }[]
    ),
    [trendReport],
  );

  const activeLocationSimulation = policyScope === "location" ? locationSimulation : null;
  const activeBusinessSimulation = policyScope === "business" ? businessSimulation : null;
  const activeLocationDrift = policyScope === "location" ? locationDrift : null;
  const activeBusinessDrift = policyScope === "business" ? businessDrift : null;
  const activeStalePreviewPolicy = policyScope === "location" ? stalePreviewPolicy : null;
  const activeStaleBusinessPreviewPolicy = policyScope === "business" ? staleBusinessPreviewPolicy : null;

  const modalClass = dark ? "bg-[#0F2E4C] border border-white/[0.08]" : "bg-white border border-[#E5E7EB]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#F0F0F5]";
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const surfaceClass = dark ? "bg-white/[0.03] border border-white/[0.08]" : "bg-[#F7F8FA]/70 border border-[#E5E7EB]";
  const hasSimulationOverrides = Boolean(
    policyDraft.minimumRestHours.trim()
    || policyDraft.maxDailyMinutes.trim()
    || policyDraft.maxWeeklyMinutes.trim()
    || policyDraft.requireStructuredBreakPlans
    || policyDraft.blockUnresolvedPremiums
    || policyDraft.disableWrittenConsent
    || policyDraft.disableMealWaivers
  );

  const simulationCompliancePayload = (() => {
    const compliance: Record<string, unknown> = {};
    if (policyDraft.minimumRestHours.trim()) {
      compliance.minimum_rest_hours = Number(policyDraft.minimumRestHours);
    }
    if (policyDraft.maxDailyMinutes.trim()) {
      compliance.max_daily_minutes = Number(policyDraft.maxDailyMinutes);
    }
    if (policyDraft.maxWeeklyMinutes.trim()) {
      compliance.max_weekly_minutes = Number(policyDraft.maxWeeklyMinutes);
    }
    if (policyDraft.requireStructuredBreakPlans) {
      compliance.require_structured_break_plans = true;
    }
    if (policyDraft.blockUnresolvedPremiums) {
      compliance.block_unresolved_premiums = true;
    }
    if (policyDraft.disableWrittenConsent) {
      compliance.written_consent_allowed = false;
    }
    if (policyDraft.disableMealWaivers) {
      compliance.first_meal_waiver_allowed = false;
      compliance.second_meal_waiver_allowed = false;
    }
    return compliance;
  })();

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.3 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-40 bg-black"
        onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className={`fixed left-1/2 top-1/2 z-50 h-[86vh] w-[92vw] max-w-[920px] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl shadow-2xl ${modalClass}`}
      >
        <div className={`flex items-center justify-between border-b px-6 py-5 ${borderClass}`}>
          <div className="flex items-center gap-3">
            <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${dark ? "bg-[#635BFF]/20" : "bg-[#635BFF]/10"}`}>
              <AlertTriangle size={18} className="text-[#635BFF]" />
            </div>
            <div>
              <h3 className={`text-[17px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                Compliance Finance Review
              </h3>
              <p className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                {locationName} · {weekLabel}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className={`rounded-lg p-1.5 transition-colors ${dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"}`}
            type="button"
          >
            <X size={18} className={textSecondary} />
          </button>
        </div>

        <div className="h-[calc(86vh-152px)] overflow-auto px-6 py-5">
          {loading ? (
            <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
              <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                Loading compliance finance report
              </p>
              <p className={`mt-1 text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                Backfill is assembling premium exposure, unresolved calculations, and artifact usage for this week.
              </p>
            </div>
          ) : !report ? (
            <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
              <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                Compliance finance report unavailable
              </p>
              <p className={`mt-1 text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                Backfill could not load the weekly compliance summary for this location right now.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-4">
                <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                  <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                    Premium Exposure
                  </p>
                  <p className={`mt-1 text-[20px] ${textPrimary}`} style={{ fontWeight: 640 }}>
                    {formatMoney(report.premium_total_cents)}
                  </p>
                </div>
                <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                  <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                    Unresolved
                  </p>
                  <p className={`mt-1 text-[20px] ${textPrimary}`} style={{ fontWeight: 640 }}>
                    {report.unresolved_premium_assignment_count}
                  </p>
                </div>
                <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                  <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                    Blocked
                  </p>
                  <p className={`mt-1 text-[20px] ${textPrimary}`} style={{ fontWeight: 640 }}>
                    {report.blocked_assignment_count}
                  </p>
                </div>
                <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                  <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                    Artifacts Applied
                  </p>
                  <p className={`mt-1 text-[20px] ${textPrimary}`} style={{ fontWeight: 640 }}>
                    {report.override_artifacts.length}
                  </p>
                </div>
              </div>

              {trendReport ? (
                <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                  <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                    <div>
                      <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 580 }}>
                        Trend Window
                      </p>
                      <p className={`mt-1 text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                        {trendReport.week_count} weeks ending {weekLabel}. This keeps compliance review tied to drift, not just a single publish window.
                      </p>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-3">
                      <div className={`rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Trend Premiums
                        </p>
                        <p className={`mt-1 text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatMoney(trendReport.total_premium_cents)}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Trend Blocks
                        </p>
                        <p className={`mt-1 text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                          {trendReport.total_blocked_assignment_count}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Trend Overrides
                        </p>
                        <p className={`mt-1 text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                          {trendReport.total_override_applied_count}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-2 lg:grid-cols-6">
                    {trendReport.weeks.map((week) => {
                      const premiumWidth = week.premium_total_cents > 0
                        ? `${Math.max(12, Math.round((week.premium_total_cents / trendPeakPremium) * 100))}%`
                        : "0%";
                      return (
                        <div
                          key={week.week_start_date}
                          className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}
                        >
                          <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 500 }}>
                            {formatWeekRangeLabel(week.week_start_date, week.week_end_date)}
                          </p>
                          <p className={`mt-1 text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                            {formatMoney(week.premium_total_cents)}
                          </p>
                          <div className={`mt-2 h-1.5 overflow-hidden rounded-full ${dark ? "bg-white/[0.08]" : "bg-[#E5E7EB]"}`}>
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: premiumWidth,
                                background: "linear-gradient(90deg, #F59E0B, #EF4444)",
                              }}
                            />
                          </div>
                          <p className={`mt-2 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                            {week.blocked_assignment_count} blocked · {week.unresolved_premium_assignment_count} unresolved
                          </p>
                          <p className={`mt-1 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                            {week.override_applied_count} overrides · {week.assigned_shift_count} assigned
                          </p>
                        </div>
                      );
                    })}
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    {recurringRiskGroups.map((group) => (
                      <div
                        key={group.title}
                        className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}
                      >
                        <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                          {group.title}
                        </p>
                        <div className="mt-3 space-y-2">
                          {group.rows.length ? group.rows.map((row) => (
                            <div key={`${group.title}-${row.rule_code}`} className="flex items-center justify-between gap-3">
                              <span className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                                {humanizeComplianceCode(row.rule_code)}
                              </span>
                              <span className={`text-[10px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                                {row.count}
                              </span>
                            </div>
                          )) : (
                            <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                              No recurring issues in this trend window.
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {activeLocationDrift ? (
                <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                  <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                    <div>
                      <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 580 }}>
                        Scheduled Policy Drift
                      </p>
                      <p className={`mt-1 text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                        Upcoming location impact if Backfill keeps today’s effective policy frozen versus allowing already-scheduled policy versions to activate.
                      </p>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-4">
                      <div className={`rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Premium Delta
                        </p>
                        <p className={`mt-1 text-[14px] ${activeLocationDrift.delta.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedMoney(activeLocationDrift.delta.premium_total_cents_delta)}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Block Delta
                        </p>
                        <p className={`mt-1 text-[14px] ${activeLocationDrift.delta.blocked_assignment_count_delta > 0 ? "text-[#EF4444]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedCount(activeLocationDrift.delta.blocked_assignment_count_delta)}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Unresolved Delta
                        </p>
                        <p className={`mt-1 text-[14px] ${activeLocationDrift.delta.unresolved_premium_assignment_count_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedCount(activeLocationDrift.delta.unresolved_premium_assignment_count_delta)}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Activations
                        </p>
                        <p className={`mt-1 text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                          {activeLocationDrift.activating_policy_versions.length}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-3 lg:grid-cols-2">
                    <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                      <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                        Activating Policies
                      </p>
                      <div className="mt-3 space-y-2">
                        {activeLocationDrift.activating_policy_versions.length ? activeLocationDrift.activating_policy_versions.map((activation) => (
                          <div key={activation.policy_version_id} className="flex items-center justify-between gap-3">
                            <div>
                              <p className={`text-[10px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                                {formatPolicyActivationLabel(activation)}
                              </p>
                              <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                                {activation.policy_hash.slice(0, 10)}
                              </p>
                            </div>
                          </div>
                        )) : (
                          <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                            No scheduled business or location policy versions activate in this upcoming window.
                          </p>
                        )}
                      </div>
                    </div>
                    <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                      <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                        Weekly Drift
                      </p>
                      <div className="mt-3 space-y-2">
                        {activeLocationDrift.week_deltas.map((week) => (
                          <div key={week.week_start_date} className="flex items-center justify-between gap-3">
                            <div>
                              <p className={`text-[10px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                                {formatWeekRangeLabel(week.week_start_date, week.week_end_date)}
                              </p>
                              <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                                {formatSignedCount(week.blocked_assignment_count_delta)} blocks · {formatSignedCount(week.unresolved_premium_assignment_count_delta)} unresolved
                              </p>
                            </div>
                            <p className={`text-[11px] ${week.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                              {formatSignedMoney(week.premium_total_cents_delta)}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}

              {activeBusinessDrift ? (
                <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                  <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                    <div>
                      <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 580 }}>
                        Scheduled Policy Drift
                      </p>
                      <p className={`mt-1 text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                        Upcoming business-wide impact if Backfill freezes today’s effective policy state versus allowing already-scheduled business and location policies to activate.
                      </p>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-4">
                      <div className={`rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Premium Delta
                        </p>
                        <p className={`mt-1 text-[14px] ${activeBusinessDrift.delta.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedMoney(activeBusinessDrift.delta.premium_total_cents_delta)}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Block Delta
                        </p>
                        <p className={`mt-1 text-[14px] ${activeBusinessDrift.delta.blocked_assignment_count_delta > 0 ? "text-[#EF4444]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedCount(activeBusinessDrift.delta.blocked_assignment_count_delta)}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Location Delta
                        </p>
                        <p className={`mt-1 text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                          {activeBusinessDrift.location_count}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Activations
                        </p>
                        <p className={`mt-1 text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                          {activeBusinessDrift.activating_policy_versions.length}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-3 lg:grid-cols-2">
                    <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                      <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                        Activating Policies
                      </p>
                      <div className="mt-3 space-y-2">
                        {activeBusinessDrift.activating_policy_versions.length ? activeBusinessDrift.activating_policy_versions.map((activation) => (
                          <div key={activation.policy_version_id} className="flex items-center justify-between gap-3">
                            <div>
                              <p className={`text-[10px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                                {formatPolicyActivationLabel(activation)}
                              </p>
                              <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                                {activation.policy_hash.slice(0, 10)}
                              </p>
                            </div>
                          </div>
                        )) : (
                          <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                            No scheduled business or location policy versions activate in this upcoming window.
                          </p>
                        )}
                      </div>
                    </div>
                    <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                      <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                        Weekly Drift
                      </p>
                      <div className="mt-3 space-y-2">
                        {activeBusinessDrift.week_deltas.map((week) => (
                          <div key={week.week_start_date} className="flex items-center justify-between gap-3">
                            <div>
                              <p className={`text-[10px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                                {formatWeekRangeLabel(week.week_start_date, week.week_end_date)}
                              </p>
                              <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                                {formatSignedCount(week.blocked_assignment_count_delta)} blocks · {formatSignedCount(week.unresolved_premium_assignment_count_delta)} unresolved
                              </p>
                            </div>
                            <p className={`text-[11px] ${week.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                              {formatSignedMoney(week.premium_total_cents_delta)}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className={`mt-3 rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                    <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                      Location Impact
                    </p>
                    <div className="mt-3 space-y-2">
                      {activeBusinessDrift.location_deltas.length ? activeBusinessDrift.location_deltas.map((row) => (
                        <div key={row.location_id} className="flex items-center justify-between gap-3">
                          <div>
                            <p className={`text-[10px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                              {row.location_name}
                            </p>
                            <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                              {formatSignedCount(row.blocked_assignment_count_delta)} blocks · {formatSignedCount(row.unresolved_premium_assignment_count_delta)} unresolved · {formatSignedCount(row.override_applied_count_delta)} overrides
                            </p>
                          </div>
                          <p className={`text-[11px] ${row.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                            {formatSignedMoney(row.premium_total_cents_delta)}
                          </p>
                        </div>
                      )) : (
                        <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                          No active locations show scheduled-policy drift in this upcoming window.
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ) : null}

              <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                  <div>
                    <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 580 }}>
                      Policy Simulation
                    </p>
                    <p className={`mt-1 text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                      {policyScope === "location"
                        ? "Preview a stricter location policy against the trailing review window before you save it anywhere."
                        : "Preview a stricter business default against every active location before you push it into the shared policy layer."}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <div className={`flex rounded-xl p-1 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                      {[
                        { key: "location", label: "Location Only" },
                        { key: "business", label: "Business Default" },
                      ].map((option) => (
                        <button
                          key={option.key}
                          type="button"
                          onClick={() => {
                            setPolicyScope(option.key as "location" | "business");
                            setSimulationMessage(null);
                          }}
                          className={`rounded-lg px-3 py-1.5 text-[10px] transition-colors ${
                            policyScope === option.key
                              ? dark
                                ? "bg-[#635BFF] text-white"
                                : "bg-[#0A2540] text-white"
                              : dark
                                ? "text-[#C1CED8] hover:bg-white/[0.04]"
                                : "text-[#5E6D7A] hover:bg-[#F7F8FA]"
                          }`}
                          style={{ fontWeight: 560 }}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setSimulationMessage(null);
                        setStalePreviewPolicy(null);
                        setStaleBusinessPreviewPolicy(null);
                        setPolicyDraft({
                          minimumRestHours: "",
                          maxDailyMinutes: "",
                          maxWeeklyMinutes: "",
                          requireStructuredBreakPlans: false,
                          blockUnresolvedPremiums: false,
                          disableWrittenConsent: false,
                          disableMealWaivers: false,
                        });
                        setLocationSimulation(null);
                        setBusinessSimulation(null);
                      }}
                      className={`rounded-xl border px-3 py-2 text-[11px] transition-colors ${dark ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-white"}`}
                      style={{ fontWeight: 500 }}
                    >
                      Reset
                    </button>
                    <button
                      type="button"
                      disabled={!hasSimulationOverrides || simulatingPolicy}
                      onClick={() => {
                        void (async () => {
                          if (!hasSimulationOverrides) {
                            return;
                          }
                          setSimulatingPolicy(true);
                          setSimulationMessage(null);
                          setStalePreviewPolicy(null);
                          setStaleBusinessPreviewPolicy(null);
                          try {
                            const payload = policyScope === "location"
                              ? await simulateLocationCompliancePolicy(
                                  businessId,
                                  locationId,
                                  weekStartDateKey,
                                  {
                                    week_count: 6,
                                    compliance: simulationCompliancePayload,
                                  },
                                )
                              : await simulateBusinessCompliancePolicy(
                                  businessId,
                                  weekStartDateKey,
                                  {
                                    week_count: 6,
                                    compliance: simulationCompliancePayload,
                                  },
                                );
                            if (payload) {
                              if (policyScope === "location") {
                                setLocationSimulation(payload as LocationCompliancePolicySimulation);
                                setBusinessSimulation(null);
                              } else {
                                setBusinessSimulation(payload as BusinessCompliancePolicySimulation);
                                setLocationSimulation(null);
                              }
                            } else {
                              setSimulationMessage("Backfill could not simulate this policy right now.");
                            }
                          } finally {
                            setSimulatingPolicy(false);
                          }
                        })();
                      }}
                      className={`rounded-xl px-3 py-2 text-[11px] text-white transition-all ${hasSimulationOverrides ? "" : "opacity-50"} ${dark ? "bg-[#635BFF] hover:bg-[#726BFF]" : "bg-[#0A2540] hover:bg-[#163A5B]"}`}
                      style={{ fontWeight: 540 }}
                    >
                      {simulatingPolicy ? "Running Preview" : "Run Preview"}
                    </button>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 lg:grid-cols-3">
                  <label className="space-y-1">
                    <span className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                      Minimum Rest Hours
                    </span>
                    <input
                      type="number"
                      min={0}
                      step="0.5"
                      value={policyDraft.minimumRestHours}
                      onChange={(event) =>
                        setPolicyDraft((current) => ({ ...current, minimumRestHours: event.target.value }))
                      }
                      className={`w-full rounded-xl border px-3 py-2 text-[12px] outline-none ${dark ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8FA3B5]" : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#9CA3AF]"}`}
                      placeholder="e.g. 12"
                    />
                  </label>
                  <label className="space-y-1">
                    <span className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                      Max Daily Minutes
                    </span>
                    <input
                      type="number"
                      min={0}
                      step="1"
                      value={policyDraft.maxDailyMinutes}
                      onChange={(event) =>
                        setPolicyDraft((current) => ({ ...current, maxDailyMinutes: event.target.value }))
                      }
                      className={`w-full rounded-xl border px-3 py-2 text-[12px] outline-none ${dark ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8FA3B5]" : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#9CA3AF]"}`}
                      placeholder="e.g. 480"
                    />
                  </label>
                  <label className="space-y-1">
                    <span className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                      Max Weekly Minutes
                    </span>
                    <input
                      type="number"
                      min={0}
                      step="1"
                      value={policyDraft.maxWeeklyMinutes}
                      onChange={(event) =>
                        setPolicyDraft((current) => ({ ...current, maxWeeklyMinutes: event.target.value }))
                      }
                      className={`w-full rounded-xl border px-3 py-2 text-[12px] outline-none ${dark ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8FA3B5]" : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#9CA3AF]"}`}
                      placeholder="e.g. 2400"
                    />
                  </label>
                </div>

                <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                  {[
                    {
                      key: "requireStructuredBreakPlans",
                      label: "Require Structured Break Plans",
                    },
                    {
                      key: "blockUnresolvedPremiums",
                      label: "Block Unresolved Premiums",
                    },
                    {
                      key: "disableWrittenConsent",
                      label: "Disable Written Consent",
                    },
                    {
                      key: "disableMealWaivers",
                      label: "Disable Meal Waivers",
                    },
                  ].map((item) => (
                    <label
                      key={item.key}
                      className={`flex items-center gap-2 rounded-xl px-3 py-2 ${dark ? "bg-white/[0.04]" : "bg-white"}`}
                    >
                      <input
                        type="checkbox"
                        checked={Boolean(policyDraft[item.key as keyof typeof policyDraft])}
                        onChange={(event) =>
                          setPolicyDraft((current) => ({
                            ...current,
                            [item.key]: event.target.checked,
                          }))
                        }
                      />
                      <span className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 500 }}>
                        {item.label}
                      </span>
                    </label>
                  ))}
                </div>

                {simulationMessage ? (
                  <div className={`mt-4 rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04] text-[#C1CED8]" : "bg-white text-[#5E6D7A]"}`}>
                    <p className="text-[11px]" style={{ fontWeight: 500 }}>
                      {simulationMessage}
                    </p>
                  </div>
                ) : null}

                {activeStalePreviewPolicy ? (
                  <div className={`mt-4 rounded-xl border px-3 py-3 ${dark ? "border-[#F59E0B]/30 bg-[#F59E0B]/10" : "border-[#FDE68A] bg-[#FFFBEB]"}`}>
                    <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                      The persisted compliance policy changed after this preview was generated.
                    </p>
                    <p className={`mt-1 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                      Rerun the preview before applying. Current persisted policy hash: {activeStalePreviewPolicy.currentCompliancePolicyHash.slice(0, 10)}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {Object.entries(activeStalePreviewPolicy.currentComplianceSettings).map(([key, value]) => (
                        <span
                          key={key}
                          className={`rounded-full px-2.5 py-1 text-[10px] ${dark ? "bg-white/[0.08] text-[#C1CED8]" : "bg-white text-[#5E6D7A]"}`}
                          style={{ fontWeight: 500 }}
                        >
                          {humanizeComplianceCode(key)}: {String(value)}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                {activeStaleBusinessPreviewPolicy ? (
                  <div className={`mt-4 rounded-xl border px-3 py-3 ${dark ? "border-[#F59E0B]/30 bg-[#F59E0B]/10" : "border-[#FDE68A] bg-[#FFFBEB]"}`}>
                    <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                      The persisted business compliance policy changed after this preview was generated.
                    </p>
                    <p className={`mt-1 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                      Rerun the preview before applying. Current business policy hash: {activeStaleBusinessPreviewPolicy.currentCompliancePolicyHash.slice(0, 10)}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {Object.entries(activeStaleBusinessPreviewPolicy.currentComplianceSettings).map(([key, value]) => (
                        <span
                          key={key}
                          className={`rounded-full px-2.5 py-1 text-[10px] ${dark ? "bg-white/[0.08] text-[#C1CED8]" : "bg-white text-[#5E6D7A]"}`}
                          style={{ fontWeight: 500 }}
                        >
                          {humanizeComplianceCode(key)}: {String(value)}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                {activeLocationSimulation ? (
                  <div className="mt-4 space-y-3">
                    <div className="grid gap-3 md:grid-cols-4">
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Premium Delta
                        </p>
                        <p className={`mt-1 text-[15px] ${activeLocationSimulation.delta.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedMoney(activeLocationSimulation.delta.premium_total_cents_delta)}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Block Delta
                        </p>
                        <p className={`mt-1 text-[15px] ${activeLocationSimulation.delta.blocked_assignment_count_delta > 0 ? "text-[#EF4444]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedCount(activeLocationSimulation.delta.blocked_assignment_count_delta)}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Unresolved Delta
                        </p>
                        <p className={`mt-1 text-[15px] ${activeLocationSimulation.delta.unresolved_premium_assignment_count_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedCount(activeLocationSimulation.delta.unresolved_premium_assignment_count_delta)}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Override Delta
                        </p>
                        <p className={`mt-1 text-[15px] ${activeLocationSimulation.delta.override_applied_count_delta < 0 ? "text-[#EF4444]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedCount(activeLocationSimulation.delta.override_applied_count_delta)}
                        </p>
                      </div>
                    </div>

                    <div className="grid gap-3 lg:grid-cols-2">
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                          Simulated Policy
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {Object.entries(activeLocationSimulation.proposed_location_compliance_settings).map(([key, value]) => (
                            <span
                              key={key}
                              className={`rounded-full px-2.5 py-1 text-[10px] ${dark ? "bg-white/[0.06] text-[#C1CED8]" : "bg-[#F7F8FA] text-[#5E6D7A]"}`}
                              style={{ fontWeight: 500 }}
                            >
                              {humanizeComplianceCode(key)}: {String(value)}
                            </span>
                          ))}
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <span
                            className={`rounded-full px-2.5 py-1 text-[10px] ${dark ? "bg-white/[0.06] text-[#C1CED8]" : "bg-[#F7F8FA] text-[#5E6D7A]"}`}
                            style={{ fontWeight: 500 }}
                          >
                            Preview Hash: {activeLocationSimulation.baseline_location_compliance_policy_hash.slice(0, 10)}
                          </span>
                        </div>
                      </div>
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                          Weekly Delta
                        </p>
                        <div className="mt-3 space-y-2">
                          {activeLocationSimulation.week_deltas.map((week) => (
                            <div key={week.week_start_date} className="flex items-center justify-between gap-3">
                              <div>
                                <p className={`text-[10px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                                  {formatWeekRangeLabel(week.week_start_date, week.week_end_date)}
                                </p>
                                <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                                  {formatSignedCount(week.blocked_assignment_count_delta)} blocks · {formatSignedCount(week.unresolved_premium_assignment_count_delta)} unresolved
                                </p>
                              </div>
                              <p className={`text-[11px] ${week.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                                {formatSignedMoney(week.premium_total_cents_delta)}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="flex justify-end">
                      <button
                        type="button"
                        disabled={applyingSimulation}
                        onClick={() => {
                          void (async () => {
                            setApplyingSimulation(true);
                            setSimulationMessage(null);
                            setStalePreviewPolicy(null);
                            setStaleBusinessPreviewPolicy(null);
                            try {
                              const result = await applySimulatedLocationCompliancePolicy(
                                businessId,
                                locationId,
                                {
                                  expected_compliance_policy_hash: activeLocationSimulation.baseline_location_compliance_policy_hash,
                                  compliance: activeLocationSimulation.proposed_location_compliance_settings,
                                },
                              );
                              if (result.ok) {
                                setSimulationMessage("Applied to location settings. Backfill reloaded the finance view against the saved policy.");
                                setPolicyDraft({
                                  minimumRestHours: "",
                                  maxDailyMinutes: "",
                                  maxWeeklyMinutes: "",
                                  requireStructuredBreakPlans: false,
                                  blockUnresolvedPremiums: false,
                                  disableWrittenConsent: false,
                                  disableMealWaivers: false,
                                });
                                await loadReports();
                                return;
                              }
                              if (result.reason === "stale_preview") {
                                setStalePreviewPolicy({
                                  currentCompliancePolicyHash: result.current_compliance_policy_hash,
                                  currentComplianceSettings: result.current_compliance_settings,
                                });
                                setSimulationMessage("Preview is stale. Rerun it against the current persisted policy before applying.");
                                return;
                              }
                              setSimulationMessage(result.message);
                            } finally {
                              setApplyingSimulation(false);
                            }
                          })();
                        }}
                        className={`rounded-xl px-3 py-2 text-[11px] text-white transition-all ${dark ? "bg-[#635BFF] hover:bg-[#726BFF]" : "bg-[#0A2540] hover:bg-[#163A5B]"}`}
                        style={{ fontWeight: 540 }}
                      >
                        {applyingSimulation ? "Applying Policy" : "Apply To Location Settings"}
                      </button>
                    </div>
                  </div>
                ) : null}

                {activeBusinessSimulation ? (
                  <div className="mt-4 space-y-3">
                    <div className="grid gap-3 md:grid-cols-4">
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Premium Delta
                        </p>
                        <p className={`mt-1 text-[15px] ${activeBusinessSimulation.delta.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedMoney(activeBusinessSimulation.delta.premium_total_cents_delta)}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Block Delta
                        </p>
                        <p className={`mt-1 text-[15px] ${activeBusinessSimulation.delta.blocked_assignment_count_delta > 0 ? "text-[#EF4444]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedCount(activeBusinessSimulation.delta.blocked_assignment_count_delta)}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Location Count
                        </p>
                        <p className={`mt-1 text-[15px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                          {activeBusinessSimulation.location_count}
                        </p>
                      </div>
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Override Delta
                        </p>
                        <p className={`mt-1 text-[15px] ${activeBusinessSimulation.delta.override_applied_count_delta < 0 ? "text-[#EF4444]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedCount(activeBusinessSimulation.delta.override_applied_count_delta)}
                        </p>
                      </div>
                    </div>

                    <div className="grid gap-3 lg:grid-cols-2">
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                          Business Default Policy
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {Object.entries(activeBusinessSimulation.proposed_business_compliance_settings).map(([key, value]) => (
                            <span
                              key={key}
                              className={`rounded-full px-2.5 py-1 text-[10px] ${dark ? "bg-white/[0.06] text-[#C1CED8]" : "bg-[#F7F8FA] text-[#5E6D7A]"}`}
                              style={{ fontWeight: 500 }}
                            >
                              {humanizeComplianceCode(key)}: {String(value)}
                            </span>
                          ))}
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <span
                            className={`rounded-full px-2.5 py-1 text-[10px] ${dark ? "bg-white/[0.06] text-[#C1CED8]" : "bg-[#F7F8FA] text-[#5E6D7A]"}`}
                            style={{ fontWeight: 500 }}
                          >
                            Preview Hash: {activeBusinessSimulation.baseline_business_compliance_policy_hash.slice(0, 10)}
                          </span>
                        </div>
                      </div>
                      <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                        <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                          Weekly Delta
                        </p>
                        <div className="mt-3 space-y-2">
                          {activeBusinessSimulation.week_deltas.map((week) => (
                            <div key={week.week_start_date} className="flex items-center justify-between gap-3">
                              <div>
                                <p className={`text-[10px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                                  {formatWeekRangeLabel(week.week_start_date, week.week_end_date)}
                                </p>
                                <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                                  {formatSignedCount(week.blocked_assignment_count_delta)} blocks · {formatSignedCount(week.unresolved_premium_assignment_count_delta)} unresolved
                                </p>
                              </div>
                              <p className={`text-[11px] ${week.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                                {formatSignedMoney(week.premium_total_cents_delta)}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}>
                      <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                        Location Impact
                      </p>
                      <div className="mt-3 space-y-2">
                        {activeBusinessSimulation.location_deltas.length ? activeBusinessSimulation.location_deltas.map((row) => (
                          <div key={row.location_id} className="flex items-center justify-between gap-3">
                            <div>
                              <p className={`text-[10px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                                {row.location_name}
                              </p>
                              <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                                {formatSignedCount(row.blocked_assignment_count_delta)} blocks · {formatSignedCount(row.unresolved_premium_assignment_count_delta)} unresolved · {formatSignedCount(row.override_applied_count_delta)} overrides
                              </p>
                            </div>
                            <p className={`text-[11px] ${row.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                              {formatSignedMoney(row.premium_total_cents_delta)}
                            </p>
                          </div>
                        )) : (
                          <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                            No active locations are currently affected by this proposed business default.
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex justify-end">
                      <button
                        type="button"
                        disabled={applyingSimulation}
                        onClick={() => {
                          void (async () => {
                            setApplyingSimulation(true);
                            setSimulationMessage(null);
                            setStalePreviewPolicy(null);
                            setStaleBusinessPreviewPolicy(null);
                            try {
                              const result = await applySimulatedBusinessCompliancePolicy(
                                businessId,
                                {
                                  expected_compliance_policy_hash: activeBusinessSimulation.baseline_business_compliance_policy_hash,
                                  compliance: activeBusinessSimulation.proposed_business_compliance_settings,
                                },
                              );
                              if (result.ok) {
                                setSimulationMessage("Applied as the business default. Backfill reloaded the finance view against the saved policy.");
                                setPolicyDraft({
                                  minimumRestHours: "",
                                  maxDailyMinutes: "",
                                  maxWeeklyMinutes: "",
                                  requireStructuredBreakPlans: false,
                                  blockUnresolvedPremiums: false,
                                  disableWrittenConsent: false,
                                  disableMealWaivers: false,
                                });
                                await loadReports();
                                return;
                              }
                              if (result.reason === "stale_preview") {
                                setStaleBusinessPreviewPolicy({
                                  currentCompliancePolicyHash: result.current_compliance_policy_hash,
                                  currentComplianceSettings: result.current_compliance_settings,
                                });
                                setSimulationMessage("Business preview is stale. Rerun it against the current persisted default before applying.");
                                return;
                              }
                              setSimulationMessage(result.message);
                            } finally {
                              setApplyingSimulation(false);
                            }
                          })();
                        }}
                        className={`rounded-xl px-3 py-2 text-[11px] text-white transition-all ${dark ? "bg-[#635BFF] hover:bg-[#726BFF]" : "bg-[#0A2540] hover:bg-[#163A5B]"}`}
                        style={{ fontWeight: 540 }}
                      >
                        {applyingSimulation ? "Applying Policy" : "Apply As Business Default"}
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>

              {report.artifact_type_counts.length > 0 ? (
                <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                  <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                    Artifact Mix
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {report.artifact_type_counts.map((row) => (
                      <span
                        key={row.artifact_type}
                        className={`rounded-full px-2.5 py-1 text-[11px] ${dark ? "bg-white/[0.06] text-[#C1CED8]" : "bg-white text-[#5E6D7A]"}`}
                        style={{ fontWeight: 500 }}
                      >
                        {humanizeComplianceCode(row.artifact_type)} · {row.count}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="grid gap-4 lg:grid-cols-2">
                <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                  <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 580 }}>
                    Employee Exposure
                  </p>
                  <div className="mt-3 space-y-2">
                    {topEmployees.length ? topEmployees.map((employee) => (
                      <div
                        key={employee.employee_id}
                        className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                              {employee.employee_name ?? "Assigned employee"}
                            </p>
                            <p className={`mt-0.5 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                              {employee.assignment_count} shifts · {employee.override_applied_count} artifacts applied
                            </p>
                          </div>
                          <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                            {formatMoney(employee.premium_total_cents)}
                          </p>
                        </div>
                        <p className={`mt-2 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                          Warning rules: {formatRuleCodes(employee.warning_rule_codes)}
                        </p>
                        {employee.unresolved_premium_rule_codes.length ? (
                          <p className="mt-1 text-[10px] text-[#F59E0B]" style={{ fontWeight: 520 }}>
                            Unresolved: {formatRuleCodes(employee.unresolved_premium_rule_codes)}
                          </p>
                        ) : null}
                      </div>
                    )) : (
                      <p className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                        No assigned shifts in this week have compliance-finance consequences yet.
                      </p>
                    )}
                  </div>
                </div>

                <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                  <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 580 }}>
                    Shifts Needing Attention
                  </p>
                  <div className="mt-3 space-y-2">
                    {attentionShifts.length ? attentionShifts.map((shift) => (
                      <div
                        key={shift.shift_id}
                        className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                              {shift.employee_name ?? "Assigned employee"} · {shift.role_name ?? "Role"}
                            </p>
                            <p className={`mt-0.5 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                              {formatShiftLabel(shift)} · {humanizeComplianceCode(shift.compliance_status)}
                            </p>
                          </div>
                          <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                            {formatMoney(shift.premium_total_cents)}
                          </p>
                        </div>
                        <p className={`mt-2 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                          Warning rules: {formatRuleCodes(shift.warning_rule_codes)}
                        </p>
                        {shift.unresolved_premium_rule_codes.length ? (
                          <p className="mt-1 text-[10px] text-[#F59E0B]" style={{ fontWeight: 520 }}>
                            Unresolved: {formatRuleCodes(shift.unresolved_premium_rule_codes)}
                          </p>
                        ) : null}
                      </div>
                    )) : (
                      <p className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                        This week does not currently have blocked, warning, or premium-bearing assignments.
                      </p>
                    )}
                  </div>
                </div>
              </div>

              <div className={`rounded-2xl px-4 py-4 ${surfaceClass}`}>
                <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 580 }}>
                  Recorded Artifacts
                </p>
                <div className="mt-3 space-y-2">
                  {recentArtifacts.length ? recentArtifacts.map((artifact: ComplianceOverrideArtifactSummary) => (
                    <div
                      key={artifact.artifact_id}
                      className={`rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-white"}`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                            {artifact.employee_name ?? "Assigned employee"} · {humanizeComplianceCode(artifact.artifact_type)}
                          </p>
                          <p className={`mt-0.5 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                            {humanizeComplianceCode(artifact.rule_code)}
                          </p>
                        </div>
                        <div className="flex items-center gap-1.5 text-[#00B893]">
                          <Check size={12} />
                          <span className="text-[10px]" style={{ fontWeight: 560 }}>
                            Applied
                          </span>
                        </div>
                      </div>
                      {artifact.note ? (
                        <p className={`mt-2 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                          {artifact.note}
                        </p>
                      ) : null}
                    </div>
                  )) : (
                    <p className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                      No waiver or consent artifacts were applied in this week.
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className={`flex gap-2.5 border-t px-6 py-4 ${borderClass}`}>
          <button
            onClick={onClose}
            className={`flex-1 rounded-xl border py-2.5 text-[12px] transition-colors ${dark ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"}`}
            style={{ fontWeight: 500 }}
            type="button"
          >
            Close
          </button>
          <button
            onClick={() => {
              void (async () => {
                setExportingPayroll(true);
                try {
                  const payrollExport = await getLocationCompliancePayrollExport(
                    businessId,
                    locationId,
                    weekStartDateKey,
                  );
                  if (!payrollExport) {
                    return;
                  }
                  exportCompliancePayrollCsv(payrollExport, {
                    locationName,
                    weekLabel,
                  });
                } finally {
                  setExportingPayroll(false);
                }
              })();
            }}
            className={`flex flex-1 items-center justify-center gap-2 rounded-xl py-2.5 text-[12px] transition-all ${dark ? "bg-white/[0.06] text-white hover:bg-white/[0.1]" : "bg-[#0A2540] text-white hover:bg-[#163A5B]"}`}
            style={{ fontWeight: 540 }}
            type="button"
          >
            <ReceiptText size={13} />
            {exportingPayroll ? "Preparing Payroll CSV" : "Export Payroll CSV"}
          </button>
          <button
            onClick={onOpenExport}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl py-2.5 text-[12px] text-white transition-all"
            style={{ fontWeight: 540, background: "linear-gradient(135deg, #635BFF, #8B5CF6)" }}
            type="button"
          >
            <FileDown size={13} />
            Open Export
          </button>
        </div>
      </motion.div>
    </>
  );
}
