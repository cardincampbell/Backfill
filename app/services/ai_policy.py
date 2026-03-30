from __future__ import annotations

from typing import Any

from app.config import settings


_ACTION_METADATA = {
    "get_schedule_summary": {
        "label": "Schedule summary",
        "domain": "schedule",
        "read_only": True,
        "requires_confirmation": False,
        "supports_clarification": False,
    },
    "get_unfilled_shifts": {
        "label": "Unfilled shifts",
        "domain": "coverage",
        "read_only": True,
        "requires_confirmation": False,
        "supports_clarification": False,
    },
    "get_coverage_status": {
        "label": "Coverage status",
        "domain": "coverage",
        "read_only": True,
        "requires_confirmation": False,
        "supports_clarification": False,
    },
    "get_publish_readiness": {
        "label": "Publish readiness",
        "domain": "schedule",
        "read_only": True,
        "requires_confirmation": False,
        "supports_clarification": False,
    },
    "explain_schedule_issues": {
        "label": "Explain schedule issues",
        "domain": "schedule",
        "read_only": True,
        "requires_confirmation": False,
        "supports_clarification": False,
    },
    "publish_schedule": {
        "label": "Publish schedule",
        "domain": "schedule",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": False,
    },
    "create_open_shift": {
        "label": "Create open shift",
        "domain": "schedule",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": False,
    },
    "edit_shift": {
        "label": "Edit shift",
        "domain": "schedule",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": True,
    },
    "delete_shift": {
        "label": "Delete shift",
        "domain": "schedule",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": True,
    },
    "assign_shift": {
        "label": "Assign shift",
        "domain": "schedule",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": True,
    },
    "clear_shift_assignment": {
        "label": "Clear shift assignment",
        "domain": "schedule",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": True,
    },
    "approve_fill": {
        "label": "Approve fill",
        "domain": "coverage",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": True,
    },
    "decline_fill": {
        "label": "Decline fill",
        "domain": "coverage",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": True,
    },
    "open_shift": {
        "label": "Start open-shift coverage",
        "domain": "coverage",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": True,
    },
    "cancel_open_shift_offer": {
        "label": "Cancel open-shift offer",
        "domain": "coverage",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": True,
    },
    "close_open_shift": {
        "label": "Close open shift",
        "domain": "schedule",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": True,
    },
    "reopen_open_shift": {
        "label": "Reopen open shift",
        "domain": "schedule",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": True,
    },
    "reopen_and_offer_open_shift": {
        "label": "Reopen and offer open shift",
        "domain": "coverage",
        "read_only": False,
        "requires_confirmation": True,
        "supports_clarification": True,
    },
}

_CHANNEL_ACTIONS = {
    "web": {
        "get_schedule_summary",
        "get_unfilled_shifts",
        "get_coverage_status",
        "get_publish_readiness",
        "explain_schedule_issues",
        "publish_schedule",
        "create_open_shift",
        "edit_shift",
        "delete_shift",
        "assign_shift",
        "clear_shift_assignment",
        "approve_fill",
        "decline_fill",
        "open_shift",
        "cancel_open_shift_offer",
        "close_open_shift",
        "reopen_open_shift",
        "reopen_and_offer_open_shift",
    },
    "sms": {
        "get_schedule_summary",
        "get_unfilled_shifts",
        "get_coverage_status",
        "get_publish_readiness",
        "explain_schedule_issues",
        "publish_schedule",
        "create_open_shift",
        "edit_shift",
        "delete_shift",
        "assign_shift",
        "clear_shift_assignment",
        "open_shift",
        "cancel_open_shift_offer",
        "close_open_shift",
        "reopen_open_shift",
        "reopen_and_offer_open_shift",
    },
    "voice": {
        "get_schedule_summary",
        "get_unfilled_shifts",
        "get_coverage_status",
        "get_publish_readiness",
        "explain_schedule_issues",
        "publish_schedule",
        "create_open_shift",
        "edit_shift",
        "delete_shift",
        "assign_shift",
        "clear_shift_assignment",
        "approve_fill",
        "decline_fill",
        "open_shift",
        "cancel_open_shift_offer",
        "close_open_shift",
        "reopen_open_shift",
        "reopen_and_offer_open_shift",
    },
}


def select_intent_provider(*, channel: str) -> str:
    requested = (settings.backfill_ai_provider or "rules").strip().lower() or "rules"
    if requested != "openai":
        return requested
    if channel.strip().lower() in set(settings.backfill_ai_openai_channels or []):
        return "openai"
    return "rules"


def _disabled_actions_for_channel(channel: str) -> set[str]:
    normalized_channel = channel.strip().lower()
    disabled = set(settings.backfill_ai_disabled_actions or [])
    if normalized_channel == "web":
        disabled.update(settings.backfill_ai_disabled_actions_web or [])
    elif normalized_channel == "sms":
        disabled.update(settings.backfill_ai_disabled_actions_sms or [])
    elif normalized_channel == "voice":
        disabled.update(settings.backfill_ai_disabled_actions_voice or [])
    return {value.strip().lower() for value in disabled if str(value).strip()}


def provider_policy_snapshot() -> dict[str, Any]:
    channels = {channel: select_intent_provider(channel=channel) for channel in _CHANNEL_ACTIONS}
    return {
        "default_provider": (settings.backfill_ai_provider or "rules").strip().lower() or "rules",
        "intent_provider_by_channel": channels,
        "openai_channels": list(settings.backfill_ai_openai_channels or []),
        "fallback_enabled": bool(settings.backfill_ai_fallback_enabled),
        "fallback_provider": (settings.backfill_ai_fallback_provider or "rules").strip().lower() or "rules",
        "disabled_actions": sorted(_disabled_actions_for_channel("web") | _disabled_actions_for_channel("sms") | _disabled_actions_for_channel("voice")),
        "disabled_actions_by_channel": {
            "web": sorted(_disabled_actions_for_channel("web")),
            "sms": sorted(_disabled_actions_for_channel("sms")),
            "voice": sorted(_disabled_actions_for_channel("voice")),
        },
    }


def action_capabilities() -> list[dict[str, Any]]:
    capabilities: list[dict[str, Any]] = []
    for action_type, meta in _ACTION_METADATA.items():
        channels = sorted(channel for channel, actions in _CHANNEL_ACTIONS.items() if action_type in actions)
        enabled_by_channel = {
            channel: action_type in _CHANNEL_ACTIONS.get(channel, set()) and action_type not in _disabled_actions_for_channel(channel)
            for channel in _CHANNEL_ACTIONS
        }
        capabilities.append(
            {
                "action_type": action_type,
                "channels": channels,
                "enabled_by_channel": enabled_by_channel,
                "disabled_channels": sorted(channel for channel, enabled in enabled_by_channel.items() if not enabled),
                **meta,
            }
        )
    return capabilities


async def evaluate_policy(
    *,
    channel: str,
    action_type: str,
) -> dict[str, Any]:
    allowed = action_type in _CHANNEL_ACTIONS.get(channel, set())
    if allowed and action_type in _disabled_actions_for_channel(channel):
        allowed = False
        redirect_reason = "action_disabled"
    else:
        redirect_reason = None if allowed else "unsupported_action"
    return {
        "allowed": allowed,
        "redirect_reason": redirect_reason,
    }
