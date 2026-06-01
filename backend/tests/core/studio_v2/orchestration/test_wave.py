"""Tests for wave classification (classify_wave_v2 +
root_parent_stage_v2 + stage_of_v2)."""

import pytest

from src.core.studio_v2.orchestration.wave import (
    classify_wave_v2,
    root_parent_stage_v2,
    stage_of_v2,
)
from src.core.studio_v2.types.fields import TemplateFieldV2
from src.core.studio_v2.types.wizard_sources import (
    AuthorInputKind,
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


_FIELD_UUID = "00000000-0000-0000-0000-000000000001"
_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000002"


def _field(name, params):
    return TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable=name, template_index=0, params=params,
    )


def _params(**kwargs):
    """Default-source helper — caller overrides what they care about."""
    defaults = {"source": SourceKind.GMAIL, "presentation_shape": PresentationShape.RAW}
    defaults.update(kwargs)
    return WizardSourceParams(**defaults)


# ─── stage_of_v2 ─────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "params,expected_stage",
    [
        (_params(source=SourceKind.AUTHOR_INPUT,
                 author_input_kind=AuthorInputKind.PLAIN_TEXT), "USER_INPUT"),
        (_params(source=SourceKind.GMAIL,
                 presentation_shape=PresentationShape.RAW), "LLM_DRAFT"),
        (_params(source=SourceKind.GMAIL,
                 presentation_shape=PresentationShape.DROPDOWN), "USER_INPUT"),
        (_params(source=SourceKind.CASE_FILE,
                 presentation_shape=PresentationShape.RAW), "LLM_DRAFT"),
        (_params(source=SourceKind.CASE_FILE,
                 presentation_shape=PresentationShape.MULTI_SELECT), "USER_INPUT"),
        (_params(source=SourceKind.ATTORNEY,
                 presentation_shape=PresentationShape.RAW), "SYSTEM"),
        (_params(source=SourceKind.ATTORNEY,
                 presentation_shape=PresentationShape.DROPDOWN), "USER_INPUT"),
        (_params(source=SourceKind.CURRENT_DATE), "SYSTEM"),
        (_params(source=SourceKind.CONSTANTS), "SYSTEM"),
        (_params(source=SourceKind.VALUE_FROM_PARENT_BUNDLE), "SYSTEM"),
        (_params(source=SourceKind.DERIVED_FROM_VARIABLE,
                 dependent_variable="x"), "DERIVED"),
    ],
)
def test_stage_of_v2(params, expected_stage):
    assert stage_of_v2(_field("x", params)) == expected_stage


@pytest.mark.unit
def test_stage_of_v2_no_params_is_unknown():
    field = TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable="x", params=None,
    )
    assert stage_of_v2(field) == "UNKNOWN"


# ─── root_parent_stage_v2 ────────────────────────────────────────────


@pytest.mark.unit
def test_root_parent_stage_chases_derive_chain():
    """parent (SYSTEM) ← child (DERIVED). Child's root is SYSTEM."""
    parent = _field("date", _params(source=SourceKind.CURRENT_DATE))
    child = _field(
        "deadline",
        _params(source=SourceKind.DERIVED_FROM_VARIABLE, dependent_variable="date"),
    )
    by_name = {"date": parent, "deadline": child}
    assert root_parent_stage_v2(child, by_name) == "SYSTEM"


@pytest.mark.unit
def test_root_parent_stage_multi_hop_chain():
    """root (USER_INPUT) ← derive ← derive — root is USER_INPUT."""
    root = _field(
        "creditor",
        _params(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.DROPDOWN,
        ),
    )
    mid = _field(
        "amount",
        _params(source=SourceKind.DERIVED_FROM_VARIABLE, dependent_variable="creditor"),
    )
    leaf = _field(
        "amount_formatted",
        _params(source=SourceKind.DERIVED_FROM_VARIABLE, dependent_variable="amount"),
    )
    by_name = {"creditor": root, "amount": mid, "amount_formatted": leaf}
    assert root_parent_stage_v2(leaf, by_name) == "USER_INPUT"


