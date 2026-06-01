"""Tests for TemplateAgent — two-call orchestration (extract → map constants)."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.agents.llm import base as agent_base
from src.core.agents.llm.template import (
    MergeInstruction,
    TemplateAgent,
    TemplateAgentOutput,
)
from src.core.agents.types.sources import ConstantsSourceParams, FieldSource
from src.core.agents.types.spec import TemplateVariable
from src.core.common.storage.database import ReferenceDataRepository
from tests.core.factories import make_template_variable


class _FakeRef:
    """Stand-in for a ReferenceData row (only short_code is used by
    _drop_unknown_constants_mappings)."""
    def __init__(self, short_code: str, display_name: str = "", value: str = "", description: str | None = None):
        self.short_code = short_code
        self.display_name = display_name
        self.value = value
        self.description = description


def _patch_invoke_sequence(monkeypatch, responses: list):
    """Patch Agent._invoke so consecutive calls return consecutive `responses`.

    `responses[i]` can be a Pydantic value, None, or an Exception instance
    (which will be raised). Also captures every call's (prompt, run_name).
    """
    calls: list[dict] = []

    async def fake_invoke(cls, prompt, run_name, metadata=None):
        calls.append({"prompt": prompt, "run_name": run_name, "metadata": metadata or {}})
        idx = len(calls) - 1
        if idx >= len(responses):
            raise AssertionError(f"template agent called _invoke more than {len(responses)} time(s)")
        value = responses[idx]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(agent_base.Agent, "_invoke", classmethod(fake_invoke))
    return calls


@pytest.mark.unit
async def test_run_happy_path_extracts_then_maps_constants(monkeypatch):
    # 1st call: returns 2 variables, one with a value that matches a known constant
    extract_result = TemplateAgentOutput(
        template_spec=[
            make_template_variable(template_variable="firm_name", template_property_marker="Van Horn Law Group"),
            make_template_variable(template_variable="debtor_name", template_property_marker="John Smith"),
        ],
    )
    # 2nd call: map phase adds source=CONSTANTS on firm_name
    mapped_result = TemplateAgentOutput(
        template_spec=[
            make_template_variable(
                template_variable="firm_name",
                template_property_marker="Van Horn Law Group",
                source=FieldSource.CONSTANTS,
                source_params=ConstantsSourceParams(short_code="VAN_HORN"),
            ),
            make_template_variable(template_variable="debtor_name", template_property_marker="John Smith"),
        ],
    )
    calls = _patch_invoke_sequence(monkeypatch, [extract_result, mapped_result])
    monkeypatch.setattr(
        ReferenceDataRepository,
        "list",
        AsyncMock(return_value=[_FakeRef("VAN_HORN", value="Van Horn Law Group")]),
    )

    result = await TemplateAgent.run("some document content")

    assert len(calls) == 2
    assert calls[0]["run_name"] == "TemplateExtract"
    assert calls[1]["run_name"] == "TemplateMapConstants"
    assert len(result.template_spec) == 2
    firm = next(v for v in result.template_spec if v.template_variable == "firm_name")
    assert firm.source == FieldSource.CONSTANTS


@pytest.mark.unit
async def test_run_raises_502_when_extract_raises(monkeypatch):
    calls = _patch_invoke_sequence(monkeypatch, [RuntimeError("LLM exploded")])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    with pytest.raises(HTTPException) as exc:
        await TemplateAgent.run("doc")

    assert exc.value.status_code == 502
    assert "Template extraction failed" in exc.value.detail
    assert len(calls) == 1  # map call should NOT fire


@pytest.mark.unit
async def test_run_raises_422_when_extract_returns_none(monkeypatch):
    """LangChain structured-output can return None on parse failure."""
    calls = _patch_invoke_sequence(monkeypatch, [None])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    with pytest.raises(HTTPException) as exc:
        await TemplateAgent.run("doc")

    assert exc.value.status_code == 422
    assert len(calls) == 1


@pytest.mark.unit
async def test_run_skips_map_when_ref_data_is_empty(monkeypatch):
    """No reusable constants → no point running the second LLM call."""
    extract_result = TemplateAgentOutput(
        template_spec=[make_template_variable(template_variable="x", template_property_marker="foo")],
    )
    calls = _patch_invoke_sequence(monkeypatch, [extract_result])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    result = await TemplateAgent.run("doc")

    assert result == extract_result
    assert len(calls) == 1  # only extract, no map


@pytest.mark.unit
async def test_run_skips_map_when_extract_spec_is_empty(monkeypatch):
    """Nothing to map → skip the call."""
    extract_result = TemplateAgentOutput(template_spec=[])
    calls = _patch_invoke_sequence(monkeypatch, [extract_result])
    monkeypatch.setattr(
        ReferenceDataRepository, "list", AsyncMock(return_value=[_FakeRef("FIRM_NAME")])
    )

    result = await TemplateAgent.run("doc")

    assert result == extract_result
    assert len(calls) == 1


@pytest.mark.unit
async def test_run_falls_back_to_extract_when_map_raises(monkeypatch):
    """Map-phase error must not lose the extract-phase output."""
    extract_result = TemplateAgentOutput(
        template_spec=[make_template_variable(template_variable="x", template_property_marker="foo")],
    )
    calls = _patch_invoke_sequence(monkeypatch, [extract_result, RuntimeError("map failed")])
    monkeypatch.setattr(
        ReferenceDataRepository, "list", AsyncMock(return_value=[_FakeRef("FIRM_NAME")])
    )

    result = await TemplateAgent.run("doc")

    assert result == extract_result
    assert len(calls) == 2


@pytest.mark.unit
async def test_run_drops_hallucinated_constants_mappings(monkeypatch):
    """LLM may map source=constants with a short_code that doesn't exist in
    reference_data — validator demotes those back to source=None."""
    extract_result = TemplateAgentOutput(
        template_spec=[make_template_variable(template_variable="x", template_property_marker="foo")],
    )
    mapped_result = TemplateAgentOutput(
        template_spec=[
            make_template_variable(
                template_variable="x",
                template_property_marker="foo",
                source=FieldSource.CONSTANTS,
                source_params=ConstantsSourceParams(short_code="HALLUCINATED"),
            ),
        ],
    )
    _patch_invoke_sequence(monkeypatch, [extract_result, mapped_result])
    monkeypatch.setattr(
        ReferenceDataRepository,
        "list",
        AsyncMock(return_value=[_FakeRef("REAL_CODE")]),
    )

    result = await TemplateAgent.run("doc")

    assert len(result.template_spec) == 1
    var = result.template_spec[0]
    assert var.source is None
    assert var.source_params is None


@pytest.mark.unit
async def test_run_injects_ignored_texts_block_when_provided(monkeypatch):
    """The IGNORED TEXTS block appears in the prompt with each fragment listed."""
    calls = _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=[])])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    await TemplateAgent.run(
        "doc",
        ignored_texts=[
            "Given that the Debtor's position involves handling sensitive consumer information",
            "Therefore, the Debtor respectfully requests that the Court waive the wage deduction order",
        ],
    )

    prompt = calls[0]["prompt"]
    assert "IGNORED TEXTS" in prompt
    assert "Given that the Debtor's position involves handling sensitive consumer information" in prompt
    assert "Therefore, the Debtor respectfully requests that the Court waive the wage deduction order" in prompt


@pytest.mark.unit
@pytest.mark.parametrize("ignored_texts", [None, [], ["", "   ", "\n\t"]])
async def test_run_omits_ignored_texts_block_when_empty_or_none(monkeypatch, ignored_texts):
    """No IGNORED TEXTS header when the list is None, empty, or entirely whitespace."""
    calls = _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=[])])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    await TemplateAgent.run("doc", ignored_texts=ignored_texts)

    assert "IGNORED TEXTS" not in calls[0]["prompt"]


@pytest.mark.unit
async def test_run_injects_regeneration_instruction_block_when_provided(monkeypatch):
    """The REGENERATION INSTRUCTION block appears in the prompt with the
    author's free-form steering text wrapped in <regeneration_instruction>."""
    calls = _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=[])])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    await TemplateAgent.run(
        "doc",
        regeneration_instruction=(
            "Don't extract the clerk address as a variable; merge claim_no "
            "and claim_no_title into a single claim_no_title variable."
        ),
    )

    prompt = calls[0]["prompt"]
    assert "REGENERATION INSTRUCTION" in prompt
    assert "<regeneration_instruction>" in prompt
    assert "Don't extract the clerk address as a variable" in prompt


