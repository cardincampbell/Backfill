from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app_v2.api.deps import AuthDep, SessionDep
from app_v2.models.common import MembershipRole
from app_v2.schemas.integrations import (
    SchedulerConnectionRead,
    SchedulerConnectionUpsert,
    SchedulerSyncJobRead,
    SchedulerSyncTriggerResult,
)
from app_v2.services import auth as auth_service
from app_v2.services import scheduler_sync

router = APIRouter(
    prefix="/businesses/{business_id}/locations/{location_id}/scheduler-connection",
    tags=["v2-scheduler"],
)
ADMIN_ROLES = {MembershipRole.owner, MembershipRole.admin}
READ_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}


@router.get("", response_model=SchedulerConnectionRead)
async def get_scheduler_connection(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_location_access(auth_ctx, business_id, location_id, allowed_roles=READ_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_access_denied")
    connection = await scheduler_sync.get_connection(
        session,
        business_id=business_id,
        location_id=location_id,
    )
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scheduler_connection_not_found")
    return scheduler_sync.build_connection_read(connection)


@router.put("", response_model=SchedulerConnectionRead)
async def put_scheduler_connection(
    business_id: UUID,
    location_id: UUID,
    payload: SchedulerConnectionUpsert,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_location_access(auth_ctx, business_id, location_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_admin_required")
    try:
        connection = await scheduler_sync.upsert_connection(
            session,
            business_id=business_id,
            location_id=location_id,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    await session.refresh(connection)
    return scheduler_sync.build_connection_read(connection)


@router.post("/sync", response_model=SchedulerSyncTriggerResult)
async def trigger_scheduler_sync(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_location_access(auth_ctx, business_id, location_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_admin_required")
    connection = await scheduler_sync.get_connection(
        session,
        business_id=business_id,
        location_id=location_id,
    )
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scheduler_connection_not_found")
    roster_job, schedule_job = await scheduler_sync.trigger_initial_sync(session, connection)
    await session.commit()
    await session.refresh(connection)
    return SchedulerSyncTriggerResult(
        connection=scheduler_sync.build_connection_read(connection),
        roster_job_id=roster_job.id,
        schedule_job_id=schedule_job.id,
    )


@router.get("/jobs", response_model=list[SchedulerSyncJobRead])
async def list_scheduler_jobs(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    limit: int = 20,
):
    if not auth_service.has_location_access(auth_ctx, business_id, location_id, allowed_roles=READ_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_access_denied")
    connection = await scheduler_sync.get_connection(
        session,
        business_id=business_id,
        location_id=location_id,
    )
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scheduler_connection_not_found")
    jobs = await scheduler_sync.list_jobs(session, connection_id=connection.id, limit=limit)
    return [scheduler_sync.build_job_read(job) for job in jobs]
