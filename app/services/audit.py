from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import AuditActorType
from app.models.coverage import AuditLog


def request_client_ip(request: Request) -> Optional[str]:
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or None
    if request.client is not None:
        return request.client.host
    return None


def request_user_agent(request: Request) -> Optional[str]:
    value = (request.headers.get("user-agent") or "").strip()
    return value or None


async def append(
    session: AsyncSession,
    *,
    event_name: str,
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
) -> AuditLog:
    entry = AuditLog(
        business_id=business_id,
        location_id=location_id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        actor_membership_id=actor_membership_id,
        event_name=event_name,
        target_type=target_type,
        target_id=target_id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload=payload or {},
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(entry)
    from app.services import webhooks

    await webhooks.enqueue_audit_event(session, entry)
    return entry


async def list_logs(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None = None,
    limit: int = 50,
) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.business_id == business_id)
        .order_by(AuditLog.occurred_at.desc())
        .limit(max(1, min(limit, 250)))
    )
    if location_id is not None:
        stmt = stmt.where(AuditLog.location_id == location_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())
