from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app_v2.api.deps import SessionDep
from app_v2.config import v2_settings
from app_v2.models.common import SchedulerProvider
from app_v2.models.integrations import SchedulerConnection
from app_v2.services import rate_limit, scheduler_sync
from app_v2.services.scheduler_adapters import webhook_secret_for_connection

router = APIRouter(prefix="/providers/schedulers", tags=["v2-scheduler-providers"])


def _event_type(payload: dict[str, Any]) -> str:
    return str(payload.get("type") or payload.get("event") or payload.get("topic") or payload.get("resource") or "").strip()


def _is_vacancy_event(provider: SchedulerProvider, payload: dict[str, Any]) -> bool:
    event_type = _event_type(payload).lower()
    if provider == SchedulerProvider.seven_shifts:
        return event_type in {"shift.deleted", "shift.unassigned", "punch.callout"}
    if provider == SchedulerProvider.deputy:
        status_value = str(
            payload.get("status")
            or (payload.get("data") or {}).get("status")
            or (payload.get("data") or {}).get("state")
            or ""
        ).strip().lower()
        return event_type in {"roster.delete", "roster.deleted"} or status_value in {"deleted", "cancelled", "unassigned", "open"}
    if provider == SchedulerProvider.when_i_work:
        return event_type in {"shift.deleted", "shift.unassigned", "open_shift.created", "punch.callout"}
    return False


def _signature_header(provider: SchedulerProvider, request: Request) -> str:
    if provider == SchedulerProvider.seven_shifts:
        return request.headers.get("X-7shifts-Signature", "") or request.headers.get("X-SevenShifts-Signature", "")
    if provider == SchedulerProvider.deputy:
        return request.headers.get("X-Deputy-Signature", "")
    if provider == SchedulerProvider.when_i_work:
        return request.headers.get("X-WhenIWork-Signature", "")
    return ""


async def _handle_webhook(
    provider: SchedulerProvider,
    request: Request,
    session: SessionDep,
    *,
    connection_id: UUID | None = None,
):
    client_ip = request.client.host if request.client is not None else "unknown"
    rate_limit.assert_within_limit(
        "scheduler_webhook",
        client_ip,
        limit=v2_settings.scheduler_webhook_limit_per_minute,
        window_seconds=60,
        detail="Too many scheduler webhook requests.",
    )
    raw_body = await request.body()
    body = await request.json()
    connection = await scheduler_sync.resolve_connection(
        session,
        provider=provider,
        connection_id=connection_id,
        payload=body,
    )
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scheduler_connection_not_found")

    secret = webhook_secret_for_connection(connection, provider)
    if not scheduler_sync.valid_scheduler_signature(secret, raw_body, _signature_header(provider, request)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid_webhook_signature")

    if _is_vacancy_event(provider, body):
        try:
            return await scheduler_sync.handle_vacancy_event(
                session,
                provider=provider,
                payload=body,
                connection_id=connection.id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    event, job = await scheduler_sync.enqueue_event_reconcile(
        session,
        connection=connection,
        payload=body,
        event_type=_event_type(body) or None,
        event_scope="schedule",
        scope_ref=str(connection.location_id),
        source_event_id=f"{provider.value}:{_event_type(body)}:{body.get('id') or body.get('event_id')}" if body.get("id") or body.get("event_id") else None,
    )
    await session.commit()
    processed = await scheduler_sync.process_sync_job(session, job.id)
    return {
        "connection_id": str(connection.id),
        "event_id": str(event.id),
        "job_id": str(job.id),
        "processed": processed,
    }


@router.post("/seven_shifts")
async def seven_shifts_webhook(request: Request, session: SessionDep):
    return await _handle_webhook(SchedulerProvider.seven_shifts, request, session)


@router.post("/deputy")
async def deputy_webhook(request: Request, session: SessionDep):
    return await _handle_webhook(SchedulerProvider.deputy, request, session)


@router.post("/wheniwork")
async def when_i_work_webhook(request: Request, session: SessionDep):
    return await _handle_webhook(SchedulerProvider.when_i_work, request, session)


@router.post("/webhook/{connection_id}")
async def scheduler_connection_webhook(connection_id: UUID, request: Request, session: SessionDep):
    body = await request.json()
    provider_value = str(body.get("provider") or body.get("platform") or "").strip().lower()
    try:
        provider = SchedulerProvider(provider_value)
    except ValueError:
        connection = await session.get(SchedulerConnection, connection_id)
        provider = SchedulerProvider(connection.provider) if connection is not None else SchedulerProvider.backfill_native
    return await _handle_webhook(provider, request, session, connection_id=connection_id)
