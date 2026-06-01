"""Tests for GroupDropdownAgent — extracts left/right dropdown pairs.

Unique shape: uses `_ExtractedPairs` as the structured-output wrapper
but returns just `.options` to callers. Error policy: returns `[]` (not
raises, not None).
"""

import pytest

from src.core.agents.llm.group_dropdown import (
    DropdownOption,
    GroupDropdownAgent,
    _ExtractedPairs,
)
from tests.core.factories import make_fetched_context, make_group_dropdown_composite


@pytest.mark.unit
async def test_run_unwraps_options_from_extracted_pairs(mock_agent_invoke):
    pairs = _ExtractedPairs(
        options=[
            DropdownOption(left="26-10700", right="Smith"),
            DropdownOption(left="26-10701", right="Jones"),
        ]
    )
    captured = mock_agent_invoke(pairs)

    params = make_group_dropdown_composite()
    fetched = make_fetched_context(raw_result={"sample": "data"})

    result = await GroupDropdownAgent.run(
        composite_name="docket_num__docket_title",
        params=params,
        fetched=fetched,
    )

    assert len(result) == 2
    assert all(isinstance(opt, DropdownOption) for opt in result)
    assert result[0].left == "26-10700" and result[0].right == "Smith"
    assert captured["run_name"] == "GroupDropdownExtractor"
    assert captured["metadata"] == {"composite": "docket_num__docket_title"}


@pytest.mark.unit
async def test_run_returns_empty_list_when_invoke_returns_none(mock_agent_invoke):
    mock_agent_invoke(None)

    result = await GroupDropdownAgent.run(
        composite_name="c",
        params=make_group_dropdown_composite(),
        fetched=make_fetched_context(raw_result={"x": 1}),
    )

    assert result == []


@pytest.mark.unit
async def test_run_returns_empty_list_when_invoke_raises(mock_agent_invoke):
    """Exception must not bubble — orchestrator relies on gather() succeeding
    even if a single composite's extraction fails."""
    mock_agent_invoke(RuntimeError("LLM failed"))

    result = await GroupDropdownAgent.run(
        composite_name="c",
        params=make_group_dropdown_composite(),
        fetched=make_fetched_context(raw_result={"x": 1}),
    )

    assert result == []


@pytest.mark.unit
async def test_run_injects_labels_into_prompt(mock_agent_invoke):
    captured = mock_agent_invoke(_ExtractedPairs(options=[]))
    params = make_group_dropdown_composite(
        left_label="Docket Number",
        left_variable="docket_num",
        right_label="Docket Title",
        right_variable="docket_title",
    )

    await GroupDropdownAgent.run("c", params, make_fetched_context(raw_result="data"))

    prompt = captured["prompt"]
    assert "Docket Number" in prompt
    assert "Docket Title" in prompt
    assert "'docket_num'" in prompt
    assert "'docket_title'" in prompt


@pytest.mark.unit
async def test_run_returns_empty_list_when_no_options_found(mock_agent_invoke):
    mock_agent_invoke(_ExtractedPairs(options=[]))

    result = await GroupDropdownAgent.run(
        composite_name="c",
        params=make_group_dropdown_composite(),
        fetched=make_fetched_context(raw_result={"no matches": True}),
    )

    assert result == []
