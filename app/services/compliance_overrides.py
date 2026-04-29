from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import ComplianceOverrideArtifactStatus, ComplianceOverrideArtifactType
from app.models.compliance import ComplianceOverrideArtifact


def override_artifact_is_active(
    artifact: ComplianceOverrideArtifact,
    *,
    reference_time: datetime,
) -> bool:
    status = artifact.status.value if hasattr(artifact.status, "value") else str(artifact.status)
    if status != ComplianceOverrideArtifactStatus.approved.value:
        return False
    approved_at = artifact.approved_at or artifact.created_at or reference_time
    if approved_at > reference_time:
        return False
    if artifact.expires_at is not None and artifact.expires_at <= reference_time:
        return False
    if artifact.revoked_at is not None and artifact.revoked_at <= reference_time:
        return False
    return True


async def active_artifacts_for_shift_employees(
    session: AsyncSession,
    *,
    shift_id: UUID,
    employee_ids: Sequence[UUID],
    reference_time: datetime | None = None,
) -> dict[UUID, list[ComplianceOverrideArtifact]]:
    employee_id_list = [employee_id for employee_id in employee_ids if employee_id is not None]
    if not employee_id_list:
        return {}
    now = reference_time or datetime.now(timezone.utc)
    result = await session.execute(
        select(ComplianceOverrideArtifact).where(
            ComplianceOverrideArtifact.shift_id == shift_id,
            ComplianceOverrideArtifact.employee_id.in_(employee_id_list),
            ComplianceOverrideArtifact.status == ComplianceOverrideArtifactStatus.approved,
        )
    )
    mapping: dict[UUID, list[ComplianceOverrideArtifact]] = defaultdict(list)
    for artifact in result.scalars().all():
        if not override_artifact_is_active(artifact, reference_time=now):
            continue
        mapping[artifact.employee_id].append(artifact)
    for artifacts in mapping.values():
        artifacts.sort(
            key=lambda artifact: (
                artifact.approved_at or artifact.created_at or now,
                artifact.created_at or now,
            ),
            reverse=True,
        )
    return dict(mapping)


def overridable_block_rule_codes(evaluation: Mapping[str, object] | None) -> list[str]:
    codes: list[str] = []
    for result in (evaluation or {}).get("rule_results") or []:
        if not isinstance(result, Mapping):
            continue
        if str(result.get("status") or "").lower() != "block":
            continue
        if not bool(result.get("written_consent_allowed")):
            continue
        rule_code = str(result.get("rule_code") or "").strip()
        if rule_code:
            codes.append(rule_code)
    return sorted(set(codes))


def eligible_rule_results_for_artifact_type(
    evaluation: Mapping[str, object] | None,
    *,
    artifact_type: ComplianceOverrideArtifactType | str,
) -> dict[str, dict[str, object]]:
    desired_type = artifact_type.value if hasattr(artifact_type, "value") else str(artifact_type)
    eligible: dict[str, dict[str, object]] = {}
    for raw_result in (evaluation or {}).get("rule_results") or []:
        if not isinstance(raw_result, Mapping):
            continue
        rule_code = str(raw_result.get("rule_code") or "").strip()
        if not rule_code:
            continue
        allowed_type = _allowed_artifact_type_for_result(raw_result)
        if allowed_type != desired_type:
            continue
        eligible[rule_code] = dict(raw_result)
    return eligible


def evaluation_has_overridable_block(evaluation: Mapping[str, object] | None) -> bool:
    return bool(overridable_block_rule_codes(evaluation))


def matching_override_artifact(
    evaluation: Mapping[str, object] | None,
    artifacts: Sequence[ComplianceOverrideArtifact] | None,
    *,
    reference_time: datetime | None = None,
) -> ComplianceOverrideArtifact | None:
    now = reference_time or datetime.now(timezone.utc)
    for artifact in artifacts or ():
        artifact_type = (
            artifact.artifact_type.value
            if hasattr(artifact.artifact_type, "value")
            else str(artifact.artifact_type)
        )
        eligible_rule_results = eligible_rule_results_for_artifact_type(
            evaluation,
            artifact_type=artifact_type,
        )
        if artifact.rule_code not in eligible_rule_results:
            continue
        if not override_artifact_is_active(artifact, reference_time=now):
            continue
        return artifact
    return None


