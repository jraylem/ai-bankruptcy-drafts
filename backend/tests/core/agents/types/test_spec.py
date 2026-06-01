"""Tests for TemplateField.stage — the _STAGE_BY_SOURCE dispatch.

Every FieldSource value must map to a stable ResolverStage. The pipeline
relies on this derivation in dozens of filter conditions.
"""

import pytest

from src.core.agents.types.resolution import ResolverStage
from src.core.agents.types.sources import FieldSource
from tests.core.factories import make_template_field


@pytest.mark.unit
@pytest.mark.parametrize(
    "source, expected_stage",
    [
        (FieldSource.GMAIL, ResolverStage.LLM_DRAFT),
        (FieldSource.COURT_DRIVE, ResolverStage.LLM_DRAFT),
        (FieldSource.CASE_VECTOR, ResolverStage.LLM_DRAFT),
        (FieldSource.LAW_PRACTICE_VECTOR, ResolverStage.LLM_DRAFT),
        (FieldSource.CONSTANTS, ResolverStage.LLM_DRAFT),
        (FieldSource.SYSTEM_GENERATED, ResolverStage.SYSTEM_GENERATED),
        (FieldSource.DEPENDENT_ON_VARIABLE, ResolverStage.DERIVATIVE),
        (FieldSource.GROUP_DROPDOWN_FROM_GMAIL, ResolverStage.USER_INPUT),
        (FieldSource.GROUP_DROPDOWN_FROM_COURT_DRIVE, ResolverStage.USER_INPUT),
        (FieldSource.DROPDOWN_FROM_CONSTANTS, ResolverStage.USER_INPUT),
    ],
)
def test_template_field_stage_derives_from_source(source, expected_stage):
    field = make_template_field(source=source)
    assert field.stage == expected_stage


@pytest.mark.unit
def test_template_field_stage_covers_every_field_source():
    """Safety: if a new FieldSource is added, this test fails until the
    parametrize list above is extended — catches missing enum → stage wiring."""
    # Build one field per FieldSource value and confirm .stage resolves without KeyError
    for source in FieldSource:
        field = make_template_field(source=source)
        stage = field.stage  # KeyError if _STAGE_BY_SOURCE lacks this value
        assert isinstance(stage, ResolverStage)


# ─── kind computed field ──────────────────────────────────────────────


from src.core.agents.types.spec import TemplateField, TemplateVariable  # noqa: E402


@pytest.mark.unit
def test_template_variable_kind_is_physical_when_placeholder_set():
    var = TemplateVariable(
        template_variable="claim_number",
        template_index=0,
        template_property_marker="4",
        template_variable_string="[[claim_number]]",
    )
    assert var.kind == "physical"
    assert var.model_dump()["kind"] == "physical"


@pytest.mark.unit
def test_template_variable_kind_is_virtual_when_placeholder_none():
    var = TemplateVariable(
        template_variable="proof_of_claim_row",
        template_index=0,
        template_property_marker="4 - Bank of America - $3,000",
        template_variable_string=None,
    )
    assert var.kind == "virtual"
    assert var.model_dump()["kind"] == "virtual"


@pytest.mark.unit
def test_template_field_kind_mirrors_variable():
    physical = TemplateField(
        property_name="claim_number",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        template_variable_string="[[claim_number]]",
    )
    virtual = TemplateField(
        property_name="proof_of_claim_row",
        source=FieldSource.DROPDOWN_FROM_GMAIL,
        template_variable_string=None,
    )
    assert physical.kind == "physical"
    assert virtual.kind == "virtual"


# ─── root_parent_stage helper ─────────────────────────────────────────


from src.core.agents.types.spec import (  # noqa: E402
    root_parent_is_unbound,
    root_parent_stage,
    TemplateVariable,
)
from src.core.agents.types.sources import (  # noqa: E402
    AutoDerivedSourceParams,
    CaseVectorSourceParams,
    DropdownEmailSourceParams,
)


def _by_name(*fields: TemplateField) -> dict[str, TemplateField]:
    return {f.property_name: f for f in fields}


@pytest.mark.unit
def test_root_parent_stage_returns_direct_stage_for_non_auto_derived():
    """Non-auto_derived fields short-circuit to their own stage."""
    f = TemplateField(
        property_name="case_no",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="case number"),
    )
    assert root_parent_stage(f, _by_name(f)) == ResolverStage.LLM_DRAFT


@pytest.mark.unit
def test_root_parent_stage_walks_single_hop_to_llm_draft_root():
    """A virtual parent bound to case_vector → child is effectively LLM_DRAFT."""
    parent = TemplateField(
        property_name="vehicle_record",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="vehicle"),
    )
    child = TemplateField(
        property_name="vehicle_name",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
    )
    assert root_parent_stage(child, _by_name(parent, child)) == ResolverStage.LLM_DRAFT


