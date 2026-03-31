"""
REST API routes for Backfill Native Lite.
Covers CRUD for customer locations, workers, and shifts, plus the backfill trigger.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
import secrets
import socket
from datetime import date, datetime, time, timedelta
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request, Response
import aiosqlite
import httpx

from app.config import settings
from app.db.database import get_db
from app.db import queries
from app.models.location import BusinessVertical, Location, LocationCreate
from app.models.organization import Organization, OrganizationCreate
from app.models.worker import Worker, WorkerCreate
from app.models.shift import Shift, ShiftCreate
from app.models.cascade import Cascade
from app.models.ai_actions import (
    AiActionClarifyRequest,
    AiActionDebugResponse,
    AiActionFeedbackRequest,
    AiActionFeedbackResponse,
    AiActionHistoryResponse,
    AiActionAttentionResponse,
    AiActiveSessionsResponse,
    AiCapabilitiesResponse,
    AiActionResponse,
    AiRuntimeStatsResponse,
    InternalAiActionAttentionResponse,
    InternalAiActionSessionsResponse,
    InternalAiActionRecentResponse,
    AiWebActionRequest,
)
from app.models.places import (
    PlaceAutocompleteResponse,
    PlaceDetailsResponse,
)
from app.services import (
    ai_actions as ai_actions_svc,
    auth as auth_svc,
    shift_manager,
    cascade as cascade_svc,
    backfill_shifts as backfill_shifts_svc,
    messaging as messaging_svc,
    notifications as notifications_svc,
    ops_queue,
    places as places_svc,
    preview_bootstrap as preview_bootstrap_svc,
    rate_limit,
    roster as roster_svc,
)
from app.services import retell_reconcile
from app.models.audit import AuditAction
from app.services import audit as audit_svc
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/api",
    tags=["api"],
    dependencies=[
        Depends(auth_svc.require_api_request_access),
        Depends(
            rate_limit.limit_by_request_key(
                "api_request",
                limit=900,
                window_seconds=60,
                key_func=auth_svc.request_rate_limit_key,
            )
        ),
    ],
)

logger = logging.getLogger(__name__)

_PLACE_TYPE_VERTICAL_MAP: dict[str, BusinessVertical] = {
    "restaurant": BusinessVertical.restaurant,
    "cafe": BusinessVertical.restaurant,
    "coffee_shop": BusinessVertical.restaurant,
    "bakery": BusinessVertical.restaurant,
    "bar": BusinessVertical.restaurant,
    "meal_takeaway": BusinessVertical.restaurant,
    "meal_delivery": BusinessVertical.restaurant,
    "fast_food_restaurant": BusinessVertical.restaurant,
    "grocery_store": BusinessVertical.retail,
    "supermarket": BusinessVertical.retail,
    "store": BusinessVertical.retail,
    "clothing_store": BusinessVertical.retail,
    "department_store": BusinessVertical.retail,
    "electronics_store": BusinessVertical.retail,
    "shoe_store": BusinessVertical.retail,
    "furniture_store": BusinessVertical.retail,
    "convenience_store": BusinessVertical.retail,
    "discount_store": BusinessVertical.retail,
    "home_goods_store": BusinessVertical.retail,
    "warehouse_store": BusinessVertical.retail,
    "hospital": BusinessVertical.healthcare,
    "doctor": BusinessVertical.healthcare,
    "medical_lab": BusinessVertical.healthcare,
    "dental_clinic": BusinessVertical.healthcare,
    "pharmacy": BusinessVertical.healthcare,
    "lodging": BusinessVertical.hospitality,
    "hotel": BusinessVertical.hospitality,
    "motel": BusinessVertical.hospitality,
    "inn": BusinessVertical.hospitality,
    "resort_hotel": BusinessVertical.hospitality,
    "warehouse": BusinessVertical.warehouse,
    "storage": BusinessVertical.warehouse,
    "self_storage": BusinessVertical.warehouse,
    "moving_company": BusinessVertical.warehouse,
    "shipping_company": BusinessVertical.warehouse,
}


def _infer_vertical_from_place(data: dict) -> str | None:
    raw_types: list[str] = []
    primary_type = data.get("place_primary_type")
    if isinstance(primary_type, str) and primary_type.strip():
        raw_types.append(primary_type.strip().lower())
    for value in data.get("place_types") or []:
        if isinstance(value, str) and value.strip():
            raw_types.append(value.strip().lower())
    seen: set[str] = set()
    for place_type in raw_types:
        if place_type in seen:
            continue
        seen.add(place_type)
        mapped = _PLACE_TYPE_VERTICAL_MAP.get(place_type)
        if mapped is not None:
            return mapped.value
    return None


def _google_places_error_detail(exc: httpx.HTTPStatusError, operation: str) -> str:
    default = (
        f"{operation} failed. Verify GOOGLE_PLACES_API_KEY, billing, "
        "Places API (New) access, and key restrictions."
    )
    try:
        payload = exc.response.json()
    except Exception:  # pragma: no cover - defensive parsing
        payload = None

    error = payload.get("error") if isinstance(payload, dict) else None
    status = error.get("status") if isinstance(error, dict) else None
    message = error.get("message") if isinstance(error, dict) else None

    if status or message:
        logger.warning(
            "Google Places %s error: status=%s message=%s http_status=%s",
            operation,
            status,
            message,
            exc.response.status_code,
        )
        parts = [f"{operation} failed"]
        if status:
            parts.append(str(status))
        if message:
            parts.append(str(message))
        parts.append(
            "Check GOOGLE_PLACES_API_KEY, billing, Places API (New), and key restrictions."
        )
        return ". ".join(parts)

    logger.warning(
        "Google Places %s error with undecodable payload: http_status=%s",
        operation,
        exc.response.status_code,
    )
    return default


# ── response models ───────────────────────────────────────────────────────────

class BackfillRequest(BaseModel):
    shift_id: int
    worker_id: int   # worker calling out (creates vacancy + starts cascade)


class BackfillResponse(BaseModel):
    cascade_id: int
    shift_id: int
    worker_id: int
    message: str


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    vertical: Optional[str] = None
    address: Optional[str] = None
    place_inferred_vertical: Optional[str] = None
    place_provider: Optional[str] = None
    place_id: Optional[str] = None
    place_resource_name: Optional[str] = None
    place_display_name: Optional[str] = None
    place_brand_name: Optional[str] = None
    place_location_label: Optional[str] = None
    place_formatted_address: Optional[str] = None
    place_primary_type: Optional[str] = None
    place_primary_type_display_name: Optional[str] = None
    place_business_status: Optional[str] = None
    place_latitude: Optional[float] = None
    place_longitude: Optional[float] = None
    place_google_maps_uri: Optional[str] = None
    place_website_uri: Optional[str] = None
    place_national_phone_number: Optional[str] = None
    place_international_phone_number: Optional[str] = None
    place_utc_offset_minutes: Optional[int] = None
    place_rating: Optional[float] = None
    place_user_rating_count: Optional[int] = None
    place_city: Optional[str] = None
    place_state_region: Optional[str] = None
    place_postal_code: Optional[str] = None
    place_country_code: Optional[str] = None
    place_neighborhood: Optional[str] = None
    place_sublocality: Optional[str] = None
    place_types: Optional[list[str]] = None
    place_address_components: Optional[list[dict]] = None
    place_regular_opening_hours: Optional[dict] = None
    place_plus_code: Optional[dict] = None
    place_metadata: Optional[dict] = None
    employee_count: Optional[int] = None
    manager_name: Optional[str] = None
    manager_phone: Optional[str] = None
    manager_email: Optional[str] = None
    scheduling_platform: Optional[str] = None
    scheduling_platform_id: Optional[str] = None
    integration_status: Optional[str] = None
    last_roster_sync_at: Optional[str] = None
    last_roster_sync_status: Optional[str] = None
    last_schedule_sync_at: Optional[str] = None
    last_schedule_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    integration_state: Optional[str] = None
    last_event_sync_at: Optional[str] = None
    last_rolling_sync_at: Optional[str] = None
    last_daily_sync_at: Optional[str] = None
    last_writeback_at: Optional[str] = None
    last_manager_digest_sent_at: Optional[str] = None
    writeback_enabled: Optional[bool] = None
    writeback_subscription_tier: Optional[str] = None
    backfill_shifts_enabled: Optional[bool] = None
    backfill_shifts_launch_state: Optional[str] = None
    backfill_shifts_beta_eligible: Optional[bool] = None
    coverage_requires_manager_approval: Optional[bool] = None
    late_arrival_policy: Optional[str] = None
    missed_check_in_policy: Optional[str] = None
    timezone: Optional[str] = None
    operating_mode: Optional[str] = None
    onboarding_info: Optional[str] = None
    agency_supply_approved: Optional[bool] = None
    preferred_agency_partners: Optional[list[int]] = None


class WorkerUpdate(BaseModel):
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source_id: Optional[str] = None
    worker_type: Optional[str] = None
    preferred_channel: Optional[str] = None
    roles: Optional[list[str]] = None
    certifications: Optional[list[str]] = None
    priority_rank: Optional[int] = None
    location_id: Optional[int] = None
    location_assignments: Optional[list[dict]] = None
    locations_worked: Optional[list[int]] = None
    source: Optional[str] = None
    employment_status: Optional[str] = None
    max_hours_per_week: Optional[int] = None
    sms_consent_status: Optional[str] = None
    voice_consent_status: Optional[str] = None
    rating: Optional[float] = None
    response_rate: Optional[float] = None
    acceptance_rate: Optional[float] = None
    show_up_rate: Optional[float] = None


class WorkerTransferRequest(BaseModel):
    target_location_id: int
    roles: Optional[list[str]] = None
    priority_rank: Optional[int] = Field(default=None, ge=1)


class EnrollmentInvitePreviewResponse(BaseModel):
    location_id: int
    join_number: str
    join_keyword: str
    sms_copy: str


class EnrollmentInviteSendRequest(BaseModel):
    worker_ids: list[int] = Field(default_factory=list)
    include_enrolled: bool = False


class LocationSettingsResponse(BaseModel):
    location_id: int
    scheduling_platform: Optional[str] = None
    operating_mode: Optional[str] = None
    timezone: Optional[str] = None
    writeback_enabled: bool = False
    backfill_shifts_enabled: bool = True
    backfill_shifts_launch_state: str = "enabled"
    backfill_shifts_beta_eligible: bool = False
    coverage_requires_manager_approval: bool = False
    late_arrival_policy: str = "wait"
    missed_check_in_policy: str = "start_coverage"
    agency_supply_approved: bool = False


class LocationSettingsUpdate(BaseModel):
    timezone: Optional[str] = None
    writeback_enabled: Optional[bool] = None
    backfill_shifts_enabled: Optional[bool] = None
    backfill_shifts_launch_state: Optional[str] = None
    backfill_shifts_beta_eligible: Optional[bool] = None
    coverage_requires_manager_approval: Optional[bool] = None
    late_arrival_policy: Optional[str] = None
    missed_check_in_policy: Optional[str] = None
    agency_supply_approved: Optional[bool] = None


class LocationDeleteResponse(BaseModel):
    deleted: bool
    location_id: int


class LocationManagerMembershipResponse(BaseModel):
    id: Optional[int] = None
    location_id: int
    entry_kind: str = "membership"
    phone: Optional[str] = None
    manager_name: Optional[str] = None
    manager_email: Optional[str] = None
    role: str = "manager"
    invite_status: str = "pending"
    invite_channel: str = "email"
    invited_by_phone: Optional[str] = None
    accepted_at: Optional[str] = None
    revoked_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LocationManagerInviteRequest(BaseModel):
    email: str
    manager_name: Optional[str] = None


class LocationManagerInviteResponse(BaseModel):
    location_id: int
    created: bool
    delivery_id: Optional[str] = None
    membership: LocationManagerMembershipResponse


class LocationManagerRevokeResponse(BaseModel):
    revoked: bool
    location_id: int
    access_kind: str
    access_id: int


class LocationManagerInvitePreviewResponse(BaseModel):
    invite_email: str
    manager_name: Optional[str] = None
    business_name: str
    location_id: int
    location_name: str
    location_address: Optional[str] = None
    expires_at: str
    invite_status: str


class LocationManagerInviteAccessRequest(BaseModel):
    manager_name: str
    phone: str


class DashboardOnboardingCompleteRequest(BaseModel):
    manager_name: str
    manager_email: str


class LocationBackfillShiftsMetricsResponse(BaseModel):
    location_id: int
    window_days: int
    window_start: str
    window_end: str
    launch_controls: dict
    summary: dict
    rates: dict
    recent_activity: dict


class LocationBackfillShiftsActivityResponse(BaseModel):
    location_id: int
    window_days: int
    window_start: str
    window_end: str
    summary: dict
    items: list[dict]


class BackfillShiftsWebhookHealthResponse(BaseModel):
    source: str
    window_days: int
    window_start: str
    window_end: str
    summary: dict
    recent_receipts: list[dict]


class ShiftUpdate(BaseModel):
    location_id: Optional[int] = None
    schedule_id: Optional[int] = None
    scheduling_platform_id: Optional[str] = None
    role: Optional[str] = None
    date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    pay_rate: Optional[float] = None
    requirements: Optional[list[str]] = None
    status: Optional[str] = None
    called_out_by: Optional[int] = None
    filled_by: Optional[int] = None
    fill_tier: Optional[str] = None
    source_platform: Optional[str] = None
    shift_label: Optional[str] = None
    notes: Optional[str] = None
    published_state: Optional[str] = None
    spans_midnight: Optional[bool] = None


class ManagerShiftCreate(BaseModel):
    location_id: Optional[int] = None
    role: str
    date: date
    start_time: time
    end_time: time
    pay_rate: float
    requirements: list[str] = []
    start_backfill: bool = True


class ShiftStatusResponse(BaseModel):
    shift: dict
    location: Optional[dict] = None
    cascade: Optional[dict] = None
    filled_worker: Optional[dict] = None
    outreach_attempts: list[dict]
    retell_conversations: list[dict] = []


class LocationStatusResponse(BaseModel):
    location: dict
    integration: dict
    metrics: dict
    worker_preview: list[dict]
    recent_shifts: list[dict]
    active_cascades: list[dict]
    recent_sync_jobs: list[dict]
    recent_audit: list[dict]


class OnboardingLinkRequest(BaseModel):
    phone: str
    kind: str
    location_id: int
    platform: Optional[str] = None


class OnboardingLinkResponse(BaseModel):
    kind: str
    platform: Optional[str] = None
    path: str
    url: str
    message_sid: Optional[str] = None


class DashboardAccessRequestBody(BaseModel):
    phone: str


class DashboardAccessRequestResponse(BaseModel):
    request_id: int
    destination: str
    expires_at: str
    message_sid: Optional[str] = None
    channel: str = "sms"
    organization_id: Optional[int] = None
    location_ids: list[int] = Field(default_factory=list)
    purpose: str = "login"
    resend_available_at: Optional[str] = None


class DashboardAccessExchangeBody(BaseModel):
    token: Optional[str] = None
    request_id: Optional[int] = None
    code: Optional[str] = None


class DashboardStepUpRequestBody(BaseModel):
    purpose: str


class DashboardAuthResponse(BaseModel):
    principal_type: str
    session_token: Optional[str] = None
    session_id: Optional[int] = None
    subject_phone: Optional[str] = None
    session_expires_at: Optional[str] = None
    onboarding_required: bool = False
    organization: Optional[dict] = None
    location_ids: list[int] = Field(default_factory=list)
    locations: list[dict] = Field(default_factory=list)


class TwilioRuntimeDebugResponse(BaseModel):
    step: Optional[str] = None
    host: str
    process_id: int
    railway_project_name: Optional[str] = None
    railway_service_name: Optional[str] = None
    railway_environment_name: Optional[str] = None
    railway_replica_id: Optional[str] = None
    railway_deployment_id: Optional[str] = None
    commit_sha: Optional[str] = None
    twilio_account_sid_present: bool
    twilio_account_sid_prefix: Optional[str] = None
    twilio_auth_token_present: bool
    twilio_verify_service_sid_present: bool
    twilio_verify_service_sid_prefix: Optional[str] = None


class SignupSessionResponse(BaseModel):
    id: int
    status: str
    call_type: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    role_name: Optional[str] = None
    business_name: Optional[str] = None
    location_name: Optional[str] = None
    vertical: Optional[str] = None
    location_count: Optional[int] = None
    employee_count: Optional[int] = None
    address: Optional[str] = None
    pain_point_summary: Optional[str] = None
    urgency: Optional[str] = None
    notes: Optional[str] = None
    setup_kind: Optional[str] = None
    scheduling_platform: Optional[str] = None
    extracted_fields: dict = Field(default_factory=dict)
    organization: Optional[dict] = None
    location: Optional[dict] = None


class SignupSessionCompleteRequest(BaseModel):
    business_name: Optional[str] = None
    location_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    role_name: Optional[str] = None
    vertical: Optional[str] = None
    location_count: Optional[int] = None
    employee_count: Optional[int] = None
    address: Optional[str] = None
    pain_point_summary: Optional[str] = None
    urgency: Optional[str] = None
    notes: Optional[str] = None
    setup_kind: Optional[str] = None
    scheduling_platform: Optional[str] = None


class SignupSessionCompleteResponse(BaseModel):
    status: str
    organization: Optional[dict] = None
    location: dict
    next_path: str


class RetellReconcileRequest(BaseModel):
    call_id: Optional[str] = None
    chat_id: Optional[str] = None
    lookback_minutes: int = 20
    limit: int = 50


class ImportJobCreateRequest(BaseModel):
    import_type: str
    filename: Optional[str] = None


class ImportJobMappingRequest(BaseModel):
    mapping: dict[str, str]


class ImportRowResolutionRequest(BaseModel):
    action: str
    normalized_payload: dict[str, Optional[str]] = Field(default_factory=dict)


class CopyScheduleRequest(BaseModel):
    source_schedule_id: int
    target_week_start_date: date


class CreateScheduleFromTemplateRequest(BaseModel):
    template_id: int
    target_week_start_date: date
    replace_existing: bool = False
    day_of_week_filter: list[int] = Field(default_factory=list)
    auto_assign_open_shifts: bool = False
    assignment_strategy: str = "priority_first"


class GenerateAIScheduleDraftRequest(BaseModel):
    target_week_start_date: date
    template_id: Optional[int] = None
    source_schedule_id: Optional[int] = None
    replace_existing: bool = False
    day_of_week_filter: list[int] = Field(default_factory=list)
    auto_assign_open_shifts: bool = True
    assignment_strategy: str = "priority_first"
    include_assignments_from_source: bool = True


class ScheduleDayCopyRequest(BaseModel):
    source_date: date
    target_date: date
    copy_assignments: bool = False
    replace_target_day: bool = False


class ScheduleTemplateCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    include_assignments: bool = True


class ManualScheduleTemplateCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None


class ScheduleTemplateUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ScheduleTemplateCloneRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ScheduleTemplateApplyRequest(BaseModel):
    target_week_start_date: date
    replace_existing: bool = False
    day_of_week_filter: list[int] = Field(default_factory=list)
    auto_assign_open_shifts: bool = False
    assignment_strategy: str = "priority_first"


class ScheduleTemplateRangeApplyRequest(BaseModel):
    target_week_start_dates: list[date] = Field(default_factory=list)
    replace_existing: bool = False
    day_of_week_filter: list[int] = Field(default_factory=list)
    auto_assign_open_shifts: bool = False
    assignment_strategy: str = "priority_first"


class ScheduleTemplateRefreshRequest(BaseModel):
    source_schedule_id: Optional[int] = None
    include_assignments: bool = True


class ScheduleTemplateShiftCreateRequest(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    role: str
    start_time: time
    end_time: time
    spans_midnight: bool = False
    pay_rate: float = Field(default=0.0, ge=0)
    requirements: list[str] = Field(default_factory=list)
    shift_label: Optional[str] = None
    notes: Optional[str] = None
    worker_id: Optional[int] = None
    assignment_status: Optional[str] = None


class ScheduleTemplateShiftUpdateRequest(BaseModel):
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    role: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    spans_midnight: Optional[bool] = None
    pay_rate: Optional[float] = Field(default=None, ge=0)
    requirements: Optional[list[str]] = None
    shift_label: Optional[str] = None
    notes: Optional[str] = None
    worker_id: Optional[int] = None
    assignment_status: Optional[str] = None


class ScheduleTemplateShiftBulkCreateRequest(BaseModel):
    slots: list[ScheduleTemplateShiftCreateRequest] = Field(default_factory=list)


class ScheduleTemplateShiftBulkUpdateRequest(BaseModel):
    shift_ids: list[int] = Field(default_factory=list)
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    role: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    spans_midnight: Optional[bool] = None
    pay_rate: Optional[float] = Field(default=None, ge=0)
    requirements: Optional[list[str]] = None
    shift_label: Optional[str] = None
    notes: Optional[str] = None
    worker_id: Optional[int] = None
    assignment_status: Optional[str] = None


class ScheduleTemplateShiftBulkDuplicateRequest(BaseModel):
    shift_ids: list[int] = Field(default_factory=list)
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)


class ScheduleTemplateShiftBulkDeleteRequest(BaseModel):
    shift_ids: list[int] = Field(default_factory=list)


class ScheduleTemplateAutoAssignRequest(BaseModel):
    overwrite_invalid_assignments: bool = True
    day_of_week_filter: list[int] = Field(default_factory=list)
    assignment_strategy: str = "priority_first"


class ScheduleTemplateGenerateDraftRequest(BaseModel):
    target_week_start_date: date
    replace_existing: bool = False
    day_of_week_filter: list[int] = Field(default_factory=list)
    auto_assign_open_shifts: bool = True
    assignment_strategy: str = "priority_first"


class ScheduleTemplateSuggestionSelectionRequest(BaseModel):
    shift_id: int
    worker_id: int


class ScheduleTemplateSuggestionsApplyRequest(BaseModel):
    shift_ids: list[int] = Field(default_factory=list)
    assignments: list[ScheduleTemplateSuggestionSelectionRequest] = Field(default_factory=list)
    day_of_week_filter: list[int] = Field(default_factory=list)
    overwrite_existing_assignments: bool = False
    assignment_strategy: str = "priority_first"


class ScheduleTemplateClearAssignmentsRequest(BaseModel):
    shift_ids: list[int] = Field(default_factory=list)
    day_of_week_filter: list[int] = Field(default_factory=list)
    only_invalid: bool = False


class ScheduleShiftCreateRequest(BaseModel):
    role: str
    date: date
    start_time: time
    end_time: time
    pay_rate: float = Field(default=0.0, ge=0)
    requirements: list[str] = Field(default_factory=list)
    shift_label: Optional[str] = None
    notes: Optional[str] = None
    worker_id: Optional[int] = None
    assignment_status: Optional[str] = None
    spans_midnight: Optional[bool] = None
    start_open_shift_offer: bool = False


class ShiftAssignmentUpdateRequest(BaseModel):
    worker_id: Optional[int] = None
    assignment_status: str
    notes: Optional[str] = None


class BulkShiftAssignmentItemRequest(BaseModel):
    shift_id: int
    worker_id: Optional[int] = None
    notes: Optional[str] = None


class BulkShiftAssignmentRequest(BaseModel):
    assignments: list[BulkShiftAssignmentItemRequest] = Field(default_factory=list)


class ScheduleShiftBulkEditRequest(BaseModel):
    shift_ids: list[int] = Field(default_factory=list)
    role: Optional[str] = None
    date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    pay_rate: Optional[float] = Field(default=None, ge=0)
    requirements: Optional[list[str]] = None
    shift_label: Optional[str] = None
    notes: Optional[str] = None
    spans_midnight: Optional[bool] = None


class ScheduleOpenShiftOfferRequest(BaseModel):
    shift_ids: list[int] = Field(default_factory=list)


class ScheduleShiftBatchActionRequest(BaseModel):
    shift_ids: list[int] = Field(default_factory=list)
    action: str


class ScheduleExceptionActionRequest(BaseModel):
    shift_id: int
    code: str
    action: str


class ScheduleExceptionActionBatchRequest(BaseModel):
    week_start: Optional[date] = None
    actions: list[ScheduleExceptionActionRequest] = Field(default_factory=list)


async def _resolve_organization_id(
    db: aiosqlite.Connection,
    *,
    organization_id: Optional[int],
    organization_name: Optional[str],
    vertical: Optional[str],
    contact_name: Optional[str],
    contact_phone: Optional[str],
    contact_email: Optional[str],
) -> Optional[int]:
    if organization_id is not None:
        organization = await queries.get_organization(db, organization_id)
        if organization is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return organization_id

    normalized_name = (organization_name or "").strip()
    if not normalized_name:
        return None

    existing = await queries.get_organization_by_name(db, normalized_name)
    if existing is not None:
        return int(existing["id"])

    return await queries.insert_organization(
        db,
        {
            "name": normalized_name,
            "vertical": vertical,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "contact_email": contact_email,
        },
    )


def _build_location_owner_membership(location: dict) -> Optional[dict]:
    owner_phone = auth_svc.normalize_phone(location.get("manager_phone"))
    if owner_phone is None:
        return None
    return {
        "id": None,
        "location_id": int(location["id"]),
        "entry_kind": "membership",
        "phone": owner_phone,
        "manager_name": location.get("manager_name"),
        "manager_email": location.get("manager_email"),
        "role": "owner",
        "invite_status": "active",
        "invite_channel": "phone",
        "invited_by_phone": owner_phone,
        "accepted_at": location.get("created_at"),
        "revoked_at": None,
        "created_at": location.get("created_at"),
        "updated_at": location.get("updated_at"),
    }


def _list_location_access_memberships(
    location: dict,
    memberships: list[dict],
    pending_invites: list[dict],
) -> list[dict]:
    owner_membership = _build_location_owner_membership(location)
    rows: list[dict] = []
    seen_phones: set[str] = set()

    if owner_membership is not None:
        seen_phones.add(owner_membership["phone"])
        rows.append(owner_membership)

    for membership in memberships:
        phone = auth_svc.normalize_phone(membership.get("phone"))
        if phone is None or phone in seen_phones:
            continue
        normalized = dict(membership)
        normalized["entry_kind"] = "membership"
        normalized["phone"] = phone
        normalized["invite_channel"] = "phone"
        rows.append(normalized)
        seen_phones.add(phone)

    for invite in pending_invites:
        rows.append(
            {
                "id": int(invite["id"]),
                "location_id": int(invite["location_id"]),
                "entry_kind": "invite",
                "phone": invite.get("claimed_phone"),
                "manager_name": invite.get("claimed_name") or invite.get("manager_name"),
                "manager_email": invite.get("invite_email"),
                "role": invite.get("role") or "manager",
                "invite_status": invite.get("status") or "pending",
                "invite_channel": "email",
                "invited_by_phone": invite.get("invited_by_phone"),
                "accepted_at": invite.get("accepted_at"),
                "revoked_at": invite.get("revoked_at"),
                "created_at": invite.get("created_at"),
                "updated_at": invite.get("updated_at"),
            }
        )

    return rows


def _new_invite_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(24)}"


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _build_manager_invite_link(raw_token: str) -> str:
    return f"{settings.backfill_web_base_url}/onboarding?invite={quote(raw_token)}"


def _build_manager_invite_email_content(
    *,
    location: dict,
    manager_name: Optional[str],
    raw_token: str,
    recipient_has_phone: bool,
    inviting_user_name: Optional[str],
) -> tuple[str, str, str]:
    location_label = location.get("place_location_label") or location.get("name") or "this location"
    business_name = (
        location.get("organization_name")
        or location.get("place_brand_name")
        or location.get("name")
        or "Backfill"
    )
    invite_url = _build_manager_invite_link(raw_token)
    inviter = (inviting_user_name or location.get("manager_name") or "A Backfill manager").strip() or "A Backfill manager"
    subject = (
        f"Backfill: {inviter} invited you to manage {business_name} · {location_label}"
    )
    call_to_action = "Click the link below to accept this invitation and sign in." if recipient_has_phone else (
        "Click the link below to accept this invitation and get your account setup."
    )
    body_blurb = (
        f"{inviter} has invited you to manage {business_name} · {location_label} in Backfill. "
        f"{call_to_action}"
    )
    text_body = "\n\n".join(
        [
            body_blurb,
            f"Accept the invitation: {invite_url}",
            "Backfill handles callouts and last-minute shift changes automatically — so you never have to.",
            "If you weren’t expecting this invite, just ignore this email.",
        ]
    )
    html_body = (
        "<div style=\"font-family: 'Helvetica Neue', Arial, sans-serif; color: #1f1f1f; max-width: 600px; margin: 0 auto; padding: 0 16px;\">\n"
        "  <div style=\"display:flex; justify-content:space-between; align-items:center; padding-top:24px;\">\n"
        "    <div style=\"font-weight:700; font-size:1.25rem;\">Backfill</div>\n"
        "    <div style=\"font-weight:600; font-size:0.85rem; color:#6b6b6b;\">Callouts covered.</div>\n"
        "  </div>\n"
        "  <div style=\"margin-top:32px; padding:24px; background:#f8f8f8; border-radius:16px; border:1px solid #e0e0e0;\">\n"
        "    <p style=\"font-size:2rem; font-weight:700; margin:0 0 16px;\">You've been invited to manage Backfill</p>\n"
        f"    <p style=\"margin:0 0 24px; color:#4d4d4d; font-size:1rem;\">{body_blurb}</p>\n"
        f"    <a href=\"{invite_url}\" style=\"display:inline-block; padding:12px 28px; background:#1f1f1f; color:#fff; text-decoration:none; border-radius:99px; font-weight:600;\">Accept invitation</a>\n"
        "  </div>\n"
        "  <p style=\"margin:28px 0 0; color:#4d4d4d; font-size:0.9rem;\">Backfill handles callouts and last-minute shift changes automatically — so you never have to.</p>\n"
        "  <p style=\"margin-top:8px; color:#a1a1a1; font-size:0.8rem;\">If you believe this email was sent in error, just ignore it.</p>\n"
        "</div>"
    )
    return subject, text_body, html_body


def _ops_job_idempotency_key(job_type: str, **parts: object) -> str:
    bucket = datetime.utcnow().strftime("%Y%m%d%H%M")
    serialized = ":".join(f"{key}={parts[key]}" for key in sorted(parts))
    return f"ops:{job_type}:{serialized}:{bucket}"


def _twilio_runtime_debug_payload(step: Optional[str] = None) -> dict:
    account_sid = settings.twilio_account_sid or ""
    verify_service_sid = settings.twilio_verify_service_sid or ""
    return {
        "step": step,
        "host": socket.gethostname(),
        "process_id": os.getpid(),
        "railway_project_name": os.environ.get("RAILWAY_PROJECT_NAME"),
        "railway_service_name": os.environ.get("RAILWAY_SERVICE_NAME"),
        "railway_environment_name": os.environ.get("RAILWAY_ENVIRONMENT_NAME"),
        "railway_replica_id": os.environ.get("RAILWAY_REPLICA_ID"),
        "railway_deployment_id": os.environ.get("RAILWAY_DEPLOYMENT_ID"),
        "commit_sha": os.environ.get("RAILWAY_GIT_COMMIT_SHA")
        or os.environ.get("VERCEL_GIT_COMMIT_SHA"),
        "twilio_account_sid_present": bool(account_sid),
        "twilio_account_sid_prefix": account_sid[:2] if account_sid else None,
        "twilio_auth_token_present": bool(settings.twilio_auth_token),
        "twilio_verify_service_sid_present": bool(verify_service_sid),
        "twilio_verify_service_sid_prefix": verify_service_sid[:2] if verify_service_sid else None,
    }


def _twilio_runtime_error_detail(detail: str, *, step: str) -> str:
    payload = _twilio_runtime_debug_payload(step)
    parts = [
        detail,
        f"step={payload['step']}",
        f"host={payload['host']}",
        f"pid={payload['process_id']}",
        f"service={payload['railway_service_name'] or 'unknown'}",
        f"env={payload['railway_environment_name'] or 'unknown'}",
        f"replica={payload['railway_replica_id'] or 'unknown'}",
        f"twilio_account_sid_present={str(payload['twilio_account_sid_present']).lower()}",
        f"twilio_auth_token_present={str(payload['twilio_auth_token_present']).lower()}",
        f"twilio_verify_service_sid_present={str(payload['twilio_verify_service_sid_present']).lower()}",
        f"twilio_verify_service_sid_prefix={payload['twilio_verify_service_sid_prefix'] or 'missing'}",
    ]
    return " ".join(parts)


def _set_dashboard_session_cookie(response: Response, session_token: str) -> None:
    response.set_cookie(
        key=auth_svc.session_cookie_name(),
        value=session_token,
        max_age=auth_svc.session_cookie_max_age_seconds(),
        httponly=True,
        secure=auth_svc.session_cookie_secure(),
        samesite=auth_svc.session_cookie_samesite(),
        domain=auth_svc.session_cookie_domain(),
        path="/",
    )


def _clear_dashboard_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=auth_svc.session_cookie_name(),
        domain=auth_svc.session_cookie_domain(),
        path="/",
        secure=auth_svc.session_cookie_secure(),
        httponly=True,
        samesite=auth_svc.session_cookie_samesite(),
    )


@router.post(
    "/auth/request-access",
    response_model=DashboardAccessRequestResponse,
    dependencies=[Depends(rate_limit.limit_by_request_key("auth_request", limit=5, window_seconds=300))],
)
async def request_dashboard_access(
    body: DashboardAccessRequestBody,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await auth_svc.request_dashboard_access(db, phone=body.phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=_twilio_runtime_error_detail(str(exc), step="request-access"),
        ) from exc


@router.post(
    "/auth/request-step-up",
    response_model=DashboardAccessRequestResponse,
    dependencies=[Depends(rate_limit.limit_by_request_key("auth_step_up", limit=5, window_seconds=300))],
)
async def request_dashboard_step_up(
    body: DashboardStepUpRequestBody,
    db: aiosqlite.Connection = Depends(get_db),
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
):
    try:
        return await auth_svc.request_dashboard_step_up(
            db,
            principal=principal,
            purpose=body.purpose,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=_twilio_runtime_error_detail(str(exc), step="request-step-up"),
        ) from exc


@router.post(
    "/auth/exchange",
    response_model=DashboardAuthResponse,
    dependencies=[Depends(rate_limit.limit_by_request_key("auth_exchange", limit=12, window_seconds=300))],
)
async def exchange_dashboard_access(
    body: DashboardAccessExchangeBody,
    response: Response,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        if body.token:
            session_token, principal = await auth_svc.exchange_dashboard_access_token(
                db,
                token=body.token,
            )
        elif body.request_id is not None and body.code is not None:
            session_token, principal = await auth_svc.verify_dashboard_access_code(
                db,
                request_id=body.request_id,
                code=body.code,
            )
        else:
            raise ValueError("Provide either an access token or a request_id and verification code")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=_twilio_runtime_error_detail(str(exc), step="exchange"),
        ) from exc
    if session_token:
        _set_dashboard_session_cookie(response, session_token)
    payload = await auth_svc.build_auth_response_payload(db, principal)
    return {
        **payload,
        "session_token": session_token,
    }


@router.get("/auth/debug/twilio-runtime", response_model=TwilioRuntimeDebugResponse)
async def get_twilio_runtime_debug(step: Optional[str] = Query(default=None, max_length=64)):
    return _twilio_runtime_debug_payload(step)


@router.get("/auth/me", response_model=DashboardAuthResponse)
async def get_dashboard_auth_me(
    db: aiosqlite.Connection = Depends(get_db),
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
):
    return await auth_svc.build_auth_response_payload(db, principal)


@router.post("/auth/logout", response_model=DashboardAuthResponse)
async def logout_dashboard_session(
    response: Response,
    db: aiosqlite.Connection = Depends(get_db),
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
):
    await auth_svc.revoke_dashboard_session(db, principal)
    _clear_dashboard_session_cookie(response)
    return await auth_svc.build_auth_response_payload(db, principal)


@router.post("/auth/complete-onboarding", response_model=DashboardAuthResponse)
async def complete_dashboard_onboarding(
    body: DashboardOnboardingCompleteRequest,
    db: aiosqlite.Connection = Depends(get_db),
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
):
    manager_name = body.manager_name.strip()
    manager_email = body.manager_email.strip().lower()
    if not manager_name:
        raise HTTPException(status_code=400, detail="Manager name is required")
    if "@" not in manager_email:
        raise HTTPException(status_code=400, detail="A valid email is required")
    if not principal.subject_phone:
        raise HTTPException(status_code=403, detail="Verified operator phone is required")

    updated_count = await queries.complete_location_memberships_for_phone(
        db,
        phone=principal.subject_phone,
        manager_name=manager_name,
        manager_email=manager_email,
    )
    if updated_count == 0:
        raise HTTPException(
            status_code=400,
            detail="There are no invited manager profiles waiting for completion.",
        )

    await auth_svc.refresh_dashboard_session_access(db, principal)
    return await auth_svc.build_auth_response_payload(db, principal)


@router.get(
    "/places/autocomplete",
    response_model=PlaceAutocompleteResponse,
    dependencies=[
        Depends(
            rate_limit.limit_by_request_key(
                "places_autocomplete",
                limit=60,
                window_seconds=60,
                key_func=auth_svc.request_rate_limit_key,
            )
        )
    ],
)
async def get_places_autocomplete(
    q: str = Query(..., min_length=2, max_length=120),
    session_token: Optional[str] = Query(default=None, max_length=256),
    latitude: Optional[float] = Query(default=None, ge=-90, le=90),
    longitude: Optional[float] = Query(default=None, ge=-180, le=180),
    radius_meters: Optional[float] = Query(default=None, gt=0, le=50000),
):
    try:
        payload = await places_svc.autocomplete_places(
            q,
            session_token=session_token,
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=_google_places_error_detail(exc, "Places autocomplete")) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Places autocomplete unavailable") from exc
    return {
        "query": q.strip(),
        "provider": payload["provider"],
        "suggestions": payload["suggestions"],
    }


@router.get(
    "/places/details",
    response_model=PlaceDetailsResponse,
    dependencies=[
        Depends(
            rate_limit.limit_by_request_key(
                "places_details",
                limit=60,
                window_seconds=60,
                key_func=auth_svc.request_rate_limit_key,
            )
        )
    ],
)
async def get_place_details(
    place_id: str = Query(..., min_length=2, max_length=256),
    session_token: Optional[str] = Query(default=None, max_length=256),
):
    try:
        place = await places_svc.get_place_details(place_id, session_token=session_token)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=_google_places_error_detail(exc, "Place lookup")) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Place lookup unavailable") from exc
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return {
        "provider": place["provider"],
        "place": place,
    }


@router.post("/ai-actions/web", response_model=AiActionResponse)
async def post_ai_web_action(
    body: AiWebActionRequest,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        await auth_svc.ensure_location_access(db, principal, body.location_id)
        return await ai_actions_svc.handle_web_action(
            db,
            principal=principal,
            location_id=body.location_id,
            text=body.text,
            context=body.context,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/ai-actions/{action_request_id}", response_model=AiActionResponse)
async def get_ai_action_request(
    action_request_id: int,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.get_action_request_detail(
            db,
            principal=principal,
            action_request_id=action_request_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/ai-actions/{action_request_id}/debug", response_model=AiActionDebugResponse)
async def get_ai_action_request_debug(
    action_request_id: int,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.get_action_request_debug_detail(
            db,
            principal=principal,
            action_request_id=action_request_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/ai-actions/{action_request_id}/confirm", response_model=AiActionResponse)
async def confirm_ai_action_request(
    action_request_id: int,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.confirm_action_request(
            db,
            principal=principal,
            action_request_id=action_request_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 409 if "awaiting confirmation" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/ai-actions/{action_request_id}/clarify", response_model=AiActionResponse)
async def clarify_ai_action_request(
    action_request_id: int,
    body: AiActionClarifyRequest,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.clarify_action_request(
            db,
            principal=principal,
            action_request_id=action_request_id,
            selection=body.selection,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 409 if "awaiting clarification" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/ai-actions/{action_request_id}/cancel", response_model=AiActionResponse)
async def cancel_ai_action_request(
    action_request_id: int,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.cancel_action_request(
            db,
            principal=principal,
            action_request_id=action_request_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/ai-actions/{action_request_id}/retry", response_model=AiActionResponse)
async def retry_ai_action_request(
    action_request_id: int,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.retry_action_request(
            db,
            principal=principal,
            action_request_id=action_request_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 409 if "still active" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/ai-actions/{action_request_id}/feedback", response_model=AiActionFeedbackResponse)
async def submit_ai_action_feedback(
    action_request_id: int,
    body: AiActionFeedbackRequest,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.record_action_feedback(
            db,
            principal=principal,
            action_request_id=action_request_id,
            feedback=body.model_dump(mode="json"),
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/locations/{location_id}/ai-active-sessions", response_model=AiActiveSessionsResponse)
async def get_location_ai_active_sessions(
    location_id: int,
    include_expired: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.list_location_active_sessions(
            db,
            principal=principal,
            location_id=location_id,
            include_expired=include_expired,
            limit=limit,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/locations/{location_id}/ai-action-history", response_model=AiActionHistoryResponse)
async def get_location_ai_action_history(
    location_id: int,
    status: Optional[str] = Query(default=None),
    channel: Optional[str] = Query(default=None),
    fallback_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.list_location_action_history(
            db,
            principal=principal,
            location_id=location_id,
            status=status,
            channel=channel,
            fallback_only=fallback_only,
            limit=limit,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/locations/{location_id}/ai-action-attention", response_model=AiActionAttentionResponse)
async def get_location_ai_action_attention(
    location_id: int,
    include_resolved: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.list_location_action_attention(
            db,
            principal=principal,
            location_id=location_id,
            include_resolved=include_resolved,
            limit=limit,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/locations/{location_id}/ai-runtime-stats", response_model=AiRuntimeStatsResponse)
async def get_location_ai_runtime_stats(
    location_id: int,
    days: int = Query(default=7, ge=1, le=90),
    channel: Optional[str] = Query(default=None),
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.get_location_runtime_stats(
            db,
            principal=principal,
            location_id=location_id,
            days=days,
            channel=channel,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/locations/{location_id}/ai-capabilities", response_model=AiCapabilitiesResponse)
async def get_location_ai_capabilities(
    location_id: int,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.get_location_ai_capabilities(
            db,
            principal=principal,
            location_id=location_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 403 if "forbidden" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/organizations", response_model=Organization, status_code=201)
async def create_organization(
    body: OrganizationCreate,
    db: aiosqlite.Connection = Depends(get_db),
):
    existing = await queries.get_organization_by_name(db, body.name)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Organization already exists")
    organization_id = await queries.insert_organization(db, body.model_dump(mode="json"))
    return {**body.model_dump(mode="json"), "id": organization_id}


@router.get("/organizations", response_model=List[Organization])
async def list_organizations(db: aiosqlite.Connection = Depends(get_db)):
    return await queries.list_organizations(db)


@router.get("/organizations/{organization_id}", response_model=Organization)
async def get_organization(
    organization_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await queries.get_organization(db, organization_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return row

@router.post("/locations", response_model=Location, status_code=201)
async def create_location(
    body: LocationCreate,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db)
):
    principal = auth_svc.get_request_principal(request)
    if principal is not None and principal.is_setup:
        raise HTTPException(status_code=403, detail="Setup token cannot create a new location")
    data = body.model_dump(mode="json")
    if principal is not None and principal.is_session and principal.subject_phone:
        submitted_manager_phone = auth_svc.normalize_phone(data.get("manager_phone"))
        if submitted_manager_phone and submitted_manager_phone != principal.subject_phone:
            raise HTTPException(status_code=400, detail="Verified phone number must match the manager phone on the location")
        data["manager_phone"] = principal.subject_phone
    inferred_vertical = _infer_vertical_from_place(data)
    if inferred_vertical:
        data["place_inferred_vertical"] = inferred_vertical
        if "vertical" not in body.model_fields_set:
            data["vertical"] = inferred_vertical
    data["organization_id"] = await _resolve_organization_id(
        db,
        organization_id=data.get("organization_id"),
        organization_name=data.get("organization_name"),
        vertical=data.get("vertical"),
        contact_name=data.get("manager_name"),
        contact_phone=data.get("manager_phone"),
        contact_email=data.get("manager_email"),
    )
    data.pop("organization_name", None)
    location_id = await queries.insert_location(db, data)
    if principal is not None and principal.is_session and principal.subject_phone:
        await queries.upsert_location_membership(
            db,
            location_id=location_id,
            phone=principal.subject_phone,
            manager_name=data.get("manager_name"),
            manager_email=data.get("manager_email"),
            role="owner",
            invite_status="active",
            invited_by_phone=principal.subject_phone,
            accepted_at=datetime.utcnow().isoformat(),
        )
    if principal is not None and principal.is_session:
        await auth_svc.refresh_dashboard_session_access(db, principal)
    await audit_svc.append(
        db,
        AuditAction.location_created,
        entity_type="location",
        entity_id=location_id,
    )
    created = await queries.get_location(db, location_id)
    assert created is not None
    return created


@router.post("/locations/{location_id}/preview-bootstrap")
async def bootstrap_preview_location(
    location_id: int,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    principal = auth_svc.get_request_principal(request)
    if principal is not None and not principal.is_internal:
        await auth_svc.ensure_location_access(db, principal, location_id)
    elif settings.backfill_dashboard_auth_required:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await preview_bootstrap_svc.bootstrap_preview_location(
            db,
            location_id=location_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/locations", response_model=List[Location])
async def list_locations(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await queries.list_locations(db)
    principal = auth_svc.get_request_principal(request)
    if principal is None:
        return []
    return auth_svc.filter_locations_for_principal(rows, principal)


@router.get("/locations/{location_id}", response_model=Location)
async def get_location(
    location_id: int, db: aiosqlite.Connection = Depends(get_db)
):
    row = await queries.get_location(db, location_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return row


@router.get("/locations/{location_id}/settings", response_model=LocationSettingsResponse)
async def get_location_settings(
    location_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await queries.get_location(db, location_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return {
        "location_id": location_id,
        "scheduling_platform": row.get("scheduling_platform"),
        "operating_mode": row.get("operating_mode"),
        "timezone": row.get("timezone"),
        "writeback_enabled": bool(row.get("writeback_enabled")),
        "backfill_shifts_enabled": bool(row.get("backfill_shifts_enabled", True)),
        "backfill_shifts_launch_state": row.get("backfill_shifts_launch_state") or "enabled",
        "backfill_shifts_beta_eligible": bool(row.get("backfill_shifts_beta_eligible")),
        "coverage_requires_manager_approval": bool(row.get("coverage_requires_manager_approval")),
        "late_arrival_policy": row.get("late_arrival_policy") or "wait",
        "missed_check_in_policy": row.get("missed_check_in_policy") or "start_coverage",
        "agency_supply_approved": bool(row.get("agency_supply_approved")),
    }


@router.get("/locations/{location_id}/status", response_model=LocationStatusResponse)
async def get_location_status(
    location_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import scheduling as scheduling_svc

    payload = await queries.get_location_status(db, location_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Location not found")
    payload["integration"] = await scheduling_svc.get_integration_health(db, location_id)
    return payload


@router.get("/locations/{location_id}/roster")
async def get_location_roster(
    location_id: int,
    include_inactive: bool = Query(default=True),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await roster_svc.list_roster_for_location(
            db,
            location_id=location_id,
            include_inactive=include_inactive,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/locations/{location_id}/eligible-workers")
async def get_location_eligible_workers(
    location_id: int,
    role: Optional[str] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await roster_svc.list_eligible_workers(
            db,
            location_id=location_id,
            role=role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/locations/{location_id}/manager-memberships",
    response_model=List[LocationManagerMembershipResponse],
)
async def list_location_manager_memberships(
    location_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    memberships = await queries.list_location_memberships_for_location(db, location_id)
    pending_invites = await queries.list_location_manager_invites_for_location(
        db,
        location_id,
    )
    return _list_location_access_memberships(location, memberships, pending_invites)


@router.post(
    "/locations/{location_id}/manager-memberships",
    response_model=LocationManagerInviteResponse,
)
async def invite_location_manager(
    location_id: int,
    body: LocationManagerInviteRequest,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")

    invite_email = body.email.strip().lower()
    if "@" not in invite_email:
        raise HTTPException(status_code=400, detail="A valid email is required")

    raw_token = _new_invite_token("bfinvite")
    existing = await queries.get_location_manager_invite_by_email(
        db,
        location_id=location_id,
        invite_email=invite_email,
        include_revoked=True,
    )
    existing_membership = await queries.get_location_membership_by_email(db, invite_email)
    inviter_membership = (
        await queries.get_location_membership_by_phone(
            db,
            location_id,
            principal.subject_phone or "",
        )
        if principal.subject_phone
        else None
    )
    membership = await queries.upsert_location_manager_invite(
        db,
        location_id=location_id,
        invite_email=invite_email,
        manager_name=(body.manager_name or "").strip() or None,
        role="manager",
        token_hash=_hash_token(raw_token),
        invited_by_phone=principal.subject_phone,
        expires_at=(
            datetime.utcnow()
            + timedelta(hours=settings.backfill_location_invite_ttl_hours)
        ).isoformat(),
    )

    delivery_id: Optional[str] = None
    try:
        subject, text_body, html_body = _build_manager_invite_email_content(
            location=location,
            manager_name=membership.get("manager_name"),
            raw_token=raw_token,
            recipient_has_phone=bool(existing_membership and existing_membership.get("phone")),
            inviting_user_name=(inviter_membership or {}).get("manager_name") if inviter_membership else None,
        )
        delivery_id = messaging_svc.send_email(
            invite_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to send manager invite email for location_id=%s", location_id)
        raise HTTPException(status_code=502, detail="Could not send manager invite email") from exc

    await audit_svc.append(
        db,
        AuditAction.location_manager_invited,
        actor=principal.subject_phone or "unknown",
        entity_type="location",
        entity_id=location_id,
        details={
            "invited_email": invite_email,
            "manager_name": membership.get("manager_name"),
            "created": existing is None,
            "invite_status": membership.get("status"),
            "recipient_has_phone": bool(existing_membership and existing_membership.get("phone")),
        },
    )
    return {
        "location_id": location_id,
        "created": existing is None or existing.get("status") == "revoked",
        "delivery_id": delivery_id,
        "membership": {
            "id": int(membership["id"]),
            "location_id": int(membership["location_id"]),
            "entry_kind": "invite",
            "phone": membership.get("claimed_phone"),
            "manager_name": membership.get("claimed_name") or membership.get("manager_name"),
            "manager_email": membership.get("invite_email"),
            "role": membership.get("role") or "manager",
            "invite_status": membership.get("status") or "pending",
            "invite_channel": "email",
            "invited_by_phone": membership.get("invited_by_phone"),
            "accepted_at": membership.get("accepted_at"),
            "revoked_at": membership.get("revoked_at"),
            "created_at": membership.get("created_at"),
            "updated_at": membership.get("updated_at"),
        },
    }


@router.delete(
    "/locations/{location_id}/manager-memberships/{membership_id}",
    response_model=LocationManagerRevokeResponse,
)
async def revoke_location_manager(
    location_id: int,
    membership_id: int,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    membership = await queries.get_location_membership(db, membership_id)
    if membership is None or int(membership["location_id"]) != location_id:
        raise HTTPException(status_code=404, detail="Manager invite not found")
    if membership.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Owner access cannot be removed here")

    await queries.revoke_location_membership(db, membership_id)
    await audit_svc.append(
        db,
        AuditAction.location_manager_revoked,
        actor=principal.subject_phone or "unknown",
        entity_type="location",
        entity_id=location_id,
        details={
            "revoked_phone": membership.get("phone"),
            "membership_id": membership_id,
        },
    )
    return {
        "revoked": True,
        "location_id": location_id,
        "access_kind": "membership",
        "access_id": membership_id,
    }


@router.delete(
    "/locations/{location_id}/manager-invites/{invite_id}",
    response_model=LocationManagerRevokeResponse,
)
async def revoke_location_manager_invite(
    location_id: int,
    invite_id: int,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    invite = await queries.get_location_manager_invite(db, invite_id)
    if invite is None or int(invite["location_id"]) != location_id:
        raise HTTPException(status_code=404, detail="Manager invite not found")

    await queries.revoke_location_manager_invite(db, invite_id)
    await audit_svc.append(
        db,
        AuditAction.location_manager_revoked,
        actor=principal.subject_phone or "unknown",
        entity_type="location",
        entity_id=location_id,
        details={
            "invited_email": invite.get("invite_email"),
            "access_kind": "invite",
            "invite_id": invite_id,
        },
    )
    return {
        "revoked": True,
        "location_id": location_id,
        "access_kind": "invite",
        "access_id": invite_id,
    }


@router.get(
    "/location-manager-invites/{token}",
    response_model=LocationManagerInvitePreviewResponse,
)
async def get_location_manager_invite_preview(
    token: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    invite = await queries.get_location_manager_invite_by_token_hash(
        db,
        _hash_token(token),
    )
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.get("status") != "pending" or auth_svc._is_expired(invite.get("expires_at")):
        raise HTTPException(status_code=410, detail="Invite has expired")

    location = await queries.get_location(db, int(invite["location_id"]))
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")

    business_name = (
        location.get("organization_name")
        or location.get("place_brand_name")
        or location.get("name")
        or "Backfill"
    )
    location_name = location.get("place_location_label") or location.get("name") or "Assigned location"
    return {
        "invite_email": invite.get("invite_email"),
        "manager_name": invite.get("manager_name"),
        "business_name": business_name,
        "location_id": int(location["id"]),
        "location_name": location_name,
        "location_address": location.get("address") or location.get("place_formatted_address"),
        "expires_at": invite.get("expires_at"),
        "invite_status": invite.get("status") or "pending",
    }


@router.post(
    "/location-manager-invites/{token}/request-access",
    response_model=DashboardAccessRequestResponse,
    dependencies=[Depends(rate_limit.limit_by_request_key("auth_request", limit=5, window_seconds=300))],
)
async def request_location_manager_invite_access(
    token: str,
    body: LocationManagerInviteAccessRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await auth_svc.request_dashboard_access_for_location_invite(
            db,
            invite_token=token,
            manager_name=body.manager_name,
            phone=body.phone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=_twilio_runtime_error_detail(str(exc), step="invite-request-access"),
        ) from exc


@router.get("/locations/{location_id}/enrollment-invite-preview", response_model=EnrollmentInvitePreviewResponse)
async def get_enrollment_invite_preview(
    location_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return {
        "location_id": location_id,
        "join_number": settings.backfill_phone_number,
        "join_keyword": "JOIN",
        "sms_copy": notifications_svc.build_worker_enrollment_invite_text(
            location_name=location["name"],
            organization_name=location.get("organization_name"),
        ),
    }


@router.post("/locations/{location_id}/enrollment-invites")
async def send_enrollment_invites(
    location_id: int,
    body: EnrollmentInviteSendRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await roster_svc.send_enrollment_invites_for_location(
            db,
            location_id=location_id,
            worker_ids=body.worker_ids,
            include_enrolled=body.include_enrolled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/locations/{location_id}", response_model=Location)
async def update_location(
    location_id: int,
    body: LocationUpdate,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await queries.get_location(db, location_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Location not found")
    principal = auth_svc.get_request_principal(request)
    if principal is not None and not principal.is_internal:
        await auth_svc.ensure_location_access(db, principal, location_id)
    payload = body.model_dump(mode="json", exclude_none=True)
    if principal is not None and principal.is_session and "manager_phone" in payload:
        current_phone = auth_svc.normalize_phone(row.get("manager_phone"))
        next_phone = auth_svc.normalize_phone(payload.get("manager_phone"))
        if next_phone != current_phone:
            await auth_svc.require_recent_step_up(
                db,
                principal,
                reason="phone_number_update",
            )
    inferred_vertical = _infer_vertical_from_place(payload)
    if inferred_vertical:
        payload["place_inferred_vertical"] = inferred_vertical
        if "vertical" not in body.model_fields_set and not row.get("vertical"):
            payload["vertical"] = inferred_vertical
    if "organization_id" in payload or "organization_name" in payload:
        payload["organization_id"] = await _resolve_organization_id(
            db,
            organization_id=payload.get("organization_id"),
            organization_name=payload.get("organization_name"),
            vertical=payload.get("vertical") or row.get("vertical"),
            contact_name=payload.get("manager_name") or row.get("manager_name"),
            contact_phone=payload.get("manager_phone") or row.get("manager_phone"),
            contact_email=payload.get("manager_email") or row.get("manager_email"),
        )
        payload.pop("organization_name", None)
    await queries.update_location(db, location_id, payload)
    return await queries.get_location(db, location_id)


@router.delete("/locations/{location_id}", response_model=LocationDeleteResponse)
async def delete_location(
    location_id: int,
    principal: auth_svc.AuthPrincipal = Depends(auth_svc.require_dashboard_session),
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await queries.get_location(db, location_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Location not found")

    await auth_svc.ensure_location_access(db, principal, location_id)

    if not principal.subject_phone:
        raise HTTPException(status_code=403, detail="Verified operator phone is required")

    location_phone = auth_svc.normalize_phone(row.get("manager_phone"))
    if location_phone != principal.subject_phone:
        raise HTTPException(
            status_code=403,
            detail="Only the verified operator attached to this location can delete it",
        )

    try:
        await queries.delete_location(db, location_id)
    except aiosqlite.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="This location already has operational data and cannot be deleted from the account profile.",
        ) from exc

    await auth_svc.refresh_dashboard_session_access(db, principal)
    await audit_svc.append(
        db,
        AuditAction.location_deleted,
        actor=principal.subject_phone,
        entity_type="location",
        entity_id=location_id,
        details={"name": row.get("name"), "organization_id": row.get("organization_id")},
    )
    return {"deleted": True, "location_id": location_id}


@router.patch("/locations/{location_id}/settings", response_model=LocationSettingsResponse)
async def update_location_settings(
    location_id: int,
    body: LocationSettingsUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await queries.get_location(db, location_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Location not found")
    payload = body.model_dump(mode="json", exclude_none=True)
    if payload:
        await queries.update_location(db, location_id, payload)
        row = await queries.get_location(db, location_id)
        assert row is not None
    return {
        "location_id": location_id,
        "scheduling_platform": row.get("scheduling_platform"),
        "operating_mode": row.get("operating_mode"),
        "timezone": row.get("timezone"),
        "writeback_enabled": bool(row.get("writeback_enabled")),
        "backfill_shifts_enabled": bool(row.get("backfill_shifts_enabled", True)),
        "backfill_shifts_launch_state": row.get("backfill_shifts_launch_state") or "enabled",
        "backfill_shifts_beta_eligible": bool(row.get("backfill_shifts_beta_eligible")),
        "coverage_requires_manager_approval": bool(row.get("coverage_requires_manager_approval")),
        "late_arrival_policy": row.get("late_arrival_policy") or "wait",
        "missed_check_in_policy": row.get("missed_check_in_policy") or "start_coverage",
        "agency_supply_approved": bool(row.get("agency_supply_approved")),
    }


@router.get(
    "/locations/{location_id}/backfill-shifts-metrics",
    response_model=LocationBackfillShiftsMetricsResponse,
)
async def get_location_backfill_shifts_metrics(
    location_id: int,
    days: int = Query(default=30, ge=1, le=365),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_location_backfill_shifts_metrics(
            db,
            location_id=location_id,
            days=days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/locations/{location_id}/backfill-shifts-activity",
    response_model=LocationBackfillShiftsActivityResponse,
)
async def get_location_backfill_shifts_activity(
    location_id: int,
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_location_backfill_shifts_activity(
            db,
            location_id=location_id,
            days=days,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/retell/reconcile")
async def reconcile_retell_activity(
    body: RetellReconcileRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    if body.call_id:
        return await retell_reconcile.sync_call_by_id(db, body.call_id)
    if body.chat_id:
        return await retell_reconcile.sync_chat_by_id(db, body.chat_id)
    return await retell_reconcile.sync_recent_activity(
        db,
        lookback_minutes=body.lookback_minutes,
        limit=body.limit,
    )


@router.post("/locations/{location_id}/sync-roster")
async def sync_location_roster(
    location_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import scheduling as scheduling_svc

    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        return await scheduling_svc.sync_roster(db, location_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/locations/{location_id}/sync-schedule")
async def sync_location_schedule(
    location_id: int,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import scheduling as scheduling_svc

    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    effective_start = start_date or date.today()
    effective_end = end_date or (effective_start + timedelta(days=14))
    try:
        return await scheduling_svc.sync_schedule(db, location_id, effective_start, effective_end)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/locations/{location_id}/connect-sync")
async def connect_and_sync_location(
    location_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import scheduling as scheduling_svc

    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        return await scheduling_svc.connect_and_sync_location(db, location_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/locations/{location_id}/import-jobs", status_code=201)
async def create_import_job(
    location_id: int,
    body: ImportJobCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    job_id = await queries.insert_import_job(
        db,
        {
            "location_id": location_id,
            "import_type": body.import_type,
            "filename": body.filename,
            "status": "uploaded",
            "summary_json": {
                "total_rows": 0,
                "worker_rows": 0,
                "shift_rows": 0,
                "success_rows": 0,
                "warning_rows": 0,
                "failed_rows": 0,
            },
        },
    )
    await audit_svc.append(
        db,
        AuditAction.import_job_created,
        entity_type="import_job",
        entity_id=job_id,
        details={"location_id": location_id, "import_type": body.import_type},
    )
    job = await queries.get_import_job(db, job_id)
    assert job is not None
    return {
        "id": job["id"],
        "location_id": job["location_id"],
        "import_type": job["import_type"],
        "status": job["status"],
        "filename": job.get("filename"),
        "summary": job.get("summary_json") or {},
    }


@router.post("/import-jobs/{job_id}/upload")
async def upload_import_job(
    job_id: int,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    job = await queries.get_import_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    content = await file.read(backfill_shifts_svc.MAX_CSV_BYTES + 1)
    try:
        return await backfill_shifts_svc.upload_import_file(
            db,
            job_id=job_id,
            filename=file.filename or job.get("filename") or "import.csv",
            content=content,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 413 if "exceeds 10 MB" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/import-jobs/{job_id}/mapping")
async def save_import_job_mapping(
    job_id: int,
    body: ImportJobMappingRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.validate_import_mapping(
            db,
            job_id=job_id,
            mapping=body.mapping,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/import-jobs/{job_id}/rows")
async def list_import_job_rows(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    job = await queries.get_import_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return {
        "job": {
            "id": job["id"],
            "status": job["status"],
        },
        "rows": await queries.list_import_row_results(db, job_id),
    }


@router.patch("/import-rows/{row_id}")
async def resolve_import_row(
    row_id: int,
    body: ImportRowResolutionRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.resolve_import_row(
            db,
            row_id=row_id,
            action=body.action,
            normalized_payload=body.normalized_payload,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/import-jobs/{job_id}/error-csv")
async def export_import_job_error_csv(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.export_import_errors_csv(db, job_id=job_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/import-jobs/{job_id}/commit")
async def commit_import_job(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.commit_import_job(db, job_id=job_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/locations/{location_id}/schedules/current")
async def get_current_schedule(
    location_id: int,
    week_start: Optional[date] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return await backfill_shifts_svc.get_schedule_view(
        db,
        location_id=location_id,
        week_start=week_start.isoformat() if week_start else None,
    )


@router.get("/schedules/{schedule_id}/review")
async def get_schedule_review(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_review(
            db,
            schedule_id=schedule_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedules/{schedule_id}/publish-readiness")
async def get_schedule_publish_readiness(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_publish_readiness(
            db,
            schedule_id=schedule_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedules/{schedule_id}/change-summary")
async def get_schedule_change_summary(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_change_summary(
            db,
            schedule_id=schedule_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedules/{schedule_id}/publish-diff")
async def get_schedule_publish_diff(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_publish_diff(
            db,
            schedule_id=schedule_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedules/{schedule_id}/draft-rationale")
async def get_schedule_draft_rationale(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_draft_rationale(
            db,
            schedule_id=schedule_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedules/{schedule_id}/publish-impact")
async def get_schedule_publish_impact(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_publish_impact(
            db,
            schedule_id=schedule_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedules/{schedule_id}/publish-preview")
async def get_schedule_publish_preview(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_publish_preview(
            db,
            schedule_id=schedule_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedules/{schedule_id}/message-preview")
async def get_schedule_message_preview(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_message_preview(
            db,
            schedule_id=schedule_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedules/{schedule_id}/versions")
async def list_schedule_versions(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.list_schedule_history_versions(
            db,
            schedule_id=schedule_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedules/{schedule_id}/versions/{version_id}/diff")
async def get_schedule_version_diff(
    schedule_id: int,
    version_id: int,
    compare_to: str = Query(default="default"),
    compare_to_version_id: Optional[int] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_version_diff(
            db,
            schedule_id=schedule_id,
            version_id=version_id,
            compare_to=compare_to,
            compare_to_version_id=compare_to_version_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/locations/{location_id}/schedule-exceptions")
async def get_location_schedule_exceptions(
    location_id: int,
    week_start: Optional[date] = Query(default=None),
    action_required_only: bool = Query(default=False),
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return await backfill_shifts_svc.get_schedule_exception_queue(
        db,
        location_id=location_id,
        week_start=week_start.isoformat() if week_start else None,
        action_required_only=action_required_only,
    )


@router.get("/locations/{location_id}/schedule-draft-options")
async def get_location_schedule_draft_options(
    location_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return await backfill_shifts_svc.get_schedule_draft_options(
        db,
        location_id=location_id,
    )


@router.get("/locations/{location_id}/schedule-templates")
async def list_location_schedule_templates(
    location_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return await backfill_shifts_svc.list_schedule_templates(
        db,
        location_id=location_id,
    )


@router.post("/locations/{location_id}/schedule-templates")
async def create_manual_schedule_template(
    location_id: int,
    body: ManualScheduleTemplateCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        return await backfill_shifts_svc.create_manual_schedule_template(
            db,
            location_id=location_id,
            name=body.name,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/schedule-templates/{template_id}")
async def get_schedule_template(
    template_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_template_detail(
            db,
            template_id=template_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/locations/{location_id}/schedule-exceptions/actions")
async def apply_location_schedule_exception_actions(
    location_id: int,
    body: ScheduleExceptionActionBatchRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return await backfill_shifts_svc.apply_schedule_exception_actions(
        db,
        location_id=location_id,
        week_start=body.week_start.isoformat() if body.week_start else None,
        actions=[item.model_dump(mode="json") for item in body.actions],
    )


@router.post("/locations/{location_id}/schedules/copy-last-week")
async def copy_last_week_schedule(
    location_id: int,
    body: CopyScheduleRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.copy_schedule_week(
            db,
            location_id=location_id,
            source_schedule_id=body.source_schedule_id,
            target_week_start_date=body.target_week_start_date.isoformat(),
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 409 if "already exists" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/locations/{location_id}/schedules/create-from-template")
async def create_schedule_from_template_for_location(
    location_id: int,
    body: CreateScheduleFromTemplateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        return await backfill_shifts_svc.create_schedule_from_template_for_location(
            db,
            location_id=location_id,
            template_id=body.template_id,
            target_week_start_date=body.target_week_start_date.isoformat(),
            replace_existing=body.replace_existing,
            day_of_week_filter=body.day_of_week_filter,
            auto_assign_open_shifts=body.auto_assign_open_shifts,
            assignment_strategy=body.assignment_strategy,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 409 if "already has shifts" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/locations/{location_id}/schedules/ai-draft")
async def generate_ai_schedule_draft(
    location_id: int,
    body: GenerateAIScheduleDraftRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        return await backfill_shifts_svc.generate_ai_schedule_draft(
            db,
            location_id=location_id,
            target_week_start_date=body.target_week_start_date.isoformat(),
            template_id=body.template_id,
            source_schedule_id=body.source_schedule_id,
            replace_existing=body.replace_existing,
            day_of_week_filter=body.day_of_week_filter,
            auto_assign_open_shifts=body.auto_assign_open_shifts,
            assignment_strategy=body.assignment_strategy,
            include_assignments_from_source=body.include_assignments_from_source,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 409 if "already has shifts" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedules/{schedule_id}/copy-day")
async def copy_schedule_day(
    schedule_id: int,
    body: ScheduleDayCopyRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.copy_schedule_day(
            db,
            schedule_id=schedule_id,
            source_date=body.source_date.isoformat(),
            target_date=body.target_date.isoformat(),
            copy_assignments=body.copy_assignments,
            replace_target_day=body.replace_target_day,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 409 if "already has shifts" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedules/{schedule_id}/templates")
async def create_schedule_template(
    schedule_id: int,
    body: ScheduleTemplateCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.create_schedule_template_from_schedule(
            db,
            schedule_id=schedule_id,
            name=body.name,
            description=body.description,
            include_assignments=body.include_assignments,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/clone")
async def clone_schedule_template(
    template_id: int,
    body: ScheduleTemplateCloneRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.clone_schedule_template(
            db,
            template_id=template_id,
            name=body.name,
            description=body.description,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.patch("/schedule-templates/{template_id}")
async def update_schedule_template(
    template_id: int,
    body: ScheduleTemplateUpdateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.update_schedule_template(
            db,
            template_id=template_id,
            patch=body.model_dump(mode="json", exclude_unset=True),
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedule-templates/{template_id}/preview")
async def preview_schedule_template(
    template_id: int,
    target_week_start_date: date = Query(...),
    day_of_week: Optional[list[int]] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.preview_schedule_template(
            db,
            template_id=template_id,
            target_week_start_date=target_week_start_date.isoformat(),
            day_of_week_filter=day_of_week,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedule-templates/{template_id}/staffing-plan")
async def get_schedule_template_staffing_plan(
    template_id: int,
    day_of_week: Optional[list[int]] = Query(default=None),
    strategy: str = Query(default="priority_first"),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_template_staffing_plan(
            db,
            template_id=template_id,
            day_of_week_filter=day_of_week,
            assignment_strategy=strategy,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/schedule-templates/{template_id}/suggestions")
async def get_schedule_template_suggestions(
    template_id: int,
    day_of_week: Optional[list[int]] = Query(default=None),
    strategy: str = Query(default="priority_first"),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.get_schedule_template_suggestions(
            db,
            template_id=template_id,
            day_of_week_filter=day_of_week,
            assignment_strategy=strategy,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/refresh")
async def refresh_schedule_template(
    template_id: int,
    body: ScheduleTemplateRefreshRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.refresh_schedule_template_from_schedule(
            db,
            template_id=template_id,
            source_schedule_id=body.source_schedule_id,
            include_assignments=body.include_assignments,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/auto-assign")
async def auto_assign_schedule_template(
    template_id: int,
    body: ScheduleTemplateAutoAssignRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.auto_assign_schedule_template(
            db,
            template_id=template_id,
            overwrite_invalid_assignments=body.overwrite_invalid_assignments,
            day_of_week_filter=body.day_of_week_filter,
            assignment_strategy=body.assignment_strategy,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/suggestions/apply")
async def apply_schedule_template_suggestions(
    template_id: int,
    body: ScheduleTemplateSuggestionsApplyRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.apply_schedule_template_suggestions(
            db,
            template_id=template_id,
            shift_ids=body.shift_ids,
            selections=[item.model_dump(mode="json") for item in body.assignments],
            day_of_week_filter=body.day_of_week_filter,
            overwrite_existing_assignments=body.overwrite_existing_assignments,
            assignment_strategy=body.assignment_strategy,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/assignments/clear")
async def clear_schedule_template_assignments(
    template_id: int,
    body: ScheduleTemplateClearAssignmentsRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.clear_schedule_template_assignments(
            db,
            template_id=template_id,
            shift_ids=body.shift_ids,
            day_of_week_filter=body.day_of_week_filter,
            only_invalid=body.only_invalid,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/shifts")
async def create_schedule_template_shift(
    template_id: int,
    body: ScheduleTemplateShiftCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.create_schedule_template_shift(
            db,
            template_id=template_id,
            slot=body.model_dump(mode="json"),
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/shifts/bulk")
async def create_schedule_template_shifts_bulk(
    template_id: int,
    body: ScheduleTemplateShiftBulkCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.create_schedule_template_shifts_bulk(
            db,
            template_id=template_id,
            slots=[item.model_dump(mode="json") for item in body.slots],
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.patch("/schedule-templates/{template_id}/shifts")
async def update_schedule_template_shifts_bulk(
    template_id: int,
    body: ScheduleTemplateShiftBulkUpdateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        payload = body.model_dump(mode="json", exclude_unset=True)
        shift_ids = payload.pop("shift_ids", [])
        return await backfill_shifts_svc.update_schedule_template_shifts_bulk(
            db,
            template_id=template_id,
            shift_ids=shift_ids,
            patch=payload,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/shifts/duplicate")
async def duplicate_schedule_template_shifts_bulk(
    template_id: int,
    body: ScheduleTemplateShiftBulkDuplicateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.duplicate_schedule_template_shifts_bulk(
            db,
            template_id=template_id,
            shift_ids=body.shift_ids,
            day_of_week=body.day_of_week,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.patch("/schedule-template-shifts/{template_shift_id}")
async def update_schedule_template_shift(
    template_shift_id: int,
    body: ScheduleTemplateShiftUpdateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.update_schedule_template_shift(
            db,
            template_shift_id=template_shift_id,
            patch=body.model_dump(mode="json", exclude_unset=True),
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-template-shifts/{template_shift_id}/duplicate")
async def duplicate_schedule_template_shift(
    template_shift_id: int,
    day_of_week: Optional[int] = Query(default=None, ge=0, le=6),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.duplicate_schedule_template_shift(
            db,
            template_shift_id=template_shift_id,
            day_of_week=day_of_week,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.delete("/schedule-templates/{template_id}")
async def delete_schedule_template(
    template_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.delete_schedule_template(db, template_id=template_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/shifts/delete")
async def delete_schedule_template_shifts_bulk(
    template_id: int,
    body: ScheduleTemplateShiftBulkDeleteRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.delete_schedule_template_shifts_bulk(
            db,
            template_id=template_id,
            shift_ids=body.shift_ids,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.delete("/schedule-template-shifts/{template_shift_id}")
async def delete_schedule_template_shift(
    template_shift_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.delete_schedule_template_shift(
            db,
            template_shift_id=template_shift_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/apply")
async def apply_schedule_template(
    template_id: int,
    body: ScheduleTemplateApplyRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.apply_schedule_template(
            db,
            template_id=template_id,
            target_week_start_date=body.target_week_start_date.isoformat(),
            replace_existing=body.replace_existing,
            day_of_week_filter=body.day_of_week_filter,
            auto_assign_open_shifts=body.auto_assign_open_shifts,
            assignment_strategy=body.assignment_strategy,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = (
            404 if "not found" in detail else 409 if "already has shifts" in detail else 400
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/apply-range")
async def apply_schedule_template_range(
    template_id: int,
    body: ScheduleTemplateRangeApplyRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.apply_schedule_template_range(
            db,
            template_id=template_id,
            target_week_start_dates=[
                item.isoformat() for item in body.target_week_start_dates
            ],
            replace_existing=body.replace_existing,
            day_of_week_filter=body.day_of_week_filter,
            auto_assign_open_shifts=body.auto_assign_open_shifts,
            assignment_strategy=body.assignment_strategy,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedule-templates/{template_id}/generate-draft")
async def generate_schedule_draft_from_template(
    template_id: int,
    body: ScheduleTemplateGenerateDraftRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.generate_schedule_draft_from_template(
            db,
            template_id=template_id,
            target_week_start_date=body.target_week_start_date.isoformat(),
            replace_existing=body.replace_existing,
            day_of_week_filter=body.day_of_week_filter,
            auto_assign_open_shifts=body.auto_assign_open_shifts,
            assignment_strategy=body.assignment_strategy,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = (
            404 if "not found" in detail else 409 if "already has shifts" in detail else 400
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedules/{schedule_id}/publish")
async def publish_schedule(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.publish_schedule(db, schedule_id=schedule_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedules/{schedule_id}/offer-open-shifts")
async def offer_schedule_open_shifts(
    schedule_id: int,
    body: ScheduleOpenShiftOfferRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.offer_open_shifts_for_schedule(
            db,
            schedule_id=schedule_id,
            shift_ids=body.shift_ids,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedules/{schedule_id}/shifts/actions")
async def apply_schedule_shift_actions(
    schedule_id: int,
    body: ScheduleShiftBatchActionRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.apply_schedule_shift_actions(
            db,
            schedule_id=schedule_id,
            shift_ids=body.shift_ids,
            action=body.action,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedules/{schedule_id}/recall")
async def recall_schedule(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.recall_schedule(db, schedule_id=schedule_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedules/{schedule_id}/archive")
async def archive_schedule(
    schedule_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.archive_schedule(db, schedule_id=schedule_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedules/{schedule_id}/shifts")
async def create_schedule_shift(
    schedule_id: int,
    body: ScheduleShiftCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.create_schedule_shift(
            db,
            schedule_id=schedule_id,
            shift_payload=body.model_dump(mode="json"),
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.patch("/shifts/{shift_id}/assignment")
async def update_shift_assignment(
    shift_id: int,
    body: ShiftAssignmentUpdateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.amend_shift_assignment(
            db,
            shift_id=shift_id,
            worker_id=body.worker_id,
            assignment_status=body.assignment_status,
            notes=body.notes,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/schedules/{schedule_id}/shifts/assignments")
async def apply_schedule_shift_assignments(
    schedule_id: int,
    body: BulkShiftAssignmentRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.apply_schedule_shift_assignments(
            db,
            schedule_id=schedule_id,
            assignments=[item.model_dump(mode="json") for item in body.assignments],
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.patch("/schedules/{schedule_id}/shifts")
async def apply_schedule_shift_edits(
    schedule_id: int,
    body: ScheduleShiftBulkEditRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        payload = body.model_dump(mode="json", exclude_unset=True)
        shift_ids = payload.pop("shift_ids", [])
        return await backfill_shifts_svc.apply_schedule_shift_edits(
            db,
            schedule_id=schedule_id,
            shift_ids=shift_ids,
            patch=payload,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.delete("/shifts/{shift_id}")
async def delete_shift(
    shift_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.delete_schedule_shift(db, shift_id=shift_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/locations/{location_id}/coverage")
async def get_location_coverage(
    location_id: int,
    week_start: Optional[date] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return await backfill_shifts_svc.get_coverage_view(
        db,
        location_id=location_id,
        week_start=week_start.isoformat() if week_start else None,
    )


@router.get("/locations/{location_id}/manager-actions")
async def get_location_manager_actions(
    location_id: int,
    week_start: Optional[date] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return await backfill_shifts_svc.get_manager_action_queue(
        db,
        location_id=location_id,
        week_start=week_start.isoformat() if week_start else None,
    )


@router.post("/cascades/{cascade_id}/approve-fill")
async def approve_coverage_fill(
    cascade_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await cascade_svc.approve_pending_claim(db, cascade_id=cascade_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/cascades/{cascade_id}/decline-fill")
async def decline_coverage_fill(
    cascade_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await cascade_svc.decline_pending_claim(db, cascade_id=cascade_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/cascades/{cascade_id}/approve-agency")
async def approve_coverage_agency_routing(
    cascade_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await cascade_svc.approve_agency_routing(db, cascade_id=cascade_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/shifts/{shift_id}/coverage/start")
async def start_coverage_for_open_shift(
    shift_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.start_coverage_for_open_shift(db, shift_id=shift_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/shifts/{shift_id}/coverage/cancel")
async def cancel_coverage_for_open_shift(
    shift_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.cancel_open_shift_offer(db, shift_id=shift_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/shifts/{shift_id}/open-shift/close")
async def close_open_shift(
    shift_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.close_open_shift(db, shift_id=shift_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/shifts/{shift_id}/open-shift/reopen")
async def reopen_open_shift(
    shift_id: int,
    start_open_shift_offer: bool = Query(default=False),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.reopen_open_shift(
            db,
            shift_id=shift_id,
            start_open_shift_offer=start_open_shift_offer,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/shifts/{shift_id}/attendance/wait")
async def wait_for_attendance_issue(
    shift_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.wait_for_attendance_issue(db, shift_id=shift_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/shifts/{shift_id}/attendance/start-coverage")
async def start_coverage_for_attendance_issue(
    shift_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.start_coverage_for_attendance_issue(db, shift_id=shift_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/internal/sync/process-due")
async def process_due_sync_jobs(
    platform: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import sync_engine

    return {
        "platform": platform,
        "results": await sync_engine.process_due_sync_jobs(db, platform=platform, limit=limit),
    }


@router.post("/internal/sync/rolling")
async def queue_rolling_reconcile(
    location_id: Optional[int] = Query(default=None, ge=1),
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import sync_engine

    if location_id is not None:
        return await sync_engine.enqueue_rolling_reconcile(
            db, location_id=location_id
        )
    return {"jobs": await sync_engine.enqueue_rolling_reconcile_for_due_locations(db)}


@router.post("/internal/sync/daily")
async def queue_daily_reconcile(
    location_id: Optional[int] = Query(default=None, ge=1),
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import sync_engine

    if location_id is not None:
        return await sync_engine.enqueue_daily_reconcile(
            db, location_id=location_id
        )
    return {"jobs": await sync_engine.enqueue_daily_reconcile_for_due_locations(db)}


# ── workers ───────────────────────────────────────────────────────────────────

@router.post("/workers", response_model=Worker, status_code=201)
async def create_worker(
    body: WorkerCreate,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db)
):
    principal = auth_svc.get_request_principal(request)
    data = body.model_dump(mode="json")
    location_id = data.get("location_id")
    if principal is not None and not principal.is_internal:
        if location_id is None:
            raise HTTPException(status_code=400, detail="location_id is required")
        await auth_svc.ensure_location_access(db, principal, int(location_id))
    wid = await queries.insert_worker(db, data)
    await audit_svc.append(
        db, AuditAction.worker_created, entity_type="worker", entity_id=wid
    )
    created = await queries.get_worker(db, wid)
    if created is None:
        raise HTTPException(status_code=404, detail="Worker not found")
    return created


@router.get("/workers", response_model=List[Worker])
async def list_workers(
    request: Request,
    location_id: Optional[int] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    principal = auth_svc.get_request_principal(request)
    if principal is not None and not principal.is_internal and location_id is None:
        allowed_ids = set(principal.location_ids)
        if principal.organization_id is not None:
            locations = await queries.list_locations(db)
            allowed_ids.update(
                int(location["id"])
                for location in locations
                if location.get("organization_id") == principal.organization_id
            )
        workers = await queries.list_workers(db)
        return [
            worker
            for worker in workers
            if worker.get("location_id") in allowed_ids
        ]
    return await queries.list_workers(db, location_id=location_id)


@router.post("/workers/import-csv", status_code=201)
async def import_workers_csv(
    location_id: Optional[int] = Query(default=None),
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Upload a CSV with columns: name, phone, role, priority_rank (optional).
    Creates worker records for a customer location — fastest onboarding path
    for operators without scheduling software.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    if location_id is None:
        raise HTTPException(status_code=400, detail="location_id is required")

    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")

    max_csv_bytes = 10 * 1024 * 1024
    content = await file.read(max_csv_bytes + 1)
    if len(content) > max_csv_bytes:
        raise HTTPException(status_code=413, detail="CSV file exceeds 10 MB limit")
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))

    created, skipped = [], []
    for i, row in enumerate(reader, start=2):  # row 1 = header
        name = (row.get("name") or "").strip()
        phone = (row.get("phone") or "").strip()
        if not name or not phone:
            skipped.append({"row": i, "reason": "missing name or phone"})
            continue

        existing = await queries.get_worker_by_phone(db, phone)
        if existing:
            skipped.append({"row": i, "reason": f"phone {phone} already exists"})
            continue

        role = (row.get("role") or "").strip()
        try:
            priority = int(row.get("priority_rank", 1))
        except ValueError:
            priority = 1

        wid = await queries.insert_worker(db, {
            "name": name,
            "phone": phone,
            "roles": [role] if role else [],
            "priority_rank": priority,
            "location_id": location_id,
            "source": "csv_import",
        })
        created.append({"id": wid, "name": name, "phone": phone})

    return {
        "created": len(created),
        "skipped": len(skipped),
        "workers": created,
        "skipped_details": skipped,
    }


@router.get("/exports/workers")
async def export_workers_csv(
    location_id: Optional[int] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    workers = await queries.list_workers(db, location_id=location_id)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "name",
            "phone",
            "email",
            "worker_type",
            "preferred_channel",
            "roles",
            "certifications",
            "priority_rank",
            "location_id",
            "sms_consent_status",
            "voice_consent_status",
        ],
    )
    fieldnames = writer.fieldnames or []
    writer.writeheader()
    for worker in workers:
        row = {
            field: worker.get(field)
            for field in fieldnames
        }
        writer.writerow(
            {
                **row,
                "roles": ",".join(worker.get("roles") or []),
                "certifications": ",".join(worker.get("certifications") or []),
            }
        )
    return {"csv": output.getvalue(), "count": len(workers)}


@router.get("/workers/{worker_id}", response_model=Worker)
async def get_worker(
    worker_id: int, db: aiosqlite.Connection = Depends(get_db)
):
    row = await queries.get_worker(db, worker_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Worker not found")
    return row


@router.patch("/workers/{worker_id}", response_model=Worker)
async def update_worker(
    worker_id: int,
    body: WorkerUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await queries.get_worker(db, worker_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Worker not found")
    data = body.model_dump(mode="json", exclude_none=True)
    await queries.update_worker(db, worker_id, data)
    updated = await queries.get_worker(db, worker_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Worker not found")
    return updated


@router.post("/workers/{worker_id}/deactivate", response_model=Worker)
async def deactivate_worker(
    worker_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await roster_svc.deactivate_worker(db, worker_id=worker_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workers/{worker_id}/reactivate", response_model=Worker)
async def reactivate_worker(
    worker_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await roster_svc.reactivate_worker(db, worker_id=worker_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workers/{worker_id}/transfer", response_model=Worker)
async def transfer_worker(
    worker_id: int,
    body: WorkerTransferRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await roster_svc.transfer_worker(
            db,
            worker_id=worker_id,
            target_location_id=body.target_location_id,
            roles=body.roles,
            priority_rank=body.priority_rank,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


# ── shifts ────────────────────────────────────────────────────────────────────

@router.post("/shifts", response_model=Shift, status_code=201)
async def create_shift(
    body: ShiftCreate,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db)
):
    principal = auth_svc.get_request_principal(request)
    data = body.model_dump(mode="json")
    location_id = data.get("location_id")
    if principal is not None and not principal.is_internal:
        if location_id is None:
            raise HTTPException(status_code=400, detail="location_id is required")
        await auth_svc.ensure_location_access(db, principal, int(location_id))
    sid = await queries.insert_shift(db, data)
    created = await queries.get_shift(db, sid)
    if created is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return created


@router.get("/shifts", response_model=List[Shift])
async def list_shifts(
    request: Request,
    location_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    principal = auth_svc.get_request_principal(request)
    if principal is not None and not principal.is_internal and location_id is None:
        allowed_ids = set(principal.location_ids)
        if principal.organization_id is not None:
            locations = await queries.list_locations(db)
            allowed_ids.update(
                int(location["id"])
                for location in locations
                if location.get("organization_id") == principal.organization_id
            )
        shifts = await queries.list_shifts(db, status=status)
        return [
            shift
            for shift in shifts
            if shift.get("location_id") in allowed_ids
        ]
    return await queries.list_shifts(db, location_id=location_id, status=status)


@router.post("/manager/shifts", response_model=Shift, status_code=201)
async def manager_create_shift(
    body: ManagerShiftCreate,
    db: aiosqlite.Connection = Depends(get_db),
):
    data = body.model_dump(mode="json")
    location_id = data.get("location_id")
    if location_id is None:
        raise HTTPException(status_code=400, detail="location_id is required")

    location = await queries.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    start_backfill = data.pop("start_backfill", True)
    data["status"] = "vacant" if start_backfill else "scheduled"
    data["source_platform"] = "backfill_native"
    shift_id = await queries.insert_shift(db, data)
    if start_backfill:
        cascade = await shift_manager.create_vacancy(
            db,
            shift_id=shift_id,
            called_out_by_worker_id=None,
            actor=f"manager:{location_id}",
        )
        await cascade_svc.advance(db, cascade["id"])
    shift = await queries.get_shift(db, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return shift


@router.get("/exports/shifts")
async def export_shifts_csv(
    location_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    shifts = await queries.list_shifts(db, location_id=location_id, status=status)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "location_id",
            "role",
            "date",
            "start_time",
            "end_time",
            "spans_midnight",
            "pay_rate",
            "requirements",
            "status",
            "called_out_by",
            "filled_by",
            "fill_tier",
            "source_platform",
        ],
    )
    fieldnames = writer.fieldnames or []
    writer.writeheader()
    for shift in shifts:
        row = {
            field: shift.get(field)
            for field in fieldnames
        }
        writer.writerow(
            {
                **row,
                "requirements": ",".join(shift.get("requirements") or []),
            }
        )
    return {"csv": output.getvalue(), "count": len(shifts)}


@router.get("/shifts/{shift_id}", response_model=Shift)
async def get_shift(
    shift_id: int, db: aiosqlite.Connection = Depends(get_db)
):
    row = await queries.get_shift(db, shift_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return row


@router.patch("/shifts/{shift_id}", response_model=Shift)
async def update_shift(
    shift_id: int,
    body: ShiftUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await queries.get_shift(db, shift_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    data = body.model_dump(mode="json", exclude_none=True)
    await queries.update_shift(db, shift_id, data)
    updated = await queries.get_shift(db, shift_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return updated


@router.get("/shifts/{shift_id}/status", response_model=ShiftStatusResponse)
async def get_shift_status(
    shift_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    payload = await queries.get_shift_status(db, shift_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return payload


# ── backfill trigger ──────────────────────────────────────────────────────────

@router.post("/shifts/backfill", response_model=BackfillResponse)
async def backfill_shift(
    body: BackfillRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Mark a shift vacant (worker calling out) and kick off the Tier 1 cascade.
    In production this is triggered automatically by the Retell inbound agent
    via /webhooks/retell — but you can also trigger it directly via this endpoint.
    """
    shift = await queries.get_shift(db, body.shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail=f"Shift {body.shift_id} not found")

    worker = await queries.get_worker(db, body.worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail=f"Worker {body.worker_id} not found")

    cascade = await shift_manager.create_vacancy(
        db,
        shift_id=body.shift_id,
        called_out_by_worker_id=body.worker_id,
        actor=f"worker:{body.worker_id}",
    )

    # Kick off first outreach
    await cascade_svc.advance(db, cascade["id"])

    return BackfillResponse(
        cascade_id=cascade["id"],
        shift_id=body.shift_id,
        worker_id=body.worker_id,
        message=(
            f"Vacancy created for {shift['role']} on {shift['date']}. "
            f"Cascade started — reaching out to Tier 1 workers."
        ),
    )


