import type {
  ComplianceReviewItem,
  ComplianceReviewSummary,
} from "@/lib/api/workspace";

export type { ComplianceReviewItem, ComplianceReviewSummary };
export type ComplianceReviewIssue = ComplianceReviewItem["issues"][number];
export type ComplianceArtifactType = "written_consent" | "meal_waiver";

const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

export function humanizeComplianceCode(value: string | null | undefined) {
  if (!value) {
    return "Compliance rule";
  }
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function complianceArtifactActionLabel(value: ComplianceArtifactType) {
  return value === "meal_waiver" ? "Record meal waiver" : "Record written consent";
}

export function complianceArtifactRecordedLabel(value: string | null | undefined) {
  return value === "meal_waiver" ? "Meal waiver applied" : "Consent artifact applied";
}

export function complianceReasonLabel(value: string) {
  const normalized = value.trim().toLowerCase();
  const labels: Record<string, string> = {
    structured_break_plan_missing: "Structured break plan missing",
    waiver_possible_but_not_modelled: "Waiver can resolve this",
    premium_required_if_overridden: "Premium still applies if overridden",
    written_consent_required: "Written consent required",
    labor_rule_profile_unresolved: "Labor rule profile is unresolved",
    wage_dependent_premium_unresolved: "Premium depends on wage data",
    split_shift_detected: "Split shift detected",
    spread_of_hours_detected: "Spread-of-hours threshold exceeded",
    minimum_rest_window_violation: "Required rest window not met",
    first_meal_break_missing: "First meal break missing",
    second_meal_break_missing: "Second meal break missing",
    rest_break_quota_missing: "Required paid rest break missing",
    override_artifact_applied: "Artifact recorded",
    structured_break_plan_required_by_policy: "Company policy requires structured breaks",
    max_daily_minutes_exceeded_by_policy: "Company daily-hours limit exceeded",
    max_weekly_minutes_exceeded_by_policy: "Company weekly-hours limit exceeded",
    unresolved_premium_blocked_by_policy: "Company policy blocks unresolved premiums",
    waiver_disabled_by_policy: "Company policy disables waivers here",
    employee_is_minor: "Employee is a minor",
    work_permit_missing: "Work permit is missing",
    work_permit_not_yet_effective: "Work permit is not active yet",
    work_permit_expired: "Work permit is expired",
    work_permit_valid: "Work permit is valid",
    active_work_permit_restriction_applied: "Active permit restriction applied",
    work_permit_daily_minutes_exceeded: "Permit daily-hours limit exceeded",
    work_permit_daily_minutes_within_limit: "Permit daily-hours limit satisfied",
    work_permit_weekly_minutes_exceeded: "Permit weekly-hours limit exceeded",
    work_permit_weekly_minutes_within_limit: "Permit weekly-hours limit satisfied",
    work_permit_shift_starts_too_early: "Permit start time is too early",
    work_permit_shift_ends_too_late: "Permit end time is too late",
    work_permit_weekday_not_allowed: "Permit does not allow this weekday",
    work_permit_weekday_allowed: "Permit weekday restriction satisfied",
    work_permit_time_window_satisfied: "Permit time window satisfied",
    minor_daily_minutes_exceeded: "Minor daily-hours limit exceeded",
    minor_daily_minutes_within_limit: "Minor daily-hours limit satisfied",
    minor_weekly_minutes_exceeded: "Minor weekly-hours limit exceeded",
    minor_weekly_minutes_within_limit: "Minor weekly-hours limit satisfied",
    minor_shift_starts_too_early: "Minor shift starts too early",
    minor_shift_ends_too_late: "Minor shift ends too late",
    minor_time_window_satisfied: "Minor time window satisfied",
  };
  return labels[normalized] ?? humanizeComplianceCode(normalized);
}

export function summarizeComplianceReviewItems(
  items: ComplianceReviewItem[],
): ComplianceReviewSummary {
  const warningRuleCodes = new Set<string>();
  const unresolvedPremiumRuleCodes = new Set<string>();
  const overrideEligibleArtifactTypes = new Set<string>();
  const warningShiftIds = new Set<string>();
  const blockedShiftIds = new Set<string>();
  const overrideEligibleShiftIds = new Set<string>();
  const overrideArtifactIds = new Set<string>();

  for (const item of items) {
    if (item.status === "warning") {
      warningShiftIds.add(item.shift_id);
    }
    if (item.status === "block") {
      blockedShiftIds.add(item.shift_id);
    }
    for (const ruleCode of item.warning_rule_codes) {
      warningRuleCodes.add(ruleCode);
    }
    for (const ruleCode of item.unresolved_premium_rule_codes) {
      unresolvedPremiumRuleCodes.add(ruleCode);
    }
    if (item.override_applied && item.override_artifact_id) {
      overrideArtifactIds.add(item.override_artifact_id);
    }
    if (item.override_eligible_artifact_types.length > 0) {
      overrideEligibleShiftIds.add(item.shift_id);
    }
    for (const artifactType of item.override_eligible_artifact_types) {
      overrideEligibleArtifactTypes.add(artifactType);
    }
  }

  return {
    selected_assignment_count: items.length,
    clear_assignment_count: items.filter((item) => item.status === "clear").length,
    warning_assignment_count: items.filter((item) => item.status === "warning").length,
    blocked_assignment_count: items.filter((item) => item.status === "block").length,
    override_applied_count: overrideArtifactIds.size,
    override_eligible_warning_count: items.reduce(
      (sum, item) =>
        sum
        + item.issues.filter(
          (issue) => issue.artifact_type_allowed && !issue.override_applied,
        ).length,
      0,
    ),
    premium_total_cents: items.reduce((sum, item) => sum + item.premium_total_cents, 0),
    unresolved_premium_rule_count: unresolvedPremiumRuleCodes.size,
    unresolved_premium_rule_codes: Array.from(unresolvedPremiumRuleCodes).sort(),
    warning_rule_codes: Array.from(warningRuleCodes).sort(),
    override_eligible_artifact_types: Array.from(overrideEligibleArtifactTypes).sort(),
    warning_shift_ids: Array.from(warningShiftIds).sort(),
    blocked_shift_ids: Array.from(blockedShiftIds).sort(),
    override_eligible_shift_ids: Array.from(overrideEligibleShiftIds).sort(),
  };
}

export function applyArtifactToComplianceReviewItems(
  items: ComplianceReviewItem[],
  payload: {
    shiftId: string;
    employeeId: string;
    ruleCode: string;
    artifactType: ComplianceArtifactType;
    artifactId: string;
  },
): ComplianceReviewItem[] {
  return items.map((item) => {
    if (item.shift_id !== payload.shiftId || item.employee_id !== payload.employeeId) {
      return item;
    }
    const issues = item.issues.map((issue) => {
      if (
        issue.rule_code !== payload.ruleCode
        || issue.artifact_type_allowed !== payload.artifactType
        || issue.override_applied
      ) {
        return issue;
      }
      if (payload.artifactType === "meal_waiver") {
        return {
          ...issue,
          status: "clear",
          premium_required: false,
          premium_type: null,
          premium_cents: 0,
          unresolved_premium: false,
          would_block: false,
          override_applied: true,
          override_artifact_id: payload.artifactId,
        };
      }
      return {
        ...issue,
        status: "warning",
        would_block: false,
        override_applied: true,
        override_artifact_id: payload.artifactId,
      };
    });
    const blockingRuleCodes = issues
      .filter((issue) => issue.status === "block" && !issue.override_applied)
      .map((issue) => issue.rule_code);
    const warningRuleCodes = issues
      .filter((issue) => issue.status === "warning")
      .map((issue) => issue.rule_code);
    const unresolvedPremiumRuleCodes = issues
      .filter((issue) => issue.unresolved_premium)
      .map((issue) => issue.rule_code);
    const premiumTotalCents = issues.reduce(
      (sum, issue) => sum + (issue.premium_required ? issue.premium_cents : 0),
      0,
    );
    const overrideEligibleArtifactTypes = issues
      .filter((issue) => issue.artifact_type_allowed && !issue.override_applied)
      .map((issue) => issue.artifact_type_allowed!)
      .sort();
    const overrideArtifactIds = issues
      .map((issue) => issue.override_artifact_id)
      .filter((value): value is string => Boolean(value));
    const status =
      blockingRuleCodes.length > 0
        ? "block"
        : warningRuleCodes.length > 0
            || unresolvedPremiumRuleCodes.length > 0
            || premiumTotalCents > 0
          ? "warning"
          : "clear";
    return {
      ...item,
      status,
      blocking_rule_codes: blockingRuleCodes,
      warning_rule_codes: warningRuleCodes,
      premium_total_cents: premiumTotalCents,
      unresolved_premium_rule_codes: unresolvedPremiumRuleCodes,
      override_applied: overrideArtifactIds.length > 0,
      override_artifact_id: overrideArtifactIds[0] ?? null,
      override_eligible_artifact_types: overrideEligibleArtifactTypes,
      issues,
    };
  });
}

export function describeComplianceIssue(issue: ComplianceReviewIssue) {
  const normalizedRuleCode = issue.rule_code.trim().toLowerCase();
  const reasonCodes = new Set(
    issue.reason_codes.map((value) => value.trim().toLowerCase()).filter(Boolean),
  );

  let title = humanizeComplianceCode(issue.rule_code);
  let detail = "This shift needs review before it can be scheduled safely.";

  if (normalizedRuleCode === "clopening_restricted" || normalizedRuleCode === "minimum_rest_window") {
    title = "Required rest window not met";
    detail = "This employee does not have enough rest between shifts to take this assignment cleanly.";
  } else if (normalizedRuleCode === "meal_break_first_window") {
    title = "First meal break is missing or too late";
    detail = "This shift needs a compliant first meal break inside the first meal window.";
  } else if (normalizedRuleCode === "meal_break_second_window") {
    title = "Second meal break is missing";
    detail = "This long shift needs a compliant second meal break unless a valid waiver applies.";
  } else if (normalizedRuleCode === "paid_rest_break_quota") {
    title = "Paid rest break quota is missing";
    detail = "This shift structure does not currently include enough paid rest break time.";
  } else if (normalizedRuleCode === "split_shift_premium") {
    title = "Split-shift premium applies";
    detail = "The current segment layout creates a split shift and can trigger a premium obligation.";
  } else if (normalizedRuleCode === "spread_of_hours_premium") {
    title = "Spread-of-hours premium applies";
    detail = "This shift spans long enough from first start to last end to trigger a spread-of-hours premium obligation.";
  } else if (normalizedRuleCode === "overtime_projection") {
    title = "Overtime exposure increases";
    detail = "Assigning this employee pushes projected labor cost up through overtime.";
  } else if (normalizedRuleCode === "customer_policy_max_daily_work_minutes") {
    title = "Daily-hours policy limit exceeded";
    detail = "This assignment would exceed the business or location’s configured maximum daily work limit.";
  } else if (normalizedRuleCode === "customer_policy_max_weekly_work_minutes") {
    title = "Weekly-hours policy limit exceeded";
    detail = "This assignment would exceed the business or location’s configured maximum weekly work limit.";
  } else if (normalizedRuleCode === "customer_policy_structured_break_plan") {
    title = "Structured break plan required";
    detail = "This business requires explicit shift segments and breaks before schedules can be assigned or published.";
  } else if (normalizedRuleCode === "customer_policy_unresolved_premium") {
    title = "Unresolved premium blocked by policy";
    detail = "This shift still carries wage-dependent premium liability and company policy does not allow publishing it unresolved.";
  } else if (normalizedRuleCode === "minor_work_permit_required") {
    title = "Valid work permit required";
    detail = "This minor employee needs a valid work permit on file before the shift can be scheduled.";
  } else if (normalizedRuleCode === "minor_work_permit_daily_hours_limit") {
    title = "Work permit daily-hours limit exceeded";
    detail = "This shift exceeds the daily cap recorded on the employee's active work permit.";
  } else if (normalizedRuleCode === "minor_work_permit_weekly_hours_limit") {
    title = "Work permit weekly-hours limit exceeded";
    detail = "This assignment would exceed the weekly cap recorded on the employee's active work permit.";
  } else if (normalizedRuleCode === "minor_work_permit_time_window") {
    title = "Work permit time window violated";
    detail = "This shift starts or ends outside the time window recorded on the employee's active work permit.";
  } else if (normalizedRuleCode === "minor_work_permit_weekday_restriction") {
    title = "Work permit weekday restriction violated";
    detail = "This shift falls on a weekday the employee's active work permit does not allow.";
  } else if (normalizedRuleCode === "minor_daily_hours_limit") {
    title = "Minor daily-hours limit exceeded";
    detail = "This shift is too long for the configured minor daily-hours rule.";
  } else if (normalizedRuleCode === "minor_weekly_hours_limit") {
    title = "Minor weekly-hours limit exceeded";
    detail = "This assignment would push the employee over the configured minor weekly-hours rule.";
  } else if (normalizedRuleCode === "minor_time_window_restricted") {
    title = "Minor time-of-day restriction violated";
    detail = "This shift starts or ends outside the configured minor time window.";
  } else if (normalizedRuleCode === "compliance_profile_unresolved") {
    title = "Compliance profile is unresolved";
    detail = "Backfill could not resolve the active labor-rule profile for this shift with enough confidence.";
  }

  if (reasonCodes.has("structured_break_plan_missing")) {
    detail = "This shift needs explicit break structure before Backfill can treat it as compliant.";
  } else if (reasonCodes.has("written_consent_required")) {
    detail = "This assignment needs written consent before Backfill can allow the reduced rest window.";
  } else if (reasonCodes.has("waiver_possible_but_not_modelled")) {
    detail = "A waiver may resolve this, but it still needs to be recorded against the shift and employee.";
  } else if (reasonCodes.has("waiver_disabled_by_policy")) {
    detail = "The underlying law might allow a waiver here, but your configured compliance policy does not.";
  } else if (reasonCodes.has("work_permit_missing")) {
    detail = "A valid work permit is required before this minor employee can take the shift.";
  } else if (reasonCodes.has("work_permit_expired")) {
    detail = "The recorded work permit is expired for the date of this shift.";
  } else if (reasonCodes.has("work_permit_not_yet_effective")) {
    detail = "The recorded work permit does not become active until after the date of this shift.";
  } else if (reasonCodes.has("work_permit_daily_minutes_exceeded")) {
    detail = "This shift exceeds the daily limit recorded on the employee's active work permit.";
  } else if (reasonCodes.has("work_permit_weekly_minutes_exceeded")) {
    detail = "This assignment would exceed the weekly limit recorded on the employee's active work permit.";
  } else if (reasonCodes.has("work_permit_shift_starts_too_early")) {
    detail = "This shift begins earlier than the start time allowed on the employee's active work permit.";
  } else if (reasonCodes.has("work_permit_shift_ends_too_late")) {
    detail = "This shift ends later than the end time allowed on the employee's active work permit.";
  } else if (reasonCodes.has("work_permit_weekday_not_allowed")) {
    detail = "This shift falls on a weekday the employee's active work permit does not allow.";
  } else if (reasonCodes.has("minor_daily_minutes_exceeded")) {
    detail = "This shift exceeds the configured daily work limit for minor employees.";
  } else if (reasonCodes.has("minor_weekly_minutes_exceeded")) {
    detail = "This assignment would exceed the configured weekly work limit for this minor employee.";
  } else if (reasonCodes.has("minor_shift_starts_too_early")) {
    detail = "This shift begins earlier than the configured start time allowed for minor employees.";
  } else if (reasonCodes.has("minor_shift_ends_too_late")) {
    detail = "This shift ends later than the configured end time allowed for minor employees.";
  }

  let recommendedAction: string | null = null;
  if (issue.override_applied) {
    recommendedAction = "Artifact recorded. Run the assignment again so Backfill can re-evaluate against the updated compliance state.";
  } else if (issue.artifact_type_allowed === "meal_waiver") {
    recommendedAction = "Record a meal waiver only if the shift length and policy actually allow it, then retry the assignment.";
  } else if (issue.artifact_type_allowed === "written_consent") {
    recommendedAction = "Record written consent from the employee, then retry the assignment.";
  } else if (issue.would_block) {
    recommendedAction = "Change the employee, timing, or break structure before retrying this assignment.";
  }

  if (normalizedRuleCode === "customer_policy_unresolved_premium") {
    recommendedAction = "Add wage data or change policy if you want Backfill to permit unresolved premium cases.";
  } else if (normalizedRuleCode === "customer_policy_structured_break_plan") {
    recommendedAction = "Add explicit segments and breaks before retrying.";
  }

  let premiumLabel: string | null = null;
  if (issue.unresolved_premium) {
    premiumLabel = "Premium applies, but final pay still depends on wage data.";
  } else if (issue.premium_required && issue.premium_cents > 0) {
    premiumLabel = `${USD_FORMATTER.format(issue.premium_cents / 100)} premium exposure`;
  } else if (issue.premium_required) {
    premiumLabel = "Premium applies";
  }

  return {
    title,
    detail,
    recommendedAction,
    premiumLabel,
  };
}
