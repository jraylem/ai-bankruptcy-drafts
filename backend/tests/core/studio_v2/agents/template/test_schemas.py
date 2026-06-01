"""Tests for TemplateAgentV2's output schemas.

The LLM round-trip itself (TemplateAgentV2.run) needs a real test-LLM
harness — those tests live separately. These tests focus on the
schema shape: round-trip, validation, default values, and that
WizardSourceParams nests correctly inside `params`.
"""

import pytest
from pydantic import ValidationError

from src.core.studio_v2.agents.template import (
    MergeInstructionV2,
    TemplateAgentV2Output,
    TemplateFieldV2Extract,
)
from src.core.studio_v2.types.wizard_sources import (
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


@pytest.mark.unit
def test_template_field_extract_minimal():
    field = TemplateFieldV2Extract(
        template_variable="debtor_name",
        template_index=0,
    )
    assert field.template_property_marker is None
    assert field.template_property_marker_aliases == []
    assert field.template_variable_string is None
    assert field.params is None


@pytest.mark.unit
def test_template_field_extract_with_wizard_params():
    field = TemplateFieldV2Extract(
        template_variable="debtor_name",
        template_index=0,
        template_property_marker="John Smith",
        template_variable_string="[[debtor_name]]",
        template_identifying_text_match="In Re: John Smith, Debtor",
        description="The full legal name of the debtor",
        params=WizardSourceParams(source=SourceKind.CASE_FILE, extraction_prompt="the debtor's full legal name"),
    )
    raw = field.model_dump_json()
    restored = TemplateFieldV2Extract.model_validate_json(raw)
    assert restored.template_variable == "debtor_name"
    assert restored.params is not None
    assert restored.params.source == SourceKind.CASE_FILE


@pytest.mark.unit
def test_template_field_extract_virtual_parent_pattern():
    """Rule 16/18 virtual parent: template_variable_string is null."""
    parent = TemplateFieldV2Extract(
        template_variable="proof_of_claim_row",
        template_index=4,
        template_property_marker="4 - Bank of America - $3,000",
        template_variable_string=None,
        params=None,
    )
    assert parent.template_variable_string is None
    assert parent.params is None


@pytest.mark.unit
def test_template_field_extract_derived_child_carries_extraction_prompt():
    """Rule 16 child: params has derived_from_variable + extraction_prompt."""
    child = TemplateFieldV2Extract(
        template_variable="claim_number",
        template_index=5,
        template_property_marker="4",
        template_variable_string="[[claim_number]]",
        params=WizardSourceParams(
            source=SourceKind.DERIVED_FROM_VARIABLE,
            presentation_shape=PresentationShape.RAW,
            dependent_variable="proof_of_claim_row",
            extraction_prompt="Extract the claim number from the parent record — just the integer.",
        ),
    )
    raw = child.model_dump_json()
    restored = TemplateFieldV2Extract.model_validate_json(raw)
    assert restored.params is not None
    assert restored.params.source == SourceKind.DERIVED_FROM_VARIABLE
    assert restored.params.dependent_variable == "proof_of_claim_row"
    assert "claim number" in (restored.params.extraction_prompt or "")


@pytest.mark.unit
def test_template_field_extract_aliases_round_trip():
    field = TemplateFieldV2Extract(
        template_variable="debtor_name",
        template_index=0,
        template_property_marker="Judith S. Schwartz",
        template_property_marker_aliases=["Judith S Schwartz"],
    )
    restored = TemplateFieldV2Extract.model_validate_json(field.model_dump_json())
    assert restored.template_property_marker_aliases == ["Judith S Schwartz"]


@pytest.mark.unit
def test_template_field_extract_rejects_extra_fields():
    with pytest.raises(ValidationError):
        TemplateFieldV2Extract.model_validate({
            "template_variable": "x",
            "template_index": 0,
            "source": "case_file",  # v1 field name — should fail
        })


@pytest.mark.unit
def test_template_agent_v2_output_defaults_to_empty_spec():
    out = TemplateAgentV2Output()
    assert out.template_spec == []


@pytest.mark.unit
def test_template_agent_v2_output_round_trips_spec():
    out = TemplateAgentV2Output(template_spec=[
        TemplateFieldV2Extract(template_variable="debtor_name", template_index=0),
        TemplateFieldV2Extract(template_variable="case_number", template_index=1),
    ])
    raw = out.model_dump_json()
    restored = TemplateAgentV2Output.model_validate_json(raw)
    assert len(restored.template_spec) == 2
    assert restored.template_spec[0].template_variable == "debtor_name"
    assert restored.template_spec[1].template_variable == "case_number"


@pytest.mark.unit
def test_merge_instruction_v2_round_trips():
    merge = MergeInstructionV2(
        new_variable_name="case_number",
        source_variables=["claim_no_short", "claim_no_long"],
        description="Combine the two case-number forms into one",
    )
    raw = merge.model_dump_json()
    restored = MergeInstructionV2.model_validate_json(raw)
    assert restored.new_variable_name == "case_number"
    assert restored.source_variables == ["claim_no_short", "claim_no_long"]
    assert restored.description == "Combine the two case-number forms into one"


@pytest.mark.unit
def test_merge_instruction_v2_optional_description():
    merge = MergeInstructionV2(
        new_variable_name="case_number",
        source_variables=["claim_no_short", "claim_no_long"],
    )
    assert merge.description is None
