"""Tests for WebSearchEnhanceAgent — ChatAnthropic + web_search tool round-trip."""

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from src.core.agents.llm.web_search_enhance import agent as agent_module
from src.core.agents.llm.web_search_enhance import WebSearchEnhanceAgent


def _text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def _tool_use_block() -> dict:
    return {
        "type": "server_tool_use",
        "id": "srvtoolu_x",
        "name": "web_search",
        "input": {"query": "Broward County Florida judicial circuit"},
    }


def _tool_result_block() -> dict:
    return {
        "type": "web_search_tool_result",
        "tool_use_id": "srvtoolu_x",
        "content": [{"type": "web_search_result", "url": "https://example.gov", "title": "..."}],
    }


def _ai_message(*blocks_or_str) -> AIMessage:
    """Build an AIMessage whose content matches ChatAnthropic's bind_tools output.

    Pass a single string for the simple no-tool-use case, or pass content blocks
    (text / server_tool_use / web_search_tool_result dicts) for the multimodal
    interleaved shape.
    """
    if len(blocks_or_str) == 1 and isinstance(blocks_or_str[0], str):
        return AIMessage(content=blocks_or_str[0])
    return AIMessage(content=list(blocks_or_str))


def _patch_chat(monkeypatch, response_or_exc):
    """Replace ChatAnthropic on the agent module so the bind_tools().with_config()
    .ainvoke() chain returns / raises the given value. Returns the AsyncMock used
    for ainvoke so tests can assert on call args (the prompt)."""
    ainvoke = AsyncMock()
    if isinstance(response_or_exc, Exception):
        ainvoke.side_effect = response_or_exc
    else:
        ainvoke.return_value = response_or_exc

    captured: dict = {}

    class _FakeChain:
        async def ainvoke(self, prompt):
            captured["prompt"] = prompt
            return await ainvoke(prompt)

    class _FakeBound:
        def with_config(self, config):
            captured["config"] = config
            return _FakeChain()

    class _FakeChat:
        def __init__(self, **kwargs):
            captured["init_kwargs"] = kwargs

        def bind_tools(self, tools):
            captured["tools"] = tools
            return _FakeBound()

    monkeypatch.setattr(agent_module, "ChatAnthropic", _FakeChat)
    return captured, ainvoke


@pytest.mark.unit
async def test_run_parses_answer_tag_from_final_text(monkeypatch):
    captured, ainvoke = _patch_chat(monkeypatch, _ai_message(
        _text_block("Let me search for the circuit number for Broward County."),
        _tool_use_block(),
        _tool_result_block(),
        _text_block(
            "Based on Florida court records, Broward County is in the 17th circuit.\n"
            "<answer>17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA</answer>"
        ),
    ))

    out = await WebSearchEnhanceAgent.run(
        variable_name="court_circuit_and_county",
        current_value="Broward County Circuit Court",
        template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
        template_paragraph="IN THE CIRCUIT COURT OF THE [[court_circuit_and_county]]",
        case_details={"case_number": "26-10491", "chapter": 13},
    )

    assert out == "17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"
    ainvoke.assert_awaited_once()

    # Tool config: native server-side web_search tool, max_uses cap.
    assert captured["tools"] == [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
    }]
    # LangSmith span tags + run_name match the agent identity.
    assert captured["config"]["run_name"] == "WebSearchEnhanceAgent"
    assert "web_search_enhance" in captured["config"]["tags"]
    assert captured["config"]["metadata"]["variable_name"] == "court_circuit_and_county"

    # Prompt threads through every input the resolver hands us.
    prompt = captured["prompt"]
    assert "court_circuit_and_county" in prompt
    assert "Broward County Circuit Court" in prompt
    assert "11 JUDICIAL CIRCUIT" in prompt
    assert "[[court_circuit_and_county]]" in prompt
    assert "26-10491" in prompt


@pytest.mark.unit
async def test_run_uses_last_answer_tag_when_multiple_present(monkeypatch):
    """If the model writes <answer> twice (e.g. an example then the final),
    the agent should pick the LAST one."""
    _patch_chat(monkeypatch, _ai_message(_text_block(
        "Example shape: <answer>NN JUDICIAL CIRCUIT IN AND FOR XYZ COUNTY, FLORIDA</answer>\n"
        "Final: <answer>17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA</answer>"
    )))

    out = await WebSearchEnhanceAgent.run(
        variable_name="court_circuit_and_county",
        current_value="Broward County Circuit Court",
        template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
        template_paragraph=None,
        case_details=None,
    )

    assert out == "17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"


