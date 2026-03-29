from __future__ import annotations

from typing import Optional

import aiosqlite

from app.db import queries
from app.models.audit import AuditAction
from app.services import audit as audit_svc
from app.services import notifications as notifications_svc


def _enrollment_status(worker: dict) -> str:
    if worker.get("sms_consent_status") == "granted" or worker.get("voice_consent_status") == "granted":
        return "enrolled"
    return "not_enrolled"


def _employment_active(worker: dict) -> bool:
    return worker.get("employment_status") not in {"inactive", "terminated"}


def _normalize_assignment(assignment: dict, worker: dict) -> dict:
    return {
        "location_id": assignment.get("location_id"),
        "priority_rank": assignment.get("priority_rank", worker.get("priority_rank", 1)),
        "is_active": bool(assignment.get("is_active", True)),
        "roles": list(assignment.get("roles") or worker.get("roles") or []),
    }


def _assignment_for_location(worker: dict, location_id: int) -> Optional[dict]:
    assignments = worker.get("location_assignments") or []
    for assignment in assignments:
        if int(assignment.get("location_id") or 0) == location_id:
            return _normalize_assignment(assignment, worker)
    if int(worker.get("location_id") or 0) == location_id:
        return {
            "location_id": location_id,
            "priority_rank": worker.get("priority_rank", 1),
            "is_active": _employment_active(worker),
            "roles": list(worker.get("roles") or []),
        }
    return None


def _serialize_worker_for_location(worker: dict, location_id: int) -> Optional[dict]:
    assignment = _assignment_for_location(worker, location_id)
    if assignment is None:
        return None
    is_active_at_location = _employment_active(worker) and bool(assignment.get("is_active", True))
    return {
        **worker,
        "enrollment_status": _enrollment_status(worker),
        "is_active_worker": _employment_active(worker),
        "is_active_at_location": is_active_at_location,
        "active_assignment": assignment,
    }


def _sorted_assignments(assignments: list[dict]) -> list[dict]:
    return sorted(
        assignments,
        key=lambda item: (0 if item.get("is_active") else 1, int(item.get("location_id") or 0)),
    )