@pytest.mark.unit
def test_root_parent_stage_returns_user_input_for_dropdown_root():
    """Auto_derived child of a USER_INPUT parent stays USER_INPUT effective stage."""
    parent = TemplateField(
        property_name="vehicle_record",
        source=FieldSource.DROPDOWN_FROM_GMAIL,
        source_params=DropdownEmailSourceParams(
            label="Pick the vehicle", example_format="...", subject_query="vehicle"
        ),
    )
    child = TemplateField(
        property_name="vehicle_name",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
    )
    assert root_parent_stage(child, _by_name(parent, child)) == ResolverStage.USER_INPUT


@pytest.mark.unit
def test_root_parent_stage_handles_chain_depth_two():
    """auto_derived → auto_derived → case_vector resolves through to LLM_DRAFT."""
    root = TemplateField(
        property_name="vehicle_record",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="vehicle"),
    )
    mid = TemplateField(
        property_name="vehicle_name",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
    )
    leaf = TemplateField(
        property_name="vehicle_name_truncated",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_name"),
    )
    assert root_parent_stage(leaf, _by_name(root, mid, leaf)) == ResolverStage.LLM_DRAFT


@pytest.mark.unit
def test_root_parent_stage_returns_none_on_cycle():
    """A cycle in the chain must not infinite-loop; helper returns None."""
    a = TemplateField(
        property_name="a",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="b"),
    )
    b = TemplateField(
        property_name="b",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="a"),
    )
    assert root_parent_stage(a, _by_name(a, b)) is None


@pytest.mark.unit
def test_root_parent_stage_returns_none_when_parent_missing():
    """Reference to a non-existent parent returns None — chain is broken."""
    orphan = TemplateField(
        property_name="orphan",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="ghost"),
    )
    assert root_parent_stage(orphan, _by_name(orphan)) is None


# ─── root_parent_is_unbound helper ────────────────────────────────────


def _by_var_name(*vars: TemplateVariable) -> dict[str, TemplateVariable]:
    return {v.template_variable: v for v in vars}


@pytest.mark.unit
def test_root_parent_is_unbound_true_when_root_has_no_source():
    """Author created a virtual parent without binding a source. Child
    is auto_derived. Helper distinguishes this from the broken-chain
    cases below."""
    parent = TemplateVariable(
        template_variable="vehicle_record",
        template_index=0,
        source=None,
    )
    child = TemplateVariable(
        template_variable="car_model",
        template_index=1,
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
    )
    assert root_parent_is_unbound(child, _by_var_name(parent, child)) is True


@pytest.mark.unit
def test_root_parent_is_unbound_true_for_unbound_non_auto_derived_input():
    """The trivial case — passing in an unbound variable directly (not
    via the chain). The helper short-circuits and returns True."""
    var = TemplateVariable(
        template_variable="creditor_name",
        template_index=0,
        source=None,
    )
    assert root_parent_is_unbound(var, _by_var_name(var)) is True


@pytest.mark.unit
def test_root_parent_is_unbound_false_for_bound_llm_draft_root():
    """Root parent has a real LLM_DRAFT source — not unbound."""
    parent = TemplateField(
        property_name="vehicle_record",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="vehicle"),
    )
    child = TemplateField(
        property_name="car_model",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
    )
    assert root_parent_is_unbound(child, _by_name(parent, child)) is False


@pytest.mark.unit
def test_root_parent_is_unbound_false_for_bound_user_input_root():
    """Root parent has a real USER_INPUT source (Path B case) — not unbound."""
    parent = TemplateField(
        property_name="vehicle_record",
        source=FieldSource.DROPDOWN_FROM_GMAIL,
        source_params=DropdownEmailSourceParams(
            label="Pick the vehicle", example_format="...", subject_query="vehicle"
        ),
    )
    child = TemplateField(
        property_name="car_model",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
    )
    assert root_parent_is_unbound(child, _by_name(parent, child)) is False


@pytest.mark.unit
def test_root_parent_is_unbound_false_on_cycle():
    """A cycle is a broken chain — NOT unbound. Helper must distinguish
    these two None-returning cases of root_parent_stage."""
    a = TemplateVariable(
        template_variable="a",
        template_index=0,
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="b"),
    )
    b = TemplateVariable(
        template_variable="b",
        template_index=1,
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="a"),
    )
    assert root_parent_is_unbound(a, _by_var_name(a, b)) is False


@pytest.mark.unit
def test_root_parent_is_unbound_false_when_parent_missing():
    """Missing parent in by_name is a broken chain — NOT unbound."""
    orphan = TemplateVariable(
        template_variable="orphan",
        template_index=0,
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="ghost"),
    )
    assert root_parent_is_unbound(orphan, _by_var_name(orphan)) is False


@pytest.mark.unit
def test_root_parent_is_unbound_false_for_non_auto_derived_with_source():
    """Plain bound non-auto_derived input — not unbound."""
    f = TemplateField(
        property_name="case_no",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="case number"),
    )
    assert root_parent_is_unbound(f, _by_name(f)) is False
