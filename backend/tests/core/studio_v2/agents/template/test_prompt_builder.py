"""Tests for the TemplateAgentV2 prompt builder.

Pure-function tests on the block formatters + the prompt templates'
structural invariants (rules numbered 1-18 present, heuristics H1-H5
present, role guidance varies by role, etc.).
"""

import pytest

from src.core.studio_v2.agents.template import (
    MergeInstructionV2,
    TemplateFieldV2Extract,
)
from src.core.studio_v2.agents.template.prompt_builder import (
    TEMPLATE_EXTRACT_PROMPT_V2,
    TEMPLATE_MAP_CONSTANTS_PROMPT_V2,
    _format_ignored_texts_block,
    _format_merges_block,
    _format_previous_spec_block,
    _format_reference_data_block,
    _format_regeneration_instruction_block,
    _format_template_role_block,
)


# ─── extract prompt structural invariants ─────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("rule_num", list(range(1, 19)))  # rules 1..18
def test_extract_prompt_carries_every_rule_number(rule_num):
    """Each of the 18 v1 rules ports to v2; verify the prompt mentions
    each rule number in its CRITICAL RULES section."""
    # Rule 10b is special (sub-rule of 10); 18 = vehicle cluster
    needle = f"{rule_num}." if rule_num != 10 else "10."
    assert needle in TEMPLATE_EXTRACT_PROMPT_V2


@pytest.mark.unit
def test_extract_prompt_carries_rule_10b():
    assert "10b." in TEMPLATE_EXTRACT_PROMPT_V2


@pytest.mark.unit
@pytest.mark.parametrize("heuristic", ["H1.", "H2.", "H3.", "H4.", "H5."])
def test_extract_prompt_carries_source_suggestion_heuristics(heuristic):
    assert heuristic in TEMPLATE_EXTRACT_PROMPT_V2


@pytest.mark.unit
def test_extract_prompt_emphasizes_conservative_defaulting():
    """Heuristics must default to `params: null` aggressively — the
    prompt explicitly says so + carries an anti-example."""
    assert "Default to `params: null` aggressively" in TEMPLATE_EXTRACT_PROMPT_V2
    # The anti-example walks through what NOT to do (every var bound to case_file).
    assert "WORKED ANTI-EXAMPLE" in TEMPLATE_EXTRACT_PROMPT_V2


@pytest.mark.unit
def test_h2_date_detection_is_very_narrow_allowlist():
    """H2 case-file allowlist is exactly ONE entry: `petition_filing_date`
    (the petition's own filing timestamp — literally lives in the petition).
    All other date-shaped variables (court-notice dates, deadlines, etc.)
    must stay null. The prompt must explicitly warn against firing on them.
    """
    # Current-date allowlist members appear inline.
    for allowlisted in ["document_date", "today", "prepared_on"]:
        assert allowlisted in TEMPLATE_EXTRACT_PROMPT_V2

    # Case-file allowlist is ONE entry only.
    assert "Case-file (literally one entry" in TEMPLATE_EXTRACT_PROMPT_V2
    assert "petition_filing_date" in TEMPLATE_EXTRACT_PROMPT_V2

    # The prompt must explicitly warn against firing on common-looking dates
    # that DON'T live in the petition itself.
    assert "Do NOT fire H2 for ANY other date variable" in TEMPLATE_EXTRACT_PROMPT_V2
    # And specifically call out the ones paralegals would expect to be
    # auto-bound but shouldn't.
    for excluded in [
        "section_341_meeting_date",     # comes from court notice via Gmail
        "discharge_date",                # future event
        "confirmation_date",             # future event
        "filing_requirements_deadline",  # workflow-specific
    ]:
        assert excluded in TEMPLATE_EXTRACT_PROMPT_V2, (
            f"H2 anti-pattern must explicitly mention {excluded!r} as a "
            "variable that should NOT be auto-bound to case_file."
        )


@pytest.mark.unit
def test_h3_cross_doc_identifier_allowlist():
    """H3 must allowlist EXACTLY the four cross-document identifiers
    every bankruptcy filing pulls from the petition."""
    assert "Cross-document identifier ALLOWLIST" in TEMPLATE_EXTRACT_PROMPT_V2
    # All four bankruptcy-petition cross-doc identifiers explicitly named.
    for identifier in ["debtor_name", "case_number", "chapter", "court_district"]:
        assert identifier in TEMPLATE_EXTRACT_PROMPT_V2


