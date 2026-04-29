from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.common import ComplianceOverrideArtifactStatus, ComplianceOverrideArtifactType
from app.models.compliance import ComplianceOverrideArtifact
from app.services import compliance_overrides


def _evaluation(*, status: str = "block", written_consent_allowed: bool = True) -> dict[str, object]:
    return {
        "status": status,
        "blocking_rule_codes": ["clopening_restricted"] if status == "block" else [],
        "warning_rule_codes": [],
        "premium_rule_codes": ["clopening_restricted"],
        "would_block": status == "block",
        "requires_override": status == "block",
        "rule_results": [
            {
                "rule_code": "clopening_restricted",
                "status": status,
                "reason_codes": ["minimum_rest_window_violation"],
                "premium_required": True,
                "would_block": status == "block",
                "written_consent_allowed": written_consent_allowed,
            }
        ],
    }


def _meal_waiver_evaluation() -> dict[str, object]:
    return {
        "status": "warning",
        "blocking_rule_codes": [],
        "warning_rule_codes": ["meal_break_first_window"],
        "premium_rule_codes": ["meal_break_first_window"],
        "premium_total_cents": 0,
        "premium_components": [
            {
                "rule_code": "meal_break_first_window",
                "premium_type": "wage_dependent_unresolved",
                "premium_cents": 0,
                "status": "warning",
                "reason_codes": ["first_meal_break_missing", "waiver_possible_but_not_modelled"],
            }
        ],
        "unresolved_premium_rule_codes": ["meal_break_first_window"],
        "would_block": False,
        "requires_override": False,
        "rule_results": [
            {
                "rule_code": "meal_break_first_window",
                "status": "warning",
                "reason_codes": ["first_meal_break_missing", "waiver_possible_but_not_modelled"],
                "premium_required": True,
                "premium_type": "wage_dependent_unresolved",
                "premium_cents": 0,
                "would_block": False,
                "waiver_possible": True,
                "artifact_type_allowed": "meal_waiver",
            }
        ],
    }


def _artifact(
    *,
    rule_code: str = "clopening_restricted",
    artifact_type: ComplianceOverrideArtifactType = ComplianceOverrideArtifactType.written_consent,
) -> ComplianceOverrideArtifact:
    now = datetime.now(timezone.utc)
    return ComplianceOverrideArtifact(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        shift_id=uuid4(),
        employee_id=uuid4(),
        rule_code=rule_code,
        artifact_type=artifact_type,
        status=ComplianceOverrideArtifactStatus.approved,
        engine_version="deterministic_compliance_engine_v1",
        approved_at=now,
        expires_at=now + timedelta(hours=8),
        note="Employee provided written consent.",
        reason_codes=["minimum_rest_window_violation"],
        artifact_payload={},
        created_at=now,
        updated_at=now,
    )


def test_matching_override_artifact_requires_overridable_rule_code():
    evaluation = _evaluation()
    artifact = _artifact()

    matched = compliance_overrides.matching_override_artifact(evaluation, [artifact])

    assert matched is artifact
    unmatched = compliance_overrides.matching_override_artifact(
        _evaluation(written_consent_allowed=False),
        [artifact],
    )
    assert unmatched is None


def test_apply_override_artifact_downgrades_block_to_warning():
    evaluation = _evaluation()
    artifact = _artifact()

    result = compliance_overrides.apply_override_artifact(evaluation, artifact)

    assert result["status"] == "warning"
    assert result["would_block"] is False
    assert result["requires_override"] is False
    assert result["blocking_rule_codes"] == []
    assert result["warning_rule_codes"] == ["clopening_restricted"]
    assert result["override_applied"] is True
    assert result["override_artifact_id"] == str(artifact.id)
    assert result["rule_results"][0]["reason_codes"][-1] == "override_artifact_applied"


def test_matching_override_artifact_supports_meal_waiver_artifacts():
    evaluation = _meal_waiver_evaluation()
    artifact = _artifact(
        rule_code="meal_break_first_window",
        artifact_type=ComplianceOverrideArtifactType.meal_waiver,
    )

    matched = compliance_overrides.matching_override_artifact(evaluation, [artifact])

    assert matched is artifact


def test_apply_override_artifact_clears_meal_waiver_warning_and_premium():
    evaluation = _meal_waiver_evaluation()
    artifact = _artifact(
        rule_code="meal_break_first_window",
        artifact_type=ComplianceOverrideArtifactType.meal_waiver,
    )

    result = compliance_overrides.apply_override_artifact(evaluation, artifact)

    assert result["status"] == "clear"
    assert result["warning_rule_codes"] == []
    assert result["premium_rule_codes"] == []
    assert result["premium_total_cents"] == 0
    assert result["unresolved_premium_rule_codes"] == []
    assert result["override_applied"] is True
    assert result["override_artifact_id"] == str(artifact.id)
