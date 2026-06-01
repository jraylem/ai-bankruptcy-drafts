"""Template agent — analyzes a raw legal document and returns a TemplateAgentOutput.

Two-call orchestration: first extract every unique variable value from the
document as a TemplateVariable, then map each extracted value to a reusable
constants short_code if one matches. Raises HTTPException on extract-phase
failure; the constants-mapping phase is best-effort (extract-only result is
returned on mapping failure).
"""

import json
import logging

from fastapi import HTTPException
from pydantic import BaseModel, Field

from src.core.common.storage.database import ReferenceDataRepository

from ...types.sources import ConstantsSourceParams, FieldSource, GmailSourceParams
from ...types.spec import TemplateVariable
from ..base import Agent
from .prompt_builder import (
    TEMPLATE_EXTRACT_PROMPT,
    TEMPLATE_MAP_CONSTANTS_PROMPT,
    _format_ignored_texts_block,
    _format_merges_block,
    _format_previous_spec_block,
    _format_reference_data_block,
    _format_regeneration_instruction_block,
)

logger = logging.getLogger(__name__)


class TemplateAgentOutput(BaseModel):
    """Structured output containing all template variables extracted from a legal document."""
    template_spec: list[TemplateVariable] = Field(default=[], description="List of all template variables identified in the document")


class MergeInstruction(BaseModel):
    """Input to TemplateAgent.run requesting a merge of source variables into one.

    At this layer the name is always resolved (auto-generation happened
    upstream in the HTTP layer); the agent just sees the final
    new_variable_name string.
    """
    new_variable_name: str
    source_variables: list[str]
    description: str | None = None


class TemplateAgent(Agent[TemplateAgentOutput]):
    """Analyze a legal document and return every unique variable value as a TemplateVariable with constants mapped where applicable."""

    output_type = TemplateAgentOutput
    max_tokens = 30000
    tags = ["core", "agent", "template"]
    cost_kind = "template"

    @classmethod
    async def run(
        cls,
        document_content: str,
        ignored_texts: list[str] | None = None,
        merges: list[MergeInstruction] | None = None,
        regeneration_instruction: str | None = None,
        previous_spec: list[TemplateVariable] | None = None,
    ) -> TemplateAgentOutput:
        """Run the two-call template-analysis pipeline (extract variables, then map constants).

        `regeneration_instruction` is the author's optional free-form
        steering for a re-extraction pass — surfaced to the extract prompt
        as a high-priority directive (e.g. *"merge claim_no and
        claim_no_title"*, *"don't extract the clerk address"*).

        `previous_spec` is the author's confirmed baseline from the prior
        iteration. When supplied, the agent is instructed to preserve
        every baseline entry verbatim (name, marker, source, source_params,
        aliases, instruction, description) UNLESS one of the user-signal
        blocks (merges / ignored_texts / regeneration_instruction)
        explicitly contradicts the entry. Initial-generate runs pass `None`.

        Raises HTTPException(502) on extract-phase LLM failure and
        HTTPException(422) on an empty extract result. Constants-mapping
        failures are best-effort — the extract-only result is returned.
        """
        previous_spec_block = _format_previous_spec_block(previous_spec)
        ignored_texts_block = _format_ignored_texts_block(ignored_texts)
        merges_block = _format_merges_block(merges)
        regeneration_instruction_block = _format_regeneration_instruction_block(
            regeneration_instruction,
        )
        try:
            extract_result = await cls._invoke(
                TEMPLATE_EXTRACT_PROMPT.format(
                    document_content=document_content,
                    previous_spec_block=previous_spec_block,
                    ignored_texts_block=ignored_texts_block,
                    merges_block=merges_block,
                    regeneration_instruction_block=regeneration_instruction_block,
                ),
                run_name="TemplateExtract",
            )
        except Exception as e:
            logger.error(f"TemplateAgent extract LLM error: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"Template extraction failed: {e}",
            )

        if extract_result is None:
            raise HTTPException(
                status_code=422,
                detail="Could not extract template variables from document (empty LLM result)",
            )

        _force_read_only_on_auto_derived(extract_result.template_spec)

        ref_data_list = await ReferenceDataRepository.list()
        if not ref_data_list or not extract_result.template_spec:
            _auto_map_case_vector_variables(extract_result.template_spec)
            _auto_map_gmail_voluntary_petition_variables(extract_result.template_spec)
            return extract_result

        reference_data_block = _format_reference_data_block(ref_data_list)
        extracted_spec_json = json.dumps(
            [var.model_dump(mode="json") for var in extract_result.template_spec],
            indent=2,
        )

        try:
            mapped_result = await cls._invoke(
                TEMPLATE_MAP_CONSTANTS_PROMPT.format(
                    extracted_spec=extracted_spec_json,
                    reference_data_block=reference_data_block,
                ),
                run_name="TemplateMapConstants",
            )
        except Exception as e:
            logger.warning(
                f"TemplateAgent constants-mapping LLM error: {e}; "
                "returning extracted spec without constants mapping"
            )
            _auto_map_case_vector_variables(extract_result.template_spec)
            _auto_map_gmail_voluntary_petition_variables(extract_result.template_spec)
            return extract_result

        if mapped_result is None:
            _auto_map_case_vector_variables(extract_result.template_spec)
            _auto_map_gmail_voluntary_petition_variables(extract_result.template_spec)
            return extract_result

        known_codes = {ref.short_code for ref in ref_data_list}
        _drop_unknown_constants_mappings(mapped_result.template_spec, known_codes)
        _force_read_only_on_auto_derived(mapped_result.template_spec)
        _auto_map_case_vector_variables(mapped_result.template_spec)
        _auto_map_gmail_voluntary_petition_variables(mapped_result.template_spec)
        return mapped_result


