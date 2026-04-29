"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Check, X, Zap } from "lucide-react";

import {
  ScheduleWeekPublishComplianceError,
  ScheduleWeekPublishFuturePolicyConflictError,
  type ScheduleWeekFuturePolicyReview,
  type ScheduleWeekFuturePolicyReviewResponse,
  type ScheduleWeekPublishResponse,
} from "@/lib/api/workspace";
import {
  applyArtifactToComplianceReviewItems,
  complianceArtifactActionLabel,
  complianceArtifactRecordedLabel,
  complianceReasonLabel,
  describeComplianceIssue,
  summarizeComplianceReviewItems,
  type ComplianceArtifactType,
  type ComplianceReviewIssue,
  type ComplianceReviewItem,
} from "./compliance-review";

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

type PublishComplianceReviewItem = ComplianceReviewItem;
type PublishComplianceIssue = ComplianceReviewIssue;
type PublishComplianceArtifactType = ComplianceArtifactType;

function formatHourLabel(hour: number) {
  const normalized = ((hour % 24) + 24) % 24;
  const suffix = normalized >= 12 ? "PM" : "AM";
  const hour12 = normalized % 12 === 0 ? 12 : normalized % 12;
  return `${hour12}${suffix}`;
}

function formatPublishComplianceShiftLabel(shift: Shift | undefined) {
  if (!shift) {
    return "Draft shift";
  }
  const weekday = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][shift.day] ?? "Shift";
  return `${weekday} ${formatHourLabel(shift.startHour)}-${formatHourLabel(shift.endHour)} · ${shift.role}`;
}

