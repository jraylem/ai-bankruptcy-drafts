"""Tests for InheritFromParentResolver.

Two operating modes:

  - **No parent_context** (Phase 1B / standalone child dry-run): each
    `inherit_from_parent` field resolves to its `fallback_value` (or a
    `[parent.slot.<name>]` placeholder marker). No LLM, no IO.

  - **With parent_context** (Phase 2 bundling run): each slot dispatches
    on its slot_configuration: `parent_variable` reads from the parent's
    resolved values, `literal` returns the hardcoded string, and
    `extract_from_draft` runs ExtractFromDraftAgent against the parent's
    produced draft text.
"""

from unittest.mock import AsyncMock

import pytest

from src.core.agents.resolvers import inherit_from_parent_resolver as resolver_module
from src.core.agents.resolvers.inherit_from_parent_resolver import (
    InheritFromParentResolver,
)
from src.core.agents.types.bundling import (
    ExtractFromDraftSlotConfig,
    LiteralSlotConfig,
    ParentBundleContext,
    ParentVariableSlotConfig,
)
from src.core.agents.types.sources import (
    FieldSource,
    InheritFromParentSourceParams,
)
from tests.core.factories import (
    make_gmail_source_params,
    make_template_field,
)


@pytest.mark.unit
async def test_apply_returns_empty_when_no_inherit_fields():
    field = make_template_field(
        source=FieldSource.GMAIL,
        source_params=make_gmail_source_params(),
    )
    assert await InheritFromParentResolver.apply([field]) == []


@pytest.mark.unit
async def test_apply_uses_fallback_value_when_set():
    field = make_template_field(
        property_name="docket_title",
        source=FieldSource.INHERIT_FROM_PARENT,
        source_params=InheritFromParentSourceParams(fallback_value="[no parent]"),
    )

    result = await InheritFromParentResolver.apply([field])

    assert len(result) == 1
    rv = result[0]
    assert rv.property_name == "docket_title"
    assert rv.value == "[no parent]"
    assert rv.confidence == "high"
    assert "no parent context" in rv.reasoning.lower()


@pytest.mark.unit
async def test_apply_emits_empty_value_when_no_fallback_and_no_parent():
    """When the author hasn't set a fallback_value and there's no parent
    context, the resolver returns an empty low-confidence value so the
    finalizer leaves the original `[[placeholder]]` marker untouched in
    the rendered docx — visually obvious to the author that the slot is
    unfilled. Better than injecting an ugly `[parent.slot.X]` literal
    into the body text."""
    field = make_template_field(
        property_name="case_number",
        source=FieldSource.INHERIT_FROM_PARENT,
        source_params=InheritFromParentSourceParams(),
    )

    result = await InheritFromParentResolver.apply([field])

    assert len(result) == 1
    assert result[0].value == ""
    assert result[0].confidence == "low"
    assert "no fallback_value" in result[0].reasoning.lower()


@pytest.mark.unit
async def test_apply_resolves_only_inherit_from_parent_fields():
    inherit_field = make_template_field(
        property_name="case_number",
        source=FieldSource.INHERIT_FROM_PARENT,
        source_params=InheritFromParentSourceParams(fallback_value="A"),
    )
    other_field = make_template_field(
        property_name="trustee_name",
        source=FieldSource.GMAIL,
        source_params=make_gmail_source_params(),
    )

    result = await InheritFromParentResolver.apply([inherit_field, other_field])

    assert {rv.property_name for rv in result} == {"case_number"}


@pytest.mark.unit
async def test_apply_low_confidence_when_source_params_mismatch():
    # Hand-crafted scenario: source is INHERIT_FROM_PARENT but params is
    # a non-matching shape (None). Resolver guards and emits low-confidence
    # rather than crashing.
    field = make_template_field(
        property_name="case_number",
        source=FieldSource.INHERIT_FROM_PARENT,
        source_params=None,
    )

    result = await InheritFromParentResolver.apply([field])

    assert len(result) == 1
    assert result[0].confidence == "low"
    assert "inheritfromparentsourceparams" in result[0].reasoning.lower()