_AUTO_CASE_VECTOR_VARIABLES: frozenset[str] = frozenset({
    "chapter",
    "debtor_name",
    "case_number",
})


_AUTO_GMAIL_VOLUNTARY_PETITION_VARIABLES: frozenset[str] = frozenset({
    "petition_filing_date",
})


def _auto_map_case_vector_variables(template_spec: list[TemplateVariable]) -> None:
    """Assign source=CASE_VECTOR to well-known always-case-specific variables.

    Covers `chapter`, `debtor_name`, `case_number` — the three values that
    appear in every bankruptcy filing and are always sourced from the
    case_file pgvector collection. Only mutates variables whose source is
    currently None; any prior mapping (constants, auto_derived) is
    respected. Leaves source_params alone — the auto-mapped fields use
    property-name-derived queries by default, but the author can still
    add an explicit `CaseVectorSourceParams.text_query` later if the
    auto-derivation phrasing is wrong for a specific case.
    """
    for var in template_spec:
        if var.source is not None:
            continue
        if (var.template_variable or "").lower() in _AUTO_CASE_VECTOR_VARIABLES:
            var.source = FieldSource.CASE_VECTOR


def _auto_map_gmail_voluntary_petition_variables(template_spec: list[TemplateVariable]) -> None:
    """Assign source=GMAIL with subject/body queries='Voluntary Petition' to well-known variables.

    Covers `petition_filing_date` — the date the debtor filed their
    voluntary petition, which always appears in the ECF acceptance email
    whose subject and body both contain 'Voluntary Petition'. Only mutates
    variables whose source is currently None; any prior mapping is
    respected.
    """
    for var in template_spec:
        if var.source is not None:
            continue
        if (var.template_variable or "").lower() in _AUTO_GMAIL_VOLUNTARY_PETITION_VARIABLES:
            var.source = FieldSource.GMAIL
            var.source_params = GmailSourceParams(
                subject_query="Voluntary Petition",
                body_query="Voluntary Petition",
            )


def _force_read_only_on_auto_derived(template_spec: list[TemplateVariable]) -> None:
    """Defensively flag every auto_derived_from_variable variable as read_only.

    The agent prompt asks for this but LLMs can forget; keeping the flag
    in lock-step with the source type at the boundary means downstream code
    (FE, validators) can rely on `read_only=true ⇔ AUTO_DERIVED_FROM_VARIABLE`.
    """
    for var in template_spec:
        if var.source == FieldSource.AUTO_DERIVED_FROM_VARIABLE:
            var.read_only = True


def _drop_unknown_constants_mappings(
    template_spec: list[TemplateVariable],
    known_codes: set[str],
) -> None:
    """Demote any source=constants entry whose short_code isn't in known_codes.

    The TEMPLATE_MAP_CONSTANTS_PROMPT instructs the LLM to only map against
    provided reusable constants, but LLMs occasionally hallucinate short_codes
    that don't exist. Silently demoting those mappings back to source=null
    keeps downstream validation honest — the server-side short_code existence
    check in template/service.py will then 400 any that slip through.
    """
    for var in template_spec:
        if var.source != FieldSource.CONSTANTS:
            continue
        params = var.source_params
        if not isinstance(params, ConstantsSourceParams):
            continue
        if params.short_code not in known_codes:
            logger.warning(
                "TemplateAgent.run: dropping hallucinated constants mapping "
                "for variable '%s' -> short_code '%s' (not in reference_data)",
                var.template_variable,
                params.short_code,
            )
            var.source = None
            var.source_params = None
