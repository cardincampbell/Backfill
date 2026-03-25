"""
Thin wrapper around the Retell SDK.
All Retell API calls go through here so the rest of the app never imports retell directly.
"""
from typing import Optional
from retell import Retell
from app.config import settings

_client: Optional[Retell] = None


def get_client() -> Retell:
    global _client
    if _client is None:
        if not settings.retell_api_key:
            raise RuntimeError("RETELL_API_KEY is not set")
        _client = Retell(api_key=settings.retell_api_key)
    return _client


async def create_phone_call(
    to_number: str,
    metadata: dict,
    agent_id: Optional[str] = None,
    agent_kind: str = "outbound",
) -> str:
    """Trigger an outbound call. Returns the Retell call_id."""
    client = get_client()
    default_agent_id = settings.retell_agent_id
    if agent_kind == "inbound":
        default_agent_id = settings.retell_agent_id_inbound or default_agent_id
    elif agent_kind == "outbound":
        default_agent_id = settings.retell_agent_id_outbound or default_agent_id
    aid = agent_id or default_agent_id
    if not aid:
        raise RuntimeError(
            "Retell agent ID is not set. Configure RETELL_AGENT_ID_OUTBOUND or RETELL_AGENT_ID."
        )
    if not settings.retell_from_number:
        raise RuntimeError("RETELL_FROM_NUMBER is not set")

    response = client.call.create_phone_call(
        from_number=settings.retell_from_number,
        to_number=to_number,
        override_agent_id=aid,
        metadata=metadata,
    )
    return response.call_id
