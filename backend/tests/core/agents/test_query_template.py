"""Tests for the `{{var}}` query-template substitution helpers."""

import pytest

from src.core.agents.utils.query_template import (
    classify_wave,
    extract_var_refs,
    extract_var_refs_from_source_params,
    substitute,
    substitute_source_params,
)
from src.core.agents.types.resolution import ResolverStage
from src.core.agents.types.sources import (
    AutoDerivedSourceParams,
    CaseVectorQueryEntry,
    CaseVectorSourceParams,
    DropdownEmailSourceParams,
    FieldSource,
    GmailSourceParams,
    RecoChipsFromDependentVariablesSourceParams,
)
from src.core.agents.types.spec import TemplateField
from tests.core.factories import make_resolved_value


@pytest.mark.unit
def test_extract_var_refs_handles_empty_input():
    assert extract_var_refs(None) == set()
    assert extract_var_refs("") == set()
    assert extract_var_refs("plain text with no refs") == set()


@pytest.mark.unit
def test_extract_var_refs_finds_single_reference():
    assert extract_var_refs("Order Dismissing {{prior_case_number}}") == {"prior_case_number"}


@pytest.mark.unit
def test_extract_var_refs_dedupes_repeated_references():
    assert extract_var_refs("{{a}} and {{a}} and {{b}}") == {"a", "b"}


@pytest.mark.unit
def test_extract_var_refs_ignores_invalid_identifiers():
    # Numeric leads, dashes, dots are NOT snake_case identifiers.
    assert extract_var_refs("{{1abc}} {{a-b}} {{a.b}}") == set()


@pytest.mark.unit
def test_substitute_replaces_known_refs():
    resolved = {"prior_case_number": make_resolved_value("prior_case_number", "25-19062")}
    assert substitute("{{prior_case_number}}", resolved) == "25-19062"
    assert (
        substitute("Order Dismissing {{prior_case_number}}", resolved)
        == "Order Dismissing 25-19062"
    )


@pytest.mark.unit
def test_substitute_drops_unresolved_refs():
    resolved = {"x": make_resolved_value("x", "found")}
    assert substitute("{{x}} and {{y}}", resolved) == "found and "


@pytest.mark.unit
def test_substitute_passes_through_when_no_refs():
    assert substitute("Notice of Filing", {}) == "Notice of Filing"
    assert substitute(None, {}) is None
    assert substitute("", {}) == ""


@pytest.mark.unit
def test_extract_var_refs_from_source_params_walks_query_fields():
    params = GmailSourceParams(
        subject_query="{{a}} dismissed",
        body_query="related to {{b}}",
    )
    assert extract_var_refs_from_source_params(params) == {"a", "b"}


@pytest.mark.unit
def test_extract_var_refs_from_source_params_handles_none():
    assert extract_var_refs_from_source_params(None) == set()


@pytest.mark.unit
def test_substitute_source_params_clones_only_referenced_fields():
    params = GmailSourceParams(
        subject_query="Order Dismissing",
        body_query="case {{prior_case_number}}",
        scope_to_current_case=False,
    )
    resolved = {"prior_case_number": make_resolved_value("prior_case_number", "25-19062")}

    new_params = substitute_source_params(params, resolved)
    assert new_params is not params
    assert new_params.subject_query == "Order Dismissing"
    assert new_params.body_query == "case 25-19062"
    # Other fields preserved.
    assert new_params.scope_to_current_case is False


@pytest.mark.unit
def test_substitute_source_params_returns_original_when_no_refs():
    params = GmailSourceParams(subject_query="Order Dismissing", body_query="case 25-19062")
    new_params = substitute_source_params(params, {})
    assert new_params is params


@pytest.mark.unit
def test_substitute_source_params_handles_text_query_field():
    params = CaseVectorSourceParams(text_query="Schedule I {{prior_case_number}}")
    resolved = {"prior_case_number": make_resolved_value("prior_case_number", "25-19062")}
    new_params = substitute_source_params(params, resolved)
    assert new_params.text_query == "Schedule I 25-19062"


