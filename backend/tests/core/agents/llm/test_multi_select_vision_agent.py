"""Tests for MultiSelectVisionAgent — uses mock_agent_invoke style with
the multimodal variant.
"""

import pytest

from src.core.agents.llm.multi_select_vision import (
    MultiSelectVisionAgent,
    _ExtractedMultiSelectOptions,
)
from src.core.agents.llm.multi_select_vision.agent import _ExtractedOption
from src.core.agents.types.sources import MultiSelectFromCaseVectorSourceParams


def _opt(
    value: str,
    reasoning: str = "",
    supersedes: str | None = None,
) -> _ExtractedOption:
    return _ExtractedOption(value=value, reasoning=reasoning, supersedes=supersedes)


def _make_params(
    example_formats: list[str] | None = None,
) -> MultiSelectFromCaseVectorSourceParams:
    if example_formats is None:
        example_formats = ['2018 Mercedes G-Wagon, VIN# X ("Vehicle")']
    return MultiSelectFromCaseVectorSourceParams(
        label="Select Assets",
        instruction="Pick assets to mention.",
        text_query="Schedule A/B OR Schedule D",
        example_formats=example_formats,
        min_picks=1,
    )


@pytest.fixture
def mock_multimodal_invoke(monkeypatch):
    """Patch Agent._invoke_multimodal to return a caller-provided value and
    capture (content_blocks, run_name, metadata)."""
    from src.core.agents.llm import base as agent_base

    captured: dict = {}

    def make_patch(return_value):
        async def fake(cls, content_blocks, run_name, metadata=None):
            captured["content_blocks"] = content_blocks
            captured["run_name"] = run_name
            captured["metadata"] = metadata or {}
            if isinstance(return_value, Exception):
                raise return_value
            return return_value

        monkeypatch.setattr(agent_base.Agent, "_invoke_multimodal", classmethod(fake))
        return captured

    return make_patch


@pytest.mark.unit
async def test_run_returns_options_and_includes_pdf_block(mock_multimodal_invoke):
    params = _make_params()
    captured = mock_multimodal_invoke(
        _ExtractedMultiSelectOptions(
            options=[_opt("Honda"), _opt("Ford")],
        )
    )

    out = await MultiSelectVisionAgent.run(
        petition_pdf_b64="ZmFrZS1wZGY=",
        params=params,
        variable_name="selected_assets",
    )

    assert out.options == ["Honda", "Ford"]
    assert out.superseded_baseline == []
    assert captured["run_name"] == "MultiSelectVisionAgent"
    # PDF rides as the first content block
    assert captured["content_blocks"][0]["type"] == "document"
    assert captured["content_blocks"][0]["source"]["data"] == "ZmFrZS1wZGY="
    # Text prompt rides as the second block
    text_block = captured["content_blocks"][1]
    assert text_block["type"] == "text"
    # text_query renders as a <locator> block telling the LLM where to look
    assert "<locator>" in text_block["text"]
    assert "Schedule A/B OR Schedule D" in text_block["text"]
    # Format is enumerated in the prompt
    assert '2018 Mercedes G-Wagon, VIN# X ("Vehicle")' in text_block["text"]
    # Metadata carries variable + format count
    assert captured["metadata"]["variable"] == "selected_assets"
    assert captured["metadata"]["format_count"] == "1"


@pytest.mark.unit
async def test_run_renders_multiple_formats_as_bullet_list(mock_multimodal_invoke):
    params = _make_params(
        example_formats=[
            '2018 Mercedes G-Wagon, VIN# X ("Vehicle")',
            '1234 Main St ("Property")',
        ]
    )
    captured = mock_multimodal_invoke(_ExtractedMultiSelectOptions())

    await MultiSelectVisionAgent.run(petition_pdf_b64="x", params=params)

    text = captured["content_blocks"][1]["text"]
    # Bullet rendering when multiple formats
    assert "    - 2018 Mercedes G-Wagon" in text
    assert "    - 1234 Main St" in text
    assert captured["metadata"]["format_count"] == "2"


