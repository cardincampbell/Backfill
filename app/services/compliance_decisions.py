from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import AuditActorType
from app.models.compliance import ComplianceOverrideArtifact
from app.models.scheduling import Shift, ShiftAssignment
from app.schemas.compliance import ShiftComplianceDecisionRead
from app.models.workforce import Employee
from app.services import feed_projections, platform_events


def build_compliance_decision_payload(
    *,
    shift: Shift,
    employee: Employee,
    evaluation: Mapping[str, object] | None,
    decision_source: str,
    decision_outcome: str,
    assignment: ShiftAssignment | None = None,
    coverage_case_id: UUID | None = None,
    override_artifact: ComplianceOverrideArtifact | None = None,
) -> dict[str, object]:
    payload = dict(evaluation or {})
    return {
        "decision_source": decision_source,
        "decision_outcome": decision_outcome,
        "shift_id": str(shift.id),
        "employee_id": str(employee.id),
        "assignment_id": str(assignment.id) if assignment is not None else None,
        "coverage_case_id": str(coverage_case_id) if coverage_case_id is not None else None,
        "engine_version": str(payload.get("evaluation_source") or ""),
        "profile_code": payload.get("profile_code"),
        "profile_version_id": payload.get("profile_version_id"),
        "profile_payload_hash": payload.get("profile_payload_hash"),
        "policy_version_id": payload.get("policy_version_id"),
        "policy_hash": payload.get("policy_hash"),
        "policy_effective_at": payload.get("policy_effective_at"),
        "policy_scope": payload.get("policy_scope"),
        "blocking_rule_codes": list(payload.get("blocking_rule_codes") or []),
        "warning_rule_codes": list(payload.get("warning_rule_codes") or []),
        "premium_rule_codes": list(payload.get("premium_rule_codes") or []),
        "premium_total_cents": int(payload.get("premium_total_cents") or 0),
        "premium_components": list(payload.get("premium_components") or []),
        "unresolved_premium_rule_codes": list(payload.get("unresolved_premium_rule_codes") or []),
        "override_applied": bool(payload.get("override_applied")),
        "override_artifact_id": str(override_artifact.id) if override_artifact is not None else None,
        "evaluation": payload,
    }


async def record_shift_compliance_decision(
    session: AsyncSession,
    *,
    business_id: UUID,
    shift: Shift,
    employee: Employee,
    evaluation: Mapping[str, object] | None,
    decision_source: str,
    decision_outcome: str,
    assignment: ShiftAssignment | None = None,
    coverage_case_id: UUID | None = None,
    override_artifact: ComplianceOverrideArtifact | None = None,
    actor_type: AuditActorType = AuditActorType.system,
    actor_user_id: UUID | None = None,
) -> None:
    payload = build_compliance_decision_payload(
        shift=shift,
        employee=employee,
        evaluation=evaluation,
        decision_source=decision_source,
        decision_outcome=decision_outcome,
        assignment=assignment,
        coverage_case_id=coverage_case_id,
        override_artifact=override_artifact,
    )
    await platform_events.append(
        session,
        event_type=platform_events.PlatformEventType.COMPLIANCE_DECISION_RECORDED,
        target_type="shift",
        target_id=shift.id,
        business_id=business_id,
        location_id=shift.location_id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        payload=payload,
        metadata={
            "decision_source": decision_source,
            "decision_outcome": decision_outcome,
            "employee_id": str(employee.id),
            "assignment_id": str(assignment.id) if assignment is not None else None,
            "coverage_case_id": str(coverage_case_id) if coverage_case_id is not None else None,
            "override_artifact_id": str(override_artifact.id) if override_artifact is not None else None,
        },
    )


def _shift_compliance_decision_read_from_event(event) -> ShiftComplianceDecisionRead:
    payload = dict(event.payload or {})
    return ShiftComplianceDecisionRead.model_validate(
        {
            "id": event.id,
            "occurred_at": event.occurred_at,
            "actor_type": event.actor_type,
            "actor_user_id": event.actor_user_id,
            "actor_membership_id": event.actor_membership_id,
            "trace_id": event.trace_id,
            "shift_id": payload.get("shift_id") or event.entity_id,
            "employee_id": payload.get("employee_id"),
            "assignment_id": payload.get("assignment_id"),
            "coverage_case_id": payload.get("coverage_case_id"),
            "decision_source": payload.get("decision_source") or "",
            "decision_outcome": payload.get("decision_outcome") or "",
            "engine_version": payload.get("engine_version") or "",
            "profile_code": payload.get("profile_code"),
            "profile_version_id": payload.get("profile_version_id"),
            "profile_payload_hash": payload.get("profile_payload_hash"),
            "policy_version_id": payload.get("policy_version_id"),
            "policy_hash": payload.get("policy_hash"),
            "policy_effective_at": payload.get("policy_effective_at"),
            "policy_scope": payload.get("policy_scope"),
            "blocking_rule_codes": list(payload.get("blocking_rule_codes") or []),
            "warning_rule_codes": list(payload.get("warning_rule_codes") or []),
            "premium_rule_codes": list(payload.get("premium_rule_codes") or []),
            "premium_total_cents": int(payload.get("premium_total_cents") or 0),
            "premium_components": list(payload.get("premium_components") or []),
            "unresolved_premium_rule_codes": list(payload.get("unresolved_premium_rule_codes") or []),
            "override_applied": bool(payload.get("override_applied")),
            "override_artifact_id": payload.get("override_artifact_id"),
            "evaluation": dict(payload.get("evaluation") or {}),
        }
    )


async def list_shift_compliance_decisions(
    session: AsyncSession,
    *,
    business_id: UUID,
    shift_id: UUID,
    limit: int = 25,
) -> list[ShiftComplianceDecisionRead]:
    events = await feed_projections.list_feed_events(
        session,
        business_id=business_id,
        entity_type="shift",
        entity_id=shift_id,
        event_type=platform_events.PlatformEventType.COMPLIANCE_DECISION_RECORDED,
        limit=limit,
    )
    decisions: list[ShiftComplianceDecisionRead] = []
    for event in events:
        payload = dict(event.payload or {})
        if str(payload.get("shift_id") or event.entity_id or "") != str(shift_id):
            continue
        decisions.append(_shift_compliance_decision_read_from_event(event))
    return decisions
