"""Tests for the pure helpers inside generate.py — the orphan-drop pass,
the v1-shape adapter, and the persistence adapter.

The full `generate_template_v2` integration (R2 + LLM + DB) needs a
harness with all three; covered by the manual smoke test in Phase 1.
"""

import pytest

from src.core.studio_v2.agents.template import TemplateFieldV2Extract
from src.core.studio_v2.services.composer.generate import (
    _adapt_to_v1_template_variables,
    _drop_orphan_variables_v2,
    _to_create_dict,
)
from src.core.studio_v2.types.wizard_sources import (
    SourceKind,
    WizardSourceParams,
)


# ─── _adapt_to_v1_template_variables ──────────────────────────────────


@pytest.mark.unit
def test_adapter_carries_placement_fields():
    """Adapter copies the fields create_template actually reads."""
    v2 = [
        TemplateFieldV2Extract(
            template_variable="debtor_name",
            template_index=0,
            template_property_marker="John Smith",
            template_property_marker_aliases=["John Smith Jr"],
            template_variable_string="[[debtor_name]]",
            template_identifying_text_match="In Re: John Smith",
            description="The debtor's name",
        ),
    ]
    v1 = _adapt_to_v1_template_variables(v2)
    assert len(v1) == 1
    assert v1[0].template_variable == "debtor_name"
    assert v1[0].template_property_marker == "John Smith"
    assert v1[0].template_property_marker_aliases == ["John Smith Jr"]
    assert v1[0].template_variable_string == "[[debtor_name]]"
    assert v1[0].template_identifying_text_match == "In Re: John Smith"
    # All v1-specific fields are NULL — v2 doesn't emit them.
    assert v1[0].source is None
    assert v1[0].source_params is None


@pytest.mark.unit
def test_adapter_preserves_virtual_parent_pattern():
    """Rule 16/18 virtual parent has template_variable_string=None;
    adapter preserves it so create_template skips placement for it."""
    v2 = [
        TemplateFieldV2Extract(
            template_variable="proof_of_claim_row",
            template_index=4,
            template_property_marker="4 - Bank of America - $3,000",
            template_variable_string=None,
        ),
    ]
    v1 = _adapt_to_v1_template_variables(v2)
    assert v1[0].template_variable_string is None


@pytest.mark.unit
def test_adapter_empty_input_returns_empty():
    assert _adapt_to_v1_template_variables([]) == []


# ─── _drop_orphan_variables_v2 ────────────────────────────────────────


@pytest.mark.unit
def test_drop_orphans_keeps_present_variables():
    """A fake docx contains [[debtor_name]] and [[case_number]]; both
    variables survive the orphan-drop pass."""
    fake_docx_bytes = b"Random bytes that DocxTemplateService.find_missing_placeholders mocks against"
    spec = [
        TemplateFieldV2Extract(
            template_variable="debtor_name",
            template_index=0,
            template_variable_string="[[debtor_name]]",
        ),
        TemplateFieldV2Extract(
            template_variable="case_number",
            template_index=1,
            template_variable_string="[[case_number]]",
        ),
    ]

    # Patch find_missing_placeholders to return empty set (no orphans).
    from unittest.mock import patch

    with patch(
        "src.core.studio_v2.services.composer.generate.DocxTemplateService.find_missing_placeholders",
        return_value=set(),
    ):
        survivors = _drop_orphan_variables_v2(fake_docx_bytes, spec)

    assert len(survivors) == 2
    assert {f.template_variable for f in survivors} == {"debtor_name", "case_number"}


@pytest.mark.unit
def test_drop_orphans_filters_missing_placeholders():
    """If find_missing_placeholders flags [[her_var]] as not in docx, it gets dropped."""
    fake_docx_bytes = b"fake"
    spec = [
        TemplateFieldV2Extract(
            template_variable="debtor_name",
            template_index=0,
            template_variable_string="[[debtor_name]]",
        ),
        TemplateFieldV2Extract(
            template_variable="her_var",  # hallucinated sub-token
            template_index=1,
            template_variable_string="[[her_var]]",
        ),
    ]

    from unittest.mock import patch

    with patch(
        "src.core.studio_v2.services.composer.generate.DocxTemplateService.find_missing_placeholders",
        return_value={"[[her_var]]"},
    ):
        survivors = _drop_orphan_variables_v2(fake_docx_bytes, spec)

    assert len(survivors) == 1
    assert survivors[0].template_variable == "debtor_name"


