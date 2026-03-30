from __future__ import annotations

from typing import Any


SUPPORTED_PHASE1_ACTIONS = {
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
}


async def build_action_plan(
    *,
    intent: dict[str, Any],
    resolution: dict[str, Any],
    channel: str,
) -> dict[str, Any]:
    candidates = list(intent.get("action_candidates") or [])
    action_type = str(candidates[0] if candidates else "get_schedule_summary")
    schedule = resolution.get("schedule")
    location = resolution.get("location") or {}
    action_params = dict(resolution.get("action_params") or {})

    if action_type not in SUPPORTED_PHASE1_ACTIONS:
        return {
            "supported": False,
            "action_type": action_type,
            "risk_class": "red",
            "requires_confirmation": False,
            "confirmation_reason_codes": [],
            "redirect_reason": "unsupported_action",
            "proposed_actions": [],
        }

    if resolution.get("needs_clarification"):
        return {
            "supported": True,
            "action_type": action_type,
            "risk_class": "yellow" if action_type in {"publish_schedule", "create_open_shift", "edit_shift", "delete_shift", "assign_shift", "clear_shift_assignment", "approve_fill", "decline_fill", "open_shift", "cancel_open_shift_offer", "close_open_shift", "reopen_open_shift", "reopen_and_offer_open_shift"} else "green",
            "requires_confirmation": action_type in {"publish_schedule", "create_open_shift", "edit_shift", "delete_shift", "assign_shift", "clear_shift_assignment", "approve_fill", "decline_fill", "open_shift", "cancel_open_shift_offer", "close_open_shift", "reopen_open_shift", "reopen_and_offer_open_shift"},
            "requires_clarification": True,
            "confirmation_reason_codes": [],
            "redirect_reason": None,
            "clarification": dict(resolution.get("clarification") or {}),
            "proposed_actions": [
                {
                    "action_type": action_type,
                    "params": action_params,
                }
            ],
        }

    if action_type in {"publish_schedule", "create_open_shift", "edit_shift", "delete_shift", "assign_shift", "clear_shift_assignment", "approve_fill", "decline_fill", "open_shift", "cancel_open_shift_offer", "close_open_shift", "reopen_open_shift", "reopen_and_offer_open_shift"}:
        reason_code = {
            "publish_schedule": "publish_blast_radius",
            "create_open_shift": "create_open_shift_confirmation",
            "edit_shift": "shift_edit_confirmation",
            "delete_shift": "shift_delete_confirmation",
            "assign_shift": "shift_assignment_confirmation",
            "clear_shift_assignment": "shift_clear_assignment_confirmation",
            "approve_fill": "fill_approval_confirmation",
            "decline_fill": "fill_decline_confirmation",
            "open_shift": "open_shift_outreach_confirmation",
            "cancel_open_shift_offer": "open_shift_offer_cancel_confirmation",
            "close_open_shift": "open_shift_close_confirmation",
            "reopen_open_shift": "open_shift_reopen_confirmation",
            "reopen_and_offer_open_shift": "open_shift_reopen_offer_confirmation",
        }[action_type]
        return {
            "supported": True,
            "action_type": action_type,
            "risk_class": "yellow",
            "requires_confirmation": True,
            "requires_clarification": False,
            "confirmation_reason_codes": [reason_code],
            "redirect_reason": None,
            "proposed_actions": [
                {
                    "action_type": action_type,
                    "params": {
                        "location_id": int(action_params.get("location_id") or location["id"]),
                        "schedule_id": int(action_params["schedule_id"]) if action_params.get("schedule_id") is not None else int(schedule["id"]) if schedule is not None else None,
                        "week_start_date": action_params.get("week_start_date") or resolution.get("week_start_date"),
                        "shift_id": int(action_params["shift_id"]) if action_params.get("shift_id") is not None else None,
                        "worker_id": int(action_params["worker_id"]) if action_params.get("worker_id") is not None else None,
                        "cascade_id": int(action_params["cascade_id"]) if action_params.get("cascade_id") is not None else None,
                        "create_shift_payload": dict(action_params.get("create_shift_payload") or {}),
                        "shift_patch": dict(action_params.get("shift_patch") or {}),
                    },
                }
            ],
        }

    return {
        "supported": True,
        "action_type": action_type,
        "risk_class": "green",
        "requires_confirmation": False,
        "requires_clarification": False,
        "confirmation_reason_codes": [],
        "redirect_reason": None,
        "proposed_actions": [
            {
                "action_type": action_type,
                "params": {
                    "location_id": int(action_params.get("location_id") or location["id"]),
                    "schedule_id": int(action_params["schedule_id"]) if action_params.get("schedule_id") is not None else int(schedule["id"]) if schedule is not None else None,
                    "week_start_date": action_params.get("week_start_date") or resolution.get("week_start_date"),
                },
            }
        ],
    }
