from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.business import Location, Role
from app.models.common import (
    AssignmentStatus,
    CoverageCaseStatus,
    SchedulerConnectionStatus,
    SchedulerProvider,
    SchedulerSyncEventStatus,
    SchedulerSyncJobStatus,
    SchedulerSyncRunStatus,
    ShiftStatus,
)
from app.models.coverage import CoverageCase
from app.models.integrations import (
    SchedulerConnection,
    SchedulerEvent,
    SchedulerSyncJob,
    SchedulerSyncRun,
)
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee, EmployeeLocationClearance, EmployeeRole
from app.schemas.coverage import CoverageCaseCreate, CoverageExecutionDispatchRequest
from app.schemas.integrations import (
    SchedulerConnectionRead,
    SchedulerConnectionUpsert,
    SchedulerSyncJobRead,
)
from app.services import coverage as coverage_service
from app.services import businesses
from app.services import scheduling as scheduling_service
from app.services.scheduler_adapters import (
    ExternalEmployeeRecord,
    ExternalShiftRecord,
    adapter_for_connection,
    build_connection_secret_hint,
)
from app.services.utils import role_code_from_name
ROLLING_RECONCILE_INTERVAL = timedelta(minutes=30)


def _nested(data: dict[str, Any], *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_present(data: dict[str, Any], paths: list[tuple[str, ...]]) -> Any:
    for path in paths:
        value = _nested(data, *path)
        if value not in (None, ""):
            return value
    return None


def _normalize_signature(signature: str) -> str:
    normalized = signature.strip()
    if normalized.lower().startswith("sha256="):
        normalized = normalized.split("=", 1)[1]
    return normalized


def valid_scheduler_signature(secret: str, payload: bytes, signature: str) -> bool:
    if not secret:
        return True
    if not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    candidates = {
        digest.hex(),
        base64.b64encode(digest).decode("utf-8"),
    }
    normalized = _normalize_signature(signature)
    return any(hmac.compare_digest(normalized, candidate) for candidate in candidates)


def _job_priority(job_type: str) -> int:
    return {
        "event_reconcile": 10,
        "writeback": 20,
        "repair_reconcile": 30,
        "rolling_reconcile": 40,
        "daily_reconcile": 50,
        "connect_bootstrap": 60,
    }.get(job_type, 50)


def _window_for_job(job_type: str, *, reference: datetime | None = None) -> tuple[datetime, datetime]:
    current = reference or datetime.now(timezone.utc)
    if job_type == "rolling_reconcile":
        return current - timedelta(days=1), current + timedelta(days=2)
    if job_type in {"daily_reconcile", "connect_bootstrap", "repair_reconcile", "event_reconcile"}:
        return current - timedelta(days=1), current + timedelta(days=14)
    return current - timedelta(days=1), current + timedelta(days=2)


def _retry_delay(job_type: str, attempt_number: int) -> timedelta | None:
    if attempt_number >= 3:
        return None
    if job_type == "writeback":
        return timedelta(minutes=5 * attempt_number)
    if job_type == "event_reconcile":
        return timedelta(minutes=2 * attempt_number)
    return timedelta(minutes=10 * attempt_number)


def _provider_display_value(provider: SchedulerProvider | str) -> str:
    return provider.value if isinstance(provider, SchedulerProvider) else str(provider)


def _connection_has_credentials(connection: SchedulerConnection) -> bool:
    return any(bool(str(value).strip()) for value in (connection.credentials or {}).values())


def _webhook_path(connection_id: UUID | None) -> str | None:
    if connection_id is None:
        return None
    return f"/api/providers/schedulers/webhook/{connection_id}"


def build_connection_read(connection: SchedulerConnection) -> SchedulerConnectionRead:
    return SchedulerConnectionRead(
        id=connection.id,
        business_id=connection.business_id,
        location_id=connection.location_id,
        provider=_provider_display_value(connection.provider),
        provider_location_ref=connection.provider_location_ref,
        install_url=connection.install_url,
        status=connection.status,
        writeback_enabled=connection.writeback_enabled,
        has_credentials=_connection_has_credentials(connection),
        secret_hint=connection.secret_hint,
        connection_metadata=connection.connection_metadata or {},
        last_roster_sync_at=connection.last_roster_sync_at,
        last_roster_sync_status=connection.last_roster_sync_status,
        last_schedule_sync_at=connection.last_schedule_sync_at,
        last_schedule_sync_status=connection.last_schedule_sync_status,
        last_event_sync_at=connection.last_event_sync_at,
        last_rolling_sync_at=connection.last_rolling_sync_at,
        last_daily_sync_at=connection.last_daily_sync_at,
        last_writeback_at=connection.last_writeback_at,
        last_sync_error=connection.last_sync_error,
        webhook_path=_webhook_path(connection.id),
    )


def build_job_read(job: SchedulerSyncJob) -> SchedulerSyncJobRead:
    return SchedulerSyncJobRead(
        id=job.id,
        connection_id=job.connection_id,
        provider=_provider_display_value(job.provider),
        job_type=job.job_type,
        scope=job.scope,
        scope_ref=job.scope_ref,
        status=job.status,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        next_run_at=job.next_run_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        last_error=job.last_error,
    )


async def _sync_location_settings(location: Location, connection: SchedulerConnection) -> None:
    settings = dict(location.settings or {})
    settings.update(
        {
            "scheduling_platform": _provider_display_value(connection.provider),
            "writeback_enabled": connection.writeback_enabled,
            "integration_status": connection.status,
        }
    )
    location.settings = settings


async def get_connection(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
) -> SchedulerConnection | None:
    return await session.scalar(
        select(SchedulerConnection).where(
            SchedulerConnection.business_id == business_id,
            SchedulerConnection.location_id == location_id,
        )
    )


async def upsert_connection(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    payload: SchedulerConnectionUpsert,
) -> SchedulerConnection:
    location = await session.get(Location, location_id)
    if location is None or location.business_id != business_id:
        raise LookupError("location_not_found")

    connection = await get_connection(session, business_id=business_id, location_id=location_id)
    provider = SchedulerProvider(payload.provider)
    secret_hint = build_connection_secret_hint(payload.webhook_secret)
    status = SchedulerConnectionStatus.active if provider == SchedulerProvider.backfill_native else SchedulerConnectionStatus.pending
    if connection is None:
        connection = SchedulerConnection(
            business_id=business_id,
            location_id=location_id,
            provider=provider,
            provider_location_ref=payload.provider_location_ref,
            install_url=payload.install_url,
            status=status,
            writeback_enabled=payload.writeback_enabled,
            credentials=payload.credentials,
            webhook_secret=payload.webhook_secret,
            secret_hint=secret_hint,
            connection_metadata=payload.connection_metadata,
        )
        session.add(connection)
    else:
        connection.provider = provider
        connection.provider_location_ref = payload.provider_location_ref
        connection.install_url = payload.install_url
        connection.writeback_enabled = payload.writeback_enabled
        connection.credentials = payload.credentials
        connection.webhook_secret = payload.webhook_secret
        connection.secret_hint = secret_hint
        connection.connection_metadata = payload.connection_metadata
        connection.status = status
        connection.last_sync_error = None

    await session.flush()
    await _sync_location_settings(location, connection)
    await session.flush()
    return connection


async def list_jobs(
    session: AsyncSession,
    *,
    connection_id: UUID,
    limit: int = 20,
) -> list[SchedulerSyncJob]:
    result = await session.execute(
        select(SchedulerSyncJob)
        .where(SchedulerSyncJob.connection_id == connection_id)
        .order_by(SchedulerSyncJob.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def enqueue_sync_job(
    session: AsyncSession,
    *,
    connection: SchedulerConnection,
    job_type: str,
    scheduler_event: SchedulerEvent | None = None,
    scope: str | None = None,
    scope_ref: str | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    next_run_at: datetime | None = None,
    max_attempts: int = 3,
    idempotency_key: str | None = None,
) -> SchedulerSyncJob:
    if idempotency_key:
        existing = await session.scalar(
            select(SchedulerSyncJob).where(SchedulerSyncJob.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing
    start_value, end_value = window_start, window_end
    if start_value is None and end_value is None:
        start_value, end_value = _window_for_job(job_type)
    job = SchedulerSyncJob(
        connection_id=connection.id,
        scheduler_event_id=scheduler_event.id if scheduler_event is not None else None,
        business_id=connection.business_id,
        location_id=connection.location_id,
        provider=connection.provider,
        job_type=job_type,
        priority=_job_priority(job_type),
        scope=scope,
        scope_ref=scope_ref,
        window_start=start_value,
        window_end=end_value,
        status=SchedulerSyncJobStatus.queued,
        next_run_at=next_run_at or datetime.now(timezone.utc),
        max_attempts=max_attempts,
        idempotency_key=idempotency_key,
    )
    session.add(job)
    await session.flush()
    return job


async def enqueue_event_reconcile(
    session: AsyncSession,
    *,
    connection: SchedulerConnection,
    payload: dict,
    event_type: str | None,
    event_scope: str | None,
    scope_ref: str | None,
    source_event_id: str | None,
) -> tuple[SchedulerEvent, SchedulerSyncJob]:
    event = None
    if source_event_id:
        event = await session.scalar(
            select(SchedulerEvent).where(
                SchedulerEvent.provider == connection.provider,
                SchedulerEvent.source_event_id == source_event_id,
            )
        )
    if event is None:
        event = SchedulerEvent(
            connection_id=connection.id,
            business_id=connection.business_id,
            location_id=connection.location_id,
            provider=connection.provider,
            source_event_id=source_event_id,
            event_type=event_type,
            event_scope=event_scope,
            payload=payload,
            received_at=datetime.now(timezone.utc),
            status=SchedulerSyncEventStatus.queued,
        )
        session.add(event)
        await session.flush()
    job = await enqueue_sync_job(
        session,
        connection=connection,
        scheduler_event=event,
        job_type="event_reconcile",
        scope=event_scope,
        scope_ref=scope_ref,
        idempotency_key=f"{_provider_display_value(connection.provider)}:event:{source_event_id}" if source_event_id else None,
    )
    return event, job


async def enqueue_writeback(session: AsyncSession, *, shift_id: UUID) -> SchedulerSyncJob | None:
    shift = await session.get(Shift, shift_id)
    if shift is None:
        raise LookupError("shift_not_found")
    if shift.source_system == SchedulerProvider.backfill_native.value:
        return None
    connection = await get_connection(session, business_id=shift.business_id, location_id=shift.location_id)
    if connection is None or not connection.writeback_enabled:
        return None
    return await enqueue_sync_job(
        session,
        connection=connection,
        job_type="writeback",
        scope="shift",
        scope_ref=str(shift.id),
        next_run_at=datetime.now(timezone.utc),
        idempotency_key=f"writeback:{shift.id}",
    )


async def trigger_initial_sync(session: AsyncSession, connection: SchedulerConnection) -> tuple[SchedulerSyncJob, SchedulerSyncJob]:
    roster_job = await enqueue_sync_job(
        session,
        connection=connection,
        job_type="connect_bootstrap",
        scope="location",
        scope_ref=str(connection.location_id),
        idempotency_key=f"bootstrap:roster:{connection.id}",
    )
    schedule_job = await enqueue_sync_job(
        session,
        connection=connection,
        job_type="daily_reconcile",
        scope="location",
        scope_ref=str(connection.location_id),
        idempotency_key=f"bootstrap:schedule:{connection.id}",
    )
    return roster_job, schedule_job


async def _get_or_create_role(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    role_name: str,
    cache: dict[str, Role],
) -> Role:
    code = role_code_from_name(role_name)
    cached = cache.get(code)
    if cached is not None:
        return cached
    role = await businesses.ensure_business_role(
        session,
        business_id=business_id,
        role_name=role_name,
        source="scheduler_sync",
        source_metadata={"role_name": role_name},
    )
    await businesses.ensure_location_role(
        session,
        business_id=business_id,
        location_id=location_id,
        role_id=role.id,
        source="scheduler_sync",
    )
    cache[code] = role
    return role


async def _get_or_create_employee(
    session: AsyncSession,
    *,
    connection: SchedulerConnection,
    record: ExternalEmployeeRecord,
) -> tuple[Employee, bool]:
    employee = await session.scalar(
        select(Employee).where(
            Employee.business_id == connection.business_id,
            Employee.external_ref == record.external_ref,
        )
    )
    created = False
    if employee is None and record.phone_e164:
        employee = await session.scalar(
            select(Employee).where(
                Employee.business_id == connection.business_id,
                Employee.phone_e164 == record.phone_e164,
            )
        )
    if employee is None and record.email:
        employee = await session.scalar(
            select(Employee).where(
                Employee.business_id == connection.business_id,
                func.lower(Employee.email) == record.email.lower(),
            )
        )
    if employee is None:
        employee = Employee(
            business_id=connection.business_id,
            home_location_id=connection.location_id,
            external_ref=record.external_ref,
            full_name=record.full_name,
            phone_e164=record.phone_e164,
            email=record.email,
            employee_metadata={"source": "scheduler_sync", **record.metadata},
        )
        session.add(employee)
        await session.flush()
        created = True
    else:
        employee.external_ref = employee.external_ref or record.external_ref
        employee.full_name = record.full_name or employee.full_name
        employee.phone_e164 = record.phone_e164 or employee.phone_e164
        employee.email = record.email or employee.email
        employee.employee_metadata = {
            **(employee.employee_metadata or {}),
            "source": "scheduler_sync",
            **record.metadata,
        }
        if employee.home_location_id is None:
            employee.home_location_id = connection.location_id
        await session.flush()
    return employee, created


async def _sync_employee_roles_and_clearance(
    session: AsyncSession,
    *,
    connection: SchedulerConnection,
    employee: Employee,
    role_names: list[str],
    role_cache: dict[str, Role],
) -> None:
    for role_name in role_names:
        role = await _get_or_create_role(
            session,
            business_id=connection.business_id,
            location_id=connection.location_id,
            role_name=role_name,
            cache=role_cache,
        )
        employee_role = await session.scalar(
            select(EmployeeRole).where(
                EmployeeRole.employee_id == employee.id,
                EmployeeRole.role_id == role.id,
            )
        )
        if employee_role is None:
            session.add(
                EmployeeRole(
                    employee_id=employee.id,
                    role_id=role.id,
                    proficiency_level=1,
                    is_primary=False,
                    role_metadata={"source": "scheduler_sync"},
                )
            )
            await session.flush()

    clearance = await session.scalar(
        select(EmployeeLocationClearance).where(
            EmployeeLocationClearance.employee_id == employee.id,
            EmployeeLocationClearance.location_id == connection.location_id,
        )
    )
    if clearance is None:
        session.add(
            EmployeeLocationClearance(
                employee_id=employee.id,
                location_id=connection.location_id,
                access_level="approved",
                clearance_source="scheduler_sync",
                can_cover_last_minute=True,
                can_blast=True,
                clearance_metadata={},
            )
        )
        await session.flush()


async def sync_connection_roster(
    session: AsyncSession,
    connection: SchedulerConnection,
) -> dict[str, int]:
    location = await session.get(Location, connection.location_id)
    if location is not None:
        connection.location = location
    adapter = adapter_for_connection(connection)
    roster = await adapter.sync_roster(connection)

    created = 0
    updated = 0
    role_cache: dict[str, Role] = {}
    for record in roster:
        employee, was_created = await _get_or_create_employee(
            session,
            connection=connection,
            record=record,
        )
        if was_created:
            created += 1
        else:
            updated += 1
        await _sync_employee_roles_and_clearance(
            session,
            connection=connection,
            employee=employee,
            role_names=record.role_names or ["team_member"],
            role_cache=role_cache,
        )

    connection.status = SchedulerConnectionStatus.active
    connection.last_roster_sync_at = datetime.now(timezone.utc)
    connection.last_roster_sync_status = "completed"
    connection.last_sync_error = None
    if location is not None:
        await _sync_location_settings(location, connection)
    await session.flush()
    return {"created": created, "updated": updated, "skipped": 0}


async def _active_scheduler_assignments(session: AsyncSession, shift_id: UUID) -> list[ShiftAssignment]:
    result = await session.execute(
        select(ShiftAssignment).where(
            ShiftAssignment.shift_id == shift_id,
            ShiftAssignment.assigned_via == "scheduler_sync",
            ShiftAssignment.status.in_([AssignmentStatus.assigned, AssignmentStatus.accepted]),
        )
    )
    return list(result.scalars().all())


def _normalized_shift_status(status: str, seats_filled: int, seats_requested: int) -> ShiftStatus:
    normalized = status.strip().lower()
    if normalized in {"cancelled", "deleted"}:
        return ShiftStatus.cancelled
    if normalized in {"open", "vacant", "unassigned", "open_shift"} or seats_filled == 0:
        return ShiftStatus.open
    if seats_filled < max(1, seats_requested):
        return ShiftStatus.filling
    return ShiftStatus.scheduled


async def sync_connection_schedule(
    session: AsyncSession,
    connection: SchedulerConnection,
    *,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, int]:
    location = await session.get(Location, connection.location_id)
    if location is not None:
        connection.location = location
    adapter = adapter_for_connection(connection)
    records = await adapter.sync_schedule(connection, window_start=window_start, window_end=window_end)

    created = 0
    updated = 0
    skipped = 0
    role_cache: dict[str, Role] = {}

    for record in records:
        role = await _get_or_create_role(
            session,
            business_id=connection.business_id,
            location_id=connection.location_id,
            role_name=record.role_name,
            cache=role_cache,
        )
        shift = await session.scalar(
            select(Shift).where(
                Shift.source_system == _provider_display_value(connection.provider),
                Shift.source_shift_id == record.external_ref,
            )
        )
        is_created = False
        if shift is None:
            shift = Shift(
                business_id=connection.business_id,
                location_id=connection.location_id,
                role_id=role.id,
                source_system=_provider_display_value(connection.provider),
                source_shift_id=record.external_ref,
                timezone=record.timezone or (location.timezone if location else "America/Los_Angeles"),
                starts_at=record.starts_at,
                ends_at=record.ends_at,
                seats_requested=max(1, record.seats_requested),
                requires_manager_approval=record.requires_manager_approval,
                premium_cents=max(0, int(record.premium_cents or 0)),
                notes=record.notes,
                shift_metadata={"source": "scheduler_sync", **record.metadata},
            )
            session.add(shift)
            await session.flush()
            created += 1
            is_created = True
        else:
            shift.role_id = role.id
            shift.timezone = record.timezone or shift.timezone
            shift.starts_at = record.starts_at
            shift.ends_at = record.ends_at
            shift.seats_requested = max(1, record.seats_requested)
            shift.requires_manager_approval = record.requires_manager_approval
            shift.premium_cents = max(0, int(record.premium_cents or 0))
            shift.notes = record.notes
            shift.shift_metadata = {
                **(shift.shift_metadata or {}),
                "source": "scheduler_sync",
                **record.metadata,
            }
            await session.flush()
            updated += 1

        mapped_employee_ids: list[UUID] = []
        for external_ref in record.assigned_external_refs:
            employee = await session.scalar(
                select(Employee).where(
                    Employee.business_id == connection.business_id,
                    Employee.external_ref == external_ref,
                )
            )
            if employee is not None:
                mapped_employee_ids.append(employee.id)

        active_assignments = await _active_scheduler_assignments(session, shift.id)
        assignments_by_employee = {assignment.employee_id: assignment for assignment in active_assignments if assignment.employee_id}
        desired_ids = list(dict.fromkeys(mapped_employee_ids))

        sequence_no = 1
        for employee_id in desired_ids:
            assignment = assignments_by_employee.pop(employee_id, None)
            if assignment is None:
                session.add(
                    ShiftAssignment(
                        shift_id=shift.id,
                        employee_id=employee_id,
                        assigned_via="scheduler_sync",
                        status=AssignmentStatus.assigned,
                        sequence_no=sequence_no,
                        assignment_metadata={"source": "scheduler_sync"},
                    )
                )
            else:
                assignment.status = AssignmentStatus.assigned
                assignment.sequence_no = sequence_no
            sequence_no += 1

        for assignment in assignments_by_employee.values():
            assignment.status = AssignmentStatus.cancelled
            assignment.cancelled_at = datetime.now(timezone.utc)

        shift.seats_filled = len(desired_ids)
        shift.status = _normalized_shift_status(record.status, shift.seats_filled, shift.seats_requested)
        await session.flush()
        if is_created and shift.status == ShiftStatus.cancelled:
            skipped += 1

    connection.status = SchedulerConnectionStatus.active
    connection.last_schedule_sync_at = datetime.now(timezone.utc)
    connection.last_schedule_sync_status = "completed"
    connection.last_sync_error = None
    if location is not None:
        await _sync_location_settings(location, connection)
    await session.flush()
    return {"created": created, "updated": updated, "skipped": skipped}


async def _mark_connection_failure(
    session: AsyncSession,
    connection: SchedulerConnection,
    *,
    error: str,
) -> None:
    connection.status = SchedulerConnectionStatus.degraded
    connection.last_sync_error = error
    location = await session.get(Location, connection.location_id)
    if location is not None:
        await _sync_location_settings(location, connection)
    await session.flush()


async def _find_connection_for_payload(
    session: AsyncSession,
    *,
    provider: SchedulerProvider,
    payload: dict,
) -> SchedulerConnection | None:
    refs: list[str] = []
    if provider == SchedulerProvider.seven_shifts:
        refs = [
            str(value).strip()
            for value in (
                _first_present(payload, [("company_id",), ("company", "id"), ("data", "company_id")]),
                _first_present(payload, [("location_id",), ("location", "id"), ("data", "location_id")]),
            )
            if value not in (None, "")
        ]
    elif provider == SchedulerProvider.deputy:
        refs = [
            str(value).strip()
            for value in (
                _first_present(payload, [("install_url",), ("data", "install_url"), ("resource", "install_url")]),
                _first_present(payload, [("company_id",), ("data", "company_id")]),
            )
            if value not in (None, "")
        ]
    elif provider == SchedulerProvider.when_i_work:
        refs = [
            str(value).strip()
            for value in (
                _first_present(payload, [("account_id",), ("data", "account_id")]),
                _first_present(payload, [("location_id",), ("data", "location_id")]),
            )
            if value not in (None, "")
        ]
    if not refs:
        return None
    return await session.scalar(
        select(SchedulerConnection).where(
            SchedulerConnection.provider == provider,
            (SchedulerConnection.provider_location_ref.in_(refs) | SchedulerConnection.install_url.in_(refs)),
        )
    )


async def resolve_connection(
    session: AsyncSession,
    *,
    provider: SchedulerProvider,
    connection_id: UUID | None = None,
    payload: dict | None = None,
) -> SchedulerConnection | None:
    if connection_id is not None:
        connection = await session.get(SchedulerConnection, connection_id)
        if connection is None or connection.provider != provider:
            return None
        return connection
    if payload is not None:
        return await _find_connection_for_payload(session, provider=provider, payload=payload)
    return None


def _source_event_id(provider: SchedulerProvider, payload: dict) -> str | None:
    raw_id = _first_present(
        payload,
        [("event_id",), ("id",), ("data", "event_id"), ("resource", "id"), ("meta", "id")],
    )
    event_type = str(payload.get("type") or payload.get("event") or payload.get("topic") or payload.get("resource") or "")
    if raw_id not in (None, ""):
        return f"{provider.value}:{event_type}:{raw_id}"
    return None


def _shift_ref_from_event(payload: dict) -> str | None:
    raw_id = _first_present(
        payload,
        [("shift_id",), ("shift", "id"), ("data", "shift_id"), ("data", "id"), ("resource", "id")],
    )
    return str(raw_id).strip() if raw_id not in (None, "") else None


async def _resolve_shift_from_event(
    session: AsyncSession,
    *,
    connection: SchedulerConnection,
    payload: dict,
) -> Shift | None:
    shift_ref = _shift_ref_from_event(payload)
    if not shift_ref:
        return None
    return await session.scalar(
        select(Shift).where(
            Shift.source_system == _provider_display_value(connection.provider),
            Shift.source_shift_id == shift_ref,
        )
    )


def default_dispatch_channel() -> str:
    if (
        settings.retell_api_key
        and settings.retell_from_number
        and (settings.retell_agent_id or settings.retell_agent_id_outbound)
    ):
        return "voice"
    return "sms"


async def create_vacancy_for_shift(
    session: AsyncSession,
    *,
    shift_id: UUID,
    employee_id: UUID | None = None,
    triggered_by: str,
    reason_code: str = "scheduler_vacancy",
    auto_execute: bool = True,
) -> dict:
    shift = await session.get(Shift, shift_id)
    if shift is None:
        raise LookupError("shift_not_found")

    result = await session.execute(
        select(ShiftAssignment).where(
            ShiftAssignment.shift_id == shift.id,
            ShiftAssignment.status.in_([AssignmentStatus.assigned, AssignmentStatus.accepted]),
        )
    )
    active_assignments = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    for assignment in active_assignments:
        if employee_id is not None and assignment.employee_id != employee_id:
            continue
        assignment.status = AssignmentStatus.cancelled
        assignment.cancelled_at = now

    remaining_active = await session.scalar(
        select(func.count(ShiftAssignment.id)).where(
            ShiftAssignment.shift_id == shift.id,
            ShiftAssignment.status.in_([AssignmentStatus.assigned, AssignmentStatus.accepted]),
        )
    )
    shift.seats_filled = int(remaining_active or 0)
    if shift.seats_filled >= shift.seats_requested:
        shift.status = ShiftStatus.scheduled
        await session.flush()
        return {"shift_id": shift.id, "coverage_case_id": None, "offers": []}

    shift.status = ShiftStatus.filling if shift.seats_filled > 0 else ShiftStatus.open

    coverage_case = await session.scalar(
        select(CoverageCase)
        .where(
            CoverageCase.shift_id == shift.id,
            CoverageCase.status.in_(
                [
                    CoverageCaseStatus.queued,
                    CoverageCaseStatus.running,
                    CoverageCaseStatus.filled,
                    CoverageCaseStatus.exhausted,
                ]
            ),
        )
        .order_by(CoverageCase.created_at.desc())
        .limit(1)
    )
    if coverage_case is None:
        coverage_case = CoverageCase(
            shift_id=shift.id,
            location_id=shift.location_id,
            role_id=shift.role_id,
            status=CoverageCaseStatus.queued,
            phase_target="phase_1",
            reason_code=reason_code,
            priority=100,
            requires_manager_approval=shift.requires_manager_approval,
            triggered_by=triggered_by,
            opened_at=now,
            case_metadata={},
        )
        session.add(coverage_case)
        await session.flush()
    else:
        coverage_case.status = CoverageCaseStatus.queued
        coverage_case.closed_at = None

    dispatch_result = None
    standby_offers = []
    if auto_execute:
        standby_offers = await coverage_service.activate_standby_queue(
            session,
            coverage_case=coverage_case,
            shift=shift,
            reference_time=now,
            channel=default_dispatch_channel(),
            dispatch_limit=1,
        )
        if not standby_offers:
            dispatch_result = await coverage_service.execute_next_coverage_phase(
                session,
                shift.business_id,
                coverage_case.id,
                CoverageExecutionDispatchRequest(
                    channel=default_dispatch_channel(),
                    run_metadata={"triggered_by": triggered_by},
                ),
            )
    await session.flush()
    return {
        "shift_id": shift.id,
        "coverage_case_id": coverage_case.id,
        "offers": [
            str(offer.id)
            for offer in (
                standby_offers if standby_offers else (dispatch_result.offers if dispatch_result is not None else [])
            )
        ],
    }


async def handle_vacancy_event(
    session: AsyncSession,
    *,
    provider: SchedulerProvider,
    payload: dict,
    connection_id: UUID | None = None,
) -> dict:
    connection = await resolve_connection(
        session,
        provider=provider,
        connection_id=connection_id,
        payload=payload,
    )
    if connection is None:
        raise LookupError("scheduler_connection_not_found")
    event_type = str(payload.get("type") or payload.get("event") or payload.get("topic") or "").strip() or None
    scope_ref = _shift_ref_from_event(payload)
    event, job = await enqueue_event_reconcile(
        session,
        connection=connection,
        payload=payload,
        event_type=event_type,
        event_scope="shift",
        scope_ref=scope_ref,
        source_event_id=_source_event_id(provider, payload),
    )
    await session.commit()
    processed = await process_sync_job(session, job.id)
    shift = await _resolve_shift_from_event(session, connection=connection, payload=payload)
    vacancy = None
    if shift is not None:
        worker_external_ref = _first_present(payload, [("worker_id",), ("employee_id",), ("user_id",), ("data", "worker_id"), ("data", "employee_id"), ("data", "user_id")])
        employee = None
        if worker_external_ref not in (None, ""):
            employee = await session.scalar(
                select(Employee).where(
                    Employee.business_id == connection.business_id,
                    Employee.external_ref == str(worker_external_ref).strip(),
                )
            )
        vacancy = await create_vacancy_for_shift(
            session,
            shift_id=shift.id,
            employee_id=employee.id if employee is not None else None,
            triggered_by=f"scheduler:{provider.value}",
        )
        await session.commit()
    return {
        "connection_id": str(connection.id),
        "event_id": str(event.id),
        "job_id": str(job.id),
        "processed": processed,
        "vacancy": vacancy,
    }


async def process_sync_job(session: AsyncSession, job_id: UUID) -> dict:
    job = await session.get(SchedulerSyncJob, job_id)
    if job is None:
        raise LookupError("scheduler_sync_job_not_found")
    if job.status == SchedulerSyncJobStatus.queued:
        job.status = SchedulerSyncJobStatus.running
        job.started_at = datetime.now(timezone.utc)
        job.attempt_count += 1
        await session.flush()
    if job.status != SchedulerSyncJobStatus.running:
        return {"status": job.status, "job_id": str(job.id)}

    connection = await session.get(SchedulerConnection, job.connection_id) if job.connection_id else None
    if connection is None:
        raise LookupError("scheduler_connection_not_found")

    started_at = job.started_at or datetime.now(timezone.utc)
    completed_at = datetime.now(timezone.utc)
    created = 0
    updated = 0
    skipped = 0
    try:
        if job.job_type in {"connect_bootstrap", "repair_reconcile"}:
            roster_counts = await sync_connection_roster(session, connection)
            created += roster_counts["created"]
            updated += roster_counts["updated"]
            skipped += roster_counts["skipped"]

        if job.job_type in {"connect_bootstrap", "daily_reconcile", "rolling_reconcile", "event_reconcile", "repair_reconcile"}:
            start_value = job.window_start or _window_for_job(job.job_type)[0]
            end_value = job.window_end or _window_for_job(job.job_type)[1]
            schedule_counts = await sync_connection_schedule(
                session,
                connection,
                window_start=start_value,
                window_end=end_value,
            )
            created += schedule_counts["created"]
            updated += schedule_counts["updated"]
            skipped += schedule_counts["skipped"]

        if job.job_type == "writeback":
            if not job.scope_ref:
                raise ValueError("writeback_missing_scope_ref")
            shift = await session.get(Shift, UUID(job.scope_ref))
            if shift is None:
                raise LookupError("shift_not_found")
            assignment = await session.scalar(
                select(ShiftAssignment)
                .where(
                    ShiftAssignment.shift_id == shift.id,
                    ShiftAssignment.status.in_([AssignmentStatus.accepted, AssignmentStatus.assigned]),
                    ShiftAssignment.employee_id.is_not(None),
                )
                .order_by(ShiftAssignment.sequence_no.asc())
                .limit(1)
            )
            if assignment is None or assignment.employee_id is None:
                raise ValueError("writeback_missing_assignment")
            employee = await session.get(Employee, assignment.employee_id)
            if employee is None or not employee.external_ref or not shift.source_shift_id:
                raise ValueError("writeback_missing_external_refs")
            adapter = adapter_for_connection(connection)
            await adapter.push_fill(
                connection,
                external_shift_ref=shift.source_shift_id,
                external_employee_ref=employee.external_ref,
            )
            connection.last_writeback_at = completed_at
            connection.last_sync_error = None

        job.status = SchedulerSyncJobStatus.completed
        job.completed_at = completed_at
        job.last_error = None
        if job.scheduler_event_id:
            event = await session.get(SchedulerEvent, job.scheduler_event_id)
            if event is not None:
                event.status = SchedulerSyncEventStatus.processed
                event.processed_at = completed_at
                event.error = None
        session.add(
            SchedulerSyncRun(
                sync_job_id=job.id,
                attempt_number=job.attempt_count,
                started_at=started_at,
                completed_at=completed_at,
                status=SchedulerSyncRunStatus.completed,
                created_count=created,
                updated_count=updated,
                skipped_count=skipped,
                latency_ms=int((completed_at - started_at).total_seconds() * 1000),
            )
        )
        await session.commit()
        return {
            "status": "completed",
            "job_id": str(job.id),
            "created": created,
            "updated": updated,
            "skipped": skipped,
        }
    except Exception as exc:
        retry_delay = _retry_delay(job.job_type, job.attempt_count)
        final_failure = retry_delay is None or job.attempt_count >= job.max_attempts
        job.status = SchedulerSyncJobStatus.failed if final_failure else SchedulerSyncJobStatus.queued
        job.completed_at = completed_at if final_failure else None
        job.next_run_at = completed_at + retry_delay if retry_delay is not None else job.next_run_at
        job.last_error = str(exc)
        await _mark_connection_failure(session, connection, error=str(exc))
        if job.scheduler_event_id:
            event = await session.get(SchedulerEvent, job.scheduler_event_id)
            if event is not None:
                event.status = SchedulerSyncEventStatus.failed if final_failure else SchedulerSyncEventStatus.retrying
                event.processed_at = completed_at if final_failure else None
                event.error = str(exc)
        session.add(
            SchedulerSyncRun(
                sync_job_id=job.id,
                attempt_number=job.attempt_count,
                started_at=started_at,
                completed_at=completed_at,
                status=SchedulerSyncRunStatus.failed if final_failure else SchedulerSyncRunStatus.retrying,
                created_count=created,
                updated_count=updated,
                skipped_count=skipped,
                latency_ms=int((completed_at - started_at).total_seconds() * 1000),
                error=str(exc),
            )
        )
        await session.commit()
        return {
            "status": "failed" if final_failure else "retrying",
            "job_id": str(job.id),
            "error": str(exc),
        }


async def process_due_sync_jobs(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> list[dict]:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(SchedulerSyncJob)
        .where(
            SchedulerSyncJob.status == SchedulerSyncJobStatus.queued,
            SchedulerSyncJob.next_run_at <= now,
        )
        .order_by(SchedulerSyncJob.priority.asc(), SchedulerSyncJob.next_run_at.asc())
        .limit(limit)
    )
    jobs = list(result.scalars().all())
    results: list[dict] = []
    for job in jobs:
        results.append(await process_sync_job(session, job.id))
    return results