@router.get("/cascades", response_model=List[Cascade])
async def list_cascades(
    shift_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await queries.list_cascades(db, shift_id=shift_id, status=status)


@router.get("/outreach-attempts")
async def list_outreach_attempts(
    cascade_id: Optional[int] = Query(default=None),
    shift_id: Optional[int] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await queries.list_outreach_attempts(db, cascade_id=cascade_id, shift_id=shift_id)


@router.get("/agency-requests")
async def list_agency_requests(
    cascade_id: Optional[int] = Query(default=None),
    shift_id: Optional[int] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await queries.list_agency_requests(db, cascade_id=cascade_id, shift_id=shift_id)


@router.post("/cascades/{cascade_id}/approve-tier3")
async def approve_tier3(
    cascade_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import agency_router

    cascade = await queries.get_cascade(db, cascade_id)
    if cascade is None:
        raise HTTPException(status_code=404, detail="Cascade not found")
    shift = await queries.get_shift(db, cascade["shift_id"])
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    location = await queries.get_location(db, shift["location_id"])
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    if not location.get("agency_supply_approved"):
        raise HTTPException(status_code=400, detail="Location is not approved for agency supply")

    await queries.update_cascade(
        db,
        cascade_id,
        status="active",
        current_tier=3,
        manager_approved_tier3=True,
    )
    result = await agency_router.route_to_agencies(db, cascade_id=cascade_id, shift_id=shift["id"])
    return {"cascade_id": cascade_id, **result}


@router.get("/audit-log")
async def list_audit_log(
    entity_type: Optional[str] = Query(default=None),
    entity_id: Optional[int] = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await queries.list_audit_log(db, entity_type=entity_type, entity_id=entity_id, limit=limit)


@router.get("/dashboard")
async def dashboard_summary(
    request: Request,
    location_id: Optional[int] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    principal = auth_svc.get_request_principal(request)
    if principal is not None and not principal.is_internal and location_id is None:
        if len(principal.location_ids) == 1:
            location_id = principal.location_ids[0]
        else:
            raise HTTPException(status_code=400, detail="location_id is required")
    return await queries.get_dashboard_summary(db, location_id=location_id)


@router.post("/onboarding/link", response_model=OnboardingLinkResponse)
async def create_onboarding_link(
    body: OnboardingLinkRequest,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import onboarding as onboarding_svc

    principal = auth_svc.get_request_principal(request)
    if principal is None and settings.backfill_dashboard_auth_required:
        raise HTTPException(status_code=401, detail="Authentication required")
    if principal is not None and not principal.is_internal:
        await auth_svc.ensure_location_access(db, principal, body.location_id)

    try:
        return await onboarding_svc.send_onboarding_link(
            db,
            phone=body.phone,
            kind=body.kind,
            location_id=body.location_id,
            platform=body.platform,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/onboarding/sessions/{token}", response_model=SignupSessionResponse)
async def get_signup_session(
    token: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import onboarding as onboarding_svc

    session = await onboarding_svc.get_signup_session_by_token(db, token)
    if session is None:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
    return session


@router.post("/onboarding/sessions/{token}/complete", response_model=SignupSessionCompleteResponse)
async def complete_signup_session(
    token: str,
    body: SignupSessionCompleteRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import onboarding as onboarding_svc

    try:
        return await onboarding_svc.complete_signup_session(
            db,
            token,
            body.model_dump(mode="json", exclude_none=True),
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


# ── reminder SMS ──────────────────────────────────────────────────────────────

@router.post("/internal/backfill-shifts/send-confirmation-requests")
async def send_shift_confirmation_requests(
    within_minutes: int = Query(default=120, ge=15, le=24 * 60),
    location_id: Optional[int] = Query(default=None, ge=1),
    enqueue: bool = Query(default=False),
    db: aiosqlite.Connection = Depends(get_db),
):
    if enqueue:
        job = await ops_queue.enqueue_job(
            db,
            job_type="send_shift_confirmation_requests",
            location_id=location_id,
            payload={"within_minutes": within_minutes, "location_id": location_id},
            idempotency_key=_ops_job_idempotency_key(
                "send_shift_confirmation_requests",
                location_id=location_id or "all",
                within_minutes=within_minutes,
            ),
        )
        return {"status": "queued", "job": job}
    return await backfill_shifts_svc.send_shift_confirmation_requests(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )


@router.post("/internal/backfill-shifts/escalate-unconfirmed-shifts")
async def escalate_unconfirmed_shifts(
    within_minutes: int = Query(default=15, ge=1, le=120),
    location_id: Optional[int] = Query(default=None, ge=1),
    enqueue: bool = Query(default=False),
    db: aiosqlite.Connection = Depends(get_db),
):
    if enqueue:
        job = await ops_queue.enqueue_job(
            db,
            job_type="escalate_unconfirmed_shifts",
            location_id=location_id,
            payload={"within_minutes": within_minutes, "location_id": location_id},
            idempotency_key=_ops_job_idempotency_key(
                "escalate_unconfirmed_shifts",
                location_id=location_id or "all",
                within_minutes=within_minutes,
            ),
        )
        return {"status": "queued", "job": job}
    return await backfill_shifts_svc.escalate_unconfirmed_shifts(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )


@router.post("/internal/backfill-shifts/send-check-in-requests")
async def send_shift_check_in_requests(
    within_minutes: int = Query(default=15, ge=1, le=60),
    location_id: Optional[int] = Query(default=None, ge=1),
    enqueue: bool = Query(default=False),
    db: aiosqlite.Connection = Depends(get_db),
):
    if enqueue:
        job = await ops_queue.enqueue_job(
            db,
            job_type="send_shift_check_in_requests",
            location_id=location_id,
            payload={"within_minutes": within_minutes, "location_id": location_id},
            idempotency_key=_ops_job_idempotency_key(
                "send_shift_check_in_requests",
                location_id=location_id or "all",
                within_minutes=within_minutes,
            ),
        )
        return {"status": "queued", "job": job}
    return await backfill_shifts_svc.send_shift_check_in_requests(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )


@router.post("/internal/backfill-shifts/escalate-missed-check-ins")
async def escalate_missed_check_ins(
    grace_minutes: int = Query(default=10, ge=1, le=60),
    location_id: Optional[int] = Query(default=None, ge=1),
    enqueue: bool = Query(default=False),
    db: aiosqlite.Connection = Depends(get_db),
):
    if enqueue:
        job = await ops_queue.enqueue_job(
            db,
            job_type="escalate_missed_check_ins",
            location_id=location_id,
            payload={"grace_minutes": grace_minutes, "location_id": location_id},
            idempotency_key=_ops_job_idempotency_key(
                "escalate_missed_check_ins",
                grace_minutes=grace_minutes,
                location_id=location_id or "all",
            ),
        )
        return {"status": "queued", "job": job}
    return await backfill_shifts_svc.escalate_missed_check_ins(
        db,
        grace_minutes=grace_minutes,
        location_id=location_id,
    )


@router.post("/shifts/send-reminders")
async def send_shift_reminders(
    within_minutes: int = Query(default=30, ge=5, le=120),
    location_id: Optional[int] = Query(default=None, ge=1),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await backfill_shifts_svc.send_shift_reminders(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )


@router.post("/locations/{location_id}/manager-digest")
async def send_location_manager_digest(
    location_id: int,
    lookahead_hours: int = Query(default=24, ge=1, le=72),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await backfill_shifts_svc.send_manager_digest(
            db,
            location_id=location_id,
            lookahead_hours=lookahead_hours,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/internal/backfill-shifts/send-manager-digests")
async def send_due_manager_digests(
    lookahead_hours: int = Query(default=24, ge=1, le=72),
    cooldown_hours: int = Query(default=12, ge=0, le=168),
    location_id: Optional[int] = Query(default=None, ge=1),
    include_empty: bool = Query(default=False),
    enqueue: bool = Query(default=False),
    db: aiosqlite.Connection = Depends(get_db),
):
    if enqueue:
        job = await ops_queue.enqueue_job(
            db,
            job_type="send_due_manager_digests",
            location_id=location_id,
            payload={
                "lookahead_hours": lookahead_hours,
                "cooldown_hours": cooldown_hours,
                "location_id": location_id,
                "include_empty": include_empty,
            },
            idempotency_key=_ops_job_idempotency_key(
                "send_due_manager_digests",
                cooldown_hours=cooldown_hours,
                include_empty=include_empty,
                location_id=location_id or "all",
                lookahead_hours=lookahead_hours,
            ),
        )
        return {"status": "queued", "job": job}
    try:
        return await backfill_shifts_svc.send_due_manager_digests(
            db,
            lookahead_hours=lookahead_hours,
            cooldown_hours=cooldown_hours,
            location_id=location_id,
            include_empty=include_empty,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/internal/backfill-shifts/run-automation")
async def run_due_backfill_shifts_automation(
    location_id: Optional[int] = Query(default=None, ge=1),
    confirmation_within_minutes: int = Query(default=120, ge=15, le=24 * 60),
    unconfirmed_within_minutes: int = Query(default=15, ge=1, le=120),
    check_in_within_minutes: int = Query(default=15, ge=1, le=60),
    missed_check_in_grace_minutes: int = Query(default=10, ge=1, le=60),
    reminder_within_minutes: int = Query(default=30, ge=5, le=120),
    digest_lookahead_hours: int = Query(default=24, ge=1, le=72),
    digest_cooldown_hours: int = Query(default=12, ge=0, le=168),
    include_empty_digests: bool = Query(default=False),
    run_confirmations: bool = Query(default=True),
    run_unconfirmed_escalations: bool = Query(default=True),
    run_check_ins: bool = Query(default=True),
    run_missed_check_in_escalations: bool = Query(default=True),
    run_reminders: bool = Query(default=True),
    run_manager_digests: bool = Query(default=True),
    enqueue: bool = Query(default=False),
    db: aiosqlite.Connection = Depends(get_db),
):
    if enqueue:
        job = await ops_queue.enqueue_job(
            db,
            job_type="run_due_backfill_shifts_automation",
            location_id=location_id,
            payload={
                "location_id": location_id,
                "confirmation_within_minutes": confirmation_within_minutes,
                "unconfirmed_within_minutes": unconfirmed_within_minutes,
                "check_in_within_minutes": check_in_within_minutes,
                "missed_check_in_grace_minutes": missed_check_in_grace_minutes,
                "reminder_within_minutes": reminder_within_minutes,
                "digest_lookahead_hours": digest_lookahead_hours,
                "digest_cooldown_hours": digest_cooldown_hours,
                "include_empty_digests": include_empty_digests,
                "run_confirmations": run_confirmations,
                "run_unconfirmed_escalations": run_unconfirmed_escalations,
                "run_check_ins": run_check_ins,
                "run_missed_check_in_escalations": run_missed_check_in_escalations,
                "run_reminders": run_reminders,
                "run_manager_digests": run_manager_digests,
            },
            idempotency_key=_ops_job_idempotency_key(
                "run_due_backfill_shifts_automation",
                check_in_within_minutes=check_in_within_minutes,
                confirmation_within_minutes=confirmation_within_minutes,
                digest_cooldown_hours=digest_cooldown_hours,
                digest_lookahead_hours=digest_lookahead_hours,
                include_empty_digests=include_empty_digests,
                location_id=location_id or "all",
                missed_check_in_grace_minutes=missed_check_in_grace_minutes,
                reminder_within_minutes=reminder_within_minutes,
                run_check_ins=run_check_ins,
                run_confirmations=run_confirmations,
                run_manager_digests=run_manager_digests,
                run_missed_check_in_escalations=run_missed_check_in_escalations,
                run_reminders=run_reminders,
                run_unconfirmed_escalations=run_unconfirmed_escalations,
                unconfirmed_within_minutes=unconfirmed_within_minutes,
            ),
        )
        return {"status": "queued", "job": job}
    return await backfill_shifts_svc.run_due_backfill_shifts_automation(
        db,
        location_id=location_id,
        confirmation_within_minutes=confirmation_within_minutes,
        unconfirmed_within_minutes=unconfirmed_within_minutes,
        check_in_within_minutes=check_in_within_minutes,
        missed_check_in_grace_minutes=missed_check_in_grace_minutes,
        reminder_within_minutes=reminder_within_minutes,
        digest_lookahead_hours=digest_lookahead_hours,
        digest_cooldown_hours=digest_cooldown_hours,
        include_empty_digests=include_empty_digests,
        run_confirmations=run_confirmations,
        run_unconfirmed_escalations=run_unconfirmed_escalations,
        run_check_ins=run_check_ins,
        run_missed_check_in_escalations=run_missed_check_in_escalations,
        run_reminders=run_reminders,
        run_manager_digests=run_manager_digests,
    )


@router.get("/internal/ops/jobs")
async def list_internal_ops_jobs(
    status: Optional[str] = Query(default=None),
    job_type: Optional[str] = Query(default=None),
    location_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: aiosqlite.Connection = Depends(get_db),
):
    return {
        "jobs": await queries.list_ops_jobs(
            db,
            status=status,
            job_type=job_type,
            location_id=location_id,
            limit=limit,
        )
    }


@router.post("/internal/ops/process-due")
async def process_due_ops_jobs(
    limit: int = Query(default=20, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await ops_queue.process_due_jobs(db, limit=limit)


@router.get("/internal/ai-actions/recent", response_model=InternalAiActionRecentResponse)
async def list_recent_ai_actions_internal(
    location_id: Optional[int] = Query(default=None),
    organization_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    channel: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await ai_actions_svc.list_recent_ai_actions_internal(
        db,
        location_id=location_id,
        organization_id=organization_id,
        status=status,
        channel=channel,
        limit=limit,
    )


@router.get("/internal/ai-actions/attention", response_model=InternalAiActionAttentionResponse)
async def list_ai_action_attention_internal(
    location_id: Optional[int] = Query(default=None),
    organization_id: Optional[int] = Query(default=None),
    include_resolved: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await ai_actions_svc.list_ai_action_attention_internal(
        db,
        location_id=location_id,
        organization_id=organization_id,
        include_resolved=include_resolved,
        limit=limit,
    )


@router.get("/internal/ai-actions/sessions", response_model=InternalAiActionSessionsResponse)
async def list_ai_action_sessions_internal(
    location_id: Optional[int] = Query(default=None),
    organization_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default="active"),
    channel: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await ai_actions_svc.list_ai_action_sessions_internal(
        db,
        location_id=location_id,
        organization_id=organization_id,
        status=status,
        channel=channel,
        limit=limit,
    )


@router.post("/internal/ai-actions/expire-stale")
async def expire_stale_ai_action_sessions(
    location_id: Optional[int] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await ai_actions_svc.expire_stale_action_sessions_internal(
        db,
        location_id=location_id,
        limit=limit,
    )


@router.post("/internal/ai-actions/{action_request_id}/retry", response_model=AiActionResponse)
async def retry_ai_action_internal(
    action_request_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.retry_action_request_internal(
            db,
            action_request_id=action_request_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 409 if "still active" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/internal/ai-actions/{action_request_id}/cancel", response_model=AiActionResponse)
async def cancel_ai_action_internal(
    action_request_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.cancel_action_request_internal(
            db,
            action_request_id=action_request_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/internal/ai-actions/{action_request_id}/expire", response_model=AiActionResponse)
async def expire_ai_action_internal(
    action_request_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await ai_actions_svc.expire_action_request_internal(
            db,
            action_request_id=action_request_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 409 if "active session" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get(
    "/internal/backfill-shifts/webhook-health",
    response_model=BackfillShiftsWebhookHealthResponse,
)
async def get_backfill_shifts_webhook_health(
    source: str = Query(default="twilio_sms"),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await backfill_shifts_svc.get_backfill_shifts_webhook_health(
        db,
        source=source,
        days=days,
        limit=limit,
    )