@pytest.mark.unit
@pytest.mark.parametrize("regeneration_instruction", [None, "", "   \n\t"])
async def test_run_omits_regeneration_instruction_block_when_empty_or_none(
    monkeypatch, regeneration_instruction,
):
    """No REGENERATION INSTRUCTION header when the value is None, empty, or whitespace."""
    calls = _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=[])])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    await TemplateAgent.run("doc", regeneration_instruction=regeneration_instruction)

    assert "REGENERATION INSTRUCTION" not in calls[0]["prompt"]
    assert "<regeneration_instruction>" not in calls[0]["prompt"]


@pytest.mark.unit
async def test_run_injects_merges_block_when_provided(monkeypatch):
    """The MERGE INSTRUCTIONS block appears in the prompt listing each group."""
    calls = _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=[])])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    await TemplateAgent.run(
        "doc",
        merges=[
            MergeInstruction(
                new_variable_name="ecf_document",
                source_variables=["ecf_number", "document_title"],
                description="ECF docket entry and its document title as one.",
            ),
        ],
    )

    prompt = calls[0]["prompt"]
    assert "MERGE INSTRUCTIONS" in prompt
    assert "ecf_document" in prompt
    assert "'ecf_number'" in prompt
    assert "'document_title'" in prompt
    assert "ECF docket entry and its document title as one." in prompt


