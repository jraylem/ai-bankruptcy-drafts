"""Tests for UserInputResolver — both halves of the user-input stage.

  UserInputResolver.apply(...)        — build PendingGroupDropdown envelopes
                                         (mocks GroupDropdownAgent.run)
  UserInputResolver.expand_picks(...) — turn user picks into ResolvedTemplateValues
                                         (pure logic, no mocks)
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.agents.llm.dropdown import DropdownAgent, _ExtractedOptions
from src.core.agents.llm.group_dropdown import DropdownOption, GroupDropdownAgent


def _dd(options=None, completeness="full", reasoning=""):
    """Wrap a list of option strings into the `_ExtractedOptions` shape
    `DropdownAgent.run` now returns. Defaults to `completeness="full"` so
    existing tests that don't care about completeness keep their meaning
    (vision fallback only fires on partial/unknown OR count < min_picks).
    """
    return _ExtractedOptions(
        options=list(options or []),
        completeness=completeness,
        completeness_reasoning=reasoning,
    )
from src.core.agents.llm.reco_chips import RecoChipsAgent
from src.core.agents.resolvers.user_input_resolver import (
    PendingDropdown,
    PendingDropdownFromConstants,
    PendingGroupDropdown,
    PendingRecoChips,
    PendingUserInputWithDocs,
    SingleValuePick,
    SupportingDocsPick,
    UserInputResolver,
)
from src.core.agents.types.sources import (
    DropdownFromConstantsSourceParams,
    FieldSource,
    RecoChipsFromDependentVariablesSourceParams,
    UserInputWithSupportingDocsSourceParams,
)
from tests.core.factories import (
    make_dropdown_case_vector_source_params,
    make_dropdown_email_source_params,
    make_fetched_context,
    make_gmail_source_params,
    make_group_dropdown_composite,
    make_reco_chips_case_vector_source_params,
    make_reco_chips_source_params,
    make_resolved_value,
    make_template_field,
    make_group_dropdown_pick,
)


# ─── apply() — with GroupDropdownAgent mocked ─────────────────────────


def _dropdown_field(property_name: str = "docket_num__docket_title", **composite_overrides):
    composite = make_group_dropdown_composite(**composite_overrides)
    return make_template_field(
        property_name=property_name,
        source=FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
        source_params=composite,
    )


@pytest.mark.unit
async def test_apply_returns_empty_when_no_user_input_fields(monkeypatch):
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))
    gmail_field = make_template_field(
        source=FieldSource.GMAIL, source_params=make_gmail_source_params()
    )

    result = await UserInputResolver.apply([gmail_field], fetched_context=[])

    assert result == {}


@pytest.mark.unit
async def test_apply_skips_composites_with_no_fetched_context(monkeypatch):
    """Composite needs raw_result in fetched_context to extract from.
    No fetched context → skip silently."""
    run = AsyncMock(return_value=[])
    monkeypatch.setattr(GroupDropdownAgent, "run", run)
    field = _dropdown_field()

    result = await UserInputResolver.apply([field], fetched_context=[])

    assert result == {}
    run.assert_not_called()


@pytest.mark.unit
async def test_apply_skips_composites_with_none_raw_result(monkeypatch):
    run = AsyncMock(return_value=[])
    monkeypatch.setattr(GroupDropdownAgent, "run", run)
    field = _dropdown_field()
    ctx = make_fetched_context(property_name=field.property_name, raw_result=None)

    result = await UserInputResolver.apply([field], fetched_context=[ctx])

    assert result == {}
    run.assert_not_called()


@pytest.mark.unit
async def test_apply_builds_pending_envelope_with_display_value(monkeypatch):
    async def fake_run(name, params, fetched):
        return [
            DropdownOption(left="26-10700", right="Smith"),
            DropdownOption(left="26-10701", right="Jones"),
        ]

    monkeypatch.setattr(GroupDropdownAgent, "run", fake_run)
    field = _dropdown_field()
    ctx = make_fetched_context(property_name=field.property_name, raw_result={"some": "data"})

    result = await UserInputResolver.apply([field], fetched_context=[ctx])

    assert list(result.keys()) == [field.property_name]
    envelope = result[field.property_name]
    assert isinstance(envelope, PendingGroupDropdown)
    assert envelope.left_variable == "docket_number"
    assert envelope.right_variable == "docket_title"
    assert len(envelope.options) == 2
    assert envelope.options[0].display_value == "26-10700 - Smith"


@pytest.mark.unit
async def test_apply_drops_composites_where_agent_returned_empty(monkeypatch):
    """Agent returned [] for this composite → no pending entry."""
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))
    field = _dropdown_field()
    ctx = make_fetched_context(property_name=field.property_name, raw_result={"x": 1})

    result = await UserInputResolver.apply([field], fetched_context=[ctx])

    assert result == {}


@pytest.mark.unit
async def test_apply_skips_user_input_field_with_non_composite_params(monkeypatch):
    """Defensive — validator normally catches this, but if it slips through the
    resolver must log + skip instead of crashing."""
    run = AsyncMock(return_value=[])
    monkeypatch.setattr(GroupDropdownAgent, "run", run)
    bad_field = make_template_field(
        property_name="x",
        source=FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
        source_params=make_gmail_source_params(),  # wrong shape
    )

    result = await UserInputResolver.apply([bad_field], fetched_context=[])

    assert result == {}
    run.assert_not_called()


# ─── expand_picks() — pure logic ───────────────────────────────────────


def _user_input_field_with_composite(
    property_name: str,
    left_variable: str,
    right_variable: str,
):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
        source_params=make_group_dropdown_composite(
            left_variable=left_variable,
            right_variable=right_variable,
        ),
    )


@pytest.mark.unit
async def test_expand_picks_produces_two_resolved_values_per_composite():
    field = _user_input_field_with_composite(
        property_name="docket__title",
        left_variable="docket_num",
        right_variable="docket_title",
    )
    pick = make_group_dropdown_pick(left="26-10700", right="Smith")

    result = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={"docket__title": pick},
        case_id="test_case",
    )

    assert [rv.property_name for rv in result] == ["docket_num", "docket_title"]
    assert result[0].value == "26-10700"
    assert result[1].value == "Smith"
    assert result[0].confidence == "high"
    assert "docket__title" in result[0].reasoning


@pytest.mark.unit
async def test_expand_picks_rejects_unknown_keys():
    field = _user_input_field_with_composite(
        property_name="docket__title",
        left_variable="docket_num",
        right_variable="docket_title",
    )
    user_picks = {
        "docket__title": make_group_dropdown_pick(),
        "ghost_composite": make_group_dropdown_pick(left="x", right="y"),
    }

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks([field], [], user_picks, case_id="test_case")

    errors = exc.value.detail["user_pick_errors"]
    assert any("ghost_composite" in e for e in errors)


@pytest.mark.unit
async def test_expand_picks_rejects_missing_required_keys():
    f1 = _user_input_field_with_composite(
        property_name="first_composite",
        left_variable="a",
        right_variable="b",
    )
    f2 = _user_input_field_with_composite(
        property_name="second_composite",
        left_variable="c",
        right_variable="d",
    )

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[f1, f2],
            resolved_values=[],
            user_picks={"first_composite": make_group_dropdown_pick()},
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any("second_composite" in e and "missing" in e for e in errors)


@pytest.mark.unit
async def test_expand_picks_rejects_when_left_variable_already_resolved():
    field = _user_input_field_with_composite(
        property_name="composite",
        left_variable="docket_num",
        right_variable="docket_title",
    )

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[make_resolved_value(property_name="docket_num", value="already set")],
            user_picks={"composite": make_group_dropdown_pick()},
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any("'docket_num'" in e and "already contains" in e for e in errors)


@pytest.mark.unit
async def test_expand_picks_rejects_when_right_variable_already_resolved():
    field = _user_input_field_with_composite(
        property_name="composite",
        left_variable="docket_num",
        right_variable="docket_title",
    )

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[make_resolved_value(property_name="docket_title", value="already set")],
            user_picks={"composite": make_group_dropdown_pick()},
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any("'docket_title'" in e and "already contains" in e for e in errors)


@pytest.mark.unit
async def test_expand_picks_empty_inputs_returns_empty_list():
    result = await UserInputResolver.expand_picks(
        template_fields=[],
        resolved_values=[],
        user_picks={},
        case_id="test_case",
    )
    assert result == []


# ─── reco-chips: apply() ──────────────────────────────────────────────


def _reco_chips_field(
    property_name: str = "change_in_circumstances",
    label: str = "Change in Circumstances",
    example_sentence: str | None = None,
):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.RECO_CHIPS_FROM_GMAIL,
        source_params=make_reco_chips_source_params(
            label=label,
            example_sentence=example_sentence,
        ),
    )


@pytest.mark.unit
async def test_apply_builds_pending_reco_chips_envelope(monkeypatch):
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        RecoChipsAgent,
        "run",
        AsyncMock(return_value=[
            "Lost job at ABC Corp",
            "Medical emergency",
            "Divorce finalized",
        ]),
    )
    field = _reco_chips_field()
    ctx = make_fetched_context(property_name=field.property_name, raw_result={"emails": "data"})

    result = await UserInputResolver.apply([field], fetched_context=[ctx])

    assert list(result.keys()) == [field.property_name]
    envelope = result[field.property_name]
    assert isinstance(envelope, PendingRecoChips)
    assert envelope.kind == "reco_chips"
    assert envelope.label == "Change in Circumstances"
    assert envelope.chips == [
        "Lost job at ABC Corp",
        "Medical emergency",
        "Divorce finalized",
    ]


@pytest.mark.unit
async def test_apply_drops_reco_chips_where_agent_returned_empty(monkeypatch):
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))
    monkeypatch.setattr(RecoChipsAgent, "run", AsyncMock(return_value=[]))
    field = _reco_chips_field()
    ctx = make_fetched_context(property_name=field.property_name, raw_result={"emails": "data"})

    result = await UserInputResolver.apply([field], fetched_context=[ctx])

    assert result == {}


@pytest.mark.unit
async def test_apply_skips_reco_chips_with_no_fetched_context(monkeypatch):
    run = AsyncMock(return_value=["a", "b", "c"])
    monkeypatch.setattr(RecoChipsAgent, "run", run)
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))
    field = _reco_chips_field()

    result = await UserInputResolver.apply([field], fetched_context=[])

    assert result == {}
    run.assert_not_called()


@pytest.mark.unit
async def test_apply_handles_both_group_dropdown_and_reco_chips(monkeypatch):
    """Both field families resolve in a single apply() call."""
    async def fake_dropdown_run(name, params, fetched):
        return [DropdownOption(left="26-10700", right="Smith")]

    async def fake_reco_run(name, params, fetched):
        return ["chip-a", "chip-b"]

    monkeypatch.setattr(GroupDropdownAgent, "run", fake_dropdown_run)
    monkeypatch.setattr(RecoChipsAgent, "run", fake_reco_run)

    dropdown_field = make_template_field(
        property_name="docket__title",
        source=FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
        source_params=make_group_dropdown_composite(),
    )
    chips_field = _reco_chips_field()
    ctxs = [
        make_fetched_context(property_name=dropdown_field.property_name, raw_result={"x": 1}),
        make_fetched_context(property_name=chips_field.property_name, raw_result={"y": 2}),
    ]

    result = await UserInputResolver.apply(
        [dropdown_field, chips_field],
        fetched_context=ctxs,
    )

    assert set(result.keys()) == {"docket__title", "change_in_circumstances"}
    assert isinstance(result["docket__title"], PendingGroupDropdown)
    assert isinstance(result["change_in_circumstances"], PendingRecoChips)


# ─── reco_chips_from_dependent_variables — composes at apply() time ────


def _chip_from_deps_field(
    property_name: str = "dismissal_explanation",
    label: str = "Dismissal Explanation",
    example_sentence: str = "The Debtor's previous case was dismissed because...",
    dependent_variables: list[str] | None = None,
    instruction: str | None = None,
):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
        source_params=RecoChipsFromDependentVariablesSourceParams(
            label=label,
            example_sentence=example_sentence,
            dependent_variables=dependent_variables or ["trustee_reason"],
            instruction=instruction,
        ),
    )


@pytest.mark.unit
async def test_apply_chip_from_deps_composes_source_material_from_resolved_by_name(monkeypatch):
    """Handler emits a marker FetchedContext; apply() re-builds the source
    material from resolved_by_name (which includes Pass-2 LLM_DRAFT values)
    before calling RecoChipsAgent."""
    captured = {}

    async def fake_run(name, params, fetched):
        captured["fetched_raw_result"] = fetched.raw_result
        return ["chip-a", "chip-b", "chip-c"]

    monkeypatch.setattr(RecoChipsAgent, "run", fake_run)
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))

    field = _chip_from_deps_field(
        dependent_variables=["trustee_reason", "schedule_summary"],
        instruction="Synthesize 3 plausible reasons.",
    )
    marker_ctx = make_fetched_context(
        property_name=field.property_name,
        raw_result={"__deferred_chip_compose__": True},
    )
    resolved = {
        "trustee_reason": make_resolved_value("trustee_reason", "denial of confirmation of plan"),
        "schedule_summary": make_resolved_value("schedule_summary", "income $4,500/mo"),
    }

    result = await UserInputResolver.apply(
        [field],
        fetched_context=[marker_ctx],
        resolved_by_name=resolved,
    )

    assert captured["fetched_raw_result"] == {
        "trustee_reason": "denial of confirmation of plan",
        "schedule_summary": "income $4,500/mo",
        "__instruction__": "Synthesize 3 plausible reasons.",
    }
    assert isinstance(result[field.property_name], PendingRecoChips)
    assert result[field.property_name].chips == ["chip-a", "chip-b", "chip-c"]


@pytest.mark.unit
async def test_apply_chip_from_deps_skips_when_no_deps_resolved(monkeypatch):
    """If none of the dependent_variables have resolved values, the chip
    job is skipped (no agent call, no pending envelope)."""
    run = AsyncMock(return_value=["x", "y", "z"])
    monkeypatch.setattr(RecoChipsAgent, "run", run)
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))

    field = _chip_from_deps_field(dependent_variables=["nonexistent"])
    marker_ctx = make_fetched_context(
        property_name=field.property_name,
        raw_result={"__deferred_chip_compose__": True},
    )

    result = await UserInputResolver.apply(
        [field],
        fetched_context=[marker_ctx],
        resolved_by_name={},
    )

    assert result == {}
    run.assert_not_called()


@pytest.mark.unit
async def test_apply_chip_from_deps_drops_empty_resolved_values(monkeypatch):
    """Resolved values whose `.value` is empty/whitespace are skipped, but
    the job still runs as long as at least one dep has content."""
    captured = {}

    async def fake_run(name, params, fetched):
        captured["fetched_raw_result"] = fetched.raw_result
        return ["a", "b"]

    monkeypatch.setattr(RecoChipsAgent, "run", fake_run)
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))

    field = _chip_from_deps_field(dependent_variables=["a", "b"])
    marker_ctx = make_fetched_context(
        property_name=field.property_name,
        raw_result={"__deferred_chip_compose__": True},
    )
    resolved = {
        "a": make_resolved_value("a", "   "),
        "b": make_resolved_value("b", "kept"),
    }

    await UserInputResolver.apply(
        [field],
        fetched_context=[marker_ctx],
        resolved_by_name=resolved,
    )

    assert captured["fetched_raw_result"] == {"b": "kept"}


@pytest.mark.unit
async def test_apply_chip_from_deps_runs_case_vector_queries(monkeypatch):
    """case_vector_queries entries fire ToolBox.query_case_specific with
    {{var}} substituted and feed the result into the chip prompt."""
    from src.core.agents.resolvers import user_input_resolver as resolver_mod
    from src.core.agents.types.sources import CaseVectorQueryEntry, RecoChipsFromDependentVariablesSourceParams

    captured: dict = {}

    async def fake_run(name, params, fetched):
        captured["fetched_raw_result"] = fetched.raw_result
        return ["chip-a", "chip-b"]

    async def fake_query_case_specific(*, collection_name, query, k):
        captured.setdefault("queries", []).append({"query": query, "collection": collection_name})
        return [{"content": f"chunk for {query}", "relevance_score": 0.9}]

    monkeypatch.setattr(RecoChipsAgent, "run", fake_run)
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        resolver_mod.ToolBox,
        "query_case_specific",
        fake_query_case_specific,
    )

    field = make_template_field(
        property_name="change_in_circumstances_explanation",
        source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
        source_params=RecoChipsFromDependentVariablesSourceParams(
            label="Change in circumstances",
            example_sentence="...",
            dependent_variables=["prior_case_dismissal_reason"],
            case_vector_queries=[
                CaseVectorQueryEntry(
                    label="Current Schedule I & J",
                    text_query="Schedule I income Schedule J expenses",
                ),
                CaseVectorQueryEntry(
                    label="Prior Schedule",
                    text_query="Schedule I {{prior_case_number}}",
                ),
            ],
        ),
    )
    marker_ctx = make_fetched_context(
        property_name=field.property_name,
        raw_result={"__deferred_chip_compose__": True},
    )
    resolved = {
        "prior_case_dismissal_reason": make_resolved_value(
            "prior_case_dismissal_reason", "Denial of Confirmation of Plan"
        ),
        "prior_case_number": make_resolved_value("prior_case_number", "25-19062"),
    }

    await UserInputResolver.apply(
        [field],
        fetched_context=[marker_ctx],
        resolved_by_name=resolved,
        case_file_collection="case_file_26_10700",
    )

    queries = captured["queries"]
    assert {q["query"] for q in queries} == {
        "Schedule I income Schedule J expenses",
        "Schedule I 25-19062",
    }
    assert all(q["collection"] == "case_file_26_10700" for q in queries)

    composed = captured["fetched_raw_result"]
    assert "prior_case_dismissal_reason" in composed
    assert "__cv__:Current Schedule I & J" in composed
    assert "__cv__:Prior Schedule" in composed


@pytest.mark.unit
async def test_apply_chip_from_deps_skips_case_vector_when_no_collection(monkeypatch):
    from src.core.agents.resolvers import user_input_resolver as resolver_mod
    from src.core.agents.types.sources import CaseVectorQueryEntry, RecoChipsFromDependentVariablesSourceParams

    fake_query = AsyncMock()
    monkeypatch.setattr(resolver_mod.ToolBox, "query_case_specific", fake_query)
    monkeypatch.setattr(RecoChipsAgent, "run", AsyncMock(return_value=["x"]))
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))

    field = make_template_field(
        property_name="chips",
        source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
        source_params=RecoChipsFromDependentVariablesSourceParams(
            label="x",
            example_sentence="x",
            dependent_variables=["a"],
            case_vector_queries=[
                CaseVectorQueryEntry(label="X", text_query="hello"),
            ],
        ),
    )
    marker_ctx = make_fetched_context(
        property_name=field.property_name,
        raw_result={"__deferred_chip_compose__": True},
    )

    await UserInputResolver.apply(
        [field],
        fetched_context=[marker_ctx],
        resolved_by_name={"a": make_resolved_value("a", "v")},
        case_file_collection=None,  # no collection — vector queries skipped
    )

    fake_query.assert_not_awaited()


@pytest.mark.unit
async def test_apply_chip_from_deps_chained_runs_after_independent(monkeypatch):
    """Chip B with dependent_chip_variables=[A] runs after A and sees A's
    chips folded into its source material."""
    from src.core.agents.types.sources import RecoChipsFromDependentVariablesSourceParams

    captured: list = []

    async def fake_run(name, params, fetched):
        captured.append({"name": name, "raw_result": dict(fetched.raw_result)})
        return [f"{name}-chip-1", f"{name}-chip-2", f"{name}-chip-3"]

    monkeypatch.setattr(RecoChipsAgent, "run", fake_run)
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))

    chip_a = make_template_field(
        property_name="change_in_circumstances",
        source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
        source_params=RecoChipsFromDependentVariablesSourceParams(
            label="Change",
            example_sentence="x",
            dependent_variables=["trustee_reason"],
        ),
    )
    chip_b = make_template_field(
        property_name="dismissal_explanation",
        source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
        source_params=RecoChipsFromDependentVariablesSourceParams(
            label="Dismissal",
            example_sentence="x",
            dependent_variables=["trustee_reason"],
            dependent_chip_variables=["change_in_circumstances"],
        ),
    )
    ctxs = [
        make_fetched_context(property_name=chip_a.property_name,
                             raw_result={"__deferred_chip_compose__": True}),
        make_fetched_context(property_name=chip_b.property_name,
                             raw_result={"__deferred_chip_compose__": True}),
    ]

    result = await UserInputResolver.apply(
        [chip_a, chip_b],
        fetched_context=ctxs,
        resolved_by_name={"trustee_reason": make_resolved_value("trustee_reason", "denial of plan")},
    )

    # Both fields produced PendingRecoChips envelopes.
    assert set(result.keys()) == {"change_in_circumstances", "dismissal_explanation"}

    # chip_a ran first and chip_b's prompt carries chip_a's chip array.
    assert captured[0]["name"] == "change_in_circumstances"
    assert captured[1]["name"] == "dismissal_explanation"
    chip_b_raw = captured[1]["raw_result"]
    assert "__chips__:change_in_circumstances" in chip_b_raw
    assert "change_in_circumstances-chip-1" in chip_b_raw["__chips__:change_in_circumstances"]


# ─── reco-chips: expand_picks() ───────────────────────────────────────


@pytest.mark.unit
async def test_expand_picks_produces_one_resolved_value_per_reco_chip():
    field = _reco_chips_field(property_name="change_in_circumstances")

    result = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={"change_in_circumstances": SingleValuePick(value="Lost job April 2026")},
        case_id="test_case",
    )

    assert len(result) == 1
    assert result[0].property_name == "change_in_circumstances"
    assert result[0].value == "Lost job April 2026"
    assert result[0].confidence == "high"
    assert "change_in_circumstances" in result[0].reasoning


@pytest.mark.unit
async def test_expand_picks_rejects_reco_chip_key_not_in_template_fields():
    field = _reco_chips_field(property_name="change_in_circumstances")

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[],
            user_picks={
                "change_in_circumstances": SingleValuePick(value="x"),
                "ghost_field": SingleValuePick(value="y"),
            },
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any("ghost_field" in e for e in errors)


@pytest.mark.unit
async def test_expand_picks_rejects_when_reco_chip_variable_already_resolved():
    field = _reco_chips_field(property_name="change_in_circumstances")

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[
                make_resolved_value(property_name="change_in_circumstances", value="already set"),
            ],
            user_picks={"change_in_circumstances": SingleValuePick(value="new value")},
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any("'change_in_circumstances'" in e and "already contains" in e for e in errors)


@pytest.mark.unit
async def test_expand_picks_rejects_missing_required_reco_chip_key():
    field = _reco_chips_field(property_name="change_in_circumstances")

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[],
            user_picks={},
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any("change_in_circumstances" in e and "missing" in e for e in errors)


@pytest.mark.unit
async def test_apply_builds_pending_reco_chips_envelope_for_case_vector_variant(monkeypatch):
    """Case-vector variant flows through the same RecoChipsAgent and produces
    the same PendingRecoChips envelope shape."""
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        RecoChipsAgent,
        "run",
        AsyncMock(return_value=["chip-a", "chip-b", "chip-c"]),
    )
    field = make_template_field(
        property_name="employment_explanation",
        source=FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
        source_params=make_reco_chips_case_vector_source_params(
            label="Employment Description",
            text_query="employer occupation income",
            example_sentence="The Debtor is employed in a trusted role.",
        ),
    )
    ctx = make_fetched_context(
        property_name=field.property_name, raw_result={"petition": "snippets"}
    )

    result = await UserInputResolver.apply([field], fetched_context=[ctx])

    assert list(result.keys()) == [field.property_name]
    envelope = result[field.property_name]
    assert isinstance(envelope, PendingRecoChips)
    assert envelope.label == "Employment Description"
    assert envelope.chips == ["chip-a", "chip-b", "chip-c"]


@pytest.mark.unit
async def test_expand_picks_resolves_case_vector_reco_chip():
    field = make_template_field(
        property_name="employment_explanation",
        source=FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
        source_params=make_reco_chips_case_vector_source_params(
            text_query="employer occupation",
            example_sentence="The Debtor is employed in a trusted role.",
        ),
    )

    result = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={"employment_explanation": SingleValuePick(value="The Debtor is employed...")},
        case_id="test_case",
    )

    assert len(result) == 1
    assert result[0].property_name == "employment_explanation"
    assert result[0].value == "The Debtor is employed..."


@pytest.mark.unit
async def test_expand_picks_handles_mixed_dropdown_and_reco_chip_picks():
    dropdown_field = make_template_field(
        property_name="docket__title",
        source=FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
        source_params=make_group_dropdown_composite(
            left_variable="docket_num",
            right_variable="docket_title",
        ),
    )
    chips_field = _reco_chips_field(property_name="change_in_circumstances")

    result = await UserInputResolver.expand_picks(
        template_fields=[dropdown_field, chips_field],
        resolved_values=[],
        user_picks={
            "docket__title": make_group_dropdown_pick(left="26-10700", right="Smith"),
            "change_in_circumstances": SingleValuePick(value="Lost job April 2026"),
        },
        case_id="test_case",
    )

    property_names = [rv.property_name for rv in result]
    assert "docket_num" in property_names
    assert "docket_title" in property_names
    assert "change_in_circumstances" in property_names
    values = {rv.property_name: rv.value for rv in result}
    assert values["docket_num"] == "26-10700"
    assert values["docket_title"] == "Smith"
    assert values["change_in_circumstances"] == "Lost job April 2026"


# ─── plain dropdown: apply() ──────────────────────────────────────────


def _plain_dropdown_field(property_name: str = "motion_type"):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.DROPDOWN_FROM_CASE_VECTOR,
        source_params=make_dropdown_case_vector_source_params(
            text_query="motion type",
            label="Motion Type",
            example_format="Motion to Modify Plan",
        ),
    )


@pytest.mark.unit
async def test_apply_builds_pending_dropdown_envelope(monkeypatch):
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))
    monkeypatch.setattr(RecoChipsAgent, "run", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        DropdownAgent,
        "run",
        AsyncMock(return_value=_dd([
            "Motion to Modify Plan",
            "Motion to Extend Stay",
            "Motion to Waive Wage Deduction",
        ])),
    )
    field = _plain_dropdown_field()
    ctx = make_fetched_context(property_name=field.property_name, raw_result={"case": "data"})

    result = await UserInputResolver.apply([field], fetched_context=[ctx])

    assert list(result.keys()) == [field.property_name]
    envelope = result[field.property_name]
    assert isinstance(envelope, PendingDropdown)
    assert envelope.kind == "dropdown"
    assert envelope.label == "Motion Type"
    assert envelope.options == [
        "Motion to Modify Plan",
        "Motion to Extend Stay",
        "Motion to Waive Wage Deduction",
    ]


@pytest.mark.unit
async def test_apply_drops_dropdown_where_extraction_returned_empty(monkeypatch):
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))
    monkeypatch.setattr(RecoChipsAgent, "run", AsyncMock(return_value=[]))
    monkeypatch.setattr(DropdownAgent, "run", AsyncMock(return_value=_dd()))
    field = _plain_dropdown_field()
    ctx = make_fetched_context(property_name=field.property_name, raw_result={"case": "data"})

    result = await UserInputResolver.apply([field], fetched_context=[ctx])

    assert result == {}


@pytest.mark.unit
async def test_apply_dispatches_all_three_families_in_parallel(monkeypatch):
    """Group-dropdown + reco-chips + dropdown fields all get their own agent
    call, all in one asyncio.gather."""
    async def fake_group_run(name, params, fetched):
        return [DropdownOption(left="L", right="R")]

    async def fake_reco_run(name, params, fetched):
        return ["chip-a"]

    async def fake_dd_run(name, params, fetched):
        return _dd(["option-a"])

    monkeypatch.setattr(GroupDropdownAgent, "run", fake_group_run)
    monkeypatch.setattr(RecoChipsAgent, "run", fake_reco_run)
    monkeypatch.setattr(DropdownAgent, "run", fake_dd_run)

    gd_field = make_template_field(
        property_name="docket__title",
        source=FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
        source_params=make_group_dropdown_composite(),
    )
    rc_field = make_template_field(
        property_name="change_in_circumstances",
        source=FieldSource.RECO_CHIPS_FROM_GMAIL,
        source_params=make_reco_chips_source_params(label="Change"),
    )
    dd_field = _plain_dropdown_field()

    ctxs = [
        make_fetched_context(property_name=gd_field.property_name, raw_result={"x": 1}),
        make_fetched_context(property_name=rc_field.property_name, raw_result={"y": 2}),
        make_fetched_context(property_name=dd_field.property_name, raw_result={"z": 3}),
    ]

    result = await UserInputResolver.apply(
        [gd_field, rc_field, dd_field],
        fetched_context=ctxs,
    )

    assert set(result.keys()) == {"docket__title", "change_in_circumstances", "motion_type"}
    assert isinstance(result["docket__title"], PendingGroupDropdown)
    assert isinstance(result["change_in_circumstances"], PendingRecoChips)
    assert isinstance(result["motion_type"], PendingDropdown)


# ─── plain dropdown: expand_picks() ───────────────────────────────────


@pytest.mark.unit
async def test_expand_picks_produces_one_resolved_value_per_dropdown():
    field = _plain_dropdown_field(property_name="motion_type")

    result = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={"motion_type": SingleValuePick(value="Motion to Modify Plan")},
        case_id="test_case",
    )

    assert len(result) == 1
    assert result[0].property_name == "motion_type"
    assert result[0].value == "Motion to Modify Plan"
    assert result[0].confidence == "high"
    assert "motion_type" in result[0].reasoning
    assert "dropdown" in result[0].reasoning


@pytest.mark.unit
async def test_expand_picks_rejects_dropdown_key_not_in_template_fields():
    field = _plain_dropdown_field(property_name="motion_type")

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[],
            user_picks={
                "motion_type": SingleValuePick(value="Motion to Modify Plan"),
                "ghost_field": SingleValuePick(value="X"),
            },
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any("ghost_field" in e for e in errors)


@pytest.mark.unit
async def test_expand_picks_rejects_when_dropdown_variable_already_resolved():
    field = _plain_dropdown_field(property_name="motion_type")

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[
                make_resolved_value(property_name="motion_type", value="pre-existing"),
            ],
            user_picks={"motion_type": SingleValuePick(value="Motion to Modify Plan")},
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any("'motion_type'" in e and "already contains" in e for e in errors)


@pytest.mark.unit
async def test_expand_picks_rejects_group_dropdown_pick_for_dropdown_field():
    """GroupDropdownPick (left/right shape) is structurally distinct from
    SingleValuePick ({value: str}) — sending one to a single-value (plain
    dropdown or reco-chips) field must be rejected."""
    field = _plain_dropdown_field(property_name="motion_type")

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[],
            user_picks={"motion_type": make_group_dropdown_pick(left="26-10700", right="Smith")},
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any("motion_type" in e and "value" in e for e in errors)


# ─── user_input_with_supporting_docs: apply() + expand_picks() ────────


def _supporting_docs_field(property_name: str = "letter_of_explanation"):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.USER_INPUT_WITH_SUPPORTING_DOCS,
        source_params=UserInputWithSupportingDocsSourceParams(
            label="Letter of Explanation",
            accepted_file_types=["pdf", "docx", "txt", "md", "png", "jpg", "jpeg"],
        ),
    )


@pytest.mark.unit
async def test_apply_emits_pending_user_input_with_docs_envelope_without_llm_call(monkeypatch):
    """No pre-pause LLM call — the envelope is constructed from source_params alone."""
    monkeypatch.setattr(GroupDropdownAgent, "run", AsyncMock(return_value=[]))
    monkeypatch.setattr(RecoChipsAgent, "run", AsyncMock(return_value=[]))
    monkeypatch.setattr(DropdownAgent, "run", AsyncMock(return_value=_dd()))

    field = _supporting_docs_field(property_name="letter_of_explanation")

    # Intentionally pass an EMPTY fetched_context — supporting-docs fields
    # have no pre-pause context to fetch; the envelope must still be emitted.
    result = await UserInputResolver.apply([field], fetched_context=[])

    assert list(result.keys()) == ["letter_of_explanation"]
    envelope = result["letter_of_explanation"]
    assert isinstance(envelope, PendingUserInputWithDocs)
    assert envelope.kind == "user_input_with_docs"
    assert envelope.label == "Letter of Explanation"
    assert "pdf" in envelope.accepted_file_types


@pytest.mark.unit
async def test_expand_picks_resolves_supporting_docs_via_enhancement_agent(monkeypatch):
    """Happy path: pick with empty file_urls (so no R2 download path exercised)
    short-circuits through ExplanationEnhanceAgent which is stubbed to return
    a polished string. The pick's user_text is NOT the returned value — the
    agent's output is."""
    from src.core.agents.resolvers import user_input_resolver as resolver_module

    async def fake_enhance(*, variable_name, label, user_text, supporting_docs):
        return f"enhanced::{variable_name}::{user_text}"

    monkeypatch.setattr(
        resolver_module.ExplanationEnhanceAgent,
        "run",
        classmethod(lambda cls, **kw: fake_enhance(**kw)),
    )

    field = _supporting_docs_field(property_name="letter_of_explanation")
    pick = SupportingDocsPick(user_text="Raw user explanation.", file_urls=[])

    result = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={"letter_of_explanation": pick},
        case_id="test_case",
    )

    assert len(result) == 1
    assert result[0].property_name == "letter_of_explanation"
    assert result[0].value == "enhanced::letter_of_explanation::Raw user explanation."


