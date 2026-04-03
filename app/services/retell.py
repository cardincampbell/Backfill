"""
Thin wrapper around the Retell SDK for Backfill.
"""
from __future__ import annotations

from typing import Optional

import httpx

from app.config import settings

_client = None


def get_client():
    global _client
    if _client is None:
        if not settings.retell_api_key:
            raise RuntimeError("RETELL_API_KEY is not set")
        try:
            from retell import Retell
        except ImportError as exc:
            raise RuntimeError("retell package is not installed") from exc
        _client = Retell(api_key=settings.retell_api_key)
    return _client


def _serialize(payload):
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return payload
    return dict(payload)


def _default_call_agent_id(agent_kind: str = "outbound") -> str:
    default_agent_id = settings.retell_agent_id
    if agent_kind == "inbound":
        return settings.retell_agent_id_inbound or default_agent_id
    if agent_kind == "outbound":
        return settings.retell_agent_id_outbound or default_agent_id
    return default_agent_id


def _default_chat_agent_id(agent_kind: str = "outbound") -> str:
    default_agent_id = settings.retell_chat_agent_id
    if agent_kind == "inbound":
        return settings.retell_chat_agent_id_inbound or default_agent_id
    if agent_kind == "outbound":
        return settings.retell_chat_agent_id_outbound or default_agent_id
    return default_agent_id


async def create_phone_call(
    *,
    to_number: str,
    metadata: dict,
    agent_id: Optional[str] = None,
    agent_kind: str = "outbound",
) -> str:
    client = get_client()
    effective_agent_id = agent_id or _default_call_agent_id(agent_kind=agent_kind)
    if not effective_agent_id:
        raise RuntimeError("Retell call agent ID is not configured")
    if not settings.retell_from_number:
        raise RuntimeError("RETELL_FROM_NUMBER is not set")
    response = client.call.create_phone_call(
        from_number=settings.retell_from_number,
        to_number=to_number,
        override_agent_id=effective_agent_id,
        metadata=metadata,
    )
    return response.call_id


def create_sms_chat(
    *,
    to_number: str,
    body: str,
    metadata: Optional[dict] = None,
    dynamic_variables: Optional[dict] = None,
    agent_id: Optional[str] = None,
    agent_kind: str = "outbound",
) -> str:
    if not settings.retell_api_key:
        raise RuntimeError("RETELL_API_KEY is not set")
    if not settings.retell_from_number:
        raise RuntimeError("RETELL_FROM_NUMBER is not set")

    effective_agent_id = agent_id or _default_chat_agent_id(agent_kind=agent_kind)
    payload = {
        "from_number": settings.retell_from_number,
        "to_number": to_number,
        "metadata": {**(metadata or {})},
        "retell_llm_dynamic_variables": {
            "initial_message": body,
            **(dynamic_variables or {}),
        },
    }
    if effective_agent_id:
        payload["override_agent_id"] = effective_agent_id
    response = httpx.post(
        "https://api.retellai.com/create-sms-chat",
        headers={"Authorization": f"Bearer {settings.retell_api_key}"},
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["chat_id"]


async def get_call(call_id: str) -> dict:
    response = get_client().call.retrieve(call_id)
    return _serialize(response)


async def list_calls(limit: int = 50) -> list[dict]:
    response = get_client().call.list(limit=limit, sort_order="descending")
    if isinstance(response, list):
        return [_serialize(item) for item in response]
    return [_serialize(item) for item in getattr(response, "data", response)]


async def get_chat(chat_id: str) -> dict:
    response = httpx.get(
        f"https://api.retellai.com/get-chat/{chat_id}",
        headers={"Authorization": f"Bearer {settings.retell_api_key}"},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


async def list_chats(limit: int = 50) -> list[dict]:
    response = httpx.get(
        "https://api.retellai.com/list-chat",
        headers={"Authorization": f"Bearer {settings.retell_api_key}"},
        params={"limit": limit, "sort_order": "descending"},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "chats", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []
