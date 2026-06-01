"""Tests for AutoDerivedResolver — dispatches AutoDeriveAgent per derived field.

Mocks AutoDeriveAgent.run so tests stay deterministic.
"""

from unittest.mock import AsyncMock

import pytest

from src.core.agents.llm.auto_derive import AutoDeriveAgent
from src.core.agents.resolvers.auto_derived_resolver import AutoDerivedResolver
from src.core.agents.types.sources import (
    AutoDerivedSourceParams,
    FieldSource,
)
from src.core.agents.types.spec import TemplateField
from tests.core.factories import make_resolved_value


def _auto_derived_field(
    property_name: str,
    parent: str,
    marker: str = "",
    context: str = "",
) -> TemplateField:
    return TemplateField(
        property_name=property_name,
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable=parent),
        template_variable_string=f"[[{property_name}]]",
        template_property_marker=marker,
        template_identifying_text_match=context,
    )


@pytest.mark.unit
async def test_apply_emits_one_resolved_value_per_derived_field(monkeypatch):
    monkeypatch.setattr(AutoDeriveAgent, "run", AsyncMock(return_value="3"))

    field = _auto_derived_field(
        property_name="ecf_title",
        parent="ecf_full",
        marker="3",
        context="(ECF 3)",
    )
    resolved = [
        make_resolved_value(
            property_name="ecf_full",
            value="3, being a Certification of Budget and Credit Counseling Course by Debtor",
        ),
    ]

    out = await AutoDerivedResolver.apply([field], resolved_values=resolved)

    assert len(out) == 1
    assert out[0].property_name == "ecf_title"
    assert out[0].value == "3"
    assert out[0].confidence == "high"
    assert "ecf_full" in out[0].reasoning


@pytest.mark.unit
async def test_apply_skips_when_parent_missing_from_resolved_values(monkeypatch):
    run_mock = AsyncMock(return_value="X")
    monkeypatch.setattr(AutoDeriveAgent, "run", run_mock)

    field = _auto_derived_field(property_name="derived", parent="missing_parent")

    out = await AutoDerivedResolver.apply([field], resolved_values=[])

    run_mock.assert_not_called()
    assert out == []


@pytest.mark.unit
async def test_apply_skips_when_parent_value_is_empty(monkeypatch):
    run_mock = AsyncMock(return_value="X")
    monkeypatch.setattr(AutoDeriveAgent, "run", run_mock)

    field = _auto_derived_field(property_name="derived", parent="parent")
    resolved = [make_resolved_value(property_name="parent", value="")]

    out = await AutoDerivedResolver.apply([field], resolved_values=resolved)

    run_mock.assert_not_called()
    assert out == []


@pytest.mark.unit
async def test_apply_skips_when_agent_returns_empty(monkeypatch):
    """LLM couldn't derive → no ResolvedTemplateValue emitted; placeholder
    surfaces as unresolved at fill time."""
    monkeypatch.setattr(AutoDeriveAgent, "run", AsyncMock(return_value=""))

    field = _auto_derived_field(property_name="derived", parent="parent", marker="x")
    resolved = [make_resolved_value(property_name="parent", value="some text")]

    out = await AutoDerivedResolver.apply([field], resolved_values=resolved)

    assert out == []


@pytest.mark.unit
async def test_apply_dispatches_multiple_derivations_in_parallel(monkeypatch):
    """Two auto-derived fields, two AutoDeriveAgent calls, both healed."""
    run_mock = AsyncMock(side_effect=["A-derived", "B-derived"])
    monkeypatch.setattr(AutoDeriveAgent, "run", run_mock)

    fields = [
        _auto_derived_field(property_name="a_derived", parent="a_parent", marker="a"),
        _auto_derived_field(property_name="b_derived", parent="b_parent", marker="b"),
    ]
    resolved = [
        make_resolved_value(property_name="a_parent", value="parent a value"),
        make_resolved_value(property_name="b_parent", value="parent b value"),
    ]

    out = await AutoDerivedResolver.apply(fields, resolved_values=resolved)

    assert run_mock.await_count == 2
    assert {rv.property_name for rv in out} == {"a_derived", "b_derived"}
    assert {rv.value for rv in out} == {"A-derived", "B-derived"}


@pytest.mark.unit
async def test_apply_ignores_non_auto_derived_fields(monkeypatch):
    """Only AUTO_DERIVED stage fields go through; LLM_DRAFT / etc. ignored."""
    run_mock = AsyncMock(return_value="X")
    monkeypatch.setattr(AutoDeriveAgent, "run", run_mock)

    derived = _auto_derived_field(property_name="d", parent="p", marker="m")
    other = TemplateField(
        property_name="other",
        source=FieldSource.GMAIL,
        source_params=None,
        template_variable_string="[[other]]",
    )
    resolved = [make_resolved_value(property_name="p", value="parent")]

    out = await AutoDerivedResolver.apply([derived, other], resolved_values=resolved)

    assert run_mock.await_count == 1
    assert len(out) == 1
    assert out[0].property_name == "d"


@pytest.mark.unit
async def test_apply_passes_marker_and_context_through(monkeypatch):
    """Verify the resolver hands through template_property_marker AND
    template_identifying_text_match into the agent call."""
    captured = {}

    async def fake_run(parent_variable, parent_value, derived_marker, derived_context):
        captured["parent_variable"] = parent_variable
        captured["parent_value"] = parent_value
        captured["derived_marker"] = derived_marker
        captured["derived_context"] = derived_context
        return "ok"

    monkeypatch.setattr(AutoDeriveAgent, "run", fake_run)

    field = _auto_derived_field(
        property_name="d",
        parent="p",
        marker="MARKER_X",
        context="CONTEXT_Y",
    )
    resolved = [make_resolved_value(property_name="p", value="parent")]

    await AutoDerivedResolver.apply([field], resolved_values=resolved)

    assert captured["parent_variable"] == "p"
    assert captured["parent_value"] == "parent"
    assert captured["derived_marker"] == "MARKER_X"
    assert captured["derived_context"] == "CONTEXT_Y"


@pytest.mark.unit
async def test_apply_empty_input_short_circuits(monkeypatch):
    run_mock = AsyncMock(return_value="ignored")
    monkeypatch.setattr(AutoDeriveAgent, "run", run_mock)

    out = await AutoDerivedResolver.apply([], resolved_values=[])

    run_mock.assert_not_called()
    assert out == []


@pytest.mark.unit
async def test_apply_resolves_chain_in_topological_order(monkeypatch):
    """Chain `A (resolved) → B (auto from A) → C (auto from B)`. First pass
    resolves B (parent A is in resolved_values). Second pass resolves C
    (parent B was just added by the first pass)."""
    call_log: list[tuple[str, str]] = []

    async def fake_run(parent_variable, parent_value, derived_marker, derived_context):
        call_log.append((parent_variable, parent_value))
        # B's job: parent_value is the row text → return "4"
        # C's job: parent_value is "4" → return "4" (same value, different context)
        return "4"

    monkeypatch.setattr(AutoDeriveAgent, "run", fake_run)

    fields = [
        _auto_derived_field(
            property_name="claim_number",
            parent="proof_of_claim_row",
            marker="4",
        ),
        _auto_derived_field(
            property_name="claim_number_title",
            parent="claim_number",
            marker="4",
        ),
    ]
    resolved = [
        make_resolved_value(
            property_name="proof_of_claim_row",
            value="4 - Bank of America - $3,000",
        ),
    ]

    out = await AutoDerivedResolver.apply(fields, resolved_values=resolved)

    by_name = {rv.property_name: rv for rv in out}
    assert "claim_number" in by_name
    assert "claim_number_title" in by_name
    assert by_name["claim_number"].value == "4"
    assert by_name["claim_number_title"].value == "4"

    # First pass dispatched B (parent='proof_of_claim_row'), second pass dispatched C (parent='claim_number').
    assert call_log[0] == ("proof_of_claim_row", "4 - Bank of America - $3,000")
    assert call_log[1] == ("claim_number", "4")


@pytest.mark.unit
async def test_apply_skips_chain_when_root_unresolved(monkeypatch):
    """Root parent absent from resolved_values → both children stay
    unresolved (no exception, just a warning logged)."""
    run_mock = AsyncMock(return_value="should-not-fire")
    monkeypatch.setattr(AutoDeriveAgent, "run", run_mock)

    fields = [
        _auto_derived_field(property_name="middle", parent="missing_root"),
        _auto_derived_field(property_name="leaf", parent="middle"),
    ]

    out = await AutoDerivedResolver.apply(fields, resolved_values=[])

    assert out == []
    run_mock.assert_not_called()