@pytest.mark.unit
def test_prompt_calls_out_examples_of_variables_to_leave_null():
    """The prompt must give concrete examples of which variable shapes
    should NOT be auto-bound (paralegal judgment required)."""
    null_examples = [
        "Narrative paragraphs",      # author_input_with_docs vs case_file
        "Arbitrary recipients",      # gmail / case_file / author_input
        "Arbitrary dollar amounts",  # case_file / gmail / author_input
        "Reasons / explanations",    # almost always author_input
    ]
    for hint in null_examples:
        assert hint in TEMPLATE_EXTRACT_PROMPT_V2, (
            f"Conservative-defaulting hint missing from prompt: {hint!r}"
        )


@pytest.mark.unit
def test_extract_prompt_no_v1_emission_shape_artifacts():
    """v2 should NOT mention v1's `auto_derived_from_variable`,
    `rule_effect`, `pluralize_by_count`, `extract_substring`,
    `singular_value`, `plural_value` — those are the v1 substring-rule
    enum shape that v2 replaces with prompt-based derives."""
    forbidden = [
        "auto_derived_from_variable",
        "rule_effect",
        "pluralize_by_count",
        "extract_substring",
        "singular_value",
        "plural_value",
    ]
    for token in forbidden:
        assert token not in TEMPLATE_EXTRACT_PROMPT_V2, (
            f"v2 prompt unexpectedly mentions v1 emission shape: {token}"
        )


@pytest.mark.unit
def test_extract_prompt_emits_v2_derived_shape():
    """v2 emits `derived_from_variable` source + extraction_prompt."""
    assert "derived_from_variable" in TEMPLATE_EXTRACT_PROMPT_V2
    assert "extraction_prompt" in TEMPLATE_EXTRACT_PROMPT_V2


@pytest.mark.unit
def test_extract_prompt_lists_common_dynamic_variables():
    """The COMMON DYNAMIC VARIABLES section ports v1's heuristic
    scan list verbatim."""
    common_vars = [
        "debtor_name", "case_number", "chapter", "court_district",
        "document_date", "petition_filing_date", "section_341_meeting_date",
        "docket_number", "attorney_name",
    ]
    for var in common_vars:
        assert var in TEMPLATE_EXTRACT_PROMPT_V2, f"missing common dynamic var: {var}"


# ─── constants mapping prompt ─────────────────────────────────────────


@pytest.mark.unit
def test_map_constants_prompt_emits_v2_params_shape():
    """v2's constants mapping sets `params.source = "constants"` +
    `params.constants_short_code` (NOT v1's nested source_params)."""
    assert "constants_short_code" in TEMPLATE_MAP_CONSTANTS_PROMPT_V2
    assert '"source": "constants"' in TEMPLATE_MAP_CONSTANTS_PROMPT_V2
    # Should NOT contain v1's nested shape
    assert "source_params" not in TEMPLATE_MAP_CONSTANTS_PROMPT_V2


# ─── block formatters ────────────────────────────────────────────────


@pytest.mark.unit
def test_format_previous_spec_block_empty():
    assert _format_previous_spec_block(None) == ""
    assert _format_previous_spec_block([]) == ""


@pytest.mark.unit
def test_format_previous_spec_block_renders_json():
    block = _format_previous_spec_block([
        TemplateFieldV2Extract(template_variable="debtor_name", template_index=0),
    ])
    assert "PREVIOUS SPEC" in block
    assert "debtor_name" in block
    assert "<previous_spec>" in block


@pytest.mark.unit
def test_format_ignored_texts_block_empty():
    assert _format_ignored_texts_block(None) == ""
    assert _format_ignored_texts_block([]) == ""
    assert _format_ignored_texts_block(["   ", ""]) == ""  # all empty after strip


@pytest.mark.unit
def test_format_ignored_texts_block_renders_numbered_list():
    block = _format_ignored_texts_block(["letterhead block", "court header"])
    assert "IGNORED TEXTS" in block
    assert "1. letterhead block" in block
    assert "2. court header" in block


@pytest.mark.unit
def test_format_merges_block_empty():
    assert _format_merges_block(None) == ""
    assert _format_merges_block([]) == ""


@pytest.mark.unit
def test_format_merges_block_renders_merge_groups():
    block = _format_merges_block([
        MergeInstructionV2(
            new_variable_name="case_number",
            source_variables=["claim_no_short", "claim_no_long"],
            description="combine two forms",
        ),
    ])
    assert "MERGE INSTRUCTIONS" in block
    assert "'claim_no_short', 'claim_no_long'" in block
    assert "'case_number'" in block
    assert "combine two forms" in block