@pytest.mark.unit
async def test_expand_picks_rejects_non_supporting_docs_pick_for_docs_field(monkeypatch):
    field = _supporting_docs_field(property_name="letter_of_explanation")

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[],
            user_picks={"letter_of_explanation": SingleValuePick(value="wrong shape")},
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any(
        "SupportingDocsPick" in e and "letter_of_explanation" in e
        for e in errors
    )


@pytest.mark.unit
async def test_expand_picks_rejects_file_url_outside_case_prefix():
    field = _supporting_docs_field(property_name="letter_of_explanation")
    bad_pick = SupportingDocsPick(
        user_text="some text",
        file_urls=["cases/OTHER_CASE/supporting_docs/uuid.pdf"],
    )

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[],
            user_picks={"letter_of_explanation": bad_pick},
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any("not under" in e and "cases/test_case/supporting_docs/" in e for e in errors)


@pytest.mark.unit
async def test_expand_picks_rejects_http_url_as_file_url():
    field = _supporting_docs_field(property_name="letter_of_explanation")
    bad_pick = SupportingDocsPick(
        user_text="some text",
        file_urls=["https://evil.example.com/paystub.pdf"],
    )

    with pytest.raises(HTTPException) as exc:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[],
            user_picks={"letter_of_explanation": bad_pick},
            case_id="test_case",
        )

    errors = exc.value.detail["user_pick_errors"]
    assert any("evil.example.com" in e for e in errors)