@pytest.mark.unit
async def test_run_handles_plain_string_content(monkeypatch):
    """When ChatAnthropic returns a plain string (no tool use happened), the
    agent should still find the <answer> tag inside that string."""
    _patch_chat(monkeypatch, _ai_message(
        "Already knew this without searching.\n"
        "<answer>17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA</answer>"
    ))

    out = await WebSearchEnhanceAgent.run(
        variable_name="court_circuit_and_county",
        current_value="Broward County Circuit Court",
        template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
        template_paragraph=None,
        case_details=None,
    )

    assert out == "17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"


@pytest.mark.unit
async def test_run_falls_back_to_current_value_when_no_answer_tag(monkeypatch, caplog):
    _patch_chat(monkeypatch, _ai_message(_text_block(
        "I couldn't find a reliable circuit number for this county."
    )))

    with caplog.at_level("WARNING"):
        out = await WebSearchEnhanceAgent.run(
            variable_name="court_circuit_and_county",
            current_value="Broward County Circuit Court",
            template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
            template_paragraph=None,
            case_details=None,
        )

    assert out == "Broward County Circuit Court"
    assert any("no <answer> tag" in rec.message for rec in caplog.records)


@pytest.mark.unit
async def test_run_falls_back_when_chain_raises(monkeypatch, caplog):
    _patch_chat(monkeypatch, RuntimeError("anthropic 500"))

    with caplog.at_level("WARNING"):
        out = await WebSearchEnhanceAgent.run(
            variable_name="court_circuit_and_county",
            current_value="Broward County Circuit Court",
            template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
            template_paragraph=None,
            case_details=None,
        )

    assert out == "Broward County Circuit Court"
    assert any("LLM call failed" in rec.message for rec in caplog.records)


@pytest.mark.unit
async def test_run_falls_back_when_response_has_no_text_blocks(monkeypatch, caplog):
    """Tool-use-only responses (no text blocks) should fall back to the original
    current_value rather than crash on empty parsing."""
    _patch_chat(monkeypatch, _ai_message(_tool_use_block(), _tool_result_block()))

    with caplog.at_level("WARNING"):
        out = await WebSearchEnhanceAgent.run(
            variable_name="court_circuit_and_county",
            current_value="Broward County Circuit Court",
            template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
            template_paragraph=None,
            case_details=None,
        )

    assert out == "Broward County Circuit Court"
    assert any("no text content" in rec.message for rec in caplog.records)


@pytest.mark.unit
async def test_run_concatenates_text_across_multiple_blocks(monkeypatch):
    """If the model emits multiple text blocks (interleaved with tool_use),
    the agent should still find an <answer> tag regardless of which block
    it lives in."""
    _patch_chat(monkeypatch, _ai_message(
        _text_block("First chunk of reasoning."),
        _tool_use_block(),
        _tool_result_block(),
        _text_block("Second chunk."),
        _text_block("<answer>17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA</answer>"),
    ))

    out = await WebSearchEnhanceAgent.run(
        variable_name="court_circuit_and_county",
        current_value="Broward County Circuit Court",
        template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
        template_paragraph=None,
        case_details=None,
    )
    assert out == "17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"


@pytest.mark.unit
async def test_run_falls_back_when_answer_tag_is_empty(monkeypatch, caplog):
    """An empty `<answer></answer>` tag is treated as 'no answer' and the
    agent falls back to the original current_value rather than blanking
    the field."""
    _patch_chat(monkeypatch, _ai_message(_text_block(
        "I couldn't find a reliable result.\n<answer></answer>"
    )))

    with caplog.at_level("WARNING"):
        out = await WebSearchEnhanceAgent.run(
            variable_name="court_circuit_and_county",
            current_value="Broward County Circuit Court",
            template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
            template_paragraph=None,
            case_details=None,
        )

    assert out == "Broward County Circuit Court"
    assert any("no <answer> tag" in rec.message for rec in caplog.records)


# ─── Author-instruction blocks (role-scoped) ──────────────────────────


