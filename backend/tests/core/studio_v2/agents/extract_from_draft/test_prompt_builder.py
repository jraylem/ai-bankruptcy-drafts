"""Tests for the ExtractFromDraftAgentV2 prompt builder."""

import pytest

from src.core.studio_v2.agents.extract_from_draft.prompt_builder import (
    build_extract_from_draft_prompt,
)


@pytest.mark.unit
def test_prompt_includes_draft_text_and_instruction():
    prompt = build_extract_from_draft_prompt(
        draft_text="UNITED STATES BANKRUPTCY COURT\nIn re: Jane Doe...",
        extract_instruction="Pull the debtor's full name from the In re caption.",
    )
    assert "UNITED STATES BANKRUPTCY COURT" in prompt
    assert "In re: Jane Doe" in prompt
    assert "debtor's full name" in prompt


@pytest.mark.unit
def test_prompt_marks_draft_as_authoritative():
    prompt = build_extract_from_draft_prompt(
        draft_text="x", extract_instruction="y",
    )
    assert "FILED VERSION" in prompt
    assert "authoritative source" in prompt.lower()
    # The "Do NOT invent or paraphrase" clause may wrap across lines —
    # check both pieces rather than the full unbroken string.
    assert "invent" in prompt.lower()
    assert "paraphrase" in prompt.lower()


@pytest.mark.unit
def test_prompt_omits_shape_block_when_no_marker():
    prompt = build_extract_from_draft_prompt(
        draft_text="x", extract_instruction="y",
    )
    assert "<shape_reference>" not in prompt


@pytest.mark.unit
def test_prompt_includes_shape_block_when_marker_provided():
    prompt = build_extract_from_draft_prompt(
        draft_text="x", extract_instruction="y",
        template_property_marker="Jane Doe, Debtor.",
    )
    assert "<shape_reference>" in prompt
    assert "Jane Doe, Debtor." in prompt
    assert "NEVER copy this content verbatim" in prompt


@pytest.mark.unit
def test_prompt_instructs_empty_on_missing_value():
    prompt = build_extract_from_draft_prompt(
        draft_text="x", extract_instruction="y",
    )
    assert "empty string" in prompt
