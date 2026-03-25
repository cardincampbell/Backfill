#!/usr/bin/env python3
"""
Register Retell AI agents with their function call schemas.

Run once (or re-run to update) after setting RETELL_API_KEY in .env:

    python scripts/setup_retell_agents.py

Creates two agents:
  1. inbound_callout  — workers calling 1-800-BACKFILL to report absences
  2. outbound_t1t2    — AI calling workers to offer open shifts

Agent IDs are printed to stdout. Copy them into your .env:
  RETELL_AGENT_ID_INBOUND=<id>
  RETELL_AGENT_ID_OUTBOUND=<id>
"""
import asyncio
import os
import sys
from pathlib import Path

# Allow running from project root or scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from retell import Retell  # type: ignore

RETELL_API_KEY = os.environ.get("RETELL_API_KEY", "")
if not RETELL_API_KEY:
    sys.exit("ERROR: RETELL_API_KEY is not set in .env")

PROMPTS_DIR = Path(__file__).parent.parent / "app" / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text()


# ── Function call schemas shared by both agents ───────────────────────────────

FUNCTION_SCHEMAS = [
    {
        "name": "lookup_caller",
        "description": "Look up the caller by phone number to identify if they are a known worker or manager.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "E.164 phone number of the caller, e.g. +13105550100",
                }
            },
            "required": ["phone"],
        },
    },
    {
        "name": "log_consent",
        "description": "Record whether the worker grants or revokes consent for Backfill to contact them.",
        "parameters": {
            "type": "object",
            "properties": {
                "worker_id": {
                    "type": "integer",
                    "description": "The ID of the worker from the lookup_caller result.",
                },
                "granted": {
                    "type": "boolean",
                    "description": "True if the worker consented, False if they opted out.",
                },
                "channel": {
                    "type": "string",
                    "description": "Channel of consent capture (inbound_call or outbound_call).",
                    "default": "inbound_call",
                },
            },
            "required": ["worker_id", "granted"],
        },
    },
    {
        "name": "create_vacancy",
        "description": "Mark a shift as vacant (worker is calling out) and start the fill cascade.",
        "parameters": {
            "type": "object",
            "properties": {
                "shift_id": {
                    "type": "integer",
                    "description": "ID of the shift the worker is calling out of.",
                },
                "worker_id": {
                    "type": "integer",
                    "description": "ID of the worker who is calling out.",
                },
            },
            "required": ["shift_id", "worker_id"],
        },
    },
    {
        "name": "claim_shift",
        "description": "Atomically claim a shift for the worker if it is still open, or place them on standby if another worker already claimed it.",
        "parameters": {
            "type": "object",
            "properties": {
                "cascade_id": {
                    "type": "integer",
                    "description": "ID of the active cascade for this shift.",
                },
                "worker_id": {
                    "type": "integer",
                    "description": "ID of the worker who was offered the shift.",
                },
                "conversation_summary": {
                    "type": "string",
                    "description": "Brief summary of the conversation for the audit log.",
                    "default": "",
                },
            },
            "required": ["cascade_id", "worker_id"],
        },
    },
    {
        "name": "decline_shift",
        "description": "Record that a worker declined an outbound shift offer.",
        "parameters": {
            "type": "object",
            "properties": {
                "cascade_id": {
                    "type": "integer",
                    "description": "ID of the active cascade for this shift.",
                },
                "worker_id": {
                    "type": "integer",
                    "description": "ID of the worker who was offered the shift.",
                },
                "conversation_summary": {
                    "type": "string",
                    "description": "Brief summary of the conversation for the audit log.",
                    "default": "",
                },
            },
            "required": ["cascade_id", "worker_id"],
        },
    },
    {
        "name": "cancel_standby",
        "description": "Remove a worker from the standby queue for a shift.",
        "parameters": {
            "type": "object",
            "properties": {
                "cascade_id": {
                    "type": "integer",
                    "description": "ID of the active or recently completed cascade.",
                },
                "worker_id": {
                    "type": "integer",
                    "description": "ID of the standby worker.",
                },
                "conversation_summary": {
                    "type": "string",
                    "description": "Brief summary of the conversation for the audit log.",
                    "default": "",
                },
            },
            "required": ["cascade_id", "worker_id"],
        },
    },
    {
        "name": "promote_standby",
        "description": "Confirm a standby worker after the shift reopens.",
        "parameters": {
            "type": "object",
            "properties": {
                "cascade_id": {
                    "type": "integer",
                    "description": "ID of the related cascade.",
                },
                "worker_id": {
                    "type": "integer",
                    "description": "ID of the standby worker being promoted.",
                },
                "conversation_summary": {
                    "type": "string",
                    "description": "Brief summary of the conversation for the audit log.",
                    "default": "",
                },
            },
            "required": ["cascade_id", "worker_id"],
        },
    },
    {
        "name": "confirm_fill",
        "description": "Backward-compatible alias for older agent configs. Prefer claim_shift or decline_shift for new agents.",
        "parameters": {
            "type": "object",
            "properties": {
                "cascade_id": {
                    "type": "integer",
                    "description": "ID of the active cascade for this shift.",
                },
                "worker_id": {
                    "type": "integer",
                    "description": "ID of the worker who was offered the shift.",
                },
                "accepted": {
                    "type": "boolean",
                    "description": "True if the worker accepted, False if declined.",
                },
                "conversation_summary": {
                    "type": "string",
                    "description": "Brief summary of the conversation for the audit log.",
                    "default": "",
                },
            },
            "required": ["cascade_id", "worker_id", "accepted"],
        },
    },
    {
        "name": "get_open_shifts",
        "description": "Retrieve a list of currently open (vacant) shifts, optionally for a specific restaurant.",
        "parameters": {
            "type": "object",
            "properties": {
                "restaurant_id": {
                    "type": "integer",
                    "description": "Filter by restaurant ID (optional).",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_shift_status",
        "description": "Get the full status of a specific shift including cascade and outreach attempts.",
        "parameters": {
            "type": "object",
            "properties": {
                "shift_id": {
                    "type": "integer",
                    "description": "ID of the shift to look up.",
                }
            },
            "required": ["shift_id"],
        },
    },
    {
        "name": "create_open_shift",
        "description": "Create a new vacant shift and immediately start outreach to fill it. Used by managers calling in.",
        "parameters": {
            "type": "object",
            "properties": {
                "restaurant_id": {
                    "type": "integer",
                    "description": "ID of the restaurant that needs coverage.",
                },
                "role": {
                    "type": "string",
                    "description": "Role needed, e.g. 'line_cook', 'server', 'dishwasher'.",
                },
                "date": {
                    "type": "string",
                    "description": "Shift date in YYYY-MM-DD format.",
                },
                "start_time": {
                    "type": "string",
                    "description": "Shift start time in HH:MM:SS format.",
                },
                "end_time": {
                    "type": "string",
                    "description": "Shift end time in HH:MM:SS format.",
                },
                "pay_rate": {
                    "type": "number",
                    "description": "Hourly pay rate for the shift.",
                },
                "requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of required certifications or skills, e.g. ['food_handler_card'].",
                    "default": [],
                },
            },
            "required": ["restaurant_id", "role", "date", "start_time", "end_time", "pay_rate"],
        },
    },
    {
        "name": "send_onboarding_link",
        "description": "Text the manager the correct Backfill onboarding link based on their scheduler situation.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "Manager phone number in E.164 format.",
                },
                "kind": {
                    "type": "string",
                    "description": "One of integration, csv_upload, or manual_form.",
                },
                "platform": {
                    "type": "string",
                    "description": "Optional scheduler name for integration handoff: 7shifts, deputy, wheniwork, or homebase.",
                },
            },
            "required": ["phone", "kind"],
        },
    },
]