# ─── PLURALIZE_BY_COUNT rule_effect ───────────────────────────────────


from src.core.agents.types.sources import AutoDerivedRuleEffect


def _pluralize_field(
    property_name: str,
    parent: str,
    singular_value: str,
    plural_value: str,
) -> TemplateField:
    return TemplateField(
        property_name=property_name,
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(
            dependent_variable=parent,
            rule_effect=AutoDerivedRuleEffect.PLURALIZE_BY_COUNT,
            singular_value=singular_value,
            plural_value=plural_value,
        ),
        template_variable_string=f"[[{property_name}]]",
    )


@pytest.mark.unit
@pytest.mark.parametrize("parent_value, expected", [
    ("Aidvantage on behalf of Dept of Education", "has"),                # 1 item, no " and "
    ("Bank of America and JPMorgan Chase", "have"),                      # 2 items, " and "
    ("Bank of America, JPMorgan Chase, and Wells Fargo", "have"),        # 3+ items, ", and "
    ("Acme, Inc., on behalf of Beta", "has"),                            # 1 item with commas inside the name
    ("A and ", "has"),                                                   # malformed trailing " and " — single item
    (" and B", "has"),                                                   # malformed leading " and " — single item
])
async def test_apply_pluralize_picks_singular_or_plural_by_oxford_signal(monkeypatch, parent_value, expected):
    """Plurality detection: ', and ' OR ' and ' between non-empty fragments → plural."""
    run_mock = AsyncMock(return_value="should-not-fire")
    monkeypatch.setattr(AutoDeriveAgent, "run", run_mock)

    field = _pluralize_field(
        property_name="creditor_has_have",
        parent="creditor_names",
        singular_value="has",
        plural_value="have",
    )
    resolved = [make_resolved_value(property_name="creditor_names", value=parent_value)]

    out = await AutoDerivedResolver.apply([field], resolved_values=resolved)

    assert len(out) == 1
    assert out[0].property_name == "creditor_has_have"
    assert out[0].value == expected
    assert out[0].confidence == "high"
    run_mock.assert_not_called()  # deterministic path skips the LLM


@pytest.mark.unit
async def test_apply_pluralize_emits_empty_singular_for_s_suffix(monkeypatch):
    """The `s` suffix in `Creditor{s}` uses singular_value="" (empty);
    resolver must still emit a ResolvedTemplateValue so the docx fills
    the placeholder with "" rather than leaving the literal token."""
    run_mock = AsyncMock(return_value="should-not-fire")
    monkeypatch.setattr(AutoDeriveAgent, "run", run_mock)

    field = _pluralize_field(
        property_name="creditor_plural_suffix",
        parent="creditor_names",
        singular_value="",
        plural_value="s",
    )
    resolved = [make_resolved_value(property_name="creditor_names", value="Aidvantage")]

    out = await AutoDerivedResolver.apply([field], resolved_values=resolved)

    assert len(out) == 1
    assert out[0].property_name == "creditor_plural_suffix"
    assert out[0].value == ""
    run_mock.assert_not_called()


@pytest.mark.unit
async def test_apply_pluralize_skips_when_parent_unresolved(monkeypatch):
    """Same skip behavior as extract_substring path: parent missing → no value emitted."""
    run_mock = AsyncMock()
    monkeypatch.setattr(AutoDeriveAgent, "run", run_mock)

    field = _pluralize_field(
        property_name="creditor_has_have",
        parent="creditor_names",
        singular_value="has",
        plural_value="have",
    )

    out = await AutoDerivedResolver.apply([field], resolved_values=[])

    assert out == []
    run_mock.assert_not_called()


