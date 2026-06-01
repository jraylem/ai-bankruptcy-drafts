"""Tests for the shared extractor prompt builders — covers the
load-bearing prompt content (strict-binding language, dependency
block, example_format, paralegal-speak translation, per-shape
extraction guidance)."""

import pytest

from src.core.studio_v2.agents.extractors.prompts import (
    build_system_prompt,
    build_user_prompt,
)
from src.core.studio_v2.types.wizard_sources import (
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


# ─── system prompt ───────────────────────────────────────────────────


@pytest.mark.unit
def test_system_prompt_interpolates_submit_tool_name():
    prompt = build_system_prompt(submit_tool_name="_SubmitValue")
    assert "_SubmitValue" in prompt


@pytest.mark.unit
def test_system_prompt_marks_extraction_prompt_binding():
    prompt = build_system_prompt(submit_tool_name="_SubmitValue")
    assert "BINDING" in prompt
    assert "highest priority" in prompt.lower()


@pytest.mark.unit
def test_system_prompt_warns_against_invention():
    prompt = build_system_prompt(submit_tool_name="_SubmitValue")
    assert "do NOT invent" in prompt or "do not invent" in prompt.lower()


@pytest.mark.unit
def test_system_prompt_lists_three_tools():
    prompt = build_system_prompt(submit_tool_name="_SubmitValue")
    assert "gmail_search" in prompt
    assert "case_vector_query" in prompt
    assert "vision_fallback" in prompt


@pytest.mark.unit
def test_system_prompt_warns_about_vision_cost():
    prompt = build_system_prompt(submit_tool_name="_SubmitValue")
    assert "do not use as the first lookup" in prompt.lower()


# ─── user prompt — common ────────────────────────────────────────────


@pytest.mark.unit
def test_user_prompt_renders_source_kind_with_layman_label():
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.RAW,
        extraction_prompt="extract X",
    )
    prompt = build_user_prompt(
        template_variable="x", params=params, submit_tool_name="_SubmitValue",
    )
    assert "Email Inbox" in prompt  # layman label, not raw enum


@pytest.mark.unit
def test_user_prompt_renders_case_file_with_layman_label():
    params = WizardSourceParams(
        source=SourceKind.CASE_FILE,
        presentation_shape=PresentationShape.RAW,
        extraction_prompt="extract X",
    )
    prompt = build_user_prompt(
        template_variable="x", params=params, submit_tool_name="_SubmitValue",
    )
    assert "Case Documents" in prompt


@pytest.mark.unit
def test_user_prompt_includes_template_variable_name():
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.RAW,
        extraction_prompt="x",
    )
    prompt = build_user_prompt(
        template_variable="meeting_date",
        params=params,
        submit_tool_name="_SubmitValue",
    )
    assert "meeting_date" in prompt


@pytest.mark.unit
def test_user_prompt_includes_author_extraction_prompt_verbatim():
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.RAW,
        extraction_prompt="the most recent paystub's gross income",
    )
    prompt = build_user_prompt(
        template_variable="income",
        params=params,
        submit_tool_name="_SubmitValue",
    )
    assert "the most recent paystub's gross income" in prompt


# ─── dependency block ────────────────────────────────────────────────


@pytest.mark.unit
def test_dependency_block_omitted_when_no_dependencies():
    params = WizardSourceParams(
        source=SourceKind.GMAIL, extraction_prompt="x",
    )
    prompt = build_user_prompt(
        template_variable="x", params=params, submit_tool_name="_SubmitValue",
    )
    assert "<dependency_values>" not in prompt


@pytest.mark.unit
def test_dependency_block_included_with_values():
    params = WizardSourceParams(
        source=SourceKind.GMAIL, extraction_prompt="x",
    )
    prompt = build_user_prompt(
        template_variable="x", params=params, submit_tool_name="_SubmitValue",
        dependency_values={
            "case_number": "26-12345-ABC",
            "meeting_date": "April 30, 2026",
        },
    )
    assert "<dependency_values>" in prompt
    assert 'case_number = "26-12345-ABC"' in prompt
    assert 'meeting_date = "April 30, 2026"' in prompt


# ─── example_format + output_expectation ─────────────────────────────


@pytest.mark.unit
def test_example_format_included_when_provided():
    params = WizardSourceParams(
        source=SourceKind.GMAIL, extraction_prompt="x",
        example_format="Acme Bank — $1,200",
    )
    prompt = build_user_prompt(
        template_variable="x", params=params, submit_tool_name="_SubmitValue",
    )
    assert "Acme Bank — $1,200" in prompt
    assert "concrete sample" in prompt


@pytest.mark.unit
def test_output_expectation_included_when_provided():
    params = WizardSourceParams(
        source=SourceKind.GMAIL, extraction_prompt="x",
        output_expectation="Format as a complete sentence.",
    )
    prompt = build_user_prompt(
        template_variable="x", params=params, submit_tool_name="_SubmitValue",
    )
    assert "Format as a complete sentence." in prompt


# ─── per-shape extraction guidance ───────────────────────────────────


@pytest.mark.unit
def test_dropdown_shape_block_present_for_dropdown():
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.DROPDOWN,
        extraction_prompt="x",
    )
    prompt = build_user_prompt(
        template_variable="x", params=params, submit_tool_name="_SubmitOptions",
    )
    assert "<dropdown_extraction>" in prompt
    assert "raw_context" in prompt


@pytest.mark.unit
def test_chip_shape_block_present_for_chip():
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.CHIP,
        extraction_prompt="x",
    )
    prompt = build_user_prompt(
        template_variable="x", params=params, submit_tool_name="_SubmitChips",
    )
    assert "<chip_extraction>" in prompt
    assert "1-3 SUGGESTION chips" in prompt


@pytest.mark.unit
def test_multi_select_shape_block_present_for_multi_select():
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.MULTI_SELECT,
        extraction_prompt="x",
    )
    prompt = build_user_prompt(
        template_variable="x", params=params, submit_tool_name="_SubmitOptions",
    )
    assert "<multi_select_extraction>" in prompt
    assert "K-of-N" in prompt


@pytest.mark.unit
def test_raw_shape_omits_shape_block():
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.RAW,
        extraction_prompt="x",
    )
    prompt = build_user_prompt(
        template_variable="x", params=params, submit_tool_name="_SubmitValue",
    )
    assert "<dropdown_extraction>" not in prompt
    assert "<chip_extraction>" not in prompt
    assert "<multi_select_extraction>" not in prompt
