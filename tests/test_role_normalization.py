from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.business import Role
from app.services import llm_gateway, role_normalization


def _make_role(name: str) -> Role:
    now = datetime.now(timezone.utc)
    return Role(
        id=uuid4(),
        business_id=uuid4(),
        code=name.lower().replace(" ", "_"),
        name=name,
        category=None,
        description=None,
        min_notice_minutes=0,
        default_shift_length_minutes=None,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_normalize_role_name_reuses_exact_existing_match(monkeypatch):
    existing_roles = [_make_role("Barista")]

    async def fake_generate(*_args, **_kwargs):
        raise AssertionError("llm should not be called for exact matches")

    monkeypatch.setattr("app.services.role_normalization.llm_gateway.generate", fake_generate)
    monkeypatch.setattr(
        role_normalization,
        "settings",
        SimpleNamespace(role_normalization_model="gpt-test", openai_api_key="test-key"),
    )

    result = await role_normalization.normalize_role_name(
        object(),
        business_id=uuid4(),
        raw_name=" barista ",
        existing_roles=existing_roles,
    )

    assert result.decision == "reuse_existing"
    assert result.matched_role == existing_roles[0]
    assert result.normalized_name == "Barista"


@pytest.mark.asyncio
async def test_normalize_role_name_uses_llm_to_reuse_existing_role(monkeypatch):
    existing_roles = [_make_role("Barista")]

    async def fake_generate(_session, *, request):
        assert request.provider == llm_gateway.LlmProvider.OPENAI
        assert request.model == "gpt-test"
        return llm_gateway.LlmGenerationResult(
            provider=request.provider or "",
            model=request.model or "",
            output_text=(
                '{"decision":"reuse_existing","normalized_name":"Barista",'
                '"matched_existing_name":"Barista","confidence":0.97,'
                '"reason":"Corrected a spelling variation."}'
            ),
        )

    monkeypatch.setattr("app.services.role_normalization.llm_gateway.generate", fake_generate)
    monkeypatch.setattr(
        role_normalization,
        "settings",
        SimpleNamespace(role_normalization_model="gpt-test", openai_api_key="test-key"),
    )

    result = await role_normalization.normalize_role_name(
        object(),
        business_id=uuid4(),
        raw_name="Barrista",
        existing_roles=existing_roles,
    )

    assert result.decision == "reuse_existing"
    assert result.matched_role == existing_roles[0]
    assert result.normalized_name == "Barista"
    assert result.confidence == pytest.approx(0.97)


@pytest.mark.asyncio
async def test_normalize_role_name_rejects_low_confidence_candidate(monkeypatch):
    async def fake_generate(_session, *, request):
        return llm_gateway.LlmGenerationResult(
            provider=request.provider or "",
            model=request.model or "",
            output_text=(
                '{"decision":"create_new","normalized_name":"Shift Hero",'
                '"matched_existing_name":null,"confidence":0.32,'
                '"reason":"Unclear whether this is a real role."}'
            ),
        )

    monkeypatch.setattr("app.services.role_normalization.llm_gateway.generate", fake_generate)
    monkeypatch.setattr(
        role_normalization,
        "settings",
        SimpleNamespace(role_normalization_model="gpt-test", openai_api_key="test-key"),
    )

    result = await role_normalization.normalize_role_name(
        object(),
        business_id=uuid4(),
        raw_name="shift hero",
        existing_roles=[],
    )

    assert result.decision == "reject"
    assert result.reason == "Unclear whether this is a real role."


@pytest.mark.asyncio
async def test_normalize_role_name_rejects_placeholder_without_llm(monkeypatch):
    monkeypatch.setattr(
        role_normalization,
        "settings",
        SimpleNamespace(role_normalization_model="", openai_api_key=""),
    )

    result = await role_normalization.normalize_role_name(
        object(),
        business_id=uuid4(),
        raw_name="test",
        existing_roles=[],
    )

    assert result.decision == "reject"
    assert result.reason == "Enter a real role name instead of a placeholder."