WEBHOOK_URL = os.environ.get("BACKFILL_WEBHOOK_URL", "http://127.0.0.1:8000") + "/webhooks/retell"


def _create_agent(client: Retell, name: str, prompt: str) -> dict:
    """Create a Retell agent and return the full response object."""
    agent = client.agent.create(
        agent_name=name,
        response_engine={
            "type": "retell-llm",
            "llm_id": _get_or_create_llm(client, name, prompt),
        },
        voice_id="11labs-Adrian",  # clear, professional US English voice
        enable_backchannel=True,
        interruption_sensitivity=0.9,
        webhook_url=WEBHOOK_URL,
    )
    return agent


def _get_or_create_llm(client: Retell, name: str, prompt: str) -> str:
    """Create a Retell LLM config with the given prompt and function schemas."""
    llm = client.llm.create(
        model="gpt-4o",
        general_prompt=prompt,
        general_tools=[
            {
                "type": "custom",
                "name": fn["name"],
                "description": fn["description"],
                "parameters": fn["parameters"],
                "speak_during_execution": False,
                "speak_after_execution": True,
            }
            for fn in FUNCTION_SCHEMAS
        ],
    )
    return llm.llm_id


def main():
    client = Retell(api_key=RETELL_API_KEY)

    print("Creating inbound callout agent...")
    inbound = _create_agent(
        client,
        name="Backfill Inbound Callout",
        prompt=_load_prompt("inbound_callout.txt"),
    )
    print(f"  ✓ inbound agent_id: {inbound.agent_id}")

    print("Creating outbound shift offer agent...")
    outbound = _create_agent(
        client,
        name="Backfill Outbound Shift Offer",
        prompt=_load_prompt("outbound_voice_t1t2.txt"),
    )
    print(f"  ✓ outbound agent_id: {outbound.agent_id}")

    print()
    print("Add these to your .env:")
    print(f"  RETELL_AGENT_ID_INBOUND={inbound.agent_id}")
    print(f"  RETELL_AGENT_ID_OUTBOUND={outbound.agent_id}")


if __name__ == "__main__":
    main()
