from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import SessionDep
from app.config import settings
from app.services import rate_limit, retell_workflow

router = APIRouter(prefix="/providers/retell", tags=["retell"])


@router.post("/webhook")
async def retell_webhook(request: Request, session: SessionDep):
    client_ip = request.client.host if request.client is not None else "unknown"
    await rate_limit.assert_within_limit(
        "retell_webhook",
        client_ip,
        limit=settings.retell_webhook_limit_per_minute,
        window_seconds=60,
        detail="Too many Retell webhook requests.",
    )
    body = await request.json()
    event = str(body.get("event") or "").strip()
    try:
        if event in {"call_started", "call_ended", "call_analyzed", "chat_started", "chat_ended", "chat_analyzed"}:
            conversation = await retell_workflow.persist_payload(session, body)
            await session.commit()
            return {
                "status": "ok",
                "conversation_id": str(conversation.id) if conversation is not None else None,
            }
        if event == "function_call":
            result = await retell_workflow.dispatch_function_call(
                session,
                str(body.get("name") or "").strip(),
                body.get("args") or {},
            )
            await session.commit()
            return result
        conversation = await retell_workflow.persist_payload(session, body)
        await session.commit()
        return {
            "status": "ignored",
            "conversation_id": str(conversation.id) if conversation is not None else None,
            "event": event,
        }
    except LookupError as exc:
        if hasattr(session, "rollback"):
            await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        if hasattr(session, "rollback"):
            await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
