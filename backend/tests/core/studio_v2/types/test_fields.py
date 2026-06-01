"""Tests for TemplateFieldV2 + TemplateSpecV2."""

import pytest
from uuid import UUID, uuid4

from src.core.studio_v2.types.fields import TemplateFieldV2, TemplateSpecV2
from src.core.studio_v2.types.wizard_sources import (
    SourceKind,
    WizardSourceParams,
)


@pytest.mark.unit
def test_template_field_minimal_construction():
    field_id = uuid4()
    template_id = uuid4()
    field = TemplateFieldV2(
        id=field_id,
        template_id=template_id,
        template_variable="debtor_name",
    )
    assert field.id == field_id
    assert field.template_property_marker is None
    assert field.template_property_marker_aliases == []
    assert field.template_index == 0
    assert field.params is None


@pytest.mark.unit
def test_template_field_with_params_round_trips():
    field = TemplateFieldV2(
        id=uuid4(),
        template_id=uuid4(),
        template_variable="creditors_list",
        template_property_marker="Acme Bank, Genesis Finance, OneMain",
        template_identifying_text_match="Creditors of record: Acme Bank, ...",
        description="The list of creditors holding claims",
        template_index=4,
        params=WizardSourceParams(
            source=SourceKind.CASE_FILE,
            extraction_prompt="creditors with claims over $1,000",
        ),
    )
    raw = field.model_dump_json()
    restored = TemplateFieldV2.model_validate_json(raw)
    assert restored.template_variable == "creditors_list"
    assert restored.params is not None
    assert restored.params.source == SourceKind.CASE_FILE


@pytest.mark.unit
def test_template_field_aliases_round_trip():
    field = TemplateFieldV2(
        id=uuid4(),
        template_id=uuid4(),
        template_variable="debtor_name",
        template_property_marker="Judith S. Schwartz",
        template_property_marker_aliases=["Judith S Schwartz"],
    )
    raw = field.model_dump_json()
    restored = TemplateFieldV2.model_validate_json(raw)
    assert restored.template_property_marker_aliases == ["Judith S Schwartz"]


@pytest.mark.unit
def test_template_spec_round_trips_field_list():
    template_id = uuid4()
    spec = TemplateSpecV2(
        template_id=template_id,
        fields=[
            TemplateFieldV2(
                id=uuid4(),
                template_id=template_id,
                template_variable="case_number",
                template_index=0,
            ),
            TemplateFieldV2(
                id=uuid4(),
                template_id=template_id,
                template_variable="debtor_name",
                template_index=1,
            ),
        ],
    )
    raw = spec.model_dump_json()
    restored = TemplateSpecV2.model_validate_json(raw)
    assert restored.template_id == template_id
    assert len(restored.fields) == 2
    assert restored.fields[0].template_variable == "case_number"
    assert restored.fields[1].template_variable == "debtor_name"


@pytest.mark.unit
def test_template_spec_defaults_to_empty_fields():
    spec = TemplateSpecV2(template_id=uuid4())
    assert spec.fields == []


@pytest.mark.unit
def test_template_field_rejects_extra_fields():
    """extra='forbid' — unknown fields fail validation."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TemplateFieldV2.model_validate({
            "id": str(uuid4()),
            "template_id": str(uuid4()),
            "template_variable": "x",
            "schema_version": "v1",  # intentionally invalid
        })
