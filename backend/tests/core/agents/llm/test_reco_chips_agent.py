"""Tests for RecoChipsAgent — generates up to 3 chip candidates from email context.

Generative (not extractive), so the prompt shape differs from
GroupDropdownAgent: label + variable_name are injected, plus an optional
TEMPLATE SENTENCE EXAMPLE block when example_sentence is set. Error policy:
returns `[]` (not raises, not None).
"""

import pytest

from src.core.agents.llm.reco_chips import RecoChipsAgent, _ExtractedChips
from tests.core.factories import make_fetched_context, make_reco_chips_source_params


@pytest.mark.unit
async def test_run_unwraps_chips_from_extracted_chips(mock_agent_invoke):
    chips = _ExtractedChips(
        chips=[
            "Lost job at ABC Corp on Feb 3rd",
            "Medical emergency — hospitalized March 2026",
            "Divorce finalized April 2026",
        ]
    )
    captured = mock_agent_invoke(chips)

    result = await RecoChipsAgent.run(
        variable_name="change_in_circumstances",
        params=make_reco_chips_source_params(label="Change in Circumstances"),
        fetched=make_fetched_context(raw_result={"emails": "data"}),
    )

    assert result == [
        "Lost job at ABC Corp on Feb 3rd",
        "Medical emergency — hospitalized March 2026",
        "Divorce finalized April 2026",
    ]
    assert captured["run_name"] == "RecoChipsGenerator"
    assert captured["metadata"] == {"variable": "change_in_circumstances"}


@pytest.mark.unit
async def test_run_returns_empty_list_when_invoke_returns_none(mock_agent_invoke):
    mock_agent_invoke(None)

    result = await RecoChipsAgent.run(
        variable_name="x",
        params=make_reco_chips_source_params(),
        fetched=make_fetched_context(raw_result={"data": 1}),
    )

    assert result == []


@pytest.mark.unit
async def test_run_returns_empty_list_when_invoke_raises(mock_agent_invoke):
    """Exception must not bubble — orchestrator relies on gather() succeeding
    even if one field's generation fails."""
    mock_agent_invoke(RuntimeError("LLM failed"))

    result = await RecoChipsAgent.run(
        variable_name="x",
        params=make_reco_chips_source_params(),
        fetched=make_fetched_context(raw_result={"data": 1}),
    )

    assert result == []


@pytest.mark.unit
async def test_run_injects_label_and_variable_name_into_prompt(mock_agent_invoke):
    captured = mock_agent_invoke(_ExtractedChips(chips=[]))
    params = make_reco_chips_source_params(label="Change in Circumstances")

    await RecoChipsAgent.run(
        variable_name="change_in_circumstances",
        params=params,
        fetched=make_fetched_context(raw_result="email body"),
    )

    prompt = captured["prompt"]
    assert "change_in_circumstances" in prompt
    assert "Change in Circumstances" in prompt
    assert "email body" in prompt


@pytest.mark.unit
async def test_run_includes_template_sentence_example_block_when_example_set(mock_agent_invoke):
    captured = mock_agent_invoke(_ExtractedChips(chips=[]))
    params = make_reco_chips_source_params(
        label="Change in Circumstances",
        example_sentence="The Debtor has experienced a material change in circumstances since filing.",
    )

    await RecoChipsAgent.run(
        variable_name="x",
        params=params,
        fetched=make_fetched_context(raw_result="data"),
    )

    prompt = captured["prompt"]
    assert "TEMPLATE SENTENCE EXAMPLE" in prompt
    assert "The Debtor has experienced a material change in circumstances since filing." in prompt


@pytest.mark.unit
async def test_run_omits_template_sentence_example_block_when_none(mock_agent_invoke):
    """No empty 'TEMPLATE SENTENCE EXAMPLE' heading when example_sentence is None."""
    captured = mock_agent_invoke(_ExtractedChips(chips=[]))
    params = make_reco_chips_source_params(example_sentence=None)

    await RecoChipsAgent.run(
        variable_name="x",
        params=params,
        fetched=make_fetched_context(raw_result="data"),
    )

    # "AUTHORITATIVE for the chips" is a phrase that only appears inside the
    # example-sentence block, not in the guidance rule that merely references it.
    assert "AUTHORITATIVE for the chips" not in captured["prompt"]


@pytest.mark.unit
async def test_run_omits_template_sentence_example_block_when_whitespace(mock_agent_invoke):
    captured = mock_agent_invoke(_ExtractedChips(chips=[]))
    params = make_reco_chips_source_params(example_sentence="   \n  ")

    await RecoChipsAgent.run(
        variable_name="x",
        params=params,
        fetched=make_fetched_context(raw_result="data"),
    )

    # "AUTHORITATIVE for the chips" is a phrase that only appears inside the
    # example-sentence block, not in the guidance rule that merely references it.
    assert "AUTHORITATIVE for the chips" not in captured["prompt"]


@pytest.mark.unit
async def test_run_returns_empty_list_when_no_chips_generated(mock_agent_invoke):
    mock_agent_invoke(_ExtractedChips(chips=[]))

    result = await RecoChipsAgent.run(
        variable_name="x",
        params=make_reco_chips_source_params(),
        fetched=make_fetched_context(raw_result={"no matches": True}),
    )

    assert result == []


# ─── instruction (TemplateField.instruction → chip prompt) ────────────


@pytest.mark.unit
async def test_run_includes_author_instruction_block_when_fetched_instruction_set(mock_agent_invoke):
    """`FetchedContext.instruction` is propagated from TemplateField.instruction
    at fetch time. The chip generator surfaces it as an authoritative
    AUTHOR INSTRUCTION block so authors can steer chip-set composition
    (category spread, must-include topics, framing rules)."""
    captured = mock_agent_invoke(_ExtractedChips(chips=[]))

    await RecoChipsAgent.run(
        variable_name="change_in_circumstances",
        params=make_reco_chips_source_params(label="Change in Circumstances"),
        fetched=make_fetched_context(
            raw_result="email body",
            instruction=(
                "Produce 3 candidates from DISTINCT categories — one employment-related, "
                "one medical, one household/financial — when the source supports it."
            ),
        ),
    )

    prompt = captured["prompt"]
    assert "AUTHOR INSTRUCTION" in prompt
    assert "DISTINCT categories" in prompt
    assert "employment-related" in prompt


@pytest.mark.unit
@pytest.mark.parametrize("instruction", [None, "", "   \n   \t  "])
async def test_run_omits_author_instruction_block_when_blank(mock_agent_invoke, instruction):
    """No AUTHOR INSTRUCTION block when instruction is None or whitespace-only."""
    captured = mock_agent_invoke(_ExtractedChips(chips=[]))

    await RecoChipsAgent.run(
        variable_name="x",
        params=make_reco_chips_source_params(),
        fetched=make_fetched_context(raw_result="data", instruction=instruction),
    )

    # The block heading uses an em-dash, distinct from the inline rule
    # mention of "AUTHOR INSTRUCTION" in GUIDANCE.
    assert "AUTHOR INSTRUCTION —" not in captured["prompt"]
