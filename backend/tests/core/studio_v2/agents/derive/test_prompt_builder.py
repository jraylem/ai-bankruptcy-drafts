"""Tests for the DeriveAgent prompt builder — covers the key
load-bearing prompt content (strict-binding language, output
expectation block, paralegal-speak translation guidance)."""

import pytest

from src.core.studio_v2.agents.derive.prompt_builder import build_derive_prompt


@pytest.mark.unit
def test_prompt_contains_strict_binding_language():
    prompt = build_derive_prompt(
        child_variable="vin",
        parent_variable="vehicle_record",
        parent_value="2018 Toyota Camry VIN: 1HG... mileage 82,300",
        extraction_prompt="Extract the VIN — 11–17 alphanumeric characters.",
    )
    # The author's instruction MUST be marked binding (parallel to
    # decision #12's regeneration_instruction tightening).
    assert "BINDING" in prompt
    assert "highest priority" in prompt.lower()


@pytest.mark.unit
def test_prompt_includes_child_and_parent_vars():
    prompt = build_derive_prompt(
        child_variable="claim_amount",
        parent_variable="proof_of_claim_row",
        parent_value="4 - Bank of America - $3,000",
        extraction_prompt="Extract the dollar amount.",
    )
    assert "`claim_amount`" in prompt
    assert "`proof_of_claim_row`" in prompt


@pytest.mark.unit
def test_prompt_includes_author_instruction_verbatim():
    instruction = "Return 'are' if the parent lists multiple items joined by 'and', else 'is'."
    prompt = build_derive_prompt(
        child_variable="is_or_are",
        parent_variable="creditors_list",
        parent_value="Bank A and Bank B",
        extraction_prompt=instruction,
    )
    assert instruction in prompt


@pytest.mark.unit
def test_prompt_includes_parent_value_verbatim():
    parent_chunk = "Full email body containing creditor names and addresses."
    prompt = build_derive_prompt(
        child_variable="x",
        parent_variable="y",
        parent_value=parent_chunk,
        extraction_prompt="extract X",
    )
    assert parent_chunk in prompt


@pytest.mark.unit
def test_prompt_omits_output_expectation_block_when_none():
    prompt = build_derive_prompt(
        child_variable="x",
        parent_variable="y",
        parent_value="some value",
        extraction_prompt="extract X",
        output_expectation=None,
    )
    assert "<output_expectation>" not in prompt


@pytest.mark.unit
def test_prompt_includes_output_expectation_block_when_provided():
    prompt = build_derive_prompt(
        child_variable="x",
        parent_variable="y",
        parent_value="some value",
        extraction_prompt="extract X",
        output_expectation="Format as a single uppercase word.",
    )
    assert "<output_expectation>" in prompt
    assert "Format as a single uppercase word." in prompt


@pytest.mark.unit
def test_prompt_includes_paralegal_speak_clause():
    """The agent must accept plain English from authors, not jargon —
    the prompt explicitly tells the LLM to translate freely."""
    prompt = build_derive_prompt(
        child_variable="x",
        parent_variable="y",
        parent_value="v",
        extraction_prompt="get the docket no.",
    )
    assert "Plain paralegal English" in prompt or "paralegal English" in prompt.lower()


@pytest.mark.unit
def test_prompt_includes_no_invention_guard():
    """If the instruction asks for something not in the parent value,
    the agent must return an empty string — not hallucinate."""
    prompt = build_derive_prompt(
        child_variable="x",
        parent_variable="y",
        parent_value="v",
        extraction_prompt="extract X",
    )
    assert "Do NOT invent content" in prompt or "do not invent" in prompt.lower()