@pytest.mark.unit
@pytest.mark.parametrize("merges", [None, []])
async def test_run_omits_merges_block_when_empty_or_none(monkeypatch, merges):
    calls = _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=[])])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    await TemplateAgent.run("doc", merges=merges)

    assert "MERGE INSTRUCTIONS" not in calls[0]["prompt"]


@pytest.mark.unit
async def test_run_injects_previous_spec_block_when_provided(monkeypatch):
    """The PREVIOUS SPEC block appears in the prompt with the author's
    confirmed baseline serialized to JSON inside <previous_spec>."""
    calls = _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=[])])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    baseline = [
        TemplateVariable(
            template_variable="case_number",
            template_index=0,
            template_property_marker="26-10700-SMG",
            template_variable_string="[[case_number]]",
            description="The Chapter 13 case number.",
        ),
    ]
    await TemplateAgent.run("doc", previous_spec=baseline)

    prompt = calls[0]["prompt"]
    assert "PREVIOUS SPEC" in prompt
    assert "<previous_spec>" in prompt
    assert "case_number" in prompt
    assert "26-10700-SMG" in prompt


@pytest.mark.unit
@pytest.mark.parametrize("previous_spec", [None, []])
async def test_run_omits_previous_spec_block_when_empty_or_none(
    monkeypatch, previous_spec,
):
    """No PREVIOUS SPEC header when the baseline is None or empty —
    initial-generate paths fall through cleanly."""
    calls = _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=[])])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    await TemplateAgent.run("doc", previous_spec=previous_spec)

    assert "PREVIOUS SPEC" not in calls[0]["prompt"]
    assert "<previous_spec>" not in calls[0]["prompt"]


