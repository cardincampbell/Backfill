from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _normalized_string(value: object | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalized_string_list(value: object | None) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in value or []:
        normalized = _normalized_string(item)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _unique_rule_codes(value: object | None) -> list[str]:
    normalized = {
        str(rule_code or "").strip()
        for rule_code in value or []
        if str(rule_code or "").strip()
    }
    return sorted(normalized)


def _policy_rule_reference(
    *,
    rule_code: str,
    policy_version_id: object | None,
    policy_hash: object | None,
    policy_effective_at: object | None,
    policy_scope: object | None,
) -> dict[str, object]:
    return {
        "rule_code": rule_code,
        "source_kind": "policy_overlay",
        "source_code": _normalized_string(policy_scope) or "policy_overlay",
        "source_label": "Customer policy overlay",
        "jurisdiction_code": None,
        "source_document_title": None,
        "source_urls": [],
        "source_version": None,
        "source_hash": None,
        "version_id": _normalized_string(policy_version_id),
        "payload_hash": _normalized_string(policy_hash),
        "effective_at": policy_effective_at,
    }


def _work_permit_rule_reference(
    *,
    rule_code: str,
    template_code: object | None,
    template_label: object | None,
    jurisdiction_code: object | None,
    source_document_title: object | None,
    source_urls: object | None,
    source_version: object | None,
    source_hash: object | None,
    payload_hash: object | None,
    effective_at: object | None = None,
) -> dict[str, object]:
    return {
        "rule_code": rule_code,
        "source_kind": "work_permit_template",
        "source_code": _normalized_string(template_code),
        "source_label": _normalized_string(template_label),
        "jurisdiction_code": _normalized_string(jurisdiction_code),
        "source_document_title": _normalized_string(source_document_title),
        "source_urls": _normalized_string_list(source_urls),
        "source_version": _normalized_string(source_version),
        "source_hash": _normalized_string(source_hash),
        "version_id": None,
        "payload_hash": _normalized_string(payload_hash),
        "effective_at": effective_at,
    }


def _labor_rule_reference(
    *,
    rule_code: str,
    profile_code: object | None,
    profile_display_name: object | None,
    jurisdiction_code: object | None,
    source_document_title: object | None,
    source_urls: object | None,
    source_version: object | None,
    source_hash: object | None,
    version_id: object | None,
    payload_hash: object | None,
    effective_at: object | None = None,
) -> dict[str, object]:
    return {
        "rule_code": rule_code,
        "source_kind": "labor_rule_profile",
        "source_code": _normalized_string(profile_code),
        "source_label": _normalized_string(profile_display_name),
        "jurisdiction_code": _normalized_string(jurisdiction_code),
        "source_document_title": _normalized_string(source_document_title),
        "source_urls": _normalized_string_list(source_urls),
        "source_version": _normalized_string(source_version),
        "source_hash": _normalized_string(source_hash),
        "version_id": _normalized_string(version_id),
        "payload_hash": _normalized_string(payload_hash),
        "effective_at": effective_at,
    }


def _unknown_rule_reference(
    *,
    rule_code: str,
) -> dict[str, object]:
    return {
        "rule_code": rule_code,
        "source_kind": "unknown",
        "source_code": None,
        "source_label": None,
        "jurisdiction_code": None,
        "source_document_title": None,
        "source_urls": [],
        "source_version": None,
        "source_hash": None,
        "version_id": None,
        "payload_hash": None,
        "effective_at": None,
    }


def build_rule_source_references(
    *,
    rule_codes: list[str],
    profile_code: object | None = None,
    profile_display_name: object | None = None,
    profile_version_id: object | None = None,
    profile_payload_hash: object | None = None,
    profile_source_version: object | None = None,
    profile_source_hash: object | None = None,
    profile_source_urls: object | None = None,
    jurisdiction_code: object | None = None,
    policy_version_id: object | None = None,
    policy_hash: object | None = None,
    policy_effective_at: object | None = None,
    policy_scope: object | None = None,
    work_permit_template_code: object | None = None,
    work_permit_template_label: object | None = None,
    work_permit_jurisdiction_code: object | None = None,
    work_permit_source_document_title: object | None = None,
    work_permit_source_urls: object | None = None,
    work_permit_source_version: object | None = None,
    work_permit_source_hash: object | None = None,
    work_permit_payload_hash: object | None = None,
) -> list[dict[str, object]]:
    references: list[dict[str, object]] = []
    template_code = _normalized_string(work_permit_template_code)
    for rule_code in sorted({code for code in rule_codes if code}):
        if rule_code.startswith("customer_policy_"):
            references.append(
                _policy_rule_reference(
                    rule_code=rule_code,
                    policy_version_id=policy_version_id,
                    policy_hash=policy_hash,
                    policy_effective_at=policy_effective_at,
                    policy_scope=policy_scope,
                )
            )
            continue
        if rule_code.startswith("minor_work_permit_") and template_code is not None:
            references.append(
                _work_permit_rule_reference(
                    rule_code=rule_code,
                    template_code=template_code,
                    template_label=work_permit_template_label,
                    jurisdiction_code=work_permit_jurisdiction_code,
                    source_document_title=work_permit_source_document_title,
                    source_urls=work_permit_source_urls,
                    source_version=work_permit_source_version,
                    source_hash=work_permit_source_hash,
                    payload_hash=work_permit_payload_hash,
                )
            )
            continue
        if not any(
            (
                _normalized_string(profile_code),
                _normalized_string(profile_display_name),
                _normalized_string(profile_version_id),
                _normalized_string(profile_payload_hash),
                _normalized_string(profile_source_version),
                _normalized_string(profile_source_hash),
                _normalized_string(jurisdiction_code),
                _normalized_string_list(profile_source_urls),
            )
        ):
            references.append(
                _unknown_rule_reference(rule_code=rule_code)
            )
            continue
        references.append(
            _labor_rule_reference(
                rule_code=rule_code,
                profile_code=profile_code,
                profile_display_name=profile_display_name,
                jurisdiction_code=jurisdiction_code,
                source_document_title=None,
                source_urls=profile_source_urls,
                source_version=profile_source_version,
                source_hash=profile_source_hash,
                version_id=profile_version_id,
                payload_hash=profile_payload_hash,
            )
        )
    return references


def rule_source_references_from_evaluation(
    evaluation: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    payload = dict(evaluation or {})
    raw_existing = payload.get("rule_source_references")
    if isinstance(raw_existing, list):
        normalized_existing: list[dict[str, object]] = []
        for item in raw_existing:
            if isinstance(item, Mapping):
                normalized_existing.append(dict(item))
        if normalized_existing:
            return normalized_existing
    rule_codes = sorted(
        set(
            _unique_rule_codes(payload.get("blocking_rule_codes"))
            + _unique_rule_codes(payload.get("warning_rule_codes"))
            + _unique_rule_codes(payload.get("premium_rule_codes"))
            + _unique_rule_codes(payload.get("unresolved_premium_rule_codes"))
        )
    )
    return build_rule_source_references(
        rule_codes=rule_codes,
        profile_code=payload.get("profile_code"),
        profile_display_name=payload.get("profile_display_name"),
        profile_version_id=payload.get("profile_version_id"),
        profile_payload_hash=payload.get("profile_payload_hash"),
        profile_source_version=payload.get("profile_source_version"),
        profile_source_hash=payload.get("profile_source_hash"),
        profile_source_urls=payload.get("profile_source_urls"),
        jurisdiction_code=payload.get("jurisdiction_code"),
        policy_version_id=payload.get("policy_version_id"),
        policy_hash=payload.get("policy_hash"),
        policy_effective_at=payload.get("policy_effective_at"),
        policy_scope=payload.get("policy_scope"),
        work_permit_template_code=payload.get("work_permit_template_code"),
        work_permit_template_label=payload.get("work_permit_template_label"),
        work_permit_jurisdiction_code=payload.get("work_permit_jurisdiction_code"),
        work_permit_source_document_title=payload.get("work_permit_source_document_title"),
        work_permit_source_urls=payload.get("work_permit_source_urls"),
        work_permit_source_version=payload.get("work_permit_source_version"),
        work_permit_source_hash=payload.get("work_permit_source_hash"),
        work_permit_payload_hash=payload.get("work_permit_payload_hash"),
    )


def filter_rule_source_references(
    references: object | None,
    *,
    rule_codes: list[str] | None = None,
) -> list[dict[str, object]]:
    normalized_refs = [
        dict(item)
        for item in references or []
        if isinstance(item, Mapping)
    ]
    if not normalized_refs or not rule_codes:
        return normalized_refs
    allowed_codes = {code for code in rule_codes if code}
    return [
        reference
        for reference in normalized_refs
        if str(reference.get("rule_code") or "") in allowed_codes
    ]
