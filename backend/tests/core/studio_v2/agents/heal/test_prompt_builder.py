"""Tests for the UserInputHealAgentV2 prompt builder."""

import pytest

from src.core.studio_v2.agents.heal.prompt_builder import (
    build_user_input_heal_prompt,
)


@pytest.mark.unit
def test_prompt_includes_template_paragraph_and_placeholder():
    prompt = build_user_input_heal_prompt(
        template_paragraph="The Debtor, [[debtor_name]], moves to extend.",
        placeholder="[[debtor_name]]",
        user_value="jane doe",
        heal_target=None,
        heal_target_kind=None,
    )
    assert "The Debtor, [[debtor_name]], moves to extend." in prompt
    assert "[[debtor_name]]" in prompt
    assert "jane doe" in prompt


@pytest.mark.unit
def test_no_heal_target_omits_both_blocks():
    prompt = build_user_input_heal_prompt(
        template_paragraph="x [[ph]] y",
        placeholder="[[ph]]",
        user_value="value",
        heal_target=None,
        heal_target_kind=None,
    )
    assert "GUIDE" not in prompt
    assert "PREFERRED PRESENTATION" not in prompt


@pytest.mark.unit
def test_example_sentence_kind_renders_guide_block():
    prompt = build_user_input_heal_prompt(
        template_paragraph="x [[ph]] y",
        placeholder="[[ph]]",
        user_value="value",
        heal_target="A formal sentence describing the issue.",
        heal_target_kind="example_sentence",
    )
    assert "GUIDE" in prompt
    assert "A formal sentence describing the issue." in prompt


@pytest.mark.unit
def test_preferred_format_kind_renders_preferred_block():
    prompt = build_user_input_heal_prompt(
        template_paragraph="x [[ph]] y",
        placeholder="[[ph]]",
        user_value="value",
        heal_target="2018 Toyota Camry (\"Vehicle\")",
        heal_target_kind="preferred_format",
    )
    assert "PREFERRED PRESENTATION" in prompt
    assert "2018 Toyota Camry" in prompt
    assert "SAMPLE FROM A DIFFERENT CASE" in prompt


@pytest.mark.unit
def test_author_instruction_block_renders_when_provided():
    prompt = build_user_input_heal_prompt(
        template_paragraph="x [[ph]] y",
        placeholder="[[ph]]",
        user_value="value",
        heal_target=None,
        heal_target_kind=None,
        author_instruction="Output only the predicate; the template already supplies the subject.",
    )
    assert "AUTHOR INSTRUCTION" in prompt
    assert "Output only the predicate" in prompt


@pytest.mark.unit
def test_date_lockdown_clause_present():
    """Rule 5 tells the LLM NOT to touch date strings — important
    because date healing runs first."""
    prompt = build_user_input_heal_prompt(
        template_paragraph="x [[ph]] y",
        placeholder="[[ph]]",
        user_value="value",
        heal_target=None,
        heal_target_kind=None,
    )
    assert "date strings" in prompt.lower()
    assert "date-healing" in prompt.lower() or "date heal" in prompt.lower()


@pytest.mark.unit
def test_strict_fact_preservation_present():
    """Rule 1 forbids inventing facts."""
    prompt = build_user_input_heal_prompt(
        template_paragraph="x [[ph]] y",
        placeholder="[[ph]]",
        user_value="value",
        heal_target=None,
        heal_target_kind=None,
    )
    assert "PRESERVE EVERY FACT" in prompt
    assert "Do NOT add, remove, or alter facts" in prompt