@pytest.mark.unit
async def test_apply_mixed_batch_dispatches_substring_to_llm_pluralize_inline(monkeypatch):
    """When a parent has BOTH an extract_substring child AND a pluralize_by_count
    child, the resolver must dispatch only the substring to the LLM and resolve
    the pluralize one in-line."""
    run_mock = AsyncMock(return_value="Aidvantage")
    monkeypatch.setattr(AutoDeriveAgent, "run", run_mock)

    substring_child = _auto_derived_field(
        property_name="creditor_names_conform",
        parent="creditor_names",
        marker="Aidvantage",
        context="alterations made by Aidvantage",
    )
    pluralize_child = _pluralize_field(
        property_name="creditor_has_have",
        parent="creditor_names",
        singular_value="has",
        plural_value="have",
    )
    resolved = [
        make_resolved_value(
            property_name="creditor_names",
            value="Aidvantage on behalf of Dept of Education (POC 5)",
        ),
    ]

    out = await AutoDerivedResolver.apply(
        [substring_child, pluralize_child], resolved_values=resolved,
    )

    by_name = {rv.property_name: rv for rv in out}
    assert by_name["creditor_names_conform"].value == "Aidvantage"  # from LLM mock
    assert by_name["creditor_has_have"].value == "has"              # from inline pluralize

    # LLM called once for the substring child only.
    assert run_mock.await_count == 1
    call_kwargs = run_mock.await_args.kwargs
    assert call_kwargs["parent_variable"] == "creditor_names"


# ─── only_root_stages filter ──────────────────────────────────────────


from src.core.agents.types.resolution import ResolverStage  # noqa: E402
from src.core.agents.types.sources import (  # noqa: E402
    CaseVectorSourceParams,
    DropdownEmailSourceParams,
)


def _case_vector_parent(property_name: str) -> TemplateField:
    return TemplateField(
        property_name=property_name,
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="any"),
        template_variable_string=None,
    )


def _dropdown_parent(property_name: str) -> TemplateField:
    return TemplateField(
        property_name=property_name,
        source=FieldSource.DROPDOWN_FROM_GMAIL,
        source_params=DropdownEmailSourceParams(
            label="x", example_format="x", subject_query="x"
        ),
        template_variable_string=None,
    )


@pytest.mark.unit
async def test_apply_only_root_stages_resolves_llm_draft_parented_children(monkeypatch):
    """Early-pass invocation with only_root_stages={LLM_DRAFT, SYSTEM_GENERATED}
    must resolve children of case_vector roots and SKIP children of USER_INPUT roots."""
    monkeypatch.setattr(AutoDeriveAgent, "run", AsyncMock(return_value="2018 Toyota Camry"))

    llm_root = _case_vector_parent("vehicle_record_cv")
    llm_child = _auto_derived_field(
        property_name="vehicle_name_cv",
        parent="vehicle_record_cv",
        marker="2018 Toyota Camry",
    )
    user_root = _dropdown_parent("vehicle_record_dd")
    user_child = _auto_derived_field(
        property_name="vehicle_name_dd",
        parent="vehicle_record_dd",
        marker="2018 Toyota Camry",
    )
    # Parent resolved by the LLM_DRAFT pass:
    resolved = [
        make_resolved_value(property_name="vehicle_record_cv", value="2018 Toyota Camry · VIN · 82,300 mi"),
    ]

    out = await AutoDerivedResolver.apply(
        [llm_root, llm_child, user_root, user_child],
        resolved_values=resolved,
        only_root_stages=frozenset({ResolverStage.LLM_DRAFT, ResolverStage.SYSTEM_GENERATED}),
    )

    names = {rv.property_name for rv in out}
    assert "vehicle_name_cv" in names
    assert "vehicle_name_dd" not in names


@pytest.mark.unit
async def test_apply_is_idempotent_on_already_resolved_children(monkeypatch):
    """When a child is already in resolved_values, the late call (no filter)
    must skip it. Same body that the finalizer's late call sees after the
    early pass already populated some children."""
    run_mock = AsyncMock(return_value="should-not-be-called")
    monkeypatch.setattr(AutoDeriveAgent, "run", run_mock)

    parent = _case_vector_parent("vehicle_record")
    child = _auto_derived_field(
        property_name="vehicle_name",
        parent="vehicle_record",
        marker="2018 Toyota Camry",
    )
    resolved = [
        make_resolved_value(property_name="vehicle_record", value="row text"),
        make_resolved_value(property_name="vehicle_name", value="already-resolved"),
    ]
    out = await AutoDerivedResolver.apply([parent, child], resolved_values=resolved)

    # No re-derivation: existing value stays as-is, no LLM call fires.
    assert out == []
    assert run_mock.await_count == 0
