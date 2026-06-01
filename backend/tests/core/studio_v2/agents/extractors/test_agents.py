"""End-to-end tests for the 4 extractor agents.

We bypass real LLM + tools by patching `ExtractorAgentV2._run_loop`
to return fabricated `ExtractorRunResult`s. This isolates each agent's
public `run(...)` API: input shaping, output shaping, failure
degradation.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.agents.extractors.base import ExtractorRunResult
from src.core.studio_v2.agents.extractors.draft import DraftAgentV2, _SubmitValue
from src.core.studio_v2.agents.extractors.dropdown import (
    DropdownAgentV2,
    _ExtractedOption,
    _SubmitOptions,
)
from src.core.studio_v2.agents.extractors.multi_select import MultiSelectAgentV2
from src.core.studio_v2.agents.extractors.reco_chips import (
    RecoChipsAgentV2,
    _SubmitChips,
    _SuggestionChip,
)
from src.core.studio_v2.types.fields import TemplateFieldV2
from src.core.studio_v2.types.wizard_sources import (
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


_FIELD_UUID = "00000000-0000-0000-0000-000000000001"
_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000002"


def _field(
    name: str,
    *,
    shape: PresentationShape,
    source: SourceKind = SourceKind.GMAIL,
    extraction_prompt: str = "extract X",
    label: str | None = None,
) -> TemplateFieldV2:
    return TemplateFieldV2(
        id=_FIELD_UUID,
        template_id=_TEMPLATE_UUID,
        template_variable=name,
        template_index=0,
        params=WizardSourceParams(
            source=source,
            presentation_shape=shape,
            extraction_prompt=extraction_prompt,
            label=label,
        ),
    )


# ─── DraftAgentV2 ────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_draft_agent_returns_resolved_value():
    field = _field("debtor_income", shape=PresentationShape.RAW)
    fake_output = _SubmitValue(
        value="$4,250.00",
        raw_context="Paystub dated 2026-04-15 — gross wages $4,250.00 ...",
        confidence="high",
        note="Extracted from the most recent paystub.",
    )
    with patch.object(
        DraftAgentV2, "_run_loop",
        new=AsyncMock(return_value=ExtractorRunResult(
            output=fake_output, tool_call_count=2, iterations=3,
        )),
    ):
        rv = await DraftAgentV2.run(field=field, tools=[])
    assert rv.value == "$4,250.00"
    assert "Paystub dated 2026-04-15" in rv.raw_context
    assert rv.confidence == "high"
    assert rv.template_variable == "debtor_income"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_draft_agent_no_output_degrades_to_low_confidence():
    field = _field("x", shape=PresentationShape.RAW)
    with patch.object(
        DraftAgentV2, "_run_loop",
        new=AsyncMock(return_value=ExtractorRunResult(
            output=None, tool_call_count=8, iterations=8,
        )),
    ):
        rv = await DraftAgentV2.run(field=field, tools=[])
    assert rv.value == ""
    assert rv.confidence == "none"
    assert "loop exhausted" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_draft_agent_no_params_degrades_without_running_loop():
    field = TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable="x", params=None,
    )
    with patch.object(DraftAgentV2, "_run_loop", new=AsyncMock()) as loop_mock:
        rv = await DraftAgentV2.run(field=field, tools=[])
    loop_mock.assert_not_called()
    assert rv.confidence == "none"


# ─── DropdownAgentV2 ─────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dropdown_agent_returns_pending_envelope_with_raw_contexts():
    field = _field(
        "creditor_pick", shape=PresentationShape.DROPDOWN, label="Pick the creditor",
    )
    fake_output = _SubmitOptions(
        completeness="full",
        completeness_reasoning="All 3 creditor emails accounted for.",
        options=[
            _ExtractedOption(display="Acme Bank", raw_context="Email body 1..."),
            _ExtractedOption(display="Wells Fargo", raw_context="Email body 2..."),
        ],
    )
    with patch.object(
        DropdownAgentV2, "_run_loop",
        new=AsyncMock(return_value=ExtractorRunResult(
            output=fake_output, tool_call_count=1, iterations=2,
        )),
    ):
        env = await DropdownAgentV2.run(field=field, tools=[])
    assert env.kind == "dropdown"
    assert env.label == "Pick the creditor"
    assert env.options == ["Acme Bank", "Wells Fargo"]
    # Per-option raw_contexts must be preserved — that's the load-bearing
    # invariant for derived children downstream.
    assert env.raw_contexts == ["Email body 1...", "Email body 2..."]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dropdown_agent_no_output_returns_empty_envelope():
    field = _field("x", shape=PresentationShape.DROPDOWN)
    with patch.object(
        DropdownAgentV2, "_run_loop",
        new=AsyncMock(return_value=ExtractorRunResult(
            output=None, tool_call_count=0, iterations=1,
        )),
    ):
        env = await DropdownAgentV2.run(field=field, tools=[])
    assert env.kind == "dropdown"
    assert env.options == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dropdown_agent_derives_label_from_variable_when_no_label():
    field = _field(
        "creditor_pick", shape=PresentationShape.DROPDOWN, label=None,
    )
    with patch.object(
        DropdownAgentV2, "_run_loop",
        new=AsyncMock(return_value=ExtractorRunResult(
            output=_SubmitOptions(options=[]), tool_call_count=0, iterations=1,
        )),
    ):
        env = await DropdownAgentV2.run(field=field, tools=[])
    # Fallback humanizes the snake_case variable name.
    assert "creditor pick" in env.label.lower()


# ─── RecoChipsAgentV2 ────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reco_chips_agent_returns_pending_envelope():
    field = _field("objection_basis", shape=PresentationShape.CHIP)
    fake_output = _SubmitChips(
        chips=[
            _SuggestionChip(text="Lack of documentation", raw_context="...claim 142..."),
            _SuggestionChip(text="Untimely filing", raw_context="...filed 2026-05-01..."),
        ],
        note="Two strong objections found.",
    )
    with patch.object(
        RecoChipsAgentV2, "_run_loop",
        new=AsyncMock(return_value=ExtractorRunResult(
            output=fake_output, tool_call_count=1, iterations=2,
        )),
    ):
        env = await RecoChipsAgentV2.run(field=field, tools=[])
    assert env.kind == "chip"
    assert env.chips == ["Lack of documentation", "Untimely filing"]
    assert env.raw_contexts == ["...claim 142...", "...filed 2026-05-01..."]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reco_chips_agent_no_output_returns_empty_envelope():
    field = _field("x", shape=PresentationShape.CHIP)
    with patch.object(
        RecoChipsAgentV2, "_run_loop",
        new=AsyncMock(return_value=ExtractorRunResult(
            output=None, tool_call_count=0, iterations=1,
        )),
    ):
        env = await RecoChipsAgentV2.run(field=field, tools=[])
    assert env.kind == "chip"
    assert env.chips == []


# ─── MultiSelectAgentV2 ──────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multi_select_agent_carries_pick_bounds_from_params():
    field = TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable="creditors",
        params=WizardSourceParams(
            source=SourceKind.CASE_FILE,
            presentation_shape=PresentationShape.MULTI_SELECT,
            extraction_prompt="all creditors with claims > $1000",
            min_picks=2,
            max_picks=10,
        ),
    )
    fake_output = _SubmitOptions(
        completeness="full",
        options=[
            _ExtractedOption(display="A", raw_context="chunk a"),
            _ExtractedOption(display="B", raw_context="chunk b"),
            _ExtractedOption(display="C", raw_context="chunk c"),
        ],
    )
    with patch.object(
        MultiSelectAgentV2, "_run_loop",
        new=AsyncMock(return_value=ExtractorRunResult(
            output=fake_output, tool_call_count=1, iterations=2,
        )),
    ):
        env = await MultiSelectAgentV2.run(field=field, tools=[])
    assert env.kind == "multi_select"
    assert env.min_picks == 2
    assert env.max_picks == 10
    assert env.options == ["A", "B", "C"]
    assert env.raw_contexts == ["chunk a", "chunk b", "chunk c"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multi_select_agent_no_output_preserves_pick_bounds():
    """Even on failure, the envelope keeps the author-configured
    min_picks / max_picks so the FE renders the right constraint hint."""
    field = TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable="x",
        params=WizardSourceParams(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.MULTI_SELECT,
            min_picks=3,
            max_picks=7,
            extraction_prompt="x",
        ),
    )
    with patch.object(
        MultiSelectAgentV2, "_run_loop",
        new=AsyncMock(return_value=ExtractorRunResult(
            output=None, tool_call_count=0, iterations=1,
        )),
    ):
        env = await MultiSelectAgentV2.run(field=field, tools=[])
    assert env.options == []
    assert env.min_picks == 3
    assert env.max_picks == 7
