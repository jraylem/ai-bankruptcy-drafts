"""Tests for DropdownAgent — extracts up to 20 single-column options.

Extractive (not generative). Returns `_ExtractedOptions` carrying both the
option list AND a `completeness` self-assessment ("full" / "partial" /
"unknown") + `completeness_reasoning`. The completeness signal feeds the
vision-fallback gate in UserInputResolver. Error policy: returns an empty
`_ExtractedOptions` (no options, completeness="unknown") on None/exception.
"""

import logging

import pytest

from src.core.agents.llm.dropdown import DropdownAgent, _ExtractedOptions
from tests.core.factories import (
    make_dropdown_case_vector_source_params,
    make_dropdown_email_source_params,
    make_fetched_context,
)


@pytest.mark.unit
async def test_run_unwraps_options_from_extracted(mock_agent_invoke):
    extracted = _ExtractedOptions(
        completeness="full",
        completeness_reasoning="All 3 motion types appeared as full-text chunks.",
        options=[
            "Motion to Modify Plan",
            "Motion to Extend Stay",
            "Motion to Waive Wage Deduction",
        ],
    )
    captured = mock_agent_invoke(extracted)

    result = await DropdownAgent.run(
        variable_name="motion_type",
        params=make_dropdown_case_vector_source_params(
            text_query="motion type",
            label="Motion Type",
            example_format="Motion to Modify Plan",
        ),
        fetched=make_fetched_context(raw_result={"case": "data"}),
    )

    assert result.options == [
        "Motion to Modify Plan",
        "Motion to Extend Stay",
        "Motion to Waive Wage Deduction",
    ]
    assert result.completeness == "full"
    assert "All 3 motion types" in result.completeness_reasoning
    assert captured["run_name"] == "DropdownExtractor"
    assert captured["metadata"] == {"variable": "motion_type"}


@pytest.mark.unit
async def test_run_returns_empty_extraction_when_invoke_returns_none(mock_agent_invoke):
    mock_agent_invoke(None)

    result = await DropdownAgent.run(
        variable_name="x",
        params=make_dropdown_email_source_params(label="L", example_format="F"),
        fetched=make_fetched_context(raw_result={"data": 1}),
    )

    # On None: return the default _ExtractedOptions (empty + unknown).
    # "unknown" is the right default for the vision-fallback gate — when the
    # LLM call failed, we can't claim "full" coverage.
    assert result.options == []
    assert result.completeness == "unknown"


@pytest.mark.unit
async def test_run_returns_empty_extraction_when_invoke_raises(mock_agent_invoke):
    """Exception must not bubble — orchestrator relies on gather() succeeding
    even when a single dropdown extraction fails."""
    mock_agent_invoke(RuntimeError("LLM failed"))

    result = await DropdownAgent.run(
        variable_name="x",
        params=make_dropdown_email_source_params(label="L", example_format="F"),
        fetched=make_fetched_context(raw_result={"data": 1}),
    )

    assert result.options == []
    assert result.completeness == "unknown"


@pytest.mark.unit
async def test_run_injects_label_example_format_and_source_into_prompt(mock_agent_invoke):
    captured = mock_agent_invoke(_ExtractedOptions())
    params = make_dropdown_case_vector_source_params(
        text_query="motion type",
        label="Motion Type",
        example_format="Motion to Modify Plan",
    )

    await DropdownAgent.run(
        variable_name="motion_type",
        params=params,
        fetched=make_fetched_context(raw_result="raw docs"),
    )

    prompt = captured["prompt"]
    assert "motion_type" in prompt
    assert "Motion Type" in prompt
    assert "Motion to Modify Plan" in prompt
    assert "raw docs" in prompt


@pytest.mark.unit
async def test_run_prompt_includes_completeness_report_block(mock_agent_invoke):
    """The COMPLETENESS REPORT block must render in every dropdown
    extraction so the LLM knows to fill `completeness` + reasoning.
    The vision-fallback gate in UserInputResolver depends on this signal."""
    captured = mock_agent_invoke(_ExtractedOptions())

    await DropdownAgent.run(
        variable_name="motion_type",
        params=make_dropdown_case_vector_source_params(
            text_query="motion type",
            label="Motion Type",
            example_format="Motion to Modify Plan",
        ),
        fetched=make_fetched_context(raw_result="raw"),
    )

    prompt = captured["prompt"]
    assert "COMPLETENESS REPORT" in prompt
    # The three valid completeness values are spelled out in the prompt.
    assert '"full"' in prompt
    assert '"partial"' in prompt
    assert '"unknown"' in prompt
    # Schedule C cross-reference is the canonical "smoking gun" example.
    assert "Schedule C" in prompt


@pytest.mark.unit
async def test_run_partial_completeness_round_trips(mock_agent_invoke):
    """An LLM that self-reports `completeness='partial'` must surface
    that value to the caller — that's how UserInputResolver decides
    to fire the vision fallback."""
    extracted = _ExtractedOptions(
        completeness="partial",
        completeness_reasoning=(
            "Saw Schedule A/B header and totals page but no itemized rows; "
            "only vehicle reference came from a Schedule C exemption chunk."
        ),
        options=[
            '2186 Appleton Cir N ("Property")',
            '2018 Mercedes G-Wagon ("Vehicle")',
        ],
    )
    mock_agent_invoke(extracted)

    result = await DropdownAgent.run(
        variable_name="property_and_vehicle_description",
        params=make_dropdown_case_vector_source_params(
            text_query="Schedule A/B real and personal property",
            label="Property and Vehicles",
            example_format='2018 Mercedes G-Wagon, VIN# X ("Vehicle")',
        ),
        fetched=make_fetched_context(raw_result={"chunks": "fragmentary"}),
    )

    assert result.completeness == "partial"
    assert "Schedule C exemption chunk" in result.completeness_reasoning
    assert len(result.options) == 2


@pytest.mark.unit
async def test_run_logs_completeness_at_info(mock_agent_invoke, caplog):
    """The completeness self-assessment is echoed at INFO so authors
    can grep app logs without diving into LangSmith."""
    mock_agent_invoke(
        _ExtractedOptions(
            completeness="partial",
            completeness_reasoning="Saw fragments only.",
            options=["a", "b"],
        )
    )

    with caplog.at_level(logging.INFO, logger="src.core.agents.llm.dropdown.agent"):
        await DropdownAgent.run(
            variable_name="motion_type",
            params=make_dropdown_email_source_params(label="L", example_format="F"),
            fetched=make_fetched_context(raw_result={"x": 1}),
        )

    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "DropdownAgent[motion_type]" in log_text
    assert "completeness=partial" in log_text
    assert "Saw fragments only." in log_text
    assert "options=2" in log_text


@pytest.mark.unit
async def test_run_returns_empty_options_when_no_matches(mock_agent_invoke):
    mock_agent_invoke(_ExtractedOptions(completeness="full"))

    result = await DropdownAgent.run(
        variable_name="x",
        params=make_dropdown_email_source_params(label="L", example_format="F"),
        fetched=make_fetched_context(raw_result={"no matches": True}),
    )

    assert result.options == []
    assert result.completeness == "full"