@pytest.mark.unit
async def test_run_returns_empty_on_invoke_exception(mock_multimodal_invoke):
    mock_multimodal_invoke(RuntimeError("boom"))
    out = await MultiSelectVisionAgent.run(
        petition_pdf_b64="x",
        params=_make_params(),
    )
    assert out.options == []
    assert out.superseded_baseline == []


@pytest.mark.unit
async def test_run_returns_empty_when_pdf_b64_empty():
    out = await MultiSelectVisionAgent.run(
        petition_pdf_b64="",
        params=_make_params(),
    )
    assert out.options == []
    assert out.superseded_baseline == []


@pytest.mark.unit
async def test_run_omits_locator_block_when_text_query_blank(mock_multimodal_invoke):
    """Defensive: the source's model_validator rejects blank text_query at
    construct time, but the prompt builder's `if params.text_query` guard
    is real code that should still be tested. Forge an instance via
    model_construct to bypass validation and exercise the empty branch."""
    params = MultiSelectFromCaseVectorSourceParams.model_construct(
        label="Select Assets",
        instruction="Pick assets to mention.",
        text_query="   ",
        example_formats=['2018 Mercedes G-Wagon, VIN# X ("Vehicle")'],
        min_picks=1,
        max_picks=None,
        list_joiner=", ",
        oxford=True,
    )
    captured = mock_multimodal_invoke(_ExtractedMultiSelectOptions())

    await MultiSelectVisionAgent.run(petition_pdf_b64="x", params=params)

    text = captured["content_blocks"][1]["text"]
    assert "<locator>" not in text


@pytest.mark.unit
async def test_run_includes_instruction_block_with_role_text(mock_multimodal_invoke):
    """When `instruction` is set, both the literal text AND the role
    description ('WHAT to pick') render in the prompt so the LLM
    distinguishes the instruction's purpose from the locator's."""
    params = _make_params()
    captured = mock_multimodal_invoke(_ExtractedMultiSelectOptions())

    await MultiSelectVisionAgent.run(petition_pdf_b64="x", params=params)

    text = captured["content_blocks"][1]["text"]
    assert "<instruction>" in text
    assert "Pick assets to mention." in text
    # Role-description framing — distinguishes instruction (WHAT) from locator (WHERE).
    assert "WHAT to pick" in text or "what to pick" in text.lower()


@pytest.mark.unit
async def test_run_includes_petition_section_guidance(mock_multimodal_invoke):
    """The GUIDANCE block lists the petition's standard section names so
    the LLM has a known schema to navigate against, regardless of how the
    author wrote the locator."""
    params = _make_params()
    captured = mock_multimodal_invoke(_ExtractedMultiSelectOptions())

    await MultiSelectVisionAgent.run(petition_pdf_b64="x", params=params)

    text = captured["content_blocks"][1]["text"]
    assert "Schedule A/B" in text
    assert "Schedule D" in text
    assert "Statement of Financial Affairs" in text


@pytest.mark.unit
async def test_run_prompt_pushes_for_exhaustive_extraction(mock_multimodal_invoke):
    """Real bug: petition lists 3 vehicles (3.1, 3.2, 3.3) but the LLM
    only returned 1. Prompt must call out sub-numbered rows and tell the
    LLM not to stop after the first match."""
    params = _make_params()
    captured = mock_multimodal_invoke(_ExtractedMultiSelectOptions())

    await MultiSelectVisionAgent.run(petition_pdf_b64="x", params=params)

    text = captured["content_blocks"][1]["text"]
    assert "EXHAUSTIVE EXTRACTION" in text
    assert "3.1" in text and "3.2" in text and "3.3" in text


@pytest.mark.unit
async def test_run_prompt_asks_for_per_option_reasoning(mock_multimodal_invoke):
    """The prompt must instruct the LLM to fill `reasoning` per option
    and `extraction_notes` overall, so authors can debug why specific
    rows were extracted, skipped, or missed."""
    params = _make_params()
    captured = mock_multimodal_invoke(_ExtractedMultiSelectOptions())

    await MultiSelectVisionAgent.run(petition_pdf_b64="x", params=params)

    text = captured["content_blocks"][1]["text"]
    assert "REASONING TRAIL" in text
    assert "reasoning" in text.lower()
    assert "extraction_notes" in text


