"""
Audit trail — every significant action in the system gets logged here.
Call append() anywhere you would otherwise only print or log a message.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import aiosqlite

from app.models.audit import AuditAction
from app.db.queries import insert_audit


async def append(
    db: aiosqlite.Connection,
    action: AuditAction,
    actor: str = "system",
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
) -> int:
    return await insert_audit(
        db,
        {
            "timestamp": datetime.utcnow().isoformat(),
            "actor": actor,
            "action": action.value,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details or {},
        },
    )