@pytest.mark.unit
async def test_run_renders_web_search_instruction_block_when_provided(monkeypatch):
    """`web_search_instruction` is surfaced as an authoritative WEB SEARCH
    INSTRUCTION block in the prompt (overrides marker shape per rule 6)."""
    captured, _ = _patch_chat(monkeypatch, _ai_message(_text_block(
        "<answer>17TH JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA</answer>"
    )))

    await WebSearchEnhanceAgent.run(
        variable_name="court_circuit_and_county",
        current_value="Broward County Circuit Court",
        template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
        template_paragraph=None,
        case_details=None,
        web_search_instruction="search for Florida judicial circuit by county; ignore federal court info",
    )

    prompt = captured["prompt"]
    assert "WEB SEARCH INSTRUCTION" in prompt
    assert "search for Florida judicial circuit by county" in prompt
    # OUTPUT INSTRUCTION block heading should NOT appear on its own when
    # only web_search_instruction is provided.
    assert "OUTPUT INSTRUCTION —" not in prompt


@pytest.mark.unit
async def test_run_renders_output_instruction_block_when_provided(monkeypatch):
    """`output_instruction` is surfaced as an authoritative OUTPUT
    INSTRUCTION block (final-shape directive)."""
    captured, _ = _patch_chat(monkeypatch, _ai_message(_text_block(
        "<answer>11TH JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA</answer>"
    )))

    await WebSearchEnhanceAgent.run(
        variable_name="court_circuit_and_county",
        current_value="Miami-Dade County Circuit Court",
        template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
        template_paragraph=None,
        case_details=None,
        output_instruction="use ordinal form (11TH, 9TH)",
    )

    prompt = captured["prompt"]
    assert "OUTPUT INSTRUCTION" in prompt
    assert "use ordinal form" in prompt
    assert "WEB SEARCH INSTRUCTION —" not in prompt


@pytest.mark.unit
async def test_run_renders_both_instruction_blocks_when_both_provided(monkeypatch):
    """Both blocks coexist in the same prompt with distinct headings."""
    captured, _ = _patch_chat(monkeypatch, _ai_message(_text_block(
        "<answer>17TH JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA</answer>"
    )))

    await WebSearchEnhanceAgent.run(
        variable_name="court_circuit_and_county",
        current_value="Broward County Circuit Court",
        template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
        template_paragraph=None,
        case_details=None,
        web_search_instruction="search for circuit by county",
        output_instruction="use ordinal form",
    )

    prompt = captured["prompt"]
    assert "WEB SEARCH INSTRUCTION" in prompt
    assert "search for circuit by county" in prompt
    assert "OUTPUT INSTRUCTION" in prompt
    assert "use ordinal form" in prompt


@pytest.mark.unit
@pytest.mark.parametrize("web_search_instruction, output_instruction", [
    (None, None),
    ("", ""),
    ("   \n  ", "\t  "),
])
async def test_run_omits_blocks_when_blank(monkeypatch, web_search_instruction, output_instruction):
    """Blank / whitespace-only directives render no block. The em-dashed
    block headings (`WEB SEARCH INSTRUCTION —`, `OUTPUT INSTRUCTION —`)
    are distinct from the in-rule references in the GUIDANCE list, so
    asserting on the em-dash form is precise."""
    captured, _ = _patch_chat(monkeypatch, _ai_message(_text_block(
        "<answer>same as current_value</answer>"
    )))

    await WebSearchEnhanceAgent.run(
        variable_name="court_circuit_and_county",
        current_value="Broward County Circuit Court",
        template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
        template_paragraph=None,
        case_details=None,
        web_search_instruction=web_search_instruction,
        output_instruction=output_instruction,
    )

    prompt = captured["prompt"]
    assert "WEB SEARCH INSTRUCTION —" not in prompt
    assert "OUTPUT INSTRUCTION —" not in prompt


@pytest.mark.unit
async def test_run_includes_authoritative_guidance_rule_unconditionally(monkeypatch):
    """The 'AUTHOR INSTRUCTIONS ARE AUTHORITATIVE' guidance rule lives in
    the base prompt regardless of whether either block was rendered, so
    the LLM always knows to prefer author hints over marker-shape inference
    when present."""
    captured, _ = _patch_chat(monkeypatch, _ai_message(_text_block(
        "<answer>x</answer>"
    )))

    await WebSearchEnhanceAgent.run(
        variable_name="x",
        current_value="y",
        template_property_marker="z",
        template_paragraph=None,
        case_details=None,
    )

    assert "AUTHOR INSTRUCTIONS ARE AUTHORITATIVE" in captured["prompt"]