def _dedupe_roles(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = (value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _upsert_assignment(
    assignments: list[dict],
    *,
    location_id: int,
    roles: list[str],
    priority_rank: int,
    is_active: bool,
) -> list[dict]:
    updated = False
    next_assignments: list[dict] = []
    for assignment in assignments:
        if int(assignment.get("location_id") or 0) != location_id:
            next_assignments.append(_normalize_assignment(assignment, {"priority_rank": priority_rank, "roles": roles}))
            continue
        next_assignments.append(
            {
                "location_id": location_id,
                "priority_rank": priority_rank,
                "is_active": is_active,
                "roles": _dedupe_roles(roles or assignment.get("roles") or []),
            }
        )
        updated = True
    if not updated:
        next_assignments.append(
            {
                "location_id": location_id,
                "priority_rank": priority_rank,
                "is_active": is_active,
                "roles": _dedupe_roles(roles),
            }
        )
    return _sorted_assignments(next_assignments)


async def list_roster_for_location(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    include_inactive: bool = True,
) -> dict:
    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError("Location not found")

    workers = []
    for worker in await queries.list_workers(db):
        serialized = _serialize_worker_for_location(worker, location_id)
        if serialized is None:
            continue
        if not include_inactive and not serialized["is_active_at_location"]:
            continue
        workers.append(serialized)

    workers.sort(
        key=lambda worker: (
            0 if worker["is_active_at_location"] else 1,
            int(worker.get("priority_rank") or 9999),
            (worker.get("name") or "").lower(),
            int(worker.get("id") or 0),
        )
    )
    return {
        "location_id": location_id,
        "summary": {
            "total_workers": len(workers),
            "active_workers": sum(1 for worker in workers if worker["is_active_at_location"]),
            "inactive_workers": sum(1 for worker in workers if not worker["is_active_at_location"]),
            "enrolled_workers": sum(1 for worker in workers if worker["enrollment_status"] == "enrolled"),
        },
        "workers": workers,
    }


async def list_eligible_workers(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    role: Optional[str] = None,
) -> dict:
    role_name = (role or "").strip() or None
    roster = await list_roster_for_location(db, location_id=location_id, include_inactive=False)
    eligible_workers = []
    for worker in roster["workers"]:
        if worker.get("worker_type") not in {None, "internal"}:
            continue
        assignment = worker.get("active_assignment") or {}
        if not assignment.get("is_active", True):
            continue
        eligible_roles = _dedupe_roles(list(assignment.get("roles") or []) + list(worker.get("roles") or []))
        if role_name and role_name not in eligible_roles:
            continue
        eligible_workers.append(
            {
                **worker,
                "eligible_roles": eligible_roles,
            }
        )

    eligible_workers.sort(
        key=lambda worker: (
            int(worker.get("active_assignment", {}).get("priority_rank") or worker.get("priority_rank") or 9999),
            (worker.get("name") or "").lower(),
            int(worker.get("id") or 0),
        )
    )
    return {
        "location_id": location_id,
        "role": role_name,
        "workers": eligible_workers,
    }


async def send_enrollment_invites_for_location(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    worker_ids: Optional[list[int]] = None,
    include_enrolled: bool = False,
    actor: str = "manager_api",
) -> dict:
    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError("Location not found")

    roster = await list_roster_for_location(db, location_id=location_id, include_inactive=True)
    workers_by_id = {int(worker["id"]): worker for worker in roster["workers"]}
    if worker_ids:
        target_ids = []
        seen_ids: set[int] = set()
        for worker_id in worker_ids:
            normalized_id = int(worker_id)
            if normalized_id in seen_ids:
                continue
            seen_ids.add(normalized_id)
            target_ids.append(normalized_id)
    else:
        target_ids = [
            int(worker["id"])
            for worker in roster["workers"]
            if worker.get("is_active_at_location") and worker.get("enrollment_status") == "not_enrolled"
        ]

    sms_copy = notifications_svc.build_worker_enrollment_invite_text(
        location_name=location.get("name") or "your location",
        organization_name=location.get("organization_name"),
    )

    results: list[dict] = []
    summary = {
        "requested": len(target_ids),
        "sent": 0,
        "skipped_enrolled": 0,
        "skipped_inactive": 0,
        "skipped_missing_phone": 0,
        "skipped_not_found": 0,
        "failed": 0,
    }

    for worker_id in target_ids:
        worker = workers_by_id.get(worker_id)
        result = {"worker_id": worker_id}
        if worker is None:
            summary["skipped_not_found"] += 1
            results.append({**result, "status": "skipped_not_found"})
            continue
        result["worker_name"] = worker.get("name")
        if not worker.get("is_active_at_location"):
            summary["skipped_inactive"] += 1
            results.append({**result, "status": "skipped_inactive"})
            continue
        if worker.get("enrollment_status") == "enrolled" and not include_enrolled:
            summary["skipped_enrolled"] += 1
            results.append({**result, "status": "skipped_enrolled"})
            continue
        if not worker.get("phone"):
            summary["skipped_missing_phone"] += 1
            results.append({**result, "status": "skipped_missing_phone"})
            continue
        try:
            message_sid = notifications_svc.send_sms(worker["phone"], sms_copy)
        except Exception as exc:
            summary["failed"] += 1
            results.append({**result, "status": "failed", "error": str(exc)})
            continue
        summary["sent"] += 1
        results.append({**result, "status": "sent", "message_sid": message_sid})
        await audit_svc.append(
            db,
            AuditAction.worker_invited,
            actor=actor,
            entity_type="worker",
            entity_id=worker_id,
            details={
                "location_id": location_id,
                "channel": "sms",
                "message_sid": message_sid,
                "invite_type": "enrollment",
            },
        )

    return {
        "location_id": location_id,
        "summary": summary,
        "results": results,
        "sms_copy": sms_copy,
        "join_number": notifications_svc.settings.backfill_phone_number,
        "join_keyword": "JOIN",
    }


async def deactivate_worker(
    db: aiosqlite.Connection,
    *,
    worker_id: int,
    actor: str = "system",
) -> dict:
    worker = await queries.get_worker(db, worker_id)
    if worker is None:
        raise ValueError("Worker not found")
    assignments = [
        {
            **_normalize_assignment(assignment, worker),
            "is_active": False,
        }
        for assignment in (worker.get("location_assignments") or [])
    ]
    await queries.update_worker(
        db,
        worker_id,
        {
            "employment_status": "inactive",
            "location_assignments": _sorted_assignments(assignments),
        },
    )
    await audit_svc.append(
        db,
        AuditAction.worker_deactivated,
        actor=actor,
        entity_type="worker",
        entity_id=worker_id,
        details={"location_id": worker.get("location_id")},
    )
    updated = await queries.get_worker(db, worker_id)
    assert updated is not None
    return updated


async def reactivate_worker(
    db: aiosqlite.Connection,
    *,
    worker_id: int,
    actor: str = "system",
) -> dict:
    worker = await queries.get_worker(db, worker_id)
    if worker is None:
        raise ValueError("Worker not found")
    current_location_id = int(worker.get("location_id") or 0)
    assignments = list(worker.get("location_assignments") or [])
    if current_location_id:
        assignments = _upsert_assignment(
            assignments,
            location_id=current_location_id,
            roles=list(worker.get("roles") or []),
            priority_rank=int(worker.get("priority_rank") or 1),
            is_active=True,
        )
    await queries.update_worker(
        db,
        worker_id,
        {
            "employment_status": "active",
            "location_assignments": assignments,
        },
    )
    await audit_svc.append(
        db,
        AuditAction.worker_reactivated,
        actor=actor,
        entity_type="worker",
        entity_id=worker_id,
        details={"location_id": worker.get("location_id")},
    )
    updated = await queries.get_worker(db, worker_id)
    assert updated is not None
    return updated


async def transfer_worker(
    db: aiosqlite.Connection,
    *,
    worker_id: int,
    target_location_id: int,
    roles: Optional[list[str]] = None,
    priority_rank: Optional[int] = None,
    actor: str = "system",
) -> dict:
    worker = await queries.get_worker(db, worker_id)
    if worker is None:
        raise ValueError("Worker not found")
    target_location = await queries.get_location(db, target_location_id)
    if target_location is None:
        raise ValueError("Target location not found")

    current_location_id = int(worker.get("location_id") or 0)
    next_roles = _dedupe_roles(list(roles or []) + list(worker.get("roles") or []))
    next_priority_rank = int(priority_rank or worker.get("priority_rank") or 1)
    assignments = list(worker.get("location_assignments") or [])

    if current_location_id and current_location_id != target_location_id:
        assignments = _upsert_assignment(
            assignments,
            location_id=current_location_id,
            roles=list(worker.get("roles") or []),
            priority_rank=int(worker.get("priority_rank") or 1),
            is_active=False,
        )
    assignments = _upsert_assignment(
        assignments,
        location_id=target_location_id,
        roles=next_roles,
        priority_rank=next_priority_rank,
        is_active=True,
    )

    locations_worked = list(worker.get("locations_worked") or [])
    for location_id in [current_location_id, target_location_id]:
        if location_id and location_id not in locations_worked:
            locations_worked.append(location_id)

    await queries.update_worker(
        db,
        worker_id,
        {
            "location_id": target_location_id,
            "roles": next_roles,
            "priority_rank": next_priority_rank,
            "location_assignments": assignments,
            "locations_worked": locations_worked,
            "employment_status": "active",
        },
    )
    await audit_svc.append(
        db,
        AuditAction.worker_transferred,
        actor=actor,
        entity_type="worker",
        entity_id=worker_id,
        details={"from_location_id": current_location_id, "to_location_id": target_location_id},
    )
    updated = await queries.get_worker(db, worker_id)
    assert updated is not None
    return updated