# ─── dropdown_from_constants: apply() + expand_picks() ────────────────


from src.core.common.storage.database import Attorney  # noqa: E402
import src.core.agents.resolvers.user_input_resolver as user_input_resolver_module  # noqa: E402


def _constants_dropdown_field(
    property_name: str = "attorney_name",
    reference_short_code: str = "ATTORNEYS",
    label: str = "Signing Attorney",
    template_property_marker: str = "Chad Van Horn, Esq.",
):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.DROPDOWN_FROM_CONSTANTS,
        source_params=DropdownFromConstantsSourceParams(
            reference_short_code=reference_short_code,
            label=label,
        ),
        template_property_marker=template_property_marker,
    )


@pytest.mark.unit
async def test_apply_emits_dropdown_from_constants_envelope(monkeypatch):
    """Attorney roster populated — apply emits PendingDropdownFromConstants with
    options as plain full_name strings (same shape as other dropdown sources)."""
    attorneys = [
        Attorney(id="att-1", full_name="Chad Van Horn, Esq."),
        Attorney(id="att-2", full_name="Jane Smith, Esq."),
    ]
    monkeypatch.setattr(
        user_input_resolver_module.AttorneyRosterRepository,
        "list",
        AsyncMock(return_value=attorneys),
    )
    field = _constants_dropdown_field()

    result = await UserInputResolver.apply([field], fetched_context=[])

    assert list(result.keys()) == [field.property_name]
    envelope = result[field.property_name]
    assert isinstance(envelope, PendingDropdownFromConstants)
    assert envelope.kind == "dropdown_from_constants"
    assert envelope.label == "Signing Attorney"
    assert envelope.options == ["Chad Van Horn, Esq.", "Jane Smith, Esq."]