# ─── Phase 2: with parent_context ──────────────────────────────────────


@pytest.mark.unit
async def test_apply_with_parent_variable_slot_pulls_from_resolved_values():
    field = make_template_field(
        property_name="case_number",
        source=FieldSource.INHERIT_FROM_PARENT,
        source_params=InheritFromParentSourceParams(),
    )
    parent_ctx = ParentBundleContext(
        resolved_values={"case_number": "25-14980-PDR"},
        slot_configurations={
            "case_number": ParentVariableSlotConfig(parent_variable="case_number"),
        },
    )

    result = await InheritFromParentResolver.apply([field], parent_context=parent_ctx)

    assert len(result) == 1
    assert result[0].value == "25-14980-PDR"
    assert result[0].confidence == "high"
    assert "parent variable 'case_number'" in result[0].reasoning


@pytest.mark.unit
async def test_apply_with_literal_slot_returns_hardcoded_value():
    field = make_template_field(
        property_name="court_division",
        source=FieldSource.INHERIT_FROM_PARENT,
        source_params=InheritFromParentSourceParams(),
    )
    parent_ctx = ParentBundleContext(
        slot_configurations={
            "court_division": LiteralSlotConfig(literal_value="Fort Lauderdale"),
        },
    )

    result = await InheritFromParentResolver.apply([field], parent_context=parent_ctx)

    assert len(result) == 1
    assert result[0].value == "Fort Lauderdale"
    assert result[0].confidence == "high"


@pytest.mark.unit
async def test_apply_with_extract_from_draft_calls_agent(monkeypatch):
    field = make_template_field(
        property_name="docket_title",
        source=FieldSource.INHERIT_FROM_PARENT,
        source_params=InheritFromParentSourceParams(),
    )
    parent_ctx = ParentBundleContext(
        draft_text="In re: Motion to Modify Plan...",
        slot_configurations={
            "docket_title": ExtractFromDraftSlotConfig(
                extract_instruction="Extract the filed motion title.",
            ),
        },
    )
    extract_mock = AsyncMock(return_value="Motion to Modify Plan")
    monkeypatch.setattr(resolver_module.ExtractFromDraftAgent, "run", extract_mock)

    result = await InheritFromParentResolver.apply([field], parent_context=parent_ctx)

    extract_mock.assert_awaited_once()
    assert result[0].value == "Motion to Modify Plan"
    assert result[0].confidence == "high"


@pytest.mark.unit
async def test_apply_with_extract_from_draft_low_confidence_on_empty(monkeypatch):
    field = make_template_field(
        property_name="docket_title",
        source=FieldSource.INHERIT_FROM_PARENT,
        source_params=InheritFromParentSourceParams(),
    )
    parent_ctx = ParentBundleContext(
        draft_text="...",
        slot_configurations={
            "docket_title": ExtractFromDraftSlotConfig(extract_instruction="x"),
        },
    )
    monkeypatch.setattr(
        resolver_module.ExtractFromDraftAgent,
        "run",
        AsyncMock(return_value=""),
    )

    result = await InheritFromParentResolver.apply([field], parent_context=parent_ctx)

    assert result[0].confidence == "low"
    assert "extractfromdraftagent returned empty" in result[0].reasoning.lower()


@pytest.mark.unit
async def test_apply_with_parent_context_falls_back_when_slot_not_configured():
    field = make_template_field(
        property_name="case_number",
        source=FieldSource.INHERIT_FROM_PARENT,
        source_params=InheritFromParentSourceParams(fallback_value="FALLBACK"),
    )
    parent_ctx = ParentBundleContext()  # empty slot_configurations

    result = await InheritFromParentResolver.apply([field], parent_context=parent_ctx)

    assert result[0].value == "FALLBACK"
    assert result[0].confidence == "high"
