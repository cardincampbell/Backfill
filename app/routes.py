"""
REST API routes for Backfill Native Lite.
Covers CRUD for restaurants, workers, and shifts, plus the backfill trigger.
"""
import csv
import io
from datetime import date, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
import aiosqlite

from app.db.database import get_db
from app.db import queries
from app.models.restaurant import Restaurant, RestaurantCreate
from app.models.worker import Worker, WorkerCreate
from app.models.shift import Shift, ShiftCreate
from app.models.cascade import Cascade
from app.services import shift_manager, cascade as cascade_svc
from app.models.audit import AuditAction
from app.services import audit as audit_svc
from pydantic import BaseModel

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


class RestaurantUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    manager_name: Optional[str] = None
    manager_phone: Optional[str] = None
    manager_email: Optional[str] = None
    scheduling_platform: Optional[str] = None
    scheduling_platform_id: Optional[str] = None
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
    restaurant_id: Optional[int] = None
    restaurant_assignments: Optional[list[dict]] = None
    restaurants_worked: Optional[list[int]] = None
    source: Optional[str] = None
    sms_consent_status: Optional[str] = None
    voice_consent_status: Optional[str] = None
    rating: Optional[float] = None
    response_rate: Optional[float] = None
    acceptance_rate: Optional[float] = None
    show_up_rate: Optional[float] = None


class ShiftUpdate(BaseModel):
    restaurant_id: Optional[int] = None
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
    restaurant_id: int
    role: str
    date: date
    start_time: time
    end_time: time
    pay_rate: float
    requirements: list[str] = []
    start_backfill: bool = True


class ShiftStatusResponse(BaseModel):
    shift: dict
    restaurant: Optional[dict] = None
    cascade: Optional[dict] = None
    filled_worker: Optional[dict] = None
    outreach_attempts: list[dict]


# ── restaurants ───────────────────────────────────────────────────────────────

@router.post("/restaurants", response_model=Restaurant, status_code=201)
async def create_restaurant(
    body: RestaurantCreate, db: aiosqlite.Connection = Depends(get_db)
):
    data = body.model_dump(mode="json")
    rid = await queries.insert_restaurant(db, data)
    await audit_svc.append(db, AuditAction.restaurant_created, entity_type="restaurant", entity_id=rid)
    return {**data, "id": rid}


@router.get("/restaurants", response_model=list[Restaurant])
async def list_restaurants(db: aiosqlite.Connection = Depends(get_db)):
    return await queries.list_restaurants(db)


@router.get("/restaurants/{restaurant_id}", response_model=Restaurant)
async def get_restaurant(
    restaurant_id: int, db: aiosqlite.Connection = Depends(get_db)
):
    row = await queries.get_restaurant(db, restaurant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return row


@router.patch("/restaurants/{restaurant_id}", response_model=Restaurant)
async def update_restaurant(
    restaurant_id: int,
    body: RestaurantUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await queries.get_restaurant(db, restaurant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    await queries.update_restaurant(db, restaurant_id, body.model_dump(mode="json", exclude_none=True))
    return await queries.get_restaurant(db, restaurant_id)


@router.post("/restaurants/{restaurant_id}/sync-roster")
async def sync_restaurant_roster(
    restaurant_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import scheduling as scheduling_svc

    restaurant = await queries.get_restaurant(db, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    try:
        return await scheduling_svc.sync_roster(db, restaurant_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/restaurants/{restaurant_id}/sync-schedule")
async def sync_restaurant_schedule(
    restaurant_id: int,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    from app.services import scheduling as scheduling_svc

    restaurant = await queries.get_restaurant(db, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    effective_start = start_date or date.today()
    effective_end = end_date or (effective_start + timedelta(days=14))
    try:
        return await scheduling_svc.sync_schedule(db, restaurant_id, effective_start, effective_end)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── workers ───────────────────────────────────────────────────────────────────

@router.post("/workers", response_model=Worker, status_code=201)
async def create_worker(
    body: WorkerCreate, db: aiosqlite.Connection = Depends(get_db)
):
    data = body.model_dump(mode="json")
    wid = await queries.insert_worker(db, data)
    await audit_svc.append(db, AuditAction.worker_created, entity_type="worker", entity_id=wid)
    return {**data, "id": wid, "total_shifts_filled": 0}


@router.get("/workers", response_model=list[Worker])
async def list_workers(
    restaurant_id: Optional[int] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await queries.list_workers(db, restaurant_id=restaurant_id)


@router.post("/workers/import-csv", status_code=201)
async def import_workers_csv(
    restaurant_id: int,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Upload a CSV with columns: name, phone, role, priority_rank (optional).
    Creates worker records for a restaurant — fastest onboarding path for
    restaurants without scheduling software.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    restaurant = await queries.get_restaurant(db, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    content = await file.read()
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
            "restaurant_id": restaurant_id,
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
    restaurant_id: Optional[int] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    workers = await queries.list_workers(db, restaurant_id=restaurant_id)
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
            "restaurant_id",
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
    await queries.update_worker(db, worker_id, body.model_dump(mode="json", exclude_none=True))
    return await queries.get_worker(db, worker_id)


# ── shifts ────────────────────────────────────────────────────────────────────

@router.post("/shifts", response_model=Shift, status_code=201)
async def create_shift(
    body: ShiftCreate, db: aiosqlite.Connection = Depends(get_db)
):
    data = body.model_dump(mode="json")
    sid = await queries.insert_shift(db, data)
    return {**data, "id": sid, "called_out_by": None, "filled_by": None, "fill_tier": None}


@router.get("/shifts", response_model=list[Shift])
async def list_shifts(
    restaurant_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await queries.list_shifts(db, restaurant_id=restaurant_id, status=status)


@router.post("/manager/shifts", response_model=Shift, status_code=201)
async def manager_create_shift(
    body: ManagerShiftCreate,
    db: aiosqlite.Connection = Depends(get_db),
):
    restaurant = await queries.get_restaurant(db, body.restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    data = body.model_dump(mode="json")
    start_backfill = data.pop("start_backfill", True)
    data["status"] = "vacant" if start_backfill else "scheduled"
    data["source_platform"] = "backfill_native"
    shift_id = await queries.insert_shift(db, data)
    if start_backfill:
        cascade = await shift_manager.create_vacancy(
            db,
            shift_id=shift_id,
            called_out_by_worker_id=None,
            actor=f"manager:{body.restaurant_id}",
        )
        await cascade_svc.advance(db, cascade["id"])
    return await queries.get_shift(db, shift_id)


@router.get("/exports/shifts")
async def export_shifts_csv(
    restaurant_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    shifts = await queries.list_shifts(db, restaurant_id=restaurant_id, status=status)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "restaurant_id",
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
    await queries.update_shift(db, shift_id, body.model_dump(mode="json", exclude_none=True))
    return await queries.get_shift(db, shift_id)


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


@router.get("/cascades", response_model=list[Cascade])
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
    restaurant = await queries.get_restaurant(db, shift["restaurant_id"])
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    if not restaurant.get("agency_supply_approved"):
        raise HTTPException(status_code=400, detail="Restaurant is not approved for agency supply")

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
    restaurant_id: Optional[int] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await queries.get_dashboard_summary(db, restaurant_id=restaurant_id)


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
        restaurant = await queries.get_restaurant(db, shift["restaurant_id"]) if shift.get("restaurant_id") else None
        message = build_reminder_sms(worker, shift, restaurant)
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
