from __future__ import annotations

from app.services import compliance_source_references


def test_rule_source_references_from_evaluation_maps_policy_and_permit_rules():
    evaluation = {
        "blocking_rule_codes": [
            "customer_policy_unresolved_premium",
            "minor_work_permit_time_window",
        ],
        "warning_rule_codes": [],
        "premium_rule_codes": ["meal_break_first_window"],
        "unresolved_premium_rule_codes": [],
        "profile_code": "ca_restaurant_v1",
        "profile_display_name": "California restaurant baseline",
        "profile_version_id": "profile-version-1",
        "profile_payload_hash": "sha256:profile",
        "profile_source_version": "ca_rule_pack_v3",
        "profile_source_hash": "sha256:ca-pack",
        "profile_source_urls": ["https://example.com/ca-rule-pack"],
        "jurisdiction_code": "US-CA",
        "policy_version_id": "policy-version-1",
        "policy_hash": "policy-hash-1",
        "policy_effective_at": "2026-04-29T00:00:00Z",
        "policy_scope": "location",
        "work_permit_template_code": "ca_16_17_school_required_v1",
        "work_permit_template_label": "California ages 16-17 while school required",
        "work_permit_jurisdiction_code": "US-CA",
        "work_permit_source_document_title": "California Department of Industrial Relations minors summary charts",
        "work_permit_source_urls": ["https://www.dir.ca.gov/dlse/MinorsSummaryCharts.pdf"],
        "work_permit_source_version": "dir_minors_summary_charts_v1",
        "work_permit_source_hash": None,
        "work_permit_payload_hash": "sha256:permit",
    }

    references = compliance_source_references.rule_source_references_from_evaluation(
        evaluation
    )
    references_by_rule = {
        reference["rule_code"]: reference
        for reference in references
    }

    assert references_by_rule["customer_policy_unresolved_premium"]["source_kind"] == "policy_overlay"
    assert references_by_rule["customer_policy_unresolved_premium"]["payload_hash"] == "policy-hash-1"
    assert references_by_rule["minor_work_permit_time_window"]["source_kind"] == "work_permit_template"
    assert references_by_rule["minor_work_permit_time_window"]["source_code"] == "ca_16_17_school_required_v1"
    assert references_by_rule["meal_break_first_window"]["source_kind"] == "labor_rule_profile"
    assert references_by_rule["meal_break_first_window"]["source_code"] == "ca_restaurant_v1"
