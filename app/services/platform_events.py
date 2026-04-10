from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import AuditActorType
from app.models.coverage import AuditLog
from app.services import audit as audit_service

PLATFORM_EVENT_SCHEMA_VERSION = 1
PLATFORM_EVENT_PAYLOAD_KEY = "_platform_event"


class PlatformEventType:
    COVERAGE_CAMPAIGN_CREATED = "coverage.campaign.created"
    COVERAGE_PHASE_1_EXECUTED = "coverage.phase_1.executed"
    COVERAGE_PHASE_2_EXECUTED = "coverage.phase_2.executed"
    COVERAGE_DISPATCH_EXECUTED = "coverage.dispatch.executed"
    COVERAGE_OFFER_ACCEPTED = "coverage.offer.accepted"
    COVERAGE_OFFER_DECLINED = "coverage.offer.declined"
    COPILOT_SESSION_CREATED = "copilot.session.created"
    COPILOT_MESSAGE_RECORDED = "copilot.message.recorded"
    COPILOT_INTENT_RESOLVED = "copilot.intent.resolved"
    COPILOT_ACTION_EXECUTED = "copilot.action.executed"
    COPILOT_ACTION_FAILED = "copilot.action.failed"


def _normalize_metadata_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_metadata_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_normalize_metadata_value(item) for item in value]
    return value


def _platform_event_envelope(
    *,
    event_type: str,
    compatibility_event_name: str,
    target_type: str,
    target_id: UUID | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalized_metadata = {
        str(key): _normalize_metadata_value(value)
        for key, value in (metadata or {}).items()
    }
    trace_id = str(normalized_metadata.get("trace_id") or uuid4())
    normalized_metadata["trace_id"] = trace_id
    return {
        "schema_version": PLATFORM_EVENT_SCHEMA_VERSION,
        "event_type": event_type,
        "compatibility_event_name": compatibility_event_name,
        "target_type": target_type,
        "target_id": str(target_id) if target_id is not None else None,
        "metadata": normalized_metadata,
    }


async def append(
    session: AsyncSession,
    *,
    event_type: str,
    target_type: str,
    target_id: UUID | None = None,
    business_id: UUID | None = None,
    location_id: UUID | None = None,
    actor_type: AuditActorType = AuditActorType.system,
    actor_user_id: UUID | None = None,
    actor_membership_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    payload: Optional[dict] = None,
    metadata: Mapping[str, Any] | None = None,
    compatibility_event_name: str | None = None,
) -> AuditLog:
    event_name = compatibility_event_name or event_type
    event_payload = dict(payload or {})
    event_payload[PLATFORM_EVENT_PAYLOAD_KEY] = _platform_event_envelope(
        event_type=event_type,
        compatibility_event_name=event_name,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata,
    )
    return await audit_service.append(
        session,
        event_name=event_name,
        target_type=target_type,
        target_id=target_id,
        business_id=business_id,
        location_id=location_id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        actor_membership_id=actor_membership_id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload=event_payload,
    )
