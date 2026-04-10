from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.session import get_async_sessionmaker
from app.models.integrations import ProviderCallbackLog
from app.services import provider_callbacks


@pytest.mark.asyncio
async def test_process_callback_entry_synchronously_prevents_duplicate_execution_with_real_postgres(
    monkeypatch,
):
    sessionmaker = get_async_sessionmaker()
    callback_log_id = None
    first_request: asyncio.Task | None = None
    dispatch_started = asyncio.Event()
    allow_dispatch_finish = asyncio.Event()
    dispatch_calls: list[tuple[str, dict]] = []

    async def fake_dispatch(_session, name: str, args: dict):
        dispatch_calls.append((name, dict(args)))
        dispatch_started.set()
        await asyncio.wait_for(allow_dispatch_finish.wait(), timeout=5)
        return {"status": "accepted", "offer_id": args["offer_id"]}

    monkeypatch.setattr(provider_callbacks.retell_workflow, "dispatch_function_call", fake_dispatch)

    try:
        async with sessionmaker() as setup_session:
            entry = ProviderCallbackLog(
                provider="retell",
                route_key="retell_webhook",
                event_type="function_call",
                provider_event_id=f"call_{uuid4()}",
                dedupe_key=f"retell:test:{uuid4()}",
                status="received",
                headers={"X-Retell-Signature": "sig_test"},
                payload={
                    "event": "function_call",
                    "name": "claim_shift",
                    "args": {"offer_id": "offer_123"},
                },
                result_payload={},
            )
            setup_session.add(entry)
            await setup_session.commit()
            callback_log_id = entry.id

        async def run_sync_processor():
            async with sessionmaker() as session:
                entry = await session.get(ProviderCallbackLog, callback_log_id)
                assert entry is not None
                return await provider_callbacks.process_callback_entry_synchronously(session, entry)

        first_request = asyncio.create_task(run_sync_processor())
        await asyncio.wait_for(dispatch_started.wait(), timeout=5)

        with pytest.raises(provider_callbacks.CallbackProcessingError) as exc_info:
            await asyncio.wait_for(run_sync_processor(), timeout=5)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "callback_processing_in_progress"
        assert dispatch_calls == [("claim_shift", {"offer_id": "offer_123"})]

        allow_dispatch_finish.set()
        first_result = await asyncio.wait_for(first_request, timeout=5)

        assert first_result.response_payload == {"status": "accepted", "offer_id": "offer_123"}

        async with sessionmaker() as verification_session:
            stored_entry = await verification_session.get(ProviderCallbackLog, callback_log_id)
            assert stored_entry is not None
            assert stored_entry.status == "processed"
            assert stored_entry.result_payload == {"status": "accepted", "offer_id": "offer_123"}

        duplicate_result = await asyncio.wait_for(run_sync_processor(), timeout=5)

        assert duplicate_result.duplicate is True
        assert duplicate_result.response_payload == {"status": "accepted", "offer_id": "offer_123"}
        assert dispatch_calls == [("claim_shift", {"offer_id": "offer_123"})]
    finally:
        allow_dispatch_finish.set()
        if first_request is not None and not first_request.done():
            first_request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first_request
        if callback_log_id is not None:
            async with sessionmaker() as cleanup_session:
                await cleanup_session.execute(
                    delete(ProviderCallbackLog).where(ProviderCallbackLog.id == callback_log_id)
                )
                await cleanup_session.commit()
