"""Tests for DraftAgent — uses the mock_agent_invoke fixture from conftest
to avoid any real Anthropic API calls.
"""

import pytest

from src.core.agents.llm.draft import DraftAgent, DraftAgentOutput
from src.core.agents.types.sources import GmailSourceParams
from tests.core.factories import (
    make_agent_config,
    make_resolved_value,
    make_template_field,
)


@pytest.mark.unit
async def test_run_calls_invoke_with_expected_run_name_and_metadata(mock_agent_invoke):
    captured = mock_agent_invoke(DraftAgentOutput(resolved_values=[]))
    config = make_agent_config(
        template_id="tpl_abc",
        fields=[make_template_field(source_params=GmailSourceParams())],
    )

    await DraftAgent.run(config, context=[], case_details=None)

    assert captured["run_name"] == "DraftAgent"
    assert captured["metadata"] == {"template_id": "tpl_abc"}


@pytest.mark.unit
async def test_run_prompt_includes_expected_blocks(mock_agent_invoke):
    captured = mock_agent_invoke(DraftAgentOutput(resolved_values=[]))
    config = make_agent_config(
        template_id="tpl_abc",
        fields=[make_template_field(source_params=GmailSourceParams())],
    )

    await DraftAgent.run(
        config,
        context=[],
        case_details={"chapter": 13, "case_number": "26-10700"},
    )

    prompt = captured["prompt"]
    assert "<fields_to_resolve>" in prompt
    assert "<case_details>" in prompt
    assert "TEMPLATE: tpl_abc" in prompt
    # case_details get rendered into the prompt
    assert "chapter: 13" in prompt
    assert "case_number: 26-10700" in prompt


@pytest.mark.unit
async def test_run_escapes_newlines_in_case_details_values(mock_agent_invoke):
    """A joint-filing `case_name` carries a real `\\n`; the serializer must
    escape it to the two-character sequence `\\n` so each case_details entry
    stays on one prompt line. Otherwise the LLM misreads the suffix as a
    separate un-keyed line."""
    captured = mock_agent_invoke(DraftAgentOutput(resolved_values=[]))
    config = make_agent_config(
        template_id="tpl_joint",
        fields=[make_template_field(source_params=GmailSourceParams())],
    )

    await DraftAgent.run(
        config,
        context=[],
        case_details={"case_name": "Lori Creswell\nRobert Creswell"},
    )

    prompt = captured["prompt"]
    # Joint-ness is signalled by the escaped two-character `\n` sequence on
    # ONE line, not by a real newline splitting the value onto a second line.
    assert "  case_name: Lori Creswell\\nRobert Creswell" in prompt
    # Ensure no real newline landed inside the rendered value — that's the bug.
    assert "  case_name: Lori Creswell\n" not in prompt


@pytest.mark.unit
async def test_run_returns_output_as_is_when_invoke_returns_value(mock_agent_invoke):
    expected = DraftAgentOutput(
        resolved_values=[make_resolved_value("debtor_name", "John Smith")]
    )
    mock_agent_invoke(expected)

    result = await DraftAgent.run(make_agent_config(), context=[], case_details=None)

    assert result == expected


@pytest.mark.unit
async def test_run_returns_empty_output_when_invoke_returns_none(mock_agent_invoke):
    # LangChain can return None when structured output fails; agent must
    # coerce that into an empty DraftAgentOutput, not propagate None.
    mock_agent_invoke(None)

    result = await DraftAgent.run(make_agent_config(), context=[], case_details=None)

    assert result == DraftAgentOutput(resolved_values=[])


@pytest.mark.unit
async def test_run_returns_empty_output_when_invoke_raises(mock_agent_invoke):
    # Exceptions inside the LLM call should not bubble up — draft agent
    # degrades to empty output with a logged error.
    mock_agent_invoke(RuntimeError("boom"))

    result = await DraftAgent.run(make_agent_config(), context=[], case_details=None)

    assert result == DraftAgentOutput(resolved_values=[])


@pytest.mark.unit
def test_prompt_rule_7_forbids_marker_as_fallback_value():
    # Locks the protective wording for rule 7. Removing this guard let the
    # LLM rationalize template_property_marker as a fallback value source
    # in production (debtor_address case, May 2026).
    from src.core.agents.llm.draft.prompt_builder import DRAFT_AGENT_PROMPT
    assert "NEVER use the marker's content as a fallback value" in DRAFT_AGENT_PROMPT


# ─── output_instruction wiring ─────────────────────────────────────────


@pytest.mark.unit
def test_field_block_includes_output_instruction_when_set():
    """When a field carries an output_instruction, _build_field_block must
    render it as an <output_instruction> sibling of <instruction> so the
    DraftAgent can apply the author's output-shape directive (rule 11)."""
    from src.core.agents.llm.draft.prompt_builder import _build_field_block
    from src.core.agents.types.spec import TemplateField
    from src.core.agents.types.sources import FieldSource, GmailSourceParams

    field = TemplateField(
        property_name="recent_correspondence",
        source=FieldSource.GMAIL,
        source_params=GmailSourceParams(),
        instruction="Look up recent correspondence from opposing counsel",
        output_instruction="If multiple emails match, list each on a new line in the format <subject> — <date>",
    )

    block = _build_field_block(field, fetched=None)

    assert "<output_instruction>If multiple emails match, list each on a new line in the format <subject> — <date></output_instruction>" in block


@pytest.mark.unit
@pytest.mark.parametrize("blank_value", [None, "", "   ", "\n\t"])
def test_field_block_omits_output_instruction_when_blank(blank_value):
    """Fields without an output_instruction must NOT render the block at
    all — keeps prompts for the overwhelming majority of fields byte-
    identical to pre-wiring behavior."""
    from src.core.agents.llm.draft.prompt_builder import _build_field_block
    from src.core.agents.types.spec import TemplateField
    from src.core.agents.types.sources import FieldSource, GmailSourceParams

    field = TemplateField(
        property_name="recent_correspondence",
        source=FieldSource.GMAIL,
        source_params=GmailSourceParams(),
        output_instruction=blank_value,
    )

    block = _build_field_block(field, fetched=None)

    assert "<output_instruction>" not in block


@pytest.mark.unit
def test_draft_prompt_contains_rule_11_about_output_instruction_authority():
    """Lock the rule-11 wording so future prompt edits don't accidentally
    remove the AUTHORITATIVE designation that licenses authors to direct
    multi-value formatting via output_instruction."""
    from src.core.agents.llm.draft.prompt_builder import DRAFT_AGENT_PROMPT
    assert "`<output_instruction>` is AUTHORITATIVE for output shape" in DRAFT_AGENT_PROMPT
    assert "multi-value formatting" in DRAFT_AGENT_PROMPT