def apply_override_artifact(
    evaluation: Mapping[str, object] | None,
    artifact: ComplianceOverrideArtifact | None,
) -> dict[str, object]:
    payload = deepcopy(dict(evaluation or {}))
    if artifact is None:
        payload.setdefault("override_applied", False)
        payload.setdefault("override_artifact_id", None)
        return payload

    rule_results = []
    override_applied = False
    for raw_result in payload.get("rule_results") or []:
        result = dict(raw_result) if isinstance(raw_result, Mapping) else None
        if result is None:
            continue
        artifact_type = (
            artifact.artifact_type.value
            if hasattr(artifact.artifact_type, "value")
            else str(artifact.artifact_type)
        )
        if (
            str(result.get("rule_code") or "").strip() == artifact.rule_code
            and _allowed_artifact_type_for_result(result) == artifact_type
        ):
            reason_codes = list(result.get("reason_codes") or [])
            if "override_artifact_applied" not in reason_codes:
                reason_codes.append("override_artifact_applied")
            result = _apply_artifact_to_rule_result(result, artifact_type=artifact_type, reason_codes=reason_codes, artifact=artifact)
            override_applied = True
        rule_results.append(result)

    payload["rule_results"] = rule_results
    blocking_rule_codes = sorted(
        str(result.get("rule_code") or "").strip()
        for result in rule_results
        if str(result.get("status") or "").lower() == "block"
        and str(result.get("rule_code") or "").strip()
    )
    warning_rule_codes = sorted(
        str(result.get("rule_code") or "").strip()
        for result in rule_results
        if str(result.get("status") or "").lower() == "warning"
        and str(result.get("rule_code") or "").strip()
    )
    premium_rule_codes = sorted(
        str(result.get("rule_code") or "").strip()
        for result in rule_results
        if bool(result.get("premium_required"))
        and str(result.get("rule_code") or "").strip()
    )
    payload["blocking_rule_codes"] = blocking_rule_codes
    payload["warning_rule_codes"] = warning_rule_codes
    payload["premium_rule_codes"] = premium_rule_codes
    from app.services import compliance_engine

    premium_summary = compliance_engine._premium_liability_summary(rule_results)
    payload["premium_total_cents"] = premium_summary["premium_total_cents"]
    payload["premium_components"] = premium_summary["premium_components"]
    payload["unresolved_premium_rule_codes"] = premium_summary["unresolved_premium_rule_codes"]
    payload["would_block"] = bool(blocking_rule_codes)
    payload["requires_override"] = bool(blocking_rule_codes)
    payload["override_applied"] = override_applied
    payload["override_artifact_id"] = str(artifact.id) if override_applied else None
    if blocking_rule_codes:
        payload["status"] = "block"
    elif warning_rule_codes or premium_rule_codes:
        payload["status"] = "warning"
    else:
        payload["status"] = "clear"
    return payload


def _allowed_artifact_type_for_result(result: Mapping[str, object]) -> str | None:
    explicit = str(result.get("artifact_type_allowed") or "").strip()
    if explicit:
        return explicit
    if (
        str(result.get("status") or "").lower() == "block"
        and bool(result.get("written_consent_allowed"))
    ):
        return ComplianceOverrideArtifactType.written_consent.value
    return None


def _apply_artifact_to_rule_result(
    result: dict[str, object],
    *,
    artifact_type: str,
    reason_codes: list[str],
    artifact: ComplianceOverrideArtifact,
) -> dict[str, object]:
    updated = dict(result)
    common = {
        "reason_codes": reason_codes,
        "would_block": False,
        "override_artifact_id": str(artifact.id),
        "override_artifact_type": artifact_type,
    }
    if artifact_type == ComplianceOverrideArtifactType.meal_waiver.value:
        updated.update(
            {
                **common,
                "status": "clear",
                "premium_required": False,
                "premium_type": None,
                "premium_cents": 0,
            }
        )
        return updated
    updated.update(
        {
            **common,
            "status": "warning",
        }
    )
    return updated