@pytest.mark.unit
async def test_apply_emits_empty_options_when_roster_empty(monkeypatch):
    """Empty roster still emits the envelope so the FE can render a disabled dropdown."""
    monkeypatch.setattr(
        user_input_resolver_module.AttorneyRosterRepository,
        "list",
        AsyncMock(return_value=[]),
    )
    field = _constants_dropdown_field()

    result = await UserInputResolver.apply([field], fetched_context=[])

    assert list(result.keys()) == [field.property_name]
    envelope = result[field.property_name]
    assert isinstance(envelope, PendingDropdownFromConstants)
    assert envelope.options == []


@pytest.mark.unit
async def test_apply_emits_empty_options_for_unsupported_short_code(monkeypatch, caplog):
    """Unknown short_code logs a warning but still returns an envelope (empty)."""
    list_mock = AsyncMock()
    monkeypatch.setattr(
        user_input_resolver_module.AttorneyRosterRepository,
        "list",
        list_mock,
    )
    field = _constants_dropdown_field(reference_short_code="FUTURE_ROSTER")

    result = await UserInputResolver.apply([field], fetched_context=[])

    envelope = result[field.property_name]
    assert isinstance(envelope, PendingDropdownFromConstants)
    assert envelope.options == []
    list_mock.assert_not_called()  # ATTORNEYS-only path; other codes no-op


