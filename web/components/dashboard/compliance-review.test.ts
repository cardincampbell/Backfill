import { describe, expect, it } from "vitest";

import {
  dedupeComplianceSourceReferences,
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
});