@pytest.mark.unit
async def test_run_extracts_value_strings_from_structured_options(mock_multimodal_invoke):
    """The agent's structured output is now `_ExtractedOption(value, reasoning)`
    per item, but `run()` must still return `list[str]` to preserve the
    contract `UserInputResolver` depends on."""
    params = _make_params()
    captured = mock_multimodal_invoke(
        _ExtractedMultiSelectOptions(
            extraction_notes="Searched Schedule A/B; saw 3 vehicle rows in section 3.",
            options=[
                _opt(
                    '2022 Kia Stinger, VIN# KNAE55LC5N6117584 ("Vehicle")',
                    reasoning="Schedule A/B row 3.1; matched vehicle format.",
                ),
                _opt(
                    '2023 Kia Sportage, VIN# 5XYK443AF1PG052484 ("Vehicle")',
                    reasoning="Schedule A/B row 3.2; matched vehicle format.",
                ),
                _opt(
                    '2018 Mercedes G-Wagon, VIN# WDCYC3KH3JX288288 ("Vehicle")',
                    reasoning="Schedule A/B row 3.3; matched vehicle format.",
                ),
            ],
        )
    )

    out = await MultiSelectVisionAgent.run(
        petition_pdf_b64="x", params=params, variable_name="selected_assets",
    )

    # Caller gets values + (empty) supersedes — reasoning is in the LLM trace.
    assert out.options == [
        '2022 Kia Stinger, VIN# KNAE55LC5N6117584 ("Vehicle")',
        '2023 Kia Sportage, VIN# 5XYK443AF1PG052484 ("Vehicle")',
        '2018 Mercedes G-Wagon, VIN# WDCYC3KH3JX288288 ("Vehicle")',
    ]
    assert out.superseded_baseline == []


@pytest.mark.unit
async def test_run_logs_extraction_trail(mock_multimodal_invoke, caplog):
    """Per-option reasoning + overall extraction_notes are logged at INFO
    so they're inspectable in app logs without diving into LangSmith."""
    import logging

    params = _make_params()
    mock_multimodal_invoke(
        _ExtractedMultiSelectOptions(
            extraction_notes="Saw 3 vehicle rows; returned all 3.",
            options=[
                _opt("Honda Civic", reasoning="Schedule A/B row 3.1"),
                _opt("Ford F150", reasoning="Schedule A/B row 3.2"),
            ],
        )
    )

    with caplog.at_level(logging.INFO, logger="src.core.agents.llm.multi_select_vision.agent"):
        await MultiSelectVisionAgent.run(
            petition_pdf_b64="x", params=params, variable_name="selected_assets",
        )

    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "Saw 3 vehicle rows" in log_text
    assert "Honda Civic" in log_text
    assert "Schedule A/B row 3.1" in log_text
    assert "Ford F150" in log_text


@pytest.mark.unit
async def test_run_renders_baseline_options_block_in_prompt(mock_multimodal_invoke):
    """When baseline_options is provided, the vision prompt includes
    `<existing_options>` so the LLM can skip items already extracted by
    the DropdownAgent first pass — preventing shape-variant duplicates
    that exact-string dedup can't catch."""
    params = _make_params()
    captured = mock_multimodal_invoke(_ExtractedMultiSelectOptions())

    await MultiSelectVisionAgent.run(
        petition_pdf_b64="x",
        params=params,
        baseline_options=[
            "2018 Mercedes G-Wagon",
            "2186 Appleton Circle, North Oakland Park, FL 33309",
        ],
    )

    text = captured["content_blocks"][1]["text"]
    assert "<existing_options>" in text
    assert "- 2018 Mercedes G-Wagon" in text
    assert "- 2186 Appleton Circle, North Oakland Park, FL 33309" in text
    assert "EXISTING OPTIONS" in text
    # Both branches of the rule must appear in the prompt — SKIP when baseline
    # already matches the format, OR set `supersedes` when vision can produce
    # a richer-shaped version.
    assert "SKIP" in text
    assert "supersedes" in text
    assert "VIN" in text


