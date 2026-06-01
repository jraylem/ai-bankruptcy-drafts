"""Tests for WizardResolver.dispatch — the (source × shape) routing
table. Slice A handles: current_date, constants, attorney raw,
value_from_parent_bundle, derived_from_variable. All other paths
return a placeholder with `confidence='none'` and a `[Phase 2 NYI]`
note prefix so the orchestrator can finish the run with those fields
marked unresolved.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.orchestration.dispatcher import WizardResolver
from src.core.studio_v2.types.bundling import (
    LiteralSlotConfig,
    ParentVariableSlotConfig,
)
from src.core.studio_v2.types.fields import TemplateFieldV2
from src.core.studio_v2.types.orchestration import ParentBundleContextV2
from src.core.studio_v2.types.resolution import ResolvedTemplateValueV2
from src.core.studio_v2.types.wizard_sources import (
    AuthorInputKind,
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000001"


def _field(name: str, params: WizardSourceParams | None) -> TemplateFieldV2:
    return TemplateFieldV2(
        id="00000000-0000-0000-0000-000000000002",
        template_id=_TEMPLATE_UUID,
        template_variable=name,
        template_index=0,
        template_property_marker=None,
        template_identifying_text_match=None,
        description=None,
        params=params,
    )


# ─── slice A handlers ────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_current_date():
    field = _field("doc_date", WizardSourceParams(source=SourceKind.CURRENT_DATE))
    # Patch the resolver's now() injection by calling dispatch directly —
    # the dispatch passes through to resolve_current_date with its own now=None.
    rv = await WizardResolver.dispatch(field=field)
    assert rv.template_variable == "doc_date"
    assert rv.confidence == "high"
    assert rv.value  # an ISO date string was emitted


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_constants():
    field = _field(
        "firm_phone",
        WizardSourceParams(source=SourceKind.CONSTANTS, constants_short_code="PHONE"),
    )
    fake_row = type("R", (), {"value": "(561) 123-4567"})()
    with patch(
        "src.core.studio_v2.resolvers.constants.ReferenceDataRepository.get",
        new=AsyncMock(return_value=fake_row),
    ):
        rv = await WizardResolver.dispatch(field=field)
    assert rv.value == "(561) 123-4567"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_attorney_raw():
    field = _field(
        "attorney_name",
        WizardSourceParams(
            source=SourceKind.ATTORNEY,
            presentation_shape=PresentationShape.RAW,
            attorney_id="att-1",
        ),
    )
    fake_attorney = type("A", (), {"id": "att-1", "full_name": "Chad Van Horn"})()
    with patch(
        "src.core.studio_v2.resolvers.attorney.AttorneyRosterRepository.get",
        new=AsyncMock(return_value=fake_attorney),
    ):
        rv = await WizardResolver.dispatch(field=field)
    assert rv.value == "Chad Van Horn"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_value_from_parent_bundle():
    field = _field(
        "case_number",
        WizardSourceParams(source=SourceKind.VALUE_FROM_PARENT_BUNDLE),
    )
    parent_ctx = ParentBundleContextV2(
        resolved_values={"case_number": "26-12345-ABC"},
        slot_configurations={
            "case_number": ParentVariableSlotConfig(parent_variable="case_number"),
        },
    )
    rv = await WizardResolver.dispatch(field=field, parent_context=parent_ctx)
    assert rv.value == "26-12345-ABC"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_derived_calls_derive_agent():
    """DeriveAgent invocation is the most complex path in slice A —
    confirm dispatch routes correctly and feeds raw_context through."""
    field = _field(
        "is_or_are",
        WizardSourceParams(
            source=SourceKind.DERIVED_FROM_VARIABLE,
            dependent_variable="creditors_list",
            extraction_prompt="Return 'are' if multiple, else 'is'.",
        ),
    )
    by_name = {
        "creditors_list": ResolvedTemplateValueV2(
            template_variable="creditors_list",
            value="Bank of America and Wells Fargo",
            raw_context="Full email chunk listing creditors...",
        ),
    }
    with patch(
        "src.core.studio_v2.orchestration.dispatcher.DeriveAgent.run",
        new=AsyncMock(return_value=ResolvedTemplateValueV2(
            template_variable="is_or_are", value="are", confidence="high",
        )),
    ) as derive_mock:
        rv = await WizardResolver.dispatch(field=field, by_name=by_name)
    assert rv.value == "are"
    # Confirm raw_context was preferred over value.
    call = derive_mock.call_args
    assert call.kwargs["parent_raw_context"] == "Full email chunk listing creditors..."
    assert call.kwargs["parent_value"] == "Bank of America and Wells Fargo"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_derived_missing_parent_in_by_name():
    field = _field(
        "child", WizardSourceParams(
            source=SourceKind.DERIVED_FROM_VARIABLE,
            dependent_variable="missing_parent",
            extraction_prompt="extract X",
        ),
    )
    rv = await WizardResolver.dispatch(field=field, by_name={})
    assert rv.confidence == "none"
    assert "not been resolved" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_field_without_params():
    field = _field("unconfigured", None)
    rv = await WizardResolver.dispatch(field=field)
    assert rv.confidence == "none"
    assert "no params" in rv.note


# ─── slice B: gmail / case_file extractor routing ────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_gmail_raw_routes_to_draft_agent():
    field = _field(
        "income",
        WizardSourceParams(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.RAW,
            extraction_prompt="x",
        ),
    )
    expected = ResolvedTemplateValueV2(
        template_variable="income", value="$4,250", confidence="high",
    )
    with patch(
        "src.core.studio_v2.orchestration.dispatcher.DraftAgentV2.run",
        new=AsyncMock(return_value=expected),
    ) as agent_mock:
        rv = await WizardResolver.dispatch(field=field, toolset=[])
    agent_mock.assert_awaited_once()
    assert rv is expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_case_file_dropdown_routes_to_dropdown_agent():
    from src.core.studio_v2.types.pending import PendingDropdownV2

    field = _field(
        "creditor",
        WizardSourceParams(
            source=SourceKind.CASE_FILE,
            presentation_shape=PresentationShape.DROPDOWN,
            extraction_prompt="all creditors",
        ),
    )
    expected = PendingDropdownV2(label="Pick", options=["a"], raw_contexts=["x"])
    with patch(
        "src.core.studio_v2.orchestration.dispatcher.DropdownAgentV2.run",
        new=AsyncMock(return_value=expected),
    ) as agent_mock:
        env = await WizardResolver.dispatch(field=field, toolset=[])
    agent_mock.assert_awaited_once()
    assert env is expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_gmail_chip_routes_to_reco_chips_agent():
    from src.core.studio_v2.types.pending import PendingChipV2

    field = _field(
        "basis",
        WizardSourceParams(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.CHIP,
            extraction_prompt="basis",
        ),
    )
    expected = PendingChipV2(label="Pick", chips=["a"], raw_contexts=["x"])
    with patch(
        "src.core.studio_v2.orchestration.dispatcher.RecoChipsAgentV2.run",
        new=AsyncMock(return_value=expected),
    ) as agent_mock:
        env = await WizardResolver.dispatch(field=field, toolset=[])
    agent_mock.assert_awaited_once()
    assert env is expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_case_file_multi_select_routes_to_multi_select_agent():
    from src.core.studio_v2.types.pending import PendingMultiSelectV2

    field = _field(
        "creditors",
        WizardSourceParams(
            source=SourceKind.CASE_FILE,
            presentation_shape=PresentationShape.MULTI_SELECT,
            extraction_prompt="all creditors",
            min_picks=1, max_picks=5,
        ),
    )
    expected = PendingMultiSelectV2(
        label="Pick", options=["a", "b"], raw_contexts=["x", "y"],
        min_picks=1, max_picks=5,
    )
    with patch(
        "src.core.studio_v2.orchestration.dispatcher.MultiSelectAgentV2.run",
        new=AsyncMock(return_value=expected),
    ) as agent_mock:
        env = await WizardResolver.dispatch(field=field, toolset=[])
    agent_mock.assert_awaited_once()
    assert env is expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_extractor_without_toolset_returns_placeholder():
    """Without a toolset (orchestrator didn't pass one), extractor paths
    degrade gracefully — no crash, just a 'requires toolset' note."""
    field = _field(
        "x",
        WizardSourceParams(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.RAW,
            extraction_prompt="x",
        ),
    )
    rv = await WizardResolver.dispatch(field=field, toolset=None)
    assert rv.confidence == "none"
    assert "requires a" in rv.note
    assert "toolset" in rv.note


# ─── user-input envelope emitters (attorney pick + author_input) ─────


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "shape,expected_multi_select",
    [
        (PresentationShape.DROPDOWN, False),
        (PresentationShape.MULTI_SELECT, True),
    ],
)
async def test_dispatch_attorney_pick_emits_envelope(shape, expected_multi_select):
    field = _field(
        "attorney",
        WizardSourceParams(
            source=SourceKind.ATTORNEY,
            presentation_shape=shape,
            min_picks=1, max_picks=3,
        ),
    )
    with patch(
        "src.core.studio_v2.resolvers.user_input.AttorneyRosterRepository.list",
        new=AsyncMock(return_value=[]),
    ):
        env = await WizardResolver.dispatch(field=field)
    assert env.kind == "attorney_pick"
    assert env.multi_select is expected_multi_select


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_author_input_plain_text_emits_envelope():
    field = _field(
        "narrative",
        WizardSourceParams(
            source=SourceKind.AUTHOR_INPUT,
            author_input_kind=AuthorInputKind.PLAIN_TEXT,
        ),
    )
    env = await WizardResolver.dispatch(field=field)
    assert env.kind == "author_text"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_author_input_date_emits_envelope():
    field = _field(
        "service_date",
        WizardSourceParams(
            source=SourceKind.AUTHOR_INPUT,
            author_input_kind=AuthorInputKind.DATE,
        ),
    )
    env = await WizardResolver.dispatch(field=field)
    assert env.kind == "author_date"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_author_input_with_docs_emits_envelope():
    field = _field(
        "hardship",
        WizardSourceParams(
            source=SourceKind.AUTHOR_INPUT,
            author_input_kind=AuthorInputKind.WITH_DOCS,
        ),
    )
    env = await WizardResolver.dispatch(field=field)
    assert env.kind == "author_docs"


# ─── source-aware tool scoping ───────────────────────────────────────


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


@pytest.mark.unit
def test_tools_for_source_filters_to_source_specific_set():
    from src.core.studio_v2.orchestration.dispatcher import _tools_for_source

    gmail = _FakeTool("gmail_search")
    cvq = _FakeTool("case_vector_query")
    vision = _FakeTool("vision_fallback")
    full = [gmail, cvq, vision]

    assert _tools_for_source(SourceKind.GMAIL, full) == [gmail]
    assert _tools_for_source(SourceKind.CASE_FILE, full) == [cvq, vision]
    # Non-extractor sources receive an empty toolset (defensive — they
    # don't reach the LLM-extractor branch in practice).
    assert _tools_for_source(SourceKind.CONSTANTS, full) == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_gmail_field_receives_only_gmail_search_tool():
    """The actual smoke test: a gmail field's extractor agent is
    invoked with ONLY gmail_search bound — case_vector_query and
    vision_fallback never reach it, so the LLM cannot wander off
    source."""
    gmail = _FakeTool("gmail_search")
    cvq = _FakeTool("case_vector_query")
    vision = _FakeTool("vision_fallback")
    full = [gmail, cvq, vision]

    field = _field(
        "income",
        WizardSourceParams(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.RAW,
            extraction_prompt="last paystub amount",
        ),
    )
    expected = ResolvedTemplateValueV2(
        template_variable="income", value="$4,250", confidence="high",
    )
    with patch(
        "src.core.studio_v2.orchestration.dispatcher.DraftAgentV2.run",
        new=AsyncMock(return_value=expected),
    ) as agent_mock:
        await WizardResolver.dispatch(field=field, toolset=full)

    forwarded_tools = agent_mock.await_args.kwargs["tools"]
    assert forwarded_tools == [gmail]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_case_file_field_receives_case_vector_and_vision():
    gmail = _FakeTool("gmail_search")
    cvq = _FakeTool("case_vector_query")
    vision = _FakeTool("vision_fallback")
    full = [gmail, cvq, vision]

    field = _field(
        "creditor",
        WizardSourceParams(
            source=SourceKind.CASE_FILE,
            presentation_shape=PresentationShape.RAW,
            extraction_prompt="primary creditor",
        ),
    )
    expected = ResolvedTemplateValueV2(
        template_variable="creditor", value="Acme Bank", confidence="high",
    )
    with patch(
        "src.core.studio_v2.orchestration.dispatcher.DraftAgentV2.run",
        new=AsyncMock(return_value=expected),
    ) as agent_mock:
        await WizardResolver.dispatch(field=field, toolset=full)

    forwarded_tools = agent_mock.await_args.kwargs["tools"]
    assert forwarded_tools == [cvq, vision]
