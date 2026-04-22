from __future__ import annotations

from datetime import date, datetime
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AuthDep, SessionDep
from app.models.common import AuditActorType, MembershipRole
from app.models.scheduling import ShiftAssignment
from app.schemas.auto_scheduler import ScheduleRunApplyRead, ScheduleRunDetailRead, ScheduleRunRead
from app.schemas.scheduling import (
    PublishedShiftAmendmentRead,
    PublishedShiftAmendmentWrite,
    ScheduleWeekPublishRead,
    ScheduleWeekPublishWrite,
    ShiftAssignmentMutationResponse,
    ShiftAssignmentWrite,
    ShiftCreate,
    ShiftDeleteResponse,
    ShiftRead,
    ShiftUpdate,
)
from app.services import audit as audit_service
from app.services import auth as auth_service, auto_scheduler, businesses as businesses_service, outreach as outreach_service, platform_events, scheduling
from app.services.schedule_weeks import schedule_week_window

router = APIRouter(prefix="/businesses/{business_id}", tags=["scheduling"])
MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}
logger = logging.getLogger(__name__)


def _schedule_run_detail_read(schedule_run) -> ScheduleRunDetailRead:
    return ScheduleRunDetailRead.model_validate(
        {
            **ScheduleRunRead.model_validate(schedule_run).model_dump(),
            "inputs": schedule_run.inputs,
            "proposed_shifts": list(schedule_run.proposed_shifts or []),
            "assignments": list(schedule_run.assignments or []),
            "rejections": list(schedule_run.rejections or []),
            "explanation": schedule_run.explanation,
            "metrics": schedule_run.metrics,
            "applies": list(schedule_run.applies or []),
            "replay_run_ids": [replay_run.id for replay_run in (schedule_run.replay_runs or [])],
        }
    )


def _assignment_conflict_payload(assignment: ShiftAssignment | None) -> dict | None:
    if assignment is None:
        return None
    return {
        "assignment_id": str(assignment.id),
        "employee_id": str(assignment.employee_id) if assignment.employee_id is not None else None,
        "employee_name": scheduling._assignment_employee_name(assignment),
        "status": assignment.status.value if hasattr(assignment.status, "value") else str(assignment.status),
        "assigned_via": assignment.assigned_via,
        "accepted_at": assignment.accepted_at.isoformat() if assignment.accepted_at is not None else None,
    }