@pytest.mark.unit
async def test_run_returns_agent_output_unchanged_when_baseline_preserved(
    monkeypatch,
):
    """When the mocked LLM echoes the baseline back verbatim (no signals),
    TemplateAgent.run returns that output untouched. Locks in the contract
    that preservation is a pass-through at the agent layer — the prompt
    block does the work; the agent doesn't re-filter or re-shape."""
    baseline = [
        TemplateVariable(
            template_variable="case_number",
            template_index=0,
            template_property_marker="26-10700-SMG",
            template_variable_string="[[case_number]]",
        ),
        TemplateVariable(
            template_variable="debtor_name",
            template_index=1,
            template_property_marker="Judith S Schwartz",
            template_variable_string="[[debtor_name]]",
        ),
    ]
    _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=baseline)])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    result = await TemplateAgent.run("doc", previous_spec=baseline)

    names = [v.template_variable for v in result.template_spec]
    assert names == ["case_number", "debtor_name"]


@pytest.mark.unit
async def test_run_renders_previous_and_merge_blocks_together(monkeypatch):
    """When both previous_spec and merges are supplied, both blocks render
    in the prompt. The agent has all the info it needs to drop the merged
    baseline source vars and add the merged target — the post-agent
    `_enforce_merges` is a defense-in-depth check, not the only enforcement."""
    calls = _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=[])])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    baseline = [
        TemplateVariable(
            template_variable="case_no_short",
            template_index=0,
            template_property_marker="26-10700",
            template_variable_string="[[case_no_short]]",
        ),
        TemplateVariable(
            template_variable="case_no_long",
            template_index=1,
            template_property_marker="26-10700-SMG",
            template_variable_string="[[case_no_long]]",
        ),
    ]
    await TemplateAgent.run(
        "doc",
        previous_spec=baseline,
        merges=[
            MergeInstruction(
                new_variable_name="case_number",
                source_variables=["case_no_short", "case_no_long"],
            ),
        ],
    )

    prompt = calls[0]["prompt"]
    assert "PREVIOUS SPEC" in prompt
    assert "MERGE INSTRUCTIONS" in prompt
    assert "case_no_short" in prompt
    assert "case_no_long" in prompt
    assert "case_number" in prompt


@pytest.mark.unit
async def test_run_renders_previous_and_regen_instruction_blocks_together(
    monkeypatch,
):
    """The escape-hatch case — a regen instruction explicitly telling the
    agent to re-evaluate a baseline variable. Both blocks render so the
    agent has the baseline AND the override directive in context."""
    calls = _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=[])])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    baseline = [
        TemplateVariable(
            template_variable="chapter",
            template_index=0,
            template_property_marker="13",
            template_variable_string="[[chapter]]",
        ),
    ]
    await TemplateAgent.run(
        "doc",
        previous_spec=baseline,
        regeneration_instruction="Re-evaluate the chapter variable from scratch.",
    )

    prompt = calls[0]["prompt"]
    assert "PREVIOUS SPEC" in prompt
    assert "REGENERATION INSTRUCTION" in prompt
    assert "Re-evaluate the chapter variable from scratch." in prompt


@pytest.mark.unit
async def test_run_prompt_contains_auto_derived_rule_and_example(monkeypatch):
    """Rule 10 (auto-derived occurrences) and the auto-derived example are
    always part of the extraction prompt — these aren't optional blocks."""
    calls = _patch_invoke_sequence(monkeypatch, [TemplateAgentOutput(template_spec=[])])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    await TemplateAgent.run("doc")

    prompt = calls[0]["prompt"]
    assert "Auto-derived occurrences" in prompt
    assert "auto_derived_from_variable" in prompt
    assert "ecf_number_document_description_title" in prompt  # from the example block