@pytest.mark.unit
async def test_expand_picks_takes_constants_pick_verbatim():
    """dropdown_from_constants picks the label string verbatim — same contract
    as other dropdown sources. No repo lookup at resume time."""
    field = _constants_dropdown_field(property_name="attorney_name")

    result = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={"attorney_name": SingleValuePick(value="Chad Van Horn, Esq.")},
        case_id="test_case",
    )

    assert len(result) == 1
    assert result[0].property_name == "attorney_name"
    assert result[0].value == "Chad Van Horn, Esq."
    assert result[0].confidence == "high"
    assert "ATTORNEYS" in result[0].reasoning


# ─── user_input_plain_text: apply() + expand_picks() ──────────────────


from src.core.agents.resolvers.user_input_resolver import PendingUserInputPlainText  # noqa: E402
from src.core.agents.types.sources import UserInputPlainTextSourceParams  # noqa: E402


def _plain_text_field(
    property_name: str = "basis_for_objection",
    label: str = "Basis for Objection",
    placeholder: str | None = "Lack of supporting documentation",
    example_output_sentence: str = "The claim should be disallowed because the documentation supplied is insufficient.",
):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.USER_INPUT_PLAIN_TEXT,
        source_params=UserInputPlainTextSourceParams(
            label=label,
            placeholder=placeholder,
            example_output_sentence=example_output_sentence,
        ),
    )