@router.get("/shifts", response_model=list[ShiftRead])
async def list_shifts(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    location_id: UUID | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    return await scheduling.list_shifts(
        session,
        business_id,
        location_id=location_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )


@router.post("/shifts", response_model=ShiftRead, status_code=status.HTTP_201_CREATED)
async def create_shift(
    business_id: UUID,
    payload: ShiftCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        shift = await scheduling.create_shift(session, business_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=shift.location_id)
    await audit_service.append(
        session,
        event_name="shift.created",
        target_type="shift",
        target_id=shift.id,
        business_id=business_id,
        location_id=shift.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "role_id": str(shift.role_id),
            "starts_at": shift.starts_at.isoformat(),
            "ends_at": shift.ends_at.isoformat(),
        },
    )
    await session.commit()
    return shift


@router.post(
    "/locations/{location_id}/schedule-weeks/{week_start_date}/publish",
    response_model=ScheduleWeekPublishRead,
)
async def publish_schedule_week(
    business_id: UUID,
    location_id: UUID,
    week_start_date: date,
    payload: ScheduleWeekPublishWrite,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=MANAGER_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_access_denied")
    try:
        result = await scheduling.publish_schedule_week(
            session,
            business_id,
            location_id,
            week_start_date,
            payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except scheduling.ScheduleWeekPublishConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "stale_publish_conflict",
                "current": {
                    "week_start_date": exc.week_start_date.isoformat(),
                    "publishable_shift_ids": [str(shift_id) for shift_id in exc.publishable_shift_ids],
                    "draft_shift_count": exc.draft_shift_count,
                    "already_scheduled_shift_count": exc.already_scheduled_shift_count,
                },
            },
        ) from exc

    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=location_id)
    response = scheduling.build_schedule_week_publish_response(result)
    client_ip = audit_service.request_client_ip(request)
    user_agent = audit_service.request_user_agent(request)

    if response.published_shift_count > 0:
        for shift in result.published_shifts:
            await platform_events.append(
                session,
                event_type=platform_events.PlatformEventType.SCHEDULE_SHIFT_PUBLISHED,
                target_type="shift",
                target_id=shift.id,
                business_id=business_id,
                location_id=location_id,
                actor_type=AuditActorType.user,
                actor_user_id=auth_ctx.user.id,
                actor_membership_id=membership.id if membership is not None else None,
                ip_address=client_ip,
                user_agent=user_agent,
                payload={
                    "shift_id": str(shift.id),
                    "lifecycle_status": (
                        shift.lifecycle_status.value
                        if hasattr(shift.lifecycle_status, "value")
                        else str(shift.lifecycle_status)
                    ),
                    "staffing_status": (
                        shift.staffing_status.value
                        if hasattr(shift.staffing_status, "value")
                        else str(shift.staffing_status)
                    ),
                    "status": shift.status.value if hasattr(shift.status, "value") else str(shift.status),
                    "current_assignment": scheduling._assignment_read(
                        scheduling.shift_assignments.current_assignment(shift.assignments or [])
                    ).model_dump(mode="json")
                    if scheduling.shift_assignments.current_assignment(shift.assignments or []) is not None
                    else None,
                },
                metadata={
                    "source": payload.source,
                    "note": payload.note,
                    "week_start_date": response.week_start_date.isoformat(),
                    "week_end_date": response.week_end_date.isoformat(),
                },
            )

    await platform_events.append(
        session,
        event_type=platform_events.PlatformEventType.SCHEDULE_WEEK_PUBLISHED,
        target_type="location",
        target_id=location_id,
        business_id=business_id,
        location_id=location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=client_ip,
        user_agent=user_agent,
        payload=response.model_dump(mode="json"),
        metadata={
            "source": payload.source,
            "note": payload.note,
        },
    )

    await session.commit()
    return response