@pytest.mark.unit
async def test_run_forces_read_only_on_auto_derived_emissions_even_if_agent_omits_flag(monkeypatch):
    """Defensive post-process: any AUTO_DERIVED_FROM_VARIABLE emission has
    `read_only=True` set on the way out, even if the agent forgot."""
    from src.core.agents.types.sources import AutoDerivedSourceParams, FieldSource
    from tests.core.factories import make_template_variable

    auto_derived_var = make_template_variable(
        template_variable="ecf_title",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="ecf_full"),
    )
    # Agent (incorrectly) emitted with read_only=False:
    auto_derived_var.read_only = False
    other_var = make_template_variable(template_variable="case_number")

    extract_result = TemplateAgentOutput(template_spec=[auto_derived_var, other_var])
    _patch_invoke_sequence(monkeypatch, [extract_result])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    result = await TemplateAgent.run("doc")

    by_name = {v.template_variable: v for v in result.template_spec}
    assert by_name["ecf_title"].read_only is True
    assert by_name["case_number"].read_only is False


# ─── auto-map well-known case identifiers to case_vector ──────────────


@pytest.mark.unit
async def test_run_auto_maps_case_identifiers_to_case_vector(monkeypatch):
    """chapter, debtor_name, case_number come back from extract with source=None
    and get auto-mapped to FieldSource.CASE_VECTOR with null source_params."""
    extract_result = TemplateAgentOutput(
        template_spec=[
            make_template_variable(template_variable="chapter", source=None),
            make_template_variable(template_variable="debtor_name", source=None),
            make_template_variable(template_variable="case_number", source=None),
        ],
    )
    _patch_invoke_sequence(monkeypatch, [extract_result])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    result = await TemplateAgent.run("doc")

    by_name = {v.template_variable: v for v in result.template_spec}
    for name in ("chapter", "debtor_name", "case_number"):
        assert by_name[name].source == FieldSource.CASE_VECTOR, name
        assert by_name[name].source_params is None, name


@pytest.mark.unit
async def test_run_auto_map_respects_prior_constants_assignment(monkeypatch):
    """If the constants-mapping pass assigned a well-known variable to
    constants, the auto-map must NOT override it — only source=None gets
    auto-mapped."""
    # Extract emits debtor_name with source=None. Constants pass re-emits it
    # with source=constants (contrived, but validates the precedence rule).
    extract_result = TemplateAgentOutput(
        template_spec=[
            make_template_variable(
                template_variable="debtor_name",
                template_property_marker="Acme Corp",
                source=None,
            ),
        ],
    )
    mapped_result = TemplateAgentOutput(
        template_spec=[
            make_template_variable(
                template_variable="debtor_name",
                template_property_marker="Acme Corp",
                source=FieldSource.CONSTANTS,
                source_params=ConstantsSourceParams(short_code="ACME_CORP"),
            ),
        ],
    )
    _patch_invoke_sequence(monkeypatch, [extract_result, mapped_result])
    monkeypatch.setattr(
        ReferenceDataRepository,
        "list",
        AsyncMock(return_value=[_FakeRef("ACME_CORP")]),
    )

    result = await TemplateAgent.run("doc")

    assert result.template_spec[0].source == FieldSource.CONSTANTS
    assert isinstance(result.template_spec[0].source_params, ConstantsSourceParams)
    assert result.template_spec[0].source_params.short_code == "ACME_CORP"


@pytest.mark.unit
async def test_run_auto_map_leaves_other_variables_untouched(monkeypatch):
    """Variables outside any auto-map set (e.g. employment_description) keep
    source=None after the auto-map runs."""
    extract_result = TemplateAgentOutput(
        template_spec=[
            make_template_variable(template_variable="chapter", source=None),
            make_template_variable(template_variable="employment_description", source=None),
        ],
    )
    _patch_invoke_sequence(monkeypatch, [extract_result])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    result = await TemplateAgent.run("doc")

    by_name = {v.template_variable: v for v in result.template_spec}
    assert by_name["chapter"].source == FieldSource.CASE_VECTOR
    assert by_name["employment_description"].source is None


# ─── auto-map petition_filing_date to gmail (Voluntary Petition) ──────