@pytest.mark.unit
def test_root_parent_stage_missing_parent_unknown():
    child = _field(
        "x",
        _params(source=SourceKind.DERIVED_FROM_VARIABLE, dependent_variable="missing"),
    )
    assert root_parent_stage_v2(child, {"x": child}) == "UNKNOWN"


@pytest.mark.unit
def test_root_parent_stage_cycle_safe():
    a = _field(
        "a",
        _params(source=SourceKind.DERIVED_FROM_VARIABLE, dependent_variable="b"),
    )
    b = _field(
        "b",
        _params(source=SourceKind.DERIVED_FROM_VARIABLE, dependent_variable="a"),
    )
    assert root_parent_stage_v2(a, {"a": a, "b": b}) == "UNKNOWN"


# ─── classify_wave_v2 ────────────────────────────────────────────────


@pytest.mark.unit
def test_wave_classification_returns_none_for_non_llm_draft():
    """Wave classification only applies to LLM_DRAFT fields."""
    field = _field("x", _params(source=SourceKind.CURRENT_DATE))
    assert classify_wave_v2(field, {"x": field}) is None

    field = _field(
        "y",
        _params(source=SourceKind.GMAIL, presentation_shape=PresentationShape.DROPDOWN),
    )
    assert classify_wave_v2(field, {"y": field}) is None


@pytest.mark.unit
def test_wave_a_when_no_deps():
    field = _field(
        "x",
        _params(source=SourceKind.GMAIL, presentation_shape=PresentationShape.RAW),
    )
    assert classify_wave_v2(field, {"x": field}) == "A"


@pytest.mark.unit
def test_wave_a_when_deps_root_to_system():
    """LLM_DRAFT field with query_dependencies that root to a SYSTEM
    field (current_date) → wave A."""
    sys_field = _field("doc_date", _params(source=SourceKind.CURRENT_DATE))
    llm_field = _field(
        "extracted",
        _params(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.RAW,
            query_dependencies=["doc_date"],
        ),
    )
    by_name = {"doc_date": sys_field, "extracted": llm_field}
    assert classify_wave_v2(llm_field, by_name) == "A"


@pytest.mark.unit
def test_wave_b_when_deps_root_to_user_input():
    """LLM_DRAFT field whose dep is a USER_INPUT field → wave B."""
    user_field = _field(
        "case_number",
        _params(
            source=SourceKind.AUTHOR_INPUT,
            author_input_kind=AuthorInputKind.PLAIN_TEXT,
        ),
    )
    llm_field = _field(
        "extracted",
        _params(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.RAW,
            query_dependencies=["case_number"],
        ),
    )
    by_name = {"case_number": user_field, "extracted": llm_field}
    assert classify_wave_v2(llm_field, by_name) == "B"


@pytest.mark.unit
def test_wave_b_when_deps_transitively_reach_user_input_via_derive():
    """user_input → derive → llm_draft dep — wave-B classification
    must chase through derive."""
    user_field = _field(
        "pick",
        _params(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.DROPDOWN,
        ),
    )
    derive_field = _field(
        "extracted_pick",
        _params(
            source=SourceKind.DERIVED_FROM_VARIABLE,
            dependent_variable="pick",
        ),
    )
    llm_field = _field(
        "needs_pick",
        _params(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.RAW,
            query_dependencies=["extracted_pick"],
        ),
    )
    by_name = {
        "pick": user_field, "extracted_pick": derive_field, "needs_pick": llm_field,
    }
    assert classify_wave_v2(llm_field, by_name) == "B"


@pytest.mark.unit
def test_wave_a_with_missing_dep_is_safe():
    """Dep that isn't in by_name shouldn't crash; defaults to A."""
    llm_field = _field(
        "x",
        _params(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.RAW,
            query_dependencies=["does_not_exist"],
        ),
    )
    assert classify_wave_v2(llm_field, {"x": llm_field}) == "A"
