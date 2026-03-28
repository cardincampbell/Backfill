"""
REST API routes for Backfill Native Lite.
Covers CRUD for customer locations, workers, and shifts, plus the backfill trigger.
"""
from __future__ import annotations

import csv
import io
from datetime import date, time, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
import aiosqlite

from app.db.database import get_db
from app.db import queries
from app.models.location import Location, LocationCreate
from app.models.organization import Organization, OrganizationCreate
from app.models.worker import Worker, WorkerCreate
from app.models.shift import Shift, ShiftCreate
from app.models.cascade import Cascade
from app.services import shift_manager, cascade as cascade_svc
from app.services import retell_reconcile
from app.models.audit import AuditAction
from app.services import audit as audit_svc
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["api"])


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
    writeback_enabled: Optional[bool] = None
    writeback_subscription_tier: Optional[str] = None
    onboarding_info: Optional[str] = None
    agency_supply_approved: Optional[bool] = None
    preferred_agency_partners: Optional[list[int]] = None


class WorkerUpdate(BaseModel):
    name: Optional[str] = None
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
    sms_consent_status: Optional[str] = None
    voice_consent_status: Optional[str] = None
    rating: Optional[float] = None
    response_rate: Optional[float] = None
    acceptance_rate: Optional[float] = None
    show_up_rate: Optional[float] = None


class ShiftUpdate(BaseModel):
    location_id: Optional[int] = None
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
    platform: Optional[str] = None


class OnboardingLinkResponse(BaseModel):
    kind: str
    platform: Optional[str] = None
    path: str
    url: str
    message_sid: Optional[str] = None


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
    body: LocationCreate, db: aiosqlite.Connection = Depends(get_db)
):
    data = body.model_dump(mode="json")
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
    await audit_svc.append(
        db,
        AuditAction.location_created,
        entity_type="location",
        entity_id=location_id,
    )
    created = await queries.get_location(db, location_id)
    assert created is not None
    return created


@router.get("/locations", response_model=List[Location])
async def list_locations(db: aiosqlite.Connection = Depends(get_db)):
    return await queries.list_locations(db)


@router.get("/locations/{location_id}", response_model=Location)
async def get_location(
    location_id: int, db: aiosqlite.Connection = Depends(get_db)
):
    row = await queries.get_location(db, location_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return row


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


@router.patch("/locations/{location_id}", response_model=Location)
async def update_location(
    location_id: int,
    body: LocationUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await queries.get_location(db, location_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Location not found")
    payload = body.model_dump(mode="json", exclude_none=True)
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
    body: WorkerCreate, db: aiosqlite.Connection = Depends(get_db)
):
    data = body.model_dump(mode="json")
    wid = await queries.insert_worker(db, data)
    await audit_svc.append(
        db, AuditAction.worker_created, entity_type="worker", entity_id=wid
    )
    return {
        **data,
        "id": wid,
        "total_shifts_filled": 0,
    }


@router.get("/workers", response_model=List[Worker])
async def list_workers(
    location_id: Optional[int] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
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


# ── shifts ────────────────────────────────────────────────────────────────────

@router.post("/shifts", response_model=Shift, status_code=201)
async def create_shift(
    body: ShiftCreate, db: aiosqlite.Connection = Depends(get_db)
):
    data = body.model_dump(mode="json")
    sid = await queries.insert_shift(db, data)
    return {
        **data,
        "id": sid,
        "called_out_by": None,
        "filled_by": None,
        "fill_tier": None,
    }


@router.get("/shifts", response_model=List[Shift])
async def list_shifts(
    location_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
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
    location_id: Optional[int] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await queries.get_dashboard_summary(db, location_id=location_id)


@router.post("/onboarding/link", response_model=OnboardingLinkResponse)
async def create_onboarding_link(body: OnboardingLinkRequest):
    from app.services import onboarding as onboarding_svc

    try:
        return onboarding_svc.send_onboarding_link(
            phone=body.phone,
            kind=body.kind,
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

@router.post("/shifts/send-reminders")
async def send_shift_reminders(
    within_minutes: int = Query(default=30, ge=5, le=120),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Send a reminder SMS to every confirmed worker whose shift starts within
    `within_minutes` and hasn't yet received a reminder.

    Designed to be called by a cron job or scheduled task every few minutes.
    Returns a list of shift IDs that had reminders sent.
    """
    from app.services.messaging import send_sms
    from app.services.outreach import build_reminder_sms

    shifts = await queries.list_filled_shifts_needing_reminder(db, within_minutes=within_minutes)
    sent = []
    for shift in shifts:
        worker_id = shift.get("filled_by")
        if not worker_id:
            continue
        worker = await queries.get_worker(db, worker_id)
        if not worker:
            continue
        if worker.get("sms_consent_status") != "granted":
            continue
        location = await queries.get_location(db, shift["location_id"]) if shift.get("location_id") else None
        message = build_reminder_sms(worker, shift, location)
        send_sms(worker["phone"], message)
        await queries.mark_reminder_sent(db, shift["id"])
        await audit_svc.append(
            db,
            AuditAction.outreach_sent,
            entity_type="shift",
            entity_id=shift["id"],
            details={"channel": "sms_reminder", "worker_id": worker_id},
        )
        sent.append(shift["id"])
    return {"reminders_sent": len(sent), "shift_ids": sent}
