"""Tests for the pure helpers inside regenerate.py — the row-to-extract
adapter that turns persisted template_fields_v2 rows back into
TemplateFieldV2Extract shape for the agent's `previous_spec` input.
"""

from types import SimpleNamespace

import pytest

from src.core.studio_v2.services.composer.regenerate import _row_to_extract
from src.core.studio_v2.types.wizard_sources import SourceKind, WizardSourceParams


def _fake_row(**kwargs):
    """SimpleNamespace stand-in for an ORM row — only the attributes
    _row_to_extract reads."""
    defaults = {
        "template_variable": "debtor_name",
        "template_index": 0,
        "template_property_marker": "John Smith",
        "template_property_marker_aliases": None,
        "template_identifying_text_match": None,
        "description": None,
        "params": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.unit
def test_row_to_extract_minimal():
    extract = _row_to_extract(_fake_row())
    assert extract.template_variable == "debtor_name"
    assert extract.template_property_marker == "John Smith"
    # template_variable_string synthesized as [[name]] when marker is present
    assert extract.template_variable_string == "[[debtor_name]]"
    assert extract.params is None


@pytest.mark.unit
def test_row_to_extract_with_params_round_trips_wizard_source_params():
    row = _fake_row(params={
        "source": "case_file",
        "presentation_shape": "raw",
        "extraction_prompt": "extract the debtor's name from the petition",
    })
    extract = _row_to_extract(row)
    assert extract.params is not None
    assert extract.params.source == SourceKind.CASE_FILE
    assert "debtor's name" in extract.params.extraction_prompt


@pytest.mark.unit
def test_row_to_extract_virtual_parent_pattern():
    """Virtual parents have template_property_marker is None — adapter
    synthesizes template_variable_string=None to match.
    """
    row = _fake_row(
        template_variable="proof_of_claim_row",
        template_property_marker=None,
    )
    extract = _row_to_extract(row)
    assert extract.template_variable_string is None


@pytest.mark.unit
def test_row_to_extract_carries_aliases():
    row = _fake_row(
        template_property_marker_aliases=["John Smith Jr"],
    )
    extract = _row_to_extract(row)
    assert extract.template_property_marker_aliases == ["John Smith Jr"]


@pytest.mark.unit
def test_row_to_extract_handles_null_aliases():
    """ORM column is nullable; adapter coerces None → empty list to
    match TemplateFieldV2Extract's default_factory shape."""
    row = _fake_row(template_property_marker_aliases=None)
    extract = _row_to_extract(row)
    assert extract.template_property_marker_aliases == []


@pytest.mark.unit
def test_row_to_extract_carries_identifying_text_and_description():
    row = _fake_row(
        template_identifying_text_match="In Re: John Smith, Debtor",
        description="The debtor's full legal name",
    )
    extract = _row_to_extract(row)
    assert extract.template_identifying_text_match == "In Re: John Smith, Debtor"
    assert extract.description == "The debtor's full legal name"
