import { describe, expect, it } from "vitest";

import {
  complianceReasonLabel,
  dedupeComplianceSourceReferences,
  describeComplianceIssue,
  describeCompliancePremiumRateBasis,
  describeComplianceSourceReference,
} from "./compliance-review";

describe("compliance-review source references", () => {
  it("dedupes duplicate source references", () => {
    const references = [
      {
        rule_code: "meal_break_first_window",
        source_kind: "labor_rule_profile",
        source_code: "ca_restaurant_v1",
        source_label: "California restaurant baseline",
        jurisdiction_code: "US-CA",
        source_document_title: null,
        source_urls: ["https://example.com/ca-rule-pack"],
        source_version: "ca_rule_pack_v3",
        source_hash: "sha256:ca-pack",
        version_id: "profile_version_1",
        payload_hash: null,
        effective_at: null,
      },
      {
        rule_code: "meal_break_first_window",
        source_kind: "labor_rule_profile",
        source_code: "ca_restaurant_v1",
        source_label: "California restaurant baseline",
        jurisdiction_code: "US-CA",
        source_document_title: null,
        source_urls: ["https://example.com/ca-rule-pack"],
        source_version: "ca_rule_pack_v3",
        source_hash: "sha256:ca-pack",
        version_id: "profile_version_1",
        payload_hash: null,
        effective_at: null,
      },
    ];

    expect(dedupeComplianceSourceReferences(references)).toHaveLength(1);
  });

  it("formats source reference labels for manager-facing review", () => {
    expect(
      describeComplianceSourceReference({
        rule_code: "customer_policy_unresolved_premium",
        source_kind: "policy_overlay",
        source_code: "location_policy",
        source_label: "Customer policy overlay",
        jurisdiction_code: null,
        source_document_title: null,
        source_urls: [],
        source_version: "policy_v4",
        source_hash: "sha256:policy",
        version_id: null,
        payload_hash: "sha256:policy-payload",
        effective_at: null,
      }),
    ).toEqual({
      kindLabel: "Policy overlay",
      primaryLabel: "Customer policy overlay",
      secondaryLabel: "policy_v4",
      href: null,
      pillLabel: "Policy overlay · Customer policy overlay",
    });
  });

  it("labels Washington rest-break timing gaps clearly", () => {
    expect(complianceReasonLabel("rest_break_timing_gap_exceeded")).toBe(
      "Rest break timing gap exceeded",
    );
    expect(
      describeComplianceIssue({
        rule_code: "paid_rest_break_quota",
        status: "block",
        reason_codes: ["rest_break_quota_missing", "rest_break_timing_gap_exceeded"],
        premium_required: false,
        premium_cents: 0,
        premium_type: null,
        premium_unresolved: false,
        would_block: true,
        artifact_type_allowed: null,
        override_applied: false,
        override_artifact_id: null,
        rule_source_references: [],
      }).detail,
    ).toContain("too much continuous work time");
  });

  it("labels Colorado missed-rest wage reasons clearly", () => {
    expect(complianceReasonLabel("rest_break_wages_due")).toBe(
      "Missed rest-break wages are due",
    );
    expect(complianceReasonLabel("rest_break_wages_include_overtime")).toBe(
      "Missed rest-break wages include overtime",
    );
    expect(complianceReasonLabel("meal_break_wages_due")).toBe(
      "Missed meal-break wages are due",
    );
    expect(complianceReasonLabel("meal_break_wages_include_overtime")).toBe(
      "Missed meal-break wages include overtime",
    );
  });

  it("describes premium rate basis clearly", () => {
    expect(
      describeCompliancePremiumRateBasis("employee_compliance_regular_rate", 2675),
    ).toBe("Using saved compliance premium rate ($26.75/hr).");
    expect(
      describeCompliancePremiumRateBasis("configured_fixed_cents", null),
    ).toBe("Using configured fixed premium amount.");
  });
});