@router.post(
    "/locations/{location_id}/schedule-weeks/{week_start_date}/predictive-schedule",
    response_model=ScheduleRunDetailRead,
)
async def ensure_predictive_schedule_week(
    business_id: UUID,
    location_id: UUID,
    week_start_date: date,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=MANAGER_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_access_denied")

    location = await businesses_service.get_location(session, business_id, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="location_not_found")

    window = schedule_week_window(location.timezone, week_start_date)
    schedule_run = await auto_scheduler.latest_schedule_run_for_scope(
        session,
        business_id=business_id,
        location_id=location_id,
        planning_window_start=window.starts_at,
        planning_window_end=window.ends_at,
    )

    current_snapshot_hash = None
    if schedule_run is not None:
        try:
            generated_demand_payload = auto_scheduler.schedule_run_input_contract(schedule_run).generated_demand_payload
        except ValueError:
            generated_demand_payload = {"proposed_shifts": [], "metadata": {}}
        current_snapshot_hash = await auto_scheduler.current_scope_snapshot_hash(
            session,
            business_id=business_id,
            location_id=location_id,
            planning_window_start=window.starts_at,
            planning_window_end=window.ends_at,
            generated_demand_payload=generated_demand_payload,
        )

    if (
        schedule_run is None
        or schedule_run.input_snapshot_hash != current_snapshot_hash
        or str(schedule_run.status) in {"failed", "cancelled"}
    ):
        schedule_run = await auto_scheduler.create_and_execute_schedule_run_for_scope(
            session,
            business_id=business_id,
            location_id=location_id,
            planning_window_start=window.starts_at,
            planning_window_end=window.ends_at,
            source_metadata={
                "source": "scheduler_ui_predictive_preview",
                "week_start_date": week_start_date.isoformat(),
            },
        )

    detail = await auto_scheduler.get_schedule_run_detail(session, schedule_run.id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule_run_not_found")
    return _schedule_run_detail_read(detail)


@router.post(
    "/locations/{location_id}/schedule-weeks/{week_start_date}/predictive-schedule/{schedule_run_id}/apply",
    response_model=ScheduleRunApplyRead,
)
async def apply_predictive_schedule_week(
    business_id: UUID,
    location_id: UUID,
    week_start_date: date,
    schedule_run_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=MANAGER_ROLES,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_access_denied")

    location = await businesses_service.get_location(session, business_id, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="location_not_found")
    window = schedule_week_window(location.timezone, week_start_date)

    schedule_run = await auto_scheduler.load_schedule_run(session, schedule_run_id)
    if schedule_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule_run_not_found")
    if schedule_run.business_id != business_id or schedule_run.location_id != location_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule_run_not_found")
    if (
        schedule_run.planning_window_start != window.starts_at
        or schedule_run.planning_window_end != window.ends_at
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="schedule_run_scope_mismatch")

    apply_record = await auto_scheduler.apply_schedule_run_from_live_scope(
        session,
        schedule_run_id,
    )
    return ScheduleRunApplyRead.model_validate(apply_record)


@router.post("/shifts/{shift_id}/published-amendment", response_model=PublishedShiftAmendmentRead)
async def amend_published_shift(
    business_id: UUID,
    shift_id: UUID,
    payload: PublishedShiftAmendmentWrite,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    stage = "load_shift"
    shift = None
    result = None
    membership = None
    response = None
    try:
        shift = await scheduling.get_shift(session, business_id, shift_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        stage = "authorize_location"
        if not auth_service.has_location_access(
            auth_ctx,
            business_id,
            shift.location_id,
            allowed_roles=MANAGER_ROLES,
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="location_access_denied")

        stage = "apply_published_amendment"
        result = await scheduling.apply_published_shift_amendment(
            session,
            business_id,
            shift_id,
            payload,
            assigned_by_user_id=auth_ctx.user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    client_ip = audit_service.request_client_ip(request)
    user_agent = audit_service.request_user_agent(request)

    try:
        stage = "resolve_membership"
        membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=result.shift.location_id)

        stage = "build_response"
        response = scheduling.build_published_shift_amendment_response(result)

        stage = "emit_cancelled_coverage_cases"
        for coverage_case in result.cancelled_cases:
            cancelled_offer_ids = [
                str(offer.id)
                for offer in result.cancelled_offers
                if offer.coverage_case_id == coverage_case.id
            ]
            await platform_events.append(
                session,
                event_type="coverage.campaign.cancelled",
                compatibility_event_name="coverage.case.cancelled",
                target_type="coverage_case",
                target_id=coverage_case.id,
                business_id=business_id,
                location_id=result.shift.location_id,
                actor_type=AuditActorType.user,
                actor_user_id=auth_ctx.user.id,
                actor_membership_id=membership.id if membership is not None else None,
                ip_address=client_ip,
                user_agent=user_agent,
                payload={
                    "shift_id": str(result.shift.id),
                    "reason": f"published_shift_{result.action}",
                    "cancelled_offer_ids": cancelled_offer_ids,
                },
                metadata={"source": payload.source},
            )

        stage = "emit_cancelled_coverage_offers"
        for offer in result.cancelled_offers:
            await outreach_service.append_outreach_attempt_event(
                session,
                event_type=platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_CANCELLED,
                compatibility_event_name="coverage.offer.cancelled",
                offer=offer,
                business_id=business_id,
                location_id=result.shift.location_id,
                shift_id=result.shift.id,
                actor_type=AuditActorType.user,
                actor_user_id=auth_ctx.user.id,
                actor_membership_id=membership.id if membership is not None else None,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={
                    "source": payload.source,
                    "reason": f"published_shift_{result.action}",
                },
            )

        if result.action in {"unassign_shift", "reassign_shift"}:
            stage = "emit_assignment_transition"
            assignment_event_type = {
                "unassign_shift": platform_events.PlatformEventType.SCHEDULE_SHIFT_UNASSIGNED,
                "reassign_shift": platform_events.PlatformEventType.SCHEDULE_SHIFT_REASSIGNED,
            }[result.action]
            await platform_events.append(
                session,
                event_type=assignment_event_type,
                target_type="shift",
                target_id=result.shift.id,
                business_id=business_id,
                location_id=result.shift.location_id,
                actor_type=AuditActorType.user,
                actor_user_id=auth_ctx.user.id,
                actor_membership_id=membership.id if membership is not None else None,
                ip_address=client_ip,
                user_agent=user_agent,
                payload={
                    "shift_id": str(result.shift.id),
                    "lifecycle_status": response.lifecycle_status,
                    "staffing_status": response.staffing_status,
                    "status": response.status,
                    "current_assignment": response.current_assignment.model_dump(mode="json")
                    if response.current_assignment is not None
                    else None,
                },
                metadata={
                    "old_assignment_id": str(result.previous_assignment.id) if result.previous_assignment is not None else None,
                    "new_assignment_id": str(result.current_assignment.id) if result.current_assignment is not None else None,
                    "old_employee_id": str(result.previous_assignment.employee_id) if result.previous_assignment and result.previous_assignment.employee_id else None,
                    "new_employee_id": str(result.current_assignment.employee_id) if result.current_assignment and result.current_assignment.employee_id else None,
                    "source": payload.source,
                    "note": payload.note,
                    "reason_code": payload.reason_code,
                },
            )

        stage = "emit_shift_amended"
        await platform_events.append(
            session,
            event_type=platform_events.PlatformEventType.SCHEDULE_SHIFT_AMENDED,
            target_type="shift",
            target_id=result.shift.id,
            business_id=business_id,
            location_id=result.shift.location_id,
            actor_type=AuditActorType.user,
            actor_user_id=auth_ctx.user.id,
            actor_membership_id=membership.id if membership is not None else None,
            ip_address=client_ip,
            user_agent=user_agent,
            payload=response.model_dump(mode="json"),
            metadata={
                "action": payload.action,
                "reason_code": payload.reason_code,
                "old_employee_id": str(result.previous_assignment.employee_id) if result.previous_assignment and result.previous_assignment.employee_id else None,
                "new_employee_id": str(result.current_assignment.employee_id) if result.current_assignment and result.current_assignment.employee_id else None,
                "source": payload.source,
                "note": payload.note,
                "week_start_date": result.week_start_date.isoformat(),
                "week_end_date": result.week_end_date.isoformat(),
            },
        )

        stage = "emit_week_amended"
        await platform_events.append(
            session,
            event_type=platform_events.PlatformEventType.SCHEDULE_WEEK_AMENDED,
            target_type="location",
            target_id=result.shift.location_id,
            business_id=business_id,
            location_id=result.shift.location_id,
            actor_type=AuditActorType.user,
            actor_user_id=auth_ctx.user.id,
            actor_membership_id=membership.id if membership is not None else None,
            ip_address=client_ip,
            user_agent=user_agent,
            payload={
                "week_start_date": result.week_start_date.isoformat(),
                "week_end_date": result.week_end_date.isoformat(),
                "shift_id": str(result.shift.id),
                "action": payload.action,
                "reason_code": payload.reason_code,
            },
            metadata={
                "source": payload.source,
                "note": payload.note,
            },
        )

        stage = "commit"
        await session.commit()
        return response
    except Exception:
        logger.exception(
            "published amendment failed stage=%s business_id=%s shift_id=%s action=%s reason=%s actor_user_id=%s actor_membership_id=%s shift_lifecycle=%s shift_staffing=%s current_assignment_id=%s",
            stage,
            business_id,
            shift_id,
            payload.action,
            payload.reason_code,
            getattr(getattr(auth_ctx, "user", None), "id", None),
            getattr(membership, "id", None),
            getattr(getattr(result, "shift", None) or shift, "lifecycle_status", None),
            getattr(getattr(result, "shift", None) or shift, "staffing_status", None),
            (
                getattr(getattr(result, "current_assignment", None), "id", None)
                if result is not None
                else None
            ),
        )
        raise


@router.patch("/shifts/{shift_id}/assignment", response_model=ShiftAssignmentMutationResponse)
async def update_shift_assignment(
    business_id: UUID,
    shift_id: UUID,
    payload: ShiftAssignmentWrite,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        result = await scheduling.set_shift_assignment(
            session,
            business_id,
            shift_id,
            payload,
            assigned_by_user_id=auth_ctx.user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except scheduling.ShiftAssignmentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "stale_assignment_conflict",
                "current_assignment": _assignment_conflict_payload(exc.current_assignment),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=result.shift.location_id)
    response = scheduling.build_shift_assignment_response(result)
    client_ip = audit_service.request_client_ip(request)
    user_agent = audit_service.request_user_agent(request)

    for coverage_case in result.cancelled_cases:
        cancelled_offer_ids = [
            str(offer.id)
            for offer in result.cancelled_offers
            if offer.coverage_case_id == coverage_case.id
        ]
        await platform_events.append(
            session,
            event_type="coverage.campaign.cancelled",
            compatibility_event_name="coverage.case.cancelled",
            target_type="coverage_case",
            target_id=coverage_case.id,
            business_id=business_id,
            location_id=result.shift.location_id,
            actor_type=AuditActorType.user,
            actor_user_id=auth_ctx.user.id,
            actor_membership_id=membership.id if membership is not None else None,
            ip_address=client_ip,
            user_agent=user_agent,
            payload={
                "shift_id": str(result.shift.id),
                "reason": "manual_assignment_override",
                "cancelled_offer_ids": cancelled_offer_ids,
            },
            metadata={
                "source": payload.source,
            },
        )

    for offer in result.cancelled_offers:
        await outreach_service.append_outreach_attempt_event(
            session,
            event_type=platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_CANCELLED,
            compatibility_event_name="coverage.offer.cancelled",
            offer=offer,
            business_id=business_id,
            location_id=result.shift.location_id,
            shift_id=result.shift.id,
            actor_type=AuditActorType.user,
            actor_user_id=auth_ctx.user.id,
            actor_membership_id=membership.id if membership is not None else None,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata={
                "source": payload.source,
                "reason": "manual_assignment_override",
            },
        )

    if not result.no_op:
        event_type = {
            "assigned": platform_events.PlatformEventType.SCHEDULE_SHIFT_ASSIGNED,
            "reassigned": platform_events.PlatformEventType.SCHEDULE_SHIFT_REASSIGNED,
            "unassigned": platform_events.PlatformEventType.SCHEDULE_SHIFT_UNASSIGNED,
        }[result.action]
        await platform_events.append(
            session,
            event_type=event_type,
            target_type="shift",
            target_id=result.shift.id,
            business_id=business_id,
            location_id=result.shift.location_id,
            actor_type=AuditActorType.user,
            actor_user_id=auth_ctx.user.id,
            actor_membership_id=membership.id if membership is not None else None,
            ip_address=client_ip,
            user_agent=user_agent,
            payload=response.model_dump(mode="json"),
            metadata={
                "old_assignment_id": str(result.previous_assignment.id) if result.previous_assignment is not None else None,
                "new_assignment_id": str(result.current_assignment.id) if result.current_assignment is not None else None,
                "old_employee_id": str(result.previous_assignment.employee_id) if result.previous_assignment and result.previous_assignment.employee_id else None,
                "new_employee_id": str(result.current_assignment.employee_id) if result.current_assignment and result.current_assignment.employee_id else None,
                "source": payload.source,
                "note": payload.note,
            },
        )

    await session.commit()
    return response


@router.patch("/shifts/{shift_id}", response_model=ShiftRead)
async def update_shift(
    business_id: UUID,
    shift_id: UUID,
    payload: ShiftUpdate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        shift = await scheduling.update_shift(session, business_id, shift_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=shift.location_id)
    await audit_service.append(
        session,
        event_name="shift.updated",
        target_type="shift",
        target_id=shift.id,
        business_id=business_id,
        location_id=shift.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload=payload.model_dump(exclude_none=True, mode="json"),
    )
    await session.commit()
    return shift


@router.delete("/shifts/{shift_id}", response_model=ShiftDeleteResponse)
async def delete_shift(
    business_id: UUID,
    shift_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        shift = await scheduling.delete_shift(session, business_id, shift_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=shift.location_id)
    await audit_service.append(
        session,
        event_name="shift.deleted",
        target_type="shift",
        target_id=shift.id,
        business_id=business_id,
        location_id=shift.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={"role_id": str(shift.role_id)},
    )
    await session.commit()
    return ShiftDeleteResponse(deleted=True, shift_id=shift.id)