@pytest.mark.unit
def test_extract_var_refs_walks_case_vector_queries_text_query():
    """Refs inside a chip-from-deps source's case_vector_queries entries
    must show up in the validator's edge graph + reference checks."""
    params = RecoChipsFromDependentVariablesSourceParams(
        label="Change in circumstances",
        example_sentence="...",
        dependent_variables=["trustee_reason"],
        case_vector_queries=[
            CaseVectorQueryEntry(label="Current Schedule I & J",
                                 text_query="Schedule I income {{current_case_number}}"),
            CaseVectorQueryEntry(label="Prior Schedule",
                                 text_query="Schedule I {{prior_case_number}}"),
            CaseVectorQueryEntry(label="No refs",
                                 text_query="just plain text"),
        ],
    )
    refs = extract_var_refs_from_source_params(params)
    assert refs == {"current_case_number", "prior_case_number"}


@pytest.mark.unit
def test_substitute_source_params_works_for_dropdown_email():
    params = DropdownEmailSourceParams(
        subject_query="Order {{prior_case_number}}",
        body_query=None,
        label="Pick a row",
        example_format="...",
        scope_to_current_case=False,
    )
    resolved = {"prior_case_number": make_resolved_value("prior_case_number", "X")}
    new_params = substitute_source_params(params, resolved)
    assert new_params.subject_query == "Order X"


# ─── classify_wave ─────────────────────────────────────────────────────


def _by_name(*fields: TemplateField) -> dict[str, TemplateField]:
    return {f.property_name: f for f in fields}


@pytest.mark.unit
def test_classify_wave_wave_a_no_refs():
    """LLM_DRAFT field with no {{var}} refs in queries is wave A."""
    f = TemplateField(
        property_name="case_no",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="just text, no refs"),
    )
    assert classify_wave(f, _by_name(f)) == "A"


@pytest.mark.unit
def test_classify_wave_wave_a_llm_draft_rooted_ref():
    """LLM_DRAFT field whose refs all target LLM_DRAFT-rooted vars is wave A."""
    parent = TemplateField(
        property_name="vehicle_record",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="vehicle row"),
    )
    child = TemplateField(
        property_name="car_model",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
    )
    referencer = TemplateField(
        property_name="creditor_name",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="lien for {{car_model}}"),
    )
    assert classify_wave(referencer, _by_name(parent, child, referencer)) == "A"


@pytest.mark.unit
def test_classify_wave_wave_b_user_input_rooted_ref():
    """LLM_DRAFT field whose ref targets a USER_INPUT-rooted var is wave B."""
    parent = TemplateField(
        property_name="vehicle_record",
        source=FieldSource.DROPDOWN_FROM_GMAIL,
        source_params=DropdownEmailSourceParams(
            label="Pick a vehicle", example_format="...", subject_query="vehicle",
        ),
    )
    child = TemplateField(
        property_name="car_model",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
    )
    referencer = TemplateField(
        property_name="creditor_name",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="lien for {{car_model}}"),
    )
    assert classify_wave(referencer, _by_name(parent, child, referencer)) == "B"


@pytest.mark.unit
def test_classify_wave_wave_b_mixed_llm_and_user_input_refs():
    """If ANY ref reaches a USER_INPUT root, the field is wave B."""
    llm_parent = TemplateField(
        property_name="debtor",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="debtor"),
    )
    user_parent = TemplateField(
        property_name="vehicle_record",
        source=FieldSource.DROPDOWN_FROM_GMAIL,
        source_params=DropdownEmailSourceParams(
            label="x", example_format="x", subject_query="vehicle",
        ),
    )
    user_child = TemplateField(
        property_name="car_model",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
    )
    referencer = TemplateField(
        property_name="creditor_name",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(
            text_query="{{debtor}} lien for {{car_model}}"
        ),
    )
    assert classify_wave(referencer, _by_name(llm_parent, user_parent, user_child, referencer)) == "B"


@pytest.mark.unit
def test_classify_wave_returns_none_for_non_llm_draft_field():
    """Wave classification only applies to LLM_DRAFT-stage fields."""
    f = TemplateField(
        property_name="row",
        source=FieldSource.DROPDOWN_FROM_GMAIL,
        source_params=DropdownEmailSourceParams(
            label="x", example_format="x", subject_query="q",
        ),
    )
    assert classify_wave(f, _by_name(f)) is None


@pytest.mark.unit
def test_classify_wave_skips_unknown_refs():
    """An unknown ref (validator should have caught this) doesn't crash;
    the classifier silently skips it. If no other refs hit USER_INPUT,
    the field stays wave A."""
    f = TemplateField(
        property_name="creditor_name",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="for {{ghost_variable}}"),
    )
    assert classify_wave(f, _by_name(f)) == "A"