@pytest.mark.unit
async def test_apply_emits_plain_text_envelope_without_llm_call():
    """USER_INPUT_PLAIN_TEXT is a pure form — no fetched_context required,
    no pre-pause LLM call. apply() emits the envelope directly."""
    field = _plain_text_field()

    result = await UserInputResolver.apply([field], fetched_context=[])

    assert list(result.keys()) == [field.property_name]
    envelope = result[field.property_name]
    assert isinstance(envelope, PendingUserInputPlainText)
    assert envelope.kind == "user_input_plain_text"
    assert envelope.label == "Basis for Objection"
    assert envelope.placeholder == "Lack of supporting documentation"
    assert envelope.example_output_sentence.startswith("The claim should be disallowed")


@pytest.mark.unit
async def test_expand_picks_resolves_plain_text_value_verbatim():
    """The user's typed text fills the variable directly; heal happens later
    in the pipeline (UserInputHealAgent), not here."""
    field = _plain_text_field(property_name="basis_for_objection")

    result = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={"basis_for_objection": SingleValuePick(value="Lack of supporting documentation.")},
        case_id="test_case",
    )

    assert len(result) == 1
    assert result[0].property_name == "basis_for_objection"
    assert result[0].value == "Lack of supporting documentation."
    assert result[0].confidence == "high"
    assert "user_input_plain_text" in result[0].reasoning


# ─── multi_select_from_case_vector ─────────────────────────────────────


from src.core.agents.resolvers.user_input_resolver import (
    MultiSelectPick,
    PendingMultiSelect,
)
from src.core.agents.types.sources import (
    MultiSelectFromCaseVectorSourceParams,
)


def _multi_select_field(
    property_name: str = "selected_assets",
    label: str = "Select Assets for Reaffirmation",
    instruction: str | None = "Pick options.",
    text_query: str = "Schedule A/B property OR Schedule D vehicle",
    example_formats: list[str] | None = None,
    min_picks: int = 1,
    max_picks: int | None = None,
    list_joiner: str = ", ",
    oxford: bool = True,
):
    if example_formats is None:
        example_formats = ['2018 Mercedes G-Wagon, VIN# WDCYC3KH3JX288288 ("Vehicle")']
    params = MultiSelectFromCaseVectorSourceParams(
        label=label,
        instruction=instruction,
        text_query=text_query,
        example_formats=example_formats,
        min_picks=min_picks,
        max_picks=max_picks,
        list_joiner=list_joiner,
        oxford=oxford,
    )
    return make_template_field(
        property_name=property_name,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        source_params=params,
    )


@pytest.mark.unit
async def test_apply_emits_multi_select_envelope(monkeypatch):
    extracted = [
        '2018 Mercedes G-Wagon, VIN# WDCYC3KH3JX288288 ("Vehicle")',
        '2186 Appleton Cir N, Oakland Park, FL 33441 ("Property")',
    ]
    monkeypatch.setattr(DropdownAgent, "run", AsyncMock(return_value=_dd(extracted)))

    field = _multi_select_field()
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        raw_result={"some": "vector_chunks"},
    )

    result = await UserInputResolver.apply([field], fetched_context=[ctx])

    assert list(result.keys()) == [field.property_name]
    envelope = result[field.property_name]
    assert isinstance(envelope, PendingMultiSelect)
    assert envelope.kind == "multi_select"
    assert envelope.label == "Select Assets for Reaffirmation"
    assert envelope.options == extracted
    assert envelope.min_picks == 1


@pytest.mark.unit
async def test_apply_emits_envelope_even_when_extraction_returns_empty(monkeypatch):
    """Empty extraction still surfaces an envelope so the FE can render the
    empty-state with skip-or-cancel affordance."""
    monkeypatch.setattr(DropdownAgent, "run", AsyncMock(return_value=_dd()))

    field = _multi_select_field()
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        raw_result={"any": "thing"},
    )

    result = await UserInputResolver.apply([field], fetched_context=[ctx])
    envelope = result[field.property_name]
    assert isinstance(envelope, PendingMultiSelect)
    assert envelope.options == []


@pytest.mark.unit
async def test_expand_picks_oxford_joins_three_or_more_picks():
    field = _multi_select_field()
    picks = ["Honda Civic", "Ford F150", "Toyota Camry"]

    out = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={field.property_name: MultiSelectPick(picked_values=picks)},
        case_id="test_case",
    )

    assert len(out) == 1
    assert out[0].value == "Honda Civic, Ford F150, and Toyota Camry"
    assert out[0].confidence == "high"
    assert "multi-select" in out[0].reasoning


@pytest.mark.unit
async def test_expand_picks_two_picks_uses_and_without_comma():
    field = _multi_select_field()
    picks = ["Honda Civic", "Ford F150"]

    out = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={field.property_name: MultiSelectPick(picked_values=picks)},
        case_id="test_case",
    )

    assert out[0].value == "Honda Civic and Ford F150"


@pytest.mark.unit
async def test_expand_picks_single_pick_passes_through_verbatim():
    field = _multi_select_field()
    picks = ['2018 Mercedes G-Wagon, VIN# WDCYC3KH3JX288288 ("Vehicle")']

    out = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={field.property_name: MultiSelectPick(picked_values=picks)},
        case_id="test_case",
    )

    assert out[0].value == picks[0]


@pytest.mark.unit
async def test_expand_picks_oxford_off_uses_plain_joiner():
    field = _multi_select_field(list_joiner="; ", oxford=False)
    picks = ["A", "B", "C"]

    out = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={field.property_name: MultiSelectPick(picked_values=picks)},
        case_id="test_case",
    )

    assert out[0].value == "A; B; C"


@pytest.mark.unit
async def test_expand_picks_drops_empty_strings():
    field = _multi_select_field()
    picks = ["Honda", "  ", "", "Ford"]

    out = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={field.property_name: MultiSelectPick(picked_values=picks)},
        case_id="test_case",
    )

    assert out[0].value == "Honda and Ford"


@pytest.mark.unit
async def test_expand_picks_dedupes_case_insensitively():
    field = _multi_select_field()
    picks = ["Honda Civic", "honda civic", "FORD F150"]

    out = await UserInputResolver.expand_picks(
        template_fields=[field],
        resolved_values=[],
        user_picks={field.property_name: MultiSelectPick(picked_values=picks)},
        case_id="test_case",
    )

    # Preserves first-seen order; second "honda civic" is dropped.
    assert out[0].value == "Honda Civic and FORD F150"


@pytest.mark.unit
async def test_expand_picks_rejects_when_below_min_picks():
    field = _multi_select_field(min_picks=2)
    with pytest.raises(HTTPException) as excinfo:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[],
            user_picks={field.property_name: MultiSelectPick(picked_values=["Honda"])},
            case_id="test_case",
        )
    errors = excinfo.value.detail["user_pick_errors"]
    assert any("at least 2" in e for e in errors)


