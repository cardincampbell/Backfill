from __future__ import annotations

from typing import Any, Optional


def build_completed_response(
    *,
    action_request_id: int,
    summary: str,
    risk_class: Optional[str] = None,
    ui_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "action_request_id": action_request_id,
        "status": "completed",
        "mode": "result",
        "summary": summary,
        "risk_class": risk_class,
        "requires_confirmation": False,
        "ui_payload": ui_payload,
        "next_actions": [],
    }


def build_confirmation_response(
    *,
    action_request_id: int,
    summary: str,
    risk_class: str,
    confirmation_prompt: str,
    affected_entities: list[dict[str, Any]],
    ui_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "action_request_id": action_request_id,
        "status": "awaiting_confirmation",
        "mode": "confirmation",
        "summary": summary,
        "risk_class": risk_class,
        "requires_confirmation": True,
        "confirmation": {
            "prompt": confirmation_prompt,
            "affected_entities": affected_entities,
        },
        "ui_payload": ui_payload,
        "next_actions": [
            {"type": "confirm", "label": "Confirm"},
            {"type": "cancel", "label": "Cancel"},
        ],
    }


def build_clarification_response(
    *,
    action_request_id: int,
    summary: str,
    risk_class: str,
    clarification_prompt: str,
    candidates: list[dict[str, Any]],
    ui_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload = {
        "action_request_id": action_request_id,
        "status": "awaiting_clarification",
        "mode": "clarification",
        "summary": summary,
        "risk_class": risk_class,
        "requires_confirmation": False,
        "clarification": {
            "prompt": clarification_prompt,
            "candidates": candidates,
        },
        "ui_payload": ui_payload,
        "next_actions": [
            {"type": "clarify", "label": "Choose option"},
            {"type": "cancel", "label": "Cancel"},
        ],
    }
    if payload["ui_payload"] is None:
        payload["ui_payload"] = {
            "kind": "clarification_options",
            "data": payload["clarification"],
        }
    return payload


def build_redirect_response(
    *,
    action_request_id: int,
    summary: str,
    reason: str,
    url: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    payload = {
        "action_request_id": action_request_id,
        "status": "redirected",
        "mode": "redirect",
        "summary": summary,
        "risk_class": "red",
        "requires_confirmation": False,
        "redirect": {
            "reason": reason,
            "url": url or "",
            "label": label or "Open in Backfill",
        },
        "next_actions": [],
    }
    if url:
        payload["next_actions"] = [{"type": "open_url", "label": payload["redirect"]["label"], "value": url}]
    return payload


def build_error_response(
    *,
    action_request_id: int,
    summary: str,
) -> dict[str, Any]:
    return {
        "action_request_id": action_request_id,
        "status": "failed",
        "mode": "error",
        "summary": summary,
        "requires_confirmation": False,
        "next_actions": [],
    }


def build_cancelled_response(
    *,
    action_request_id: int,
) -> dict[str, Any]:
    return {
        "action_request_id": action_request_id,
        "status": "cancelled",
        "mode": "cancelled",
        "summary": "Cancelled. No changes were made.",
        "requires_confirmation": False,
        "next_actions": [],
    }


def build_expired_response(
    *,
    action_request_id: int,
    summary: str | None = None,
) -> dict[str, Any]:
    return {
        "action_request_id": action_request_id,
        "status": "expired",
        "mode": "expired",
        "summary": summary or "This AI action expired before it was completed. Retry it to continue.",
        "requires_confirmation": False,
        "next_actions": [
            {"type": "retry", "label": "Retry"},
        ],
    }
