"""Tests for DeriveAgent.run — covers the raw_context-preference rule
+ failure-mode degradation (no LLM calls made; _invoke is patched)."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.agents.derive import DeriveAgent
from src.core.studio_v2.agents.derive.agent import _DerivedValue


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_prefers_raw_context_over_value():
    """When both raw_context and value are present, the prompt MUST be
    built against raw_context — that's the whole point of the type."""
    captured_prompts: list[str] = []

    async def fake_invoke(prompt, run_name, metadata=None):  # noqa: ARG001
        captured_prompts.append(prompt)
        return _DerivedValue(value="extracted")

    with patch.object(DeriveAgent, "_invoke", side_effect=fake_invoke):
        rv = await DeriveAgent.run(
            child_variable="vin",
            parent_variable="vehicle_record",
            parent_raw_context="2018 Toyota Camry VIN: 1HG... mileage 82,300",
            parent_value="Camry (display)",
            extraction_prompt="Extract the VIN.",
        )

    assert rv.value == "extracted"
    assert rv.confidence == "high"
    # Verify raw_context was put into the prompt, not the display value.
    assert "1HG..." in captured_prompts[0]
    assert "Camry (display)" not in captured_prompts[0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_falls_back_to_value_when_raw_context_empty():
    captured_prompts: list[str] = []

    async def fake_invoke(prompt, run_name, metadata=None):  # noqa: ARG001
        captured_prompts.append(prompt)
        return _DerivedValue(value="from display")

    with patch.object(DeriveAgent, "_invoke", side_effect=fake_invoke):
        rv = await DeriveAgent.run(
            child_variable="x",
            parent_variable="y",
            parent_raw_context="",
            parent_value="display value",
            extraction_prompt="extract X",
        )

    assert rv.value == "from display"
    assert "display value" in captured_prompts[0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_no_parent_value_degrades_no_llm_call():
    """Empty parent → no LLM call; row carries confidence='none'."""
    with patch.object(DeriveAgent, "_invoke", new=AsyncMock()) as invoke_mock:
        rv = await DeriveAgent.run(
            child_variable="x",
            parent_variable="y",
            parent_raw_context="",
            parent_value="",
            extraction_prompt="extract X",
        )
    invoke_mock.assert_not_called()
    assert rv.confidence == "none"
    assert rv.value == ""
    assert "no value" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_no_extraction_prompt_degrades_no_llm_call():
    with patch.object(DeriveAgent, "_invoke", new=AsyncMock()) as invoke_mock:
        rv = await DeriveAgent.run(
            child_variable="x",
            parent_variable="y",
            parent_value="something",
            extraction_prompt="",
        )
    invoke_mock.assert_not_called()
    assert rv.confidence == "none"
    assert "no extraction_prompt" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_llm_exception_degrades_to_low_confidence():
    with patch.object(
        DeriveAgent, "_invoke", side_effect=RuntimeError("boom"),
    ):
        rv = await DeriveAgent.run(
            child_variable="x",
            parent_variable="y",
            parent_value="v",
            extraction_prompt="extract X",
        )
    assert rv.value == ""
    assert rv.confidence == "none"
    assert "LLM call failed" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_llm_returns_none_degrades_to_low_confidence():
    with patch.object(DeriveAgent, "_invoke", new=AsyncMock(return_value=None)):
        rv = await DeriveAgent.run(
            child_variable="x",
            parent_variable="y",
            parent_value="v",
            extraction_prompt="extract X",
        )
    assert rv.confidence == "low"
    assert "no structured output" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_llm_returns_empty_string_marks_low_confidence():
    with patch.object(
        DeriveAgent, "_invoke",
        new=AsyncMock(return_value=_DerivedValue(value="")),
    ):
        rv = await DeriveAgent.run(
            child_variable="x",
            parent_variable="y",
            parent_value="v",
            extraction_prompt="extract X",
        )
    assert rv.value == ""
    assert rv.confidence == "low"
    assert "empty string" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_strips_whitespace_from_llm_output():
    with patch.object(
        DeriveAgent, "_invoke",
        new=AsyncMock(return_value=_DerivedValue(value="  trimmed  ")),
    ):
        rv = await DeriveAgent.run(
            child_variable="x",
            parent_variable="y",
            parent_value="v",
            extraction_prompt="extract X",
        )
    assert rv.value == "trimmed"