@pytest.mark.unit
async def test_expand_picks_rejects_when_above_max_picks():
    field = _multi_select_field(max_picks=1)
    with pytest.raises(HTTPException) as excinfo:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[],
            user_picks={field.property_name: MultiSelectPick(picked_values=["A", "B"])},
            case_id="test_case",
        )
    errors = excinfo.value.detail["user_pick_errors"]
    assert any("at most 1" in e for e in errors)


@pytest.mark.unit
async def test_expand_picks_rejects_wrong_pick_type():
    field = _multi_select_field()
    with pytest.raises(HTTPException) as excinfo:
        await UserInputResolver.expand_picks(
            template_fields=[field],
            resolved_values=[],
            user_picks={field.property_name: SingleValuePick(value="not-a-multi-select-pick")},
            case_id="test_case",
        )
    errors = excinfo.value.detail["user_pick_errors"]
    assert any("MultiSelectPick" in e for e in errors)


# ─── multi_select vision fallback ──────────────────────────────────────


from src.core.agents.llm.multi_select_vision import (
    MultiSelectVisionAgent,
    VisionExtractionResult,
)
from src.core.agents.utils import petition_pdf as petition_pdf_module


def _vr(options=None, superseded=None):
    """Wrap option strings + supersedes into the `VisionExtractionResult`
    shape `MultiSelectVisionAgent.run` now returns."""
    return VisionExtractionResult(
        options=list(options or []),
        superseded_baseline=list(superseded or []),
    )


@pytest.mark.unit
async def test_apply_vision_fallback_augments_when_below_min_picks(monkeypatch):
    """DropdownAgent returns 0 options + petition_pdf_url is set + vision toggle on
    → MultiSelectVisionAgent fires and augments the option list."""
    monkeypatch.setattr(DropdownAgent, "run", AsyncMock(return_value=_dd()))
    from src.core.agents.resolvers import user_input_resolver as resolver_mod
    monkeypatch.setattr(
        resolver_mod,
        "fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"%PDF-fake"),
    )
    monkeypatch.setattr(
        MultiSelectVisionAgent,
        "run",
        AsyncMock(return_value=_vr(["A", "B"])),
    )

    field = _multi_select_field(min_picks=1)
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        raw_result={"some": "vector_chunks"},
    )

    result = await UserInputResolver.apply(
        [field],
        fetched_context=[ctx],
        petition_pdf_url="https://r2/case/petition.pdf",
    )
    envelope = result[field.property_name]
    assert envelope.options == ["A", "B"]


@pytest.mark.unit
async def test_apply_vision_fallback_dedupes_against_baseline(monkeypatch):
    """Vision options that case-insensitively match existing baseline are
    dropped; new ones are appended."""
    # Baseline of 1 with completeness="full" alone wouldn't trigger vision
    # (count >= min_picks=2 fails, but completeness OK doesn't matter — count
    # gate fires first). Use completeness="partial" so the new gate also
    # fires; result: vision still augments because count < min_picks.
    monkeypatch.setattr(
        DropdownAgent,
        "run",
        AsyncMock(return_value=_dd(["Honda"], completeness="partial")),
    )
    from src.core.agents.resolvers import user_input_resolver as resolver_mod
    monkeypatch.setattr(
        resolver_mod,
        "fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"%PDF-fake"),
    )
    monkeypatch.setattr(
        MultiSelectVisionAgent,
        "run",
        AsyncMock(return_value=_vr(["honda", "Ford"])),
    )

    field = _multi_select_field(min_picks=2)
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        raw_result={"x": 1},
    )

    result = await UserInputResolver.apply(
        [field],
        fetched_context=[ctx],
        petition_pdf_url="https://r2/case/petition.pdf",
    )
    envelope = result[field.property_name]
    assert envelope.options == ["Honda", "Ford"]


@pytest.mark.unit
async def test_apply_vision_fallback_skips_when_baseline_meets_min(monkeypatch):
    """DropdownAgent returns ≥ min_picks options AND completeness=full → vision fallback is NOT triggered."""
    vision_run = AsyncMock(return_value=_vr(["should-not-fire"]))
    monkeypatch.setattr(
        DropdownAgent,
        "run",
        AsyncMock(return_value=_dd(["A", "B"], completeness="full")),
    )
    monkeypatch.setattr(MultiSelectVisionAgent, "run", vision_run)
    from src.core.agents.resolvers import user_input_resolver as resolver_mod
    monkeypatch.setattr(
        resolver_mod,
        "fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"%PDF-fake"),
    )

    field = _multi_select_field(min_picks=2)
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        raw_result={"x": 1},
    )

    await UserInputResolver.apply(
        [field],
        fetched_context=[ctx],
        petition_pdf_url="https://r2/case/petition.pdf",
    )
    vision_run.assert_not_called()


@pytest.mark.unit
async def test_apply_vision_fallback_fires_on_partial_completeness_even_when_count_meets_min(monkeypatch):
    """Real bug from case 26-14090: DropdownAgent returned 2 options
    (passes `min_picks=1`) but the chunks were Schedule C exemption pages,
    not the source Schedule A/B itemized rows. With `completeness="partial"`,
    vision fallback MUST fire so the petition PDF is read directly."""
    monkeypatch.setattr(
        DropdownAgent,
        "run",
        AsyncMock(
            return_value=_dd(
                ["Mercedes G-Wagon", "Primary Residence"],
                completeness="partial",
                reasoning="Saw Schedule C exemption chunks; itemized Schedule A/B rows missing.",
            )
        ),
    )
    from src.core.agents.resolvers import user_input_resolver as resolver_mod
    monkeypatch.setattr(
        resolver_mod,
        "fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"%PDF-fake"),
    )
    vision_run = AsyncMock(return_value=_vr(["Kia Stinger 2022", "Kia Sportage 2023"]))
    monkeypatch.setattr(MultiSelectVisionAgent, "run", vision_run)

    field = _multi_select_field(min_picks=1)
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        raw_result={"chunks": "fragmentary"},
    )

    result = await UserInputResolver.apply(
        [field],
        fetched_context=[ctx],
        petition_pdf_url="https://r2/case/petition.pdf",
    )
    vision_run.assert_called_once()
    # Baseline options must be passed into vision so it can dedup shape variants
    # ('Mercedes G-Wagon' vs 'Mercedes G-Wagon - VIN# X') instead of the resolver
    # relying on fragile string-equality post-merge dedup.
    call_kwargs = vision_run.call_args.kwargs
    assert call_kwargs["baseline_options"] == ["Mercedes G-Wagon", "Primary Residence"]
    envelope = result[field.property_name]
    # Baseline + vision-augmented options, vision rows appended after baseline.
    assert "Mercedes G-Wagon" in envelope.options
    assert "Kia Stinger 2022" in envelope.options
    assert "Kia Sportage 2023" in envelope.options


