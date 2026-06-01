"""Tests for ExplanationEnhanceAgentV2's prompt builder."""

import pytest

from src.core.common.documents.supporting_doc_reader import InlineTextDoc
from src.core.studio_v2.agents.explanation_enhance.prompt_builder import (
    build_explanation_enhance_prompt,
)


@pytest.mark.unit
def test_prompt_includes_label_and_user_text():
    prompt = build_explanation_enhance_prompt(
        label="Hardship narrative",
        user_text="I was laid off in March and have been struggling.",
        inline_docs=[],
    )
    assert "Hardship narrative" in prompt
    assert "I was laid off in March" in prompt


@pytest.mark.unit
def test_prompt_omits_rendered_supporting_docs_when_empty():
    """The instruction text references `<supporting_text_docs>` for
    the LLM's benefit; what we're checking is that no RENDERED
    `<doc filename="...">` block appears when no inline docs were
    supplied."""
    prompt = build_explanation_enhance_prompt(
        label="x", user_text="y", inline_docs=[],
    )
    assert '<doc filename="' not in prompt


@pytest.mark.unit
def test_prompt_includes_inline_text_docs_when_provided():
    docs = [
        InlineTextDoc(filename="termination_letter.txt", text="Effective March 8, 2026, your position is eliminated."),
        InlineTextDoc(filename="paystub.txt", text="Gross wages: $4,250.00"),
    ]
    prompt = build_explanation_enhance_prompt(
        label="x", user_text="lost wages", inline_docs=docs,
    )
    assert "<supporting_text_docs>" in prompt
    assert 'filename="termination_letter.txt"' in prompt
    assert "Effective March 8, 2026" in prompt
    assert 'filename="paystub.txt"' in prompt
    assert "$4,250.00" in prompt


@pytest.mark.unit
def test_prompt_enforces_third_person_and_no_emotion_clauses():
    """Rule 4's load-bearing constraints — third-person register,
    no first/second person, no emotional language."""
    prompt = build_explanation_enhance_prompt(
        label="x", user_text="y", inline_docs=[],
    )
    assert "Third person only" in prompt
    assert "No emotional appeals" in prompt
    assert "the Debtor" in prompt


@pytest.mark.unit
def test_prompt_forbids_fabrication():
    """Rule 3 — never invent facts absent from BOTH user text + docs."""
    prompt = build_explanation_enhance_prompt(
        label="x", user_text="y", inline_docs=[],
    )
    assert "DO NOT FABRICATE" in prompt


@pytest.mark.unit
def test_prompt_demands_single_paragraph_no_commentary():
    prompt = build_explanation_enhance_prompt(
        label="x", user_text="y", inline_docs=[],
    )
    assert "PRODUCE ONE PARAGRAPH" in prompt
    assert "Return ONLY" in prompt
