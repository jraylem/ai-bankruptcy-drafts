"""TemplateAgentV2 — composer-time variable extraction agent.

Two-call orchestration mirroring v1's `TemplateAgent`:
1. **Extract** — analyzes the document and emits a list of
   `TemplateFieldV2Extract` with `params` pre-populated per the
   source-suggestion heuristics.
2. **Map constants** — second pass that maps extracted values to
   reusable firm constants. Best-effort; the extract-only result is
   returned on mapping failure.

Subclasses v1's `Agent[T]` base class (read-only import — pure
infrastructure under the no-touch rule's "shared utilities can be
imported" carve-out). Reuses `cost_attribution` so v2 template-author
spend lands in the `template_v2` semantic_id_kind bucket.
"""

import logging

from fastapi import HTTPException
from pydantic import BaseModel, Field

from src.core.studio_v2.agents._v1_base import StudioV2Agent
from src.core.common.storage.database import ReferenceDataRepository

from .prompt_builder import (
    TEMPLATE_EXTRACT_PROMPT_V2,
    TEMPLATE_MAP_CONSTANTS_PROMPT_V2,
    _format_ignored_texts_block,
    _format_merges_block,
    _format_previous_spec_block,
    _format_reference_data_block,
    _format_regeneration_instruction_block,
    _format_template_role_block,
)
from .schemas import TemplateFieldV2Extract

logger = logging.getLogger(__name__)


class TemplateAgentV2Output(BaseModel):
    """Structured output: list of TemplateFieldV2Extract.

    Composer service translates each into a `TemplateFieldV2` row +
    feeds the list to `DocxTemplateService.create_template` to place
    [[placeholders]] in the .docx.
    """
    template_spec: list[TemplateFieldV2Extract] = Field(
        default_factory=list,
        description="All template variables identified in the document",
    )


class MergeInstructionV2(BaseModel):
    """Input to TemplateAgentV2.run requesting a merge of source
    variables into one. The new_variable_name is resolved upstream
    (auto-generation happens in the HTTP layer); the agent just sees
    the final string.
    """
    new_variable_name: str
    source_variables: list[str]
    description: str | None = None


class TemplateAgentV2(StudioV2Agent[TemplateAgentV2Output]):
    """v2 composer-time variable extractor.

    Reuses v1's Agent base + cost_attribution machinery. Differs in:
    - Output type emits `WizardSourceParams` instead of v1's
      `source + source_params` pair.
    - Rules 10/10b/16/18 emission shape swapped to prompt-based
      `derived_from_variable` + `extraction_prompt`.
    - 5 source-suggestion heuristics pre-populate `params` defaults.
    - `template_role` + optional `parent_template_spec` inputs power
      heuristic H3 (value_from_parent_bundle for child-role templates).

    cost_kind = "template_v2" — separate bucket from v1's "template".
    """

    output_type = TemplateAgentV2Output
    max_tokens = 30000
    tags = ["core", "agent", "template_v2"]
    cost_kind = "template_v2"

    @classmethod
    async def run(
        cls,
        document_content: str,
        template_role: str = "single",
        parent_template_spec: list[TemplateFieldV2Extract] | None = None,
        ignored_texts: list[str] | None = None,
        merges: list[MergeInstructionV2] | None = None,
        regeneration_instruction: str | None = None,
        previous_spec: list[TemplateFieldV2Extract] | None = None,
    ) -> TemplateAgentV2Output:
        """Run the two-call pipeline (extract variables, then map constants).

        `template_role` ∈ {"single", "master", "part_of_packet"}. When
        "part_of_packet", `parent_template_spec` should be supplied so
        heuristic H3 (value_from_parent_bundle) can match v2 child vars
        against the lead's spec.

        `regeneration_instruction` is the author's optional free-form
        steering for a re-extraction pass; `previous_spec` is the
        author's confirmed baseline. Initial-generate runs pass both as
        None.

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
        template_role_block = _format_template_role_block(
            template_role,
            parent_template_spec,
        )

        try:
            extract_result = await cls._invoke(
                TEMPLATE_EXTRACT_PROMPT_V2.format(
                    document_content=document_content,
                    previous_spec_block=previous_spec_block,
                    ignored_texts_block=ignored_texts_block,
                    merges_block=merges_block,
                    regeneration_instruction_block=regeneration_instruction_block,
                    template_role_block=template_role_block,
                ),
                run_name="TemplateExtractV2",
                metadata={"template_role": template_role},
            )
        except Exception as e:
            logger.error("TemplateAgentV2 extract LLM error: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Template extraction LLM call failed: {e}",
            ) from e

        if extract_result is None or not extract_result.template_spec:
            raise HTTPException(
                status_code=422,
                detail="Template extraction returned no variables",
            )

        try:
            ref_data = await ReferenceDataRepository.list()
        except Exception as e:
            logger.warning(
                "TemplateAgentV2 reference_data fetch failed: %s; "
                "returning extract-only result",
                e,
            )
            return extract_result

        if not ref_data:
            return extract_result

        try:
            extracted_spec_json = "\n".join(
                v.model_dump_json(exclude_none=True)
                for v in extract_result.template_spec
            )
            ref_data_block = _format_reference_data_block(ref_data)
            mapping_result = await cls._invoke(
                TEMPLATE_MAP_CONSTANTS_PROMPT_V2.format(
                    extracted_spec=extracted_spec_json,
                    reference_data_block=ref_data_block,
                ),
                run_name="TemplateMapConstantsV2",
                metadata={"template_role": template_role},
            )
        except Exception as e:
            logger.warning(
                "TemplateAgentV2 constants-mapping LLM error: %s; "
                "returning extract-only result",
                e,
            )
            return extract_result

        if mapping_result is None or not mapping_result.template_spec:
            return extract_result

        if len(mapping_result.template_spec) != len(extract_result.template_spec):
            logger.warning(
                "TemplateAgentV2.run: constants-mapping returned %d entries vs "
                "%d extracted; falling back to extract-only result",
                len(mapping_result.template_spec),
                len(extract_result.template_spec),
            )
            return extract_result

        return mapping_result