@pytest.mark.unit
async def test_apply_vision_fallback_drops_baseline_strings_marked_superseded(monkeypatch):
    """Real bug from the field: baseline had bare 'Mercedes G-Wagon' (no VIN),
    vision saw the same vehicle in the PDF AND could produce the richer
    'Mercedes G-Wagon - VIN# X' that fully matches example_formats. With
    `supersedes` set on the vision option, the resolver must DROP the bare
    baseline string and keep the richer vision version — so the picker
    shows only the better-shaped option.

    Author can express this preference agnostically: shape that better
    matches `example_formats` always wins, regardless of source."""
    monkeypatch.setattr(
        DropdownAgent,
        "run",
        AsyncMock(
            return_value=_dd(
                ["Mercedes G-Wagon", "Other Asset"],
                completeness="partial",
            )
        ),
    )
    from src.core.agents.resolvers import user_input_resolver as resolver_mod
    monkeypatch.setattr(
        resolver_mod,
        "fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"%PDF-fake"),
    )
    monkeypatch.setattr(
        MultiSelectVisionAgent,
        "run",
        AsyncMock(
            return_value=_vr(
                options=[
                    "2018 Mercedes G-Wagon - VIN WDCYC3KH3JX288288",
                    "2022 Kia Stinger - VIN KNAE55LC5N6117584",
                ],
                superseded=["Mercedes G-Wagon"],
            )
        ),
    )

    field = _multi_select_field(min_picks=1)
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        raw_result={"x": 1},
    )

    result = await UserInputResolver.apply(
        [field],
        fetched_context=[ctx],
        petition_pdf_url="https://r2/case/petition.pdf",
    )
    envelope = result[field.property_name]
    # Bare baseline 'Mercedes G-Wagon' is dropped because vision superseded it.
    assert "Mercedes G-Wagon" not in envelope.options
    # The other unaffected baseline survives unchanged.
    assert "Other Asset" in envelope.options
    # Both vision options appear — the richer Mercedes shape and the new Kia.
    assert "2018 Mercedes G-Wagon - VIN WDCYC3KH3JX288288" in envelope.options
    assert "2022 Kia Stinger - VIN KNAE55LC5N6117584" in envelope.options


@pytest.mark.unit
async def test_apply_vision_fallback_supersedes_match_is_case_insensitive(monkeypatch):
    """LLM may copy the baseline string with whitespace/case drift. Resolver
    must match on stripped + lowercased identity so the supersede still drops
    the right baseline entry."""
    monkeypatch.setattr(
        DropdownAgent,
        "run",
        AsyncMock(
            return_value=_dd(
                ["MERCEDES G-WAGON  "],  # uppercased + trailing whitespace
                completeness="partial",
            )
        ),
    )
    from src.core.agents.resolvers import user_input_resolver as resolver_mod
    monkeypatch.setattr(
        resolver_mod,
        "fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"%PDF-fake"),
    )
    monkeypatch.setattr(
        MultiSelectVisionAgent,
        "run",
        AsyncMock(
            return_value=_vr(
                options=["2018 Mercedes G-Wagon - VIN X"],
                superseded=["mercedes g-wagon"],  # lowercase, no trailing ws
            )
        ),
    )

    field = _multi_select_field(min_picks=1)
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        raw_result={"x": 1},
    )

    result = await UserInputResolver.apply(
        [field],
        fetched_context=[ctx],
        petition_pdf_url="https://r2/case/petition.pdf",
    )
    envelope = result[field.property_name]
    assert "MERCEDES G-WAGON  " not in envelope.options
    assert "2018 Mercedes G-Wagon - VIN X" in envelope.options


@pytest.mark.unit
async def test_apply_vision_fallback_skips_when_no_petition_pdf(monkeypatch):
    """Without petition_pdf_url, the vision fallback never fires regardless of options count."""
    vision_run = AsyncMock(return_value=_vr(["should-not-fire"]))
    monkeypatch.setattr(DropdownAgent, "run", AsyncMock(return_value=_dd()))
    monkeypatch.setattr(MultiSelectVisionAgent, "run", vision_run)

    field = _multi_select_field(min_picks=1)
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        raw_result={"x": 1},
    )

    await UserInputResolver.apply([field], fetched_context=[ctx])  # no petition_pdf_url
    vision_run.assert_not_called()


@pytest.mark.unit
async def test_apply_vision_fallback_skips_when_kill_switch_off(monkeypatch):
    """Settings flag false → vision fallback bypassed even when other conditions met."""
    from src.core.agents.resolvers import user_input_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod.settings, "CASE_VECTOR_VISION_FALLBACK_ENABLED", False)
    vision_run = AsyncMock(return_value=_vr(["should-not-fire"]))
    monkeypatch.setattr(DropdownAgent, "run", AsyncMock(return_value=_dd()))
    monkeypatch.setattr(MultiSelectVisionAgent, "run", vision_run)

    field = _multi_select_field(min_picks=1)
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        raw_result={"x": 1},
    )

    await UserInputResolver.apply(
        [field],
        fetched_context=[ctx],
        petition_pdf_url="https://r2/case/petition.pdf",
    )
    vision_run.assert_not_called()


# ─── multi_select_from_gmail (parallel coverage to case-vector variant) ─


from src.core.agents.types.sources import MultiSelectFromGmailSourceParams


def _multi_select_gmail_field(
    property_name: str = "creditor_names",
    label: str = "Select Creditors that Altered Plan Terms",
    instruction: str | None = "Pick from the case's POC filings.",
    subject_query: str | None = "Proof of Claim",
    body_query: str | None = None,
    scope_to_current_case: bool = True,
    example_formats: list[str] | None = None,
    min_picks: int = 1,
    max_picks: int | None = None,
):
    if example_formats is None:
        example_formats = ["JPMorgan Chase Bank (POC 3)"]
    params = MultiSelectFromGmailSourceParams(
        label=label,
        instruction=instruction,
        subject_query=subject_query,
        body_query=body_query,
        scope_to_current_case=scope_to_current_case,
        example_formats=example_formats,
        min_picks=min_picks,
        max_picks=max_picks,
    )
    return make_template_field(
        property_name=property_name,
        source=FieldSource.MULTI_SELECT_FROM_GMAIL,
        source_params=params,
    )


@pytest.mark.unit
async def test_apply_emits_multi_select_envelope_for_gmail_source(monkeypatch):
    """Gmail multi-select dispatches through the same DropdownAgent + emits
    PendingMultiSelect — exact same envelope shape as the case-vector variant."""
    extracted = ["JPMorgan Chase Bank (POC 3)", "Wells Fargo (POC 7)"]
    monkeypatch.setattr(DropdownAgent, "run", AsyncMock(return_value=_dd(extracted)))

    field = _multi_select_gmail_field()
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_GMAIL,
        raw_result={"emails": ["..."]},
    )

    result = await UserInputResolver.apply([field], fetched_context=[ctx])

    envelope = result[field.property_name]
    assert isinstance(envelope, PendingMultiSelect)
    assert envelope.kind == "multi_select"
    assert envelope.label == "Select Creditors that Altered Plan Terms"
    assert envelope.options == extracted


@pytest.mark.unit
async def test_apply_vision_fallback_skips_gmail_multi_select(monkeypatch):
    """Vision fallback is petition-PDF-only and must NEVER fire on Gmail
    multi-select fields, regardless of completeness or option count."""
    vision_run = AsyncMock(return_value=_vr(["should-not-fire"]))
    monkeypatch.setattr(DropdownAgent, "run", AsyncMock(return_value=_dd()))
    monkeypatch.setattr(MultiSelectVisionAgent, "run", vision_run)

    field = _multi_select_gmail_field(min_picks=1)
    ctx = make_fetched_context(
        property_name=field.property_name,
        source=FieldSource.MULTI_SELECT_FROM_GMAIL,
        raw_result={"emails": []},
    )

    # Even with petition_pdf_url present + min_picks=1 unmet, gmail multi-select
    # must skip vision because Gmail has no PDF counterpart.
    await UserInputResolver.apply(
        [field],
        fetched_context=[ctx],
        petition_pdf_url="https://r2/case/petition.pdf",
    )
    vision_run.assert_not_called()


@pytest.mark.unit
async def test_expand_picks_oxford_joins_gmail_multi_select():
    """Pick-expansion + Oxford join works identically for the Gmail variant."""
    field = _multi_select_gmail_field(min_picks=1, max_picks=5)

    pick = MultiSelectPick(
        picked_values=["JPMorgan Chase Bank (POC 3)", "Wells Fargo (POC 7)"],
    )

    out = await UserInputResolver.expand_picks(
        [field],
        [],
        {field.property_name: pick},
        case_id="26_10491",
    )

    assert len(out) == 1
    assert out[0].property_name == field.property_name
    assert out[0].value == "JPMorgan Chase Bank (POC 3) and Wells Fargo (POC 7)"