@pytest.mark.unit
async def test_run_auto_maps_petition_filing_date_to_gmail(monkeypatch):
    """petition_filing_date with source=None gets gmail source + Voluntary
    Petition subject/body queries."""
    from src.core.agents.types.sources import GmailSourceParams

    extract_result = TemplateAgentOutput(
        template_spec=[
            make_template_variable(template_variable="petition_filing_date", source=None),
        ],
    )
    _patch_invoke_sequence(monkeypatch, [extract_result])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    result = await TemplateAgent.run("doc")

    var = result.template_spec[0]
    assert var.source == FieldSource.GMAIL
    assert isinstance(var.source_params, GmailSourceParams)
    assert var.source_params.subject_query == "Voluntary Petition"
    assert var.source_params.body_query == "Voluntary Petition"


@pytest.mark.unit
async def test_run_petition_filing_date_auto_map_respects_prior_assignment(monkeypatch):
    """If a prior pass already set the source, the gmail auto-map leaves it alone."""
    from src.core.agents.types.sources import VectorSourceParams

    extract_result = TemplateAgentOutput(
        template_spec=[
            make_template_variable(
                template_variable="petition_filing_date",
                source=FieldSource.LAW_PRACTICE_VECTOR,
                source_params=VectorSourceParams(text_query="petition filing date"),
            ),
        ],
    )
    _patch_invoke_sequence(monkeypatch, [extract_result])
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))

    result = await TemplateAgent.run("doc")

    var = result.template_spec[0]
    assert var.source == FieldSource.LAW_PRACTICE_VECTOR
    assert isinstance(var.source_params, VectorSourceParams)


# ─── rule 17: stacked (name, email) pair recognition ──────────────────


@pytest.mark.unit
def test_prompt_rule_17_requires_pairing_name_and_email_in_one_variable():
    """Lock the load-bearing wording of rule 17 so future prompt edits
    don't accidentally drop the pair-recognition guidance, the
    `\\n`-joined marker shape, the document-context prefix requirement,
    the no-identity-baking rule, the institution-name broadening, the
    extract-ALL emphasis, or the 3-recipient worked example.
    """
    from src.core.agents.llm.template.prompt_builder import TEMPLATE_EXTRACT_PROMPT
    assert "Stacked contact-info pairs" in TEMPLATE_EXTRACT_PROMPT
    assert "emit a SINGLE variable" in TEMPLATE_EXTRACT_PROMPT
    # The `\n`-joined marker shape is load-bearing — must survive prompt edits.
    assert r"Timothy R Qualls\nstalevich@yvlaw.net" in TEMPLATE_EXTRACT_PROMPT
    # Naming rule 1 — context-driven prefix (not hardcoded).
    assert "DOCUMENT-CONTEXT prefix" in TEMPLATE_EXTRACT_PROMPT
    # Naming rule 3 — ordinal `_N` suffix, not recipient identity.
    assert "ORDINAL suffix" in TEMPLATE_EXTRACT_PROMPT
    # Explicit WRONG examples must stay so the rule's anti-patterns are
    # named in the prompt.
    assert "service_recipient_qualls" in TEMPLATE_EXTRACT_PROMPT
    # Institution-name broadening — "Office of the US Trustee" was the
    # exact failure mode that prompted this; must stay in the prompt.
    assert "Office of the US Trustee" in TEMPLATE_EXTRACT_PROMPT
    assert "institution / entity name" in TEMPLATE_EXTRACT_PROMPT
    # Extract-ALL emphasis — agent under-extracted in multi-recipient
    # lists when this wording was missing.
    assert "Do NOT stop after the first pair" in TEMPLATE_EXTRACT_PROMPT
    # Section-kind requirement — bare `cos_section_N` is ambiguous when
    # a CoS has both email AND mail blocks; the middle word disambiguates.
    assert "<section_kind>" in TEMPLATE_EXTRACT_PROMPT
    assert "cos_email_section_1" in TEMPLATE_EXTRACT_PROMPT
    assert "cos_email_section_3" in TEMPLATE_EXTRACT_PROMPT
    # The three-part composed shape must appear so the agent has the
    # full template internalized.
    assert "<doc_context>_<section_kind>_section_N" in TEMPLATE_EXTRACT_PROMPT