@pytest.mark.unit
def test_format_regeneration_instruction_block_empty():
    assert _format_regeneration_instruction_block(None) == ""
    assert _format_regeneration_instruction_block("") == ""
    assert _format_regeneration_instruction_block("   ") == ""


@pytest.mark.unit
def test_format_regeneration_instruction_block_renders():
    block = _format_regeneration_instruction_block("split case_number into two")
    assert "REGENERATION INSTRUCTION" in block
    assert "split case_number into two" in block


# ─── role block ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_role_block_single():
    block = _format_template_role_block("single")
    assert "**single**" in block
    assert "Standalone filing" in block
    assert "Heuristic H3" in block  # explains H3 doesn't fire
    assert "PARENT TEMPLATE SPEC" not in block  # no parent spec for standalone


@pytest.mark.unit
def test_role_block_master():
    block = _format_template_role_block("master")
    assert "**master**" in block
    assert "Lead filing" in block
    assert "PARENT TEMPLATE SPEC" not in block


@pytest.mark.unit
def test_role_block_part_of_packet_without_parent_spec():
    """Companion role guidance now defaults the cross-doc identifier
    allowlist to case_file (same as single/master) — the old default
    of value_from_parent_bundle was footgun-y because Phase 1 doesn't
    pass parent_template_spec, leaving the agent to over-apply."""
    block = _format_template_role_block("part_of_packet")
    assert "**part_of_packet**" in block
    assert "Companion filing" in block
    assert "Heuristic H3" in block
    assert "source=case_file" in block
    assert "Do NOT default to value_from_parent_bundle" in block
    # The actual <parent_spec>...</parent_spec> block isn't rendered
    # when parent_template_spec is None.
    assert "<parent_spec>" not in block


@pytest.mark.unit
def test_role_block_part_of_packet_with_parent_spec():
    parent_spec = [
        TemplateFieldV2Extract(
            template_variable="debtor_name",
            template_index=0,
            description="The debtor's full legal name",
        ),
        TemplateFieldV2Extract(
            template_variable="case_number",
            template_index=1,
            description="The bankruptcy case number",
        ),
    ]
    block = _format_template_role_block("part_of_packet", parent_spec)
    assert "PARENT TEMPLATE SPEC" in block
    assert "<parent_spec>" in block
    assert "debtor_name" in block
    assert "case_number" in block
    assert "The debtor's full legal name" in block


# ─── reference data ───────────────────────────────────────────────────


@pytest.mark.unit
def test_format_reference_data_block_empty():
    assert _format_reference_data_block([]) == "(none)"


@pytest.mark.unit
def test_format_reference_data_block_renders():
    """The block formatter renders a ReferenceData list verbatim."""
    from src.core.common.storage.database import ReferenceData

    rows = [
        ReferenceData(
            short_code="firm_phone",
            display_name="Firm phone",
            value="(954) 765-3166",
            description="Main office line",
        ),
        ReferenceData(
            short_code="firm_address",
            display_name="Firm address",
            value="500 NE 4th Street, Fort Lauderdale, FL 33301",
            description=None,
        ),
    ]
    block = _format_reference_data_block(rows)
    assert "firm_phone" in block
    assert "(954) 765-3166" in block
    assert "Main office line" in block
    assert "firm_address" in block


# ─── prompt placeholder substitution ──────────────────────────────────


@pytest.mark.unit
def test_extract_prompt_template_substitutes_cleanly():
    """The format string should accept all six placeholder blocks
    without raising KeyError."""
    rendered = TEMPLATE_EXTRACT_PROMPT_V2.format(
        document_content="<doc>",
        previous_spec_block="",
        ignored_texts_block="",
        merges_block="",
        regeneration_instruction_block="",
        template_role_block="ROLE_BLOCK",
    )
    assert "<doc>" in rendered
    assert "ROLE_BLOCK" in rendered
    # No leftover unsubstituted placeholders
    assert "{document_content}" not in rendered
    assert "{template_role_block}" not in rendered


@pytest.mark.unit
def test_map_constants_prompt_template_substitutes_cleanly():
    rendered = TEMPLATE_MAP_CONSTANTS_PROMPT_V2.format(
        extracted_spec='{"template_variable": "x"}',
        reference_data_block="(none)",
    )
    assert "{extracted_spec}" not in rendered
    assert "{reference_data_block}" not in rendered
