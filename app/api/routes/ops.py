from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import AuthDep, SessionDep
from app.models.business import Location
from app.models.common import MembershipRole
from app.schemas.events import PlatformEventRead
from app.schemas.finance import BillingLedgerEntryRead, CostLedgerEntryRead
from app.schemas.llm import LlmGenerationSummaryRead
from app.schemas.ops import BusinessTraceRead, CalendarFeedRead, ProjectionStatusRead
from app.services import auth as auth_service
from app.services import calendar_feed as calendar_feed_service
from app.services import feed_projections, ops_reporting

router = APIRouter(prefix="/ops", tags=["ops"])
MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}


@router.get("/projections/status", response_model=list[ProjectionStatusRead])
async def get_projection_status(
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_global_access(auth_ctx, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=403, detail="global_access_denied")
    cursors = await feed_projections.get_all_projection_cursors(session)
    return [
        ProjectionStatusRead(
            projection_name=c.projection_name,
            schema_version=c.schema_version,
            last_source_created_at=c.last_source_created_at,
            last_source_event_id=c.last_source_event_id,
            cursor_status=c.cursor_status,
            last_run_started_at=c.last_run_started_at,
            last_run_completed_at=c.last_run_completed_at,
            last_error=c.last_error,
            cursor_metadata=c.cursor_metadata,
        )
        for c in cursors
    ]


@router.get("/businesses/{business_id}/traces/{trace_id}", response_model=BusinessTraceRead)
async def get_trace_report(
    business_id: UUID,
    trace_id: str,
    session: SessionDep,
    auth_ctx: AuthDep,
    location_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=403, detail="business_access_denied")

    report = await ops_reporting.trace_report(
        session,
        business_id=business_id,
        trace_id=trace_id,
        location_id=location_id,
        limit=limit,
    )
    return BusinessTraceRead(
        trace_id=report.trace_id,
        platform_event_count=len(report.platform_events),
        llm_generation_count=len(report.llm_generations),
        cost_entry_count=len(report.cost_entries),
        billing_entry_count=len(report.billing_entries),
        total_cost_micros=report.total_cost_micros,
        total_billed_cents=report.total_billed_cents,
        platform_events=[PlatformEventRead.model_validate(item) for item in report.platform_events],
        llm_generations=[
            LlmGenerationSummaryRead.model_validate(item) for item in report.llm_generations
        ],
        cost_entries=[CostLedgerEntryRead.model_validate(item) for item in report.cost_entries],
        billing_entries=[
            BillingLedgerEntryRead.model_validate(item) for item in report.billing_entries
        ],
    )


@router.get(
    "/businesses/{business_id}/locations/{location_id}/calendar-feed",
    response_model=CalendarFeedRead,
)
async def get_calendar_feed(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_location_access(
        auth_ctx, business_id, location_id, allowed_roles=MANAGER_ROLES
    ):
        raise HTTPException(status_code=403, detail="location_access_denied")
    location = await session.get(Location, location_id)
    if location is None or location.business_id != business_id:
        raise HTTPException(status_code=404, detail="location_not_found")
    token, rotated_at, created = await calendar_feed_service.get_or_create_feed_token(session, location)
    if created:
        await session.commit()
    return CalendarFeedRead(
        feed_url=calendar_feed_service.feed_url_for_token(token),
        rotated_at=rotated_at,
    )


@router.post(
    "/businesses/{business_id}/locations/{location_id}/calendar-feed/rotate",
    response_model=CalendarFeedRead,
)
async def rotate_calendar_feed(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_location_access(
        auth_ctx, business_id, location_id, allowed_roles=MANAGER_ROLES
    ):
        raise HTTPException(status_code=403, detail="location_access_denied")
    location = await session.get(Location, location_id)
    if location is None or location.business_id != business_id:
        raise HTTPException(status_code=404, detail="location_not_found")
    token, rotated_at = await calendar_feed_service.rotate_feed_token(session, location)
    await session.commit()
    return CalendarFeedRead(
        feed_url=calendar_feed_service.feed_url_for_token(token),
        rotated_at=rotated_at,
    )