@pytest.mark.unit
def test_drop_orphans_preserves_virtual_parents():
    """Virtual parents have template_variable_string=None and never
    render directly. They MUST survive orphan-drop regardless.
    """
    fake_docx_bytes = b"fake"
    spec = [
        TemplateFieldV2Extract(
            template_variable="proof_of_claim_row",
            template_index=4,
            template_property_marker="4 - Bank of America - $3,000",
            template_variable_string=None,  # virtual parent
        ),
        TemplateFieldV2Extract(
            template_variable="claim_number",
            template_index=5,
            template_variable_string="[[claim_number]]",
        ),
    ]

    from unittest.mock import patch

    with patch(
        "src.core.studio_v2.services.composer.generate.DocxTemplateService.find_missing_placeholders",
        return_value=set(),
    ):
        survivors = _drop_orphan_variables_v2(fake_docx_bytes, spec)

    # Virtual parent survives even though it has no placeholder in the docx.
    survivor_names = {f.template_variable for f in survivors}
    assert "proof_of_claim_row" in survivor_names
    assert "claim_number" in survivor_names


@pytest.mark.unit
def test_drop_orphans_with_only_virtual_parents_short_circuits():
    """If there are NO physical placeholders to check, return spec as-is."""
    fake_docx_bytes = b"fake"
    spec = [
        TemplateFieldV2Extract(
            template_variable="virtual_only",
            template_index=0,
            template_variable_string=None,
        ),
    ]
    # No patch needed — function should short-circuit before calling
    # find_missing_placeholders.
    survivors = _drop_orphan_variables_v2(fake_docx_bytes, spec)
    assert survivors == spec


@pytest.mark.unit
def test_drop_orphans_empty_spec():
    survivors = _drop_orphan_variables_v2(b"fake", [])
    assert survivors == []


# ─── _to_create_dict ──────────────────────────────────────────────────


@pytest.mark.unit
def test_to_create_dict_with_params():
    field = TemplateFieldV2Extract(
        template_variable="debtor_name",
        template_index=0,
        template_property_marker="John Smith",
        template_property_marker_aliases=["John Smith Jr"],
        template_identifying_text_match="In Re: John Smith",
        description="The debtor's name",
        template_variable_string="[[debtor_name]]",
        params=WizardSourceParams(
            source=SourceKind.CASE_FILE,
            extraction_prompt="extract debtor name",
        ),
    )
    d = _to_create_dict(field)
    assert d["template_variable"] == "debtor_name"
    assert d["template_property_marker"] == "John Smith"
    assert d["template_property_marker_aliases"] == ["John Smith Jr"]
    assert d["template_identifying_text_match"] == "In Re: John Smith"
    assert d["description"] == "The debtor's name"
    assert d["template_index"] == 0
    # template_variable_string is NOT in the dict (lives in docx, not row)
    assert "template_variable_string" not in d
    # params serialized as JSON-safe dict
    assert d["params"] is not None
    assert d["params"]["source"] == "case_file"
    assert d["params"]["extraction_prompt"] == "extract debtor name"


@pytest.mark.unit
def test_to_create_dict_without_params():
    field = TemplateFieldV2Extract(
        template_variable="placeholder",
        template_index=2,
    )
    d = _to_create_dict(field)
    assert d["params"] is None
    assert d["template_property_marker"] is None


@pytest.mark.unit
def test_to_create_dict_empty_aliases_becomes_none():
    """Avoid persisting empty arrays in JSONB — coerce to None.
    Keeps the row tidy + matches Pydantic's exclude_none behavior."""
    field = TemplateFieldV2Extract(
        template_variable="x",
        template_index=0,
        template_property_marker_aliases=[],
    )
    d = _to_create_dict(field)
    assert d["template_property_marker_aliases"] is None
