"""Tests for WizardSourceParams serialization + enum coverage."""

import pytest

from src.core.studio_v2.types.wizard_sources import (
    AuthorInputKind,
    PresentationShape,
    SourceKind,
    WizardSourceParams,
    default_wizard_params,
)


@pytest.mark.unit
def test_default_wizard_params_matches_fe_mock():
    """defaultWizardParams() in FE mock starts on gmail / raw."""
    params = default_wizard_params()
    assert params.source == SourceKind.GMAIL
    assert params.presentation_shape == PresentationShape.RAW
    assert params.min_picks == 1
    assert params.max_picks == 5
    assert params.date_format == "%B %-d, %Y"
    assert params.query_dependencies == []
    assert params.extraction_prompt is None
    assert params.label is None


@pytest.mark.unit
@pytest.mark.parametrize("source", list(SourceKind))
def test_every_source_kind_round_trips(source: SourceKind):
    """All 8 source kinds (de)serialize cleanly to JSON and back."""
    params = WizardSourceParams(source=source)
    raw = params.model_dump_json()
    restored = WizardSourceParams.model_validate_json(raw)
    assert restored == params
    assert restored.source == source


@pytest.mark.unit
@pytest.mark.parametrize("shape", list(PresentationShape))
def test_every_presentation_shape_round_trips(shape: PresentationShape):
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=shape,
        label="Pick the right one" if shape != PresentationShape.RAW else None,
    )
    raw = params.model_dump_json()
    restored = WizardSourceParams.model_validate_json(raw)
    assert restored.presentation_shape == shape


@pytest.mark.unit
@pytest.mark.parametrize("kind", list(AuthorInputKind))
def test_author_input_kind_round_trips(kind: AuthorInputKind):
    params = WizardSourceParams(
        source=SourceKind.AUTHOR_INPUT,
        author_input_kind=kind,
        label="Type the value",
    )
    raw = params.model_dump_json()
    restored = WizardSourceParams.model_validate_json(raw)
    assert restored.author_input_kind == kind


@pytest.mark.unit
def test_query_dependencies_round_trip():
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        extraction_prompt="the paystub from the most recent month",
        query_dependencies=["meeting_date", "case_number"],
    )
    raw = params.model_dump_json()
    restored = WizardSourceParams.model_validate_json(raw)
    assert restored.query_dependencies == ["meeting_date", "case_number"]


@pytest.mark.unit
def test_constants_source_carries_short_code():
    params = WizardSourceParams(
        source=SourceKind.CONSTANTS,
        constants_short_code="firm_address",
    )
    restored = WizardSourceParams.model_validate_json(params.model_dump_json())
    assert restored.constants_short_code == "firm_address"


@pytest.mark.unit
def test_attorney_raw_carries_attorney_id():
    params = WizardSourceParams(
        source=SourceKind.ATTORNEY,
        presentation_shape=PresentationShape.RAW,
        attorney_id="att_42",
    )
    restored = WizardSourceParams.model_validate_json(params.model_dump_json())
    assert restored.attorney_id == "att_42"


@pytest.mark.unit
def test_derived_from_variable_carries_dependent_and_prompt():
    params = WizardSourceParams(
        source=SourceKind.DERIVED_FROM_VARIABLE,
        dependent_variable="vehicle_record",
        extraction_prompt="extract the VIN — 11–17 alphanumeric chars",
    )
    restored = WizardSourceParams.model_validate_json(params.model_dump_json())
    assert restored.dependent_variable == "vehicle_record"
    assert restored.extraction_prompt is not None
    assert "VIN" in restored.extraction_prompt


@pytest.mark.unit
def test_value_from_parent_bundle_carries_fallback():
    params = WizardSourceParams(
        source=SourceKind.VALUE_FROM_PARENT_BUNDLE,
        parent_bundle_fallback="TBD",
    )
    restored = WizardSourceParams.model_validate_json(params.model_dump_json())
    assert restored.parent_bundle_fallback == "TBD"


@pytest.mark.unit
def test_multi_select_pick_bounds_validated():
    """min_picks / max_picks must be within [1, 20]."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WizardSourceParams(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.MULTI_SELECT,
            min_picks=0,
        )
    with pytest.raises(ValidationError):
        WizardSourceParams(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.MULTI_SELECT,
            max_picks=21,
        )


@pytest.mark.unit
def test_extra_fields_rejected():
    """Unknown fields in the payload are rejected (extra='forbid')."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WizardSourceParams.model_validate_json(
            '{"source": "gmail", "rule_effect": "extract_substring"}'
        )