@pytest.mark.unit
@pytest.mark.parametrize("baseline", [None, []])
async def test_run_omits_baseline_block_when_baseline_empty(mock_multimodal_invoke, baseline):
    """No baseline → no <existing_options> block. The vision pass behaves
    exactly as it did before this change when DropdownAgent returned 0
    options (regression guard)."""
    params = _make_params()
    captured = mock_multimodal_invoke(_ExtractedMultiSelectOptions())

    await MultiSelectVisionAgent.run(
        petition_pdf_b64="x",
        params=params,
        baseline_options=baseline,
    )

    text = captured["content_blocks"][1]["text"]
    assert "<existing_options>" not in text
    assert "EXISTING OPTIONS" not in text


@pytest.mark.unit
async def test_run_collects_supersedes_into_result(mock_multimodal_invoke):
    """When the LLM marks options as superseding baseline strings, the run
    surface aggregates them into `superseded_baseline` so the resolver can
    drop the matching baseline entries. Mixed payload: some new items, some
    supersede entries, some no supersedes."""
    params = _make_params()
    mock_multimodal_invoke(
        _ExtractedMultiSelectOptions(
            extraction_notes="3 vehicles found; 1 better-shaped than baseline.",
            options=[
                _opt(
                    '2022 Kia Stinger - VIN KNAE55LC5N6117584',
                    reasoning="Schedule A/B row 3.1; new vehicle.",
                ),
                _opt(
                    '2018 Mercedes G-Wagon - VIN WDCYC3KH3JX288288',
                    reasoning="Schedule A/B row 3.3; richer shape than baseline.",
                    supersedes='2018 Mercedes G-Wagon',
                ),
            ],
        )
    )

    out = await MultiSelectVisionAgent.run(
        petition_pdf_b64="x",
        params=params,
        variable_name="selected_assets",
        baseline_options=["2018 Mercedes G-Wagon"],
    )

    assert out.options == [
        '2022 Kia Stinger - VIN KNAE55LC5N6117584',
        '2018 Mercedes G-Wagon - VIN WDCYC3KH3JX288288',
    ]
    assert out.superseded_baseline == ['2018 Mercedes G-Wagon']


@pytest.mark.unit
async def test_run_drops_blank_supersedes_strings(mock_multimodal_invoke):
    """LLM occasionally emits whitespace-only `supersedes` for new items.
    The resolver-facing list must filter those out so we don't try to drop
    nonexistent baseline entries."""
    params = _make_params()
    mock_multimodal_invoke(
        _ExtractedMultiSelectOptions(
            options=[
                _opt('A', supersedes=None),
                _opt('B', supersedes=""),
                _opt('C', supersedes="   "),
                _opt('D', supersedes="real-baseline-string"),
            ],
        )
    )

    out = await MultiSelectVisionAgent.run(petition_pdf_b64="x", params=params)

    assert out.options == ['A', 'B', 'C', 'D']
    assert out.superseded_baseline == ['real-baseline-string']


@pytest.mark.unit
async def test_run_logs_zero_options_message_when_empty(mock_multimodal_invoke, caplog):
    """When the LLM returns 0 options, log an explicit message at INFO
    (and the extraction_notes) so the author sees WHY it came up empty."""
    import logging

    params = _make_params()
    mock_multimodal_invoke(
        _ExtractedMultiSelectOptions(
            extraction_notes="Searched Schedule A/B but found no rows matching the vehicle format.",
            options=[],
        )
    )

    with caplog.at_level(logging.INFO, logger="src.core.agents.llm.multi_select_vision.agent"):
        await MultiSelectVisionAgent.run(
            petition_pdf_b64="x", params=params, variable_name="selected_assets",
        )

    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "returned 0 options" in log_text
    assert "no rows matching the vehicle format" in log_text
