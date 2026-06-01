"""Tests for AutoDeriveAgent — extracts derived value from parent's resolved value."""

import pytest

from src.core.agents.llm.auto_derive import AutoDeriveAgent, _DerivedValue


@pytest.mark.unit
async def test_run_returns_derived_value_from_invoke(mock_agent_invoke):
    captured = mock_agent_invoke(_DerivedValue(value="3"))

    result = await AutoDeriveAgent.run(
        parent_variable="ecf_number_document_description",
        parent_value="3, being a Certification of Budget and Credit Counseling Course by Debtor",
        derived_marker="3",
        derived_context="NOTICE TO WITHDRAW DOCUMENT (ECF 3)",
    )

    assert result == "3"
    assert captured["run_name"] == "AutoDerive"
    assert captured["metadata"] == {"parent_variable": "ecf_number_document_description"}


@pytest.mark.unit
async def test_run_returns_empty_on_none(mock_agent_invoke):
    mock_agent_invoke(None)

    result = await AutoDeriveAgent.run(
        parent_variable="x",
        parent_value="parent text",
        derived_marker="m",
        derived_context="context",
    )

    assert result == ""


@pytest.mark.unit
async def test_run_returns_empty_on_exception(mock_agent_invoke):
    """LLM failure must not bubble — AutoDerivedResolver relies on gather()
    succeeding even if one derivation fails."""
    mock_agent_invoke(RuntimeError("LLM down"))

    result = await AutoDeriveAgent.run(
        parent_variable="x",
        parent_value="parent text",
        derived_marker="m",
        derived_context="context",
    )

    assert result == ""


@pytest.mark.unit
async def test_run_returns_empty_on_blank_value(mock_agent_invoke):
    """Empty `value` from the LLM means 'cannot derive' → return empty so
    the caller can skip emitting a ResolvedTemplateValue for this field."""
    mock_agent_invoke(_DerivedValue(value=""))

    result = await AutoDeriveAgent.run(
        parent_variable="x",
        parent_value="parent",
        derived_marker="m",
        derived_context="c",
    )

    assert result == ""


@pytest.mark.unit
async def test_run_injects_all_four_fields_into_prompt(mock_agent_invoke):
    captured = mock_agent_invoke(_DerivedValue(value="ignored"))

    await AutoDeriveAgent.run(
        parent_variable="parent_var",
        parent_value="parent value with details",
        derived_marker="DERIVED_MARK",
        derived_context="surrounding CONTEXT here",
    )

    prompt = captured["prompt"]
    assert "parent_var" in prompt
    assert "parent value with details" in prompt
    assert "DERIVED_MARK" in prompt
    assert "surrounding CONTEXT here" in prompt
