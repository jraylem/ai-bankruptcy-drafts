"""Tests for v2 composer schemas: parse / generate / regenerate
request-response shapes + the MergeOperationV2 helper.
"""

import pytest
from pydantic import ValidationError

from src.core.studio_v2.agents.template import TemplateFieldV2Extract
from src.core.studio_v2.services.composer.schemas import (
    DocumentParseResponseV2,
    MergeOperationV2,
    TemplateGenerateResponseV2,
    TemplateRegenerateDiffV2,
)


@pytest.mark.unit
def test_parse_response_round_trips():
    resp = DocumentParseResponseV2(
        document_id="motion.docx",
        parsed=True,
        content="In Re: John Smith, Debtor",
        metadata={"format": "docx", "paragraph_count": 1},
    )
    restored = DocumentParseResponseV2.model_validate_json(resp.model_dump_json())
    assert restored.document_id == "motion.docx"
    assert restored.metadata["paragraph_count"] == 1


@pytest.mark.unit
def test_merge_operation_v2_requires_at_least_two_sources():
    with pytest.raises(ValidationError):
        MergeOperationV2(
            new_variable_name="case_number",
            source_variables=["only_one"],
        )


@pytest.mark.unit
def test_merge_operation_v2_resolves_name():
    merge = MergeOperationV2(
        new_variable_name="case_number",
        source_variables=["claim_no_short", "claim_no_long"],
    )
    assert merge.resolve_variable_name() == "case_number"


@pytest.mark.unit
def test_generate_response_round_trips_with_spec():
    resp = TemplateGenerateResponseV2(
        template_id="tpl-abc",
        name="341a Meeting Notice",
        template_spec=[
            TemplateFieldV2Extract(template_variable="debtor_name", template_index=0),
            TemplateFieldV2Extract(template_variable="case_number", template_index=1),
        ],
        original_doc_url="https://r2.../original.docx",
        template_doc_url="https://r2.../template.docx",
    )
    restored = TemplateGenerateResponseV2.model_validate_json(resp.model_dump_json())
    assert restored.template_id == "tpl-abc"
    assert len(restored.template_spec) == 2


@pytest.mark.unit
def test_regenerate_diff_round_trips():
    diff = TemplateRegenerateDiffV2(
        template_id="tpl-abc",
        inserted=["section_341_meeting_date"],
        updated=["debtor_name", "case_number"],
        deleted=["claim_no_short", "claim_no_long"],
        preserved_params=["debtor_name"],
        template_doc_url="https://r2.../template.docx",
    )
    restored = TemplateRegenerateDiffV2.model_validate_json(diff.model_dump_json())
    assert restored.inserted == ["section_341_meeting_date"]
    assert restored.preserved_params == ["debtor_name"]


@pytest.mark.unit
def test_regenerate_diff_defaults_to_empty_lists():
    diff = TemplateRegenerateDiffV2(
        template_id="tpl-abc",
        template_doc_url="https://r2.../template.docx",
    )
    assert diff.inserted == []
    assert diff.updated == []
    assert diff.deleted == []
    assert diff.preserved_params == []


@pytest.mark.unit
def test_schemas_reject_extra_fields():
    """extra='forbid' on all composer schemas."""
    with pytest.raises(ValidationError):
        TemplateGenerateResponseV2.model_validate({
            "template_id": "x",
            "name": "y",
            "template_spec": [],
            "original_doc_url": "u",
            "template_doc_url": "v",
            "extra_field": "should_be_rejected",
        })