function formatPremiumCents(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

function formatPolicyScopeLabel(scope?: string | null) {
  return scope === "business" ? "Business default" : "Location policy";
}

function formatPolicyEffectiveAtLabel(value?: string | null) {
  if (!value) {
    return "Scheduled policy";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}


interface PublishWeekModalProps {
  weekLabel: string;
  publishableShifts: Shift[];
  weekShifts: Shift[];
  employees: Employee[];
  notificationEmployees?: Employee[];
  isRepublish?: boolean;
  publishedDateLabel?: string | null;
  dark?: boolean;
  onClose: () => void;
  onPublish: () => Promise<ScheduleWeekPublishResponse>;
  onComplete: (result: ScheduleWeekPublishResponse) => void;
  loadFuturePolicyReview: () => Promise<ScheduleWeekFuturePolicyReviewResponse>;
  onRecordArtifact: (payload: {
    shiftId: string;
    employeeId: string;
    ruleCode: string;
    artifactType: PublishComplianceArtifactType;
  }) => Promise<{ artifactId: string }>;
  onViewHistory: (shiftId: string) => void;
}

export function PublishWeekModal({
  weekLabel,
  publishableShifts,
  weekShifts,
  employees,
  notificationEmployees,
  isRepublish = false,
  publishedDateLabel = null,
  dark = false,
  onClose,
  onPublish,
  onComplete,
  loadFuturePolicyReview,
  onRecordArtifact,
  onViewHistory,
}: PublishWeekModalProps) {
  const [stage, setStage] = useState<"confirm" | "publishing" | "success">("confirm");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<ScheduleWeekPublishResponse | null>(null);
  const [complianceErrorSummary, setComplianceErrorSummary] = useState<
    ScheduleWeekPublishResponse["compliance_summary"] | null
  >(null);
  const [complianceErrorReviewItems, setComplianceErrorReviewItems] = useState<
    NonNullable<ScheduleWeekPublishResponse["compliance_review_items"]>
  >([]);
  const [futurePolicyErrorSummary, setFuturePolicyErrorSummary] = useState<
    ScheduleWeekPublishResponse["compliance_summary"] | null
  >(null);
  const [futurePolicyErrorPolicyReviews, setFuturePolicyErrorPolicyReviews] = useState<
    ScheduleWeekFuturePolicyReview[]
  >([]);
  const [futurePolicyPreviewLoading, setFuturePolicyPreviewLoading] = useState(true);
  const [submittingArtifactActionKey, setSubmittingArtifactActionKey] = useState<string | null>(null);

  const affectedEmployees = notificationEmployees
    ?? Array.from(
      new Set(
        publishableShifts
          .map((shift) => shift.employeeId)
          .filter((employeeId): employeeId is string => Boolean(employeeId)),
      ),
    )
      .map((id) => employees.find((employee) => employee.id === id))
      .filter(Boolean) as Employee[];

  const totalShifts = publishableShifts.length;
  const employeeById = new Map(employees.map((employee) => [employee.id, employee]));
  const shiftById = new Map(weekShifts.map((shift) => [shift.id, shift]));
  const decorateComplianceItems = (
    items: NonNullable<ScheduleWeekPublishResponse["compliance_review_items"]>,
  ) => items.map((item) => {
    const employee = employeeById.get(item.employee_id);
    const shift = shiftById.get(item.shift_id);
    return {
      ...item,
      employeeName: employee?.name ?? "Assigned employee",
      shiftLabel: formatPublishComplianceShiftLabel(shift),
    };
  });
  const complianceDisplayItems = decorateComplianceItems(complianceErrorReviewItems);
  const futurePolicyDisplayReviews = futurePolicyErrorPolicyReviews.map((review) => ({
    ...review,
    displayItems: decorateComplianceItems(review.review_items ?? []),
  }));
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
  const futurePolicyPublishBlocked = (futurePolicyErrorSummary?.blocked_assignment_count ?? 0) > 0;

  const renderComplianceDisplayItems = (
    items: Array<PublishComplianceReviewItem & {
      employeeName: string;
      shiftLabel: string;
    }>,
  ) => {
    if (!items.length) {
      return null;
    }
    return (
      <div className="max-h-[220px] space-y-2 overflow-y-auto pr-1">
        {items.map((item) => (
          <div
            key={`${item.assignment_id ?? item.shift_id}:${item.employee_id}`}
            className={`rounded-xl border p-3 ${rowSurfaceClass}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  {item.employeeName}
                </p>
                <p className={`mt-0.5 text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  {item.shiftLabel}
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => onViewHistory(item.shift_id)}
                  className={`rounded-full border px-2.5 py-1 text-[10px] transition-colors ${dark ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-white"}`}
                  style={{ fontWeight: 560 }}
                  disabled={submittingArtifactActionKey !== null}
                >
                  View history
                </button>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] ${
                    item.status === "block"
                      ? dark
                        ? "bg-[#F87171]/15 text-[#FECACA]"
                        : "bg-[#FEF2F2] text-[#B42318]"
                      : dark
                        ? "bg-[#F59E0B]/15 text-[#FDE68A]"
                        : "bg-[#FFF7D6] text-[#8A6100]"
                  }`}
                  style={{ fontWeight: 600 }}
                >
                  {item.status === "block" ? "Blocked" : "Warning"}
                </span>
              </div>
            </div>
            <div className="mt-3 space-y-2">
              {item.issues.map((issue: PublishComplianceIssue, index: number) => {
                const guidance = describeComplianceIssue(issue);
                return (
                  <div
                    key={`${item.assignment_id ?? item.shift_id}-${issue.rule_code}-${index}`}
                    className={subtleSurfaceClass + " rounded-lg p-2.5"}
                  >
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                            {guidance.title}
                          </p>
                          {issue.override_applied ? (
                            <span className="rounded-full bg-[#00B893]/12 px-2 py-0.5 text-[10px] text-[#00B893]">
                              {complianceArtifactRecordedLabel(issue.artifact_type_allowed)}
                            </span>
                          ) : null}
                          {issue.artifact_type_allowed && !issue.override_applied ? (
                            <span className={`rounded-full px-2 py-0.5 text-[10px] ${dark ? "bg-[#635BFF]/15 text-[#C7D2FE]" : "bg-[#EEF2FF] text-[#4338CA]"}`}>
                              {complianceReasonLabel(issue.artifact_type_allowed)} allowed
                            </span>
                          ) : null}
                          {issue.premium_required || guidance.premiumLabel ? (
                            <span className={`rounded-full px-2 py-0.5 text-[10px] ${dark ? "bg-[#F59E0B]/15 text-[#FDE68A]" : "bg-[#FFF7D6] text-[#8A6100]"}`}>
                              {guidance.premiumLabel ?? (
                                issue.unresolved_premium
                                  ? "Premium depends on wage"
                                  : `${formatPremiumCents(issue.premium_cents)} premium`
                              )}
                            </span>
                          ) : null}
                        </div>
                        {issue.reason_codes.length ? (
                          <p className={`mt-1 text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                            {issue.reason_codes.map((value) => complianceReasonLabel(value)).join(" · ")}
                          </p>
                        ) : null}
                        <p className={`mt-1.5 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                          {guidance.detail}
                        </p>
                        {guidance.recommendedAction ? (
                          <p className={`mt-1 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                            {guidance.recommendedAction}
                          </p>
                        ) : null}
                      </div>
                      {issue.artifact_type_allowed ? (
                        issue.override_applied ? (
                          <span className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                            Publish again to refresh this review.
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() =>
                              void handleRecordArtifact({
                                shiftId: item.shift_id,
                                employeeId: item.employee_id,
                                ruleCode: issue.rule_code,
                                artifactType: issue.artifact_type_allowed!,
                              })
                            }
                            className="rounded-full bg-[#635BFF] px-3 py-1.5 text-[11px] text-white transition-colors hover:bg-[#564FD8] disabled:cursor-not-allowed disabled:opacity-60"
                            style={{ fontWeight: 560 }}
                            disabled={
                              submittingArtifactActionKey ===
                              `${item.shift_id}:${item.employee_id}:${issue.rule_code}:${issue.artifact_type_allowed}`
                            }
                          >
                            {submittingArtifactActionKey ===
                            `${item.shift_id}:${item.employee_id}:${issue.rule_code}:${issue.artifact_type_allowed}`
                              ? "Recording…"
                              : complianceArtifactActionLabel(issue.artifact_type_allowed!)}
                          </button>
                        )
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    );
  };

  const handlePublish = async () => {
    setErrorMessage(null);
    setComplianceErrorSummary(null);
    setComplianceErrorReviewItems([]);
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
      if (error instanceof ScheduleWeekPublishComplianceError) {
        setComplianceErrorSummary(error.summary ?? null);
        setComplianceErrorReviewItems(error.reviewItems ?? []);
        setErrorMessage("Publish blocked by compliance. Resolve the flagged assignments before publishing.");
        return;
      }
      if (error instanceof ScheduleWeekPublishFuturePolicyConflictError) {
        setFuturePolicyErrorSummary(error.summary ?? null);
        setFuturePolicyErrorPolicyReviews(error.policyReviews ?? []);
        setErrorMessage("Publish blocked by a scheduled compliance policy change during this week. Review the affected shifts before publishing.");
        return;
      }
      setErrorMessage(
        error instanceof Error ? error.message : "Could not publish this week. Please try again.",
      );
    }
  };

  useEffect(() => {
    let cancelled = false;
    setFuturePolicyPreviewLoading(true);
    void loadFuturePolicyReview()
      .then((response) => {
        if (cancelled) {
          return;
        }
        setFuturePolicyErrorSummary(response.summary ?? null);
        setFuturePolicyErrorPolicyReviews(response.policy_reviews ?? []);
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setFuturePolicyErrorSummary(null);
        setFuturePolicyErrorPolicyReviews([]);
      })
      .finally(() => {
        if (!cancelled) {
          setFuturePolicyPreviewLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [loadFuturePolicyReview]);

  const handleRecordArtifact = async ({
    shiftId,
    employeeId,
    ruleCode,
    artifactType,
  }: {
    shiftId: string;
    employeeId: string;
    ruleCode: string;
    artifactType: PublishComplianceArtifactType;
  }) => {
    const actionKey = `${shiftId}:${employeeId}:${ruleCode}:${artifactType}`;
    setSubmittingArtifactActionKey(actionKey);
    try {
      const result = await onRecordArtifact({
        shiftId,
        employeeId,
        ruleCode,
        artifactType,
      });
      setErrorMessage(null);
      setComplianceErrorReviewItems((current) => {
        const next = applyArtifactToComplianceReviewItems(current, {
          shiftId,
          employeeId,
          ruleCode,
          artifactType,
          artifactId: result.artifactId,
        });
        setComplianceErrorSummary(summarizeComplianceReviewItems(next));
        return next;
      });
      setFuturePolicyErrorPolicyReviews((current) => {
        const next = current.map((review) => {
          const nextItems = applyArtifactToComplianceReviewItems(review.review_items ?? [], {
            shiftId,
            employeeId,
            ruleCode,
            artifactType,
            artifactId: result.artifactId,
          });
          return {
            ...review,
            review_items: nextItems,
            summary: summarizeComplianceReviewItems(nextItems),
          };
        });
        setFuturePolicyErrorSummary(
          summarizeComplianceReviewItems(next.flatMap((review) => review.review_items ?? [])),
        );
        return next;
      });
    } finally {
      setSubmittingArtifactActionKey(null);
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
              {complianceErrorSummary ? (
                <div className="mb-5 space-y-3">
                  <p
                    className={`text-[11px] uppercase tracking-[0.05em] ${textSecondary}`}
                    style={{ fontWeight: 500 }}
                  >
                    Compliance Review
                  </p>
                  <div className={`rounded-xl border p-3 ${rowSurfaceClass}`}>
                    <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                      <div>
                        <p className={textSecondary}>Blocked</p>
                        <p className={textPrimary} style={{ fontWeight: 600 }}>
                          {complianceErrorSummary.blocked_assignment_count}
                        </p>
                      </div>
                      <div>
                        <p className={textSecondary}>Warnings</p>
                        <p className={textPrimary} style={{ fontWeight: 600 }}>
                          {complianceErrorSummary.warning_assignment_count}
                        </p>
                      </div>
                      <div>
                        <p className={textSecondary}>Premiums</p>
                        <p className={textPrimary} style={{ fontWeight: 600 }}>
                          {formatPremiumCents(complianceErrorSummary.premium_total_cents ?? 0)}
                        </p>
                      </div>
                      <div>
                        <p className={textSecondary}>Unresolved</p>
                        <p className={textPrimary} style={{ fontWeight: 600 }}>
                          {complianceErrorSummary.unresolved_premium_rule_count ?? 0}
                        </p>
                      </div>
                    </div>
                    {complianceErrorSummary.override_eligible_artifact_types?.length ? (
                      <p className={`mt-3 text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                        Override-ready artifacts:{" "}
                        {complianceErrorSummary.override_eligible_artifact_types
                          .map((value) => complianceReasonLabel(value))
                          .join(", ")}
                      </p>
                    ) : null}
                  </div>
                  {renderComplianceDisplayItems(complianceDisplayItems)}
                </div>
              ) : null}
              {futurePolicyErrorSummary ? (
                <div className="mb-5 space-y-3">
                  <p
                    className={`text-[11px] uppercase tracking-[0.05em] ${textSecondary}`}
                    style={{ fontWeight: 500 }}
                  >
                    Scheduled Policy Conflict
                  </p>
                  <div className={`rounded-xl border p-3 ${rowSurfaceClass}`}>
                    <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                      <div>
                        <p className={textSecondary}>Blocked</p>
                        <p className={textPrimary} style={{ fontWeight: 600 }}>
                          {futurePolicyErrorSummary.blocked_assignment_count}
                        </p>
                      </div>
                      <div>
                        <p className={textSecondary}>Warnings</p>
                        <p className={textPrimary} style={{ fontWeight: 600 }}>
                          {futurePolicyErrorSummary.warning_assignment_count}
                        </p>
                      </div>
                      <div>
                        <p className={textSecondary}>Premiums</p>
                        <p className={textPrimary} style={{ fontWeight: 600 }}>
                          {formatPremiumCents(futurePolicyErrorSummary.premium_total_cents ?? 0)}
                        </p>
                      </div>
                      <div>
                        <p className={textSecondary}>Unresolved</p>
                        <p className={textPrimary} style={{ fontWeight: 600 }}>
                          {futurePolicyErrorSummary.unresolved_premium_rule_count ?? 0}
                        </p>
                      </div>
                    </div>
                    <p className={`mt-3 text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                      These shifts pass current rules, but a scheduled compliance policy becomes effective before they work.
                    </p>
                    {futurePolicyPreviewLoading ? (
                      <p className={`mt-2 text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                        Loading scheduled policy review…
                      </p>
                    ) : null}
                  </div>
                  <div className="max-h-[280px] space-y-3 overflow-y-auto pr-1">
                    {futurePolicyDisplayReviews.map((review) => (
                      <div
                        key={`${review.policy_version_id ?? review.policy_hash ?? review.policy_effective_at}`}
                        className={`rounded-xl border p-3 ${rowSurfaceClass}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                              {formatPolicyScopeLabel(review.policy_scope)} activates
                            </p>
                            <p className={`mt-0.5 text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                              {formatPolicyEffectiveAtLabel(review.policy_effective_at)}
                              {review.policy_hash ? ` · ${review.policy_hash.slice(0, 10)}` : ""}
                            </p>
                          </div>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] ${
                              (review.summary?.blocked_assignment_count ?? 0) > 0
                                ? dark
                                  ? "bg-[#F87171]/15 text-[#FECACA]"
                                  : "bg-[#FEF2F2] text-[#B42318]"
                                : dark
                                  ? "bg-[#F59E0B]/15 text-[#FDE68A]"
                                  : "bg-[#FFF7D6] text-[#8A6100]"
                            }`}
                            style={{ fontWeight: 600 }}
                          >
                            {(review.summary?.blocked_assignment_count ?? 0) > 0
                              ? `${review.summary?.blocked_assignment_count ?? 0} blocked`
                              : `${review.summary?.warning_assignment_count ?? 0} warnings`}
                          </span>
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                          <div>
                            <p className={textSecondary}>Blocked</p>
                            <p className={textPrimary} style={{ fontWeight: 600 }}>
                              {review.summary?.blocked_assignment_count ?? 0}
                            </p>
                          </div>
                          <div>
                            <p className={textSecondary}>Warnings</p>
                            <p className={textPrimary} style={{ fontWeight: 600 }}>
                              {review.summary?.warning_assignment_count ?? 0}
                            </p>
                          </div>
                          <div>
                            <p className={textSecondary}>Premiums</p>
                            <p className={textPrimary} style={{ fontWeight: 600 }}>
                              {formatPremiumCents(review.summary?.premium_total_cents ?? 0)}
                            </p>
                          </div>
                          <div>
                            <p className={textSecondary}>Unresolved</p>
                            <p className={textPrimary} style={{ fontWeight: 600 }}>
                              {review.summary?.unresolved_premium_rule_count ?? 0}
                            </p>
                          </div>
                        </div>
                        <div className="mt-3">
                          {renderComplianceDisplayItems(review.displayItems)}
                        </div>
                      </div>
                    ))}
                  </div>
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
                      detail: "Email notifications are enqueued asynchronously",
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
                    const employeeShifts = weekShifts.filter((shift) => shift.employeeId === employee.id);
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
                      No employees are queued to receive email updates from this publish action.
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
              className="flex flex-1 items-center justify-center gap-2 rounded-xl py-2.5 text-[12px] text-white transition-all hover:shadow-[0_0_20px_rgba(99,91,255,0.3)] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:shadow-none"
              style={{ fontWeight: 540, background: "linear-gradient(135deg, #635BFF, #8B5CF6)" }}
              disabled={futurePolicyPreviewLoading || futurePolicyPublishBlocked}
            >
              <Zap size={13} />
              {futurePolicyPublishBlocked ? "Resolve Scheduled Policy Conflicts" : "Publish & Notify"}
            </motion.button>
          </div>
        ) : null}
      </motion.div>
    </>
  );
}
