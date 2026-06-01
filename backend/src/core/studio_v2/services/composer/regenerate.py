"""regenerate_template_v2 — re-extract on regeneration.

Mirrors v1's `regenerate_template`:
1. Load existing templates_v2 row + template_fields_v2 rows.
2. Download the persisted original.docx from R2.
3. Re-parse via parse_document_v2.
4. Re-run TemplateAgentV2 with previous_spec + merges + ignored_texts +
   regeneration_instruction.
5. Re-render template.docx via DocxTemplateService.create_template;
   overwrite the existing template.docx in R2.
6. Diff the new spec against existing template_fields_v2 rows by
   template_variable name; INSERT new, UPDATE composer-fields on kept
   (PRESERVING wizard-saved `params`), DELETE dropped.
7. Touch templates_v2.updated_at. **Do NOT touch published_at /
   published_spec** — re-extract is an unpublished change; if the
   template was published, the live version stays frozen until the
   paralegal re-publishes.
8. Return TemplateRegenerateDiffV2 — FE renders a "what changed" panel.

Wrapped in cost_attribution(..., semantic_id_kind="template_v2") for
Costs dashboard rollup.
"""

import logging

from fastapi import HTTPException

from src.core.common.cost_tracking import cost_attribution
from src.core.common.storage.r2 import r2_service

from src.core.studio_v2.agents.template import TemplateFieldV2Extract
from src.core.studio_v2.repositories import (
    TemplateFieldsV2Repository,
    TemplatesV2Repository,
)
from src.core.studio_v2.types.wizard_sources import WizardSourceParams

from .generate import (
    R2_PREFIX_TEMPLATE_V2,
    _run_agent_and_upload_template_docx,
    _to_create_dict,
)
from .parse import parse_document_v2
from .schemas import MergeOperationV2, TemplateRegenerateDiffV2

logger = logging.getLogger(__name__)


async def regenerate_template_v2(
    template_id: str,
    *,
    ignored_texts: list[str] | None = None,
    merges: list[MergeOperationV2] | None = None,
    regeneration_instruction: str | None = None,
    parent_template_spec: list[TemplateFieldV2Extract] | None = None,
    firm_id: str | None = None,
    user_id: str | None = None,
) -> TemplateRegenerateDiffV2:
    """Re-extract a v2 template with author-supplied merges /
    ignored-texts / regeneration_instruction.

    The diff against existing template_fields_v2 rows preserves
    wizard-saved `params` on kept fields — paralegal's wizard work
    survives across re-extracts.
    """
    template = await TemplatesV2Repository.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    if not template.original_doc_url:
        raise HTTPException(
            status_code=400,
            detail=f"Template {template_id} has no original_doc_url — cannot regenerate",
        )

    existing_rows = await TemplateFieldsV2Repository.list_for_template(template_id)
    previous_spec = [_row_to_extract(row) for row in existing_rows]
    existing_names = {row.template_variable for row in existing_rows}

    file_content = await r2_service.download_file(
        template_id=template_id,
        filename="original.docx",
        prefix=R2_PREFIX_TEMPLATE_V2,
    )
    # Defensive flatten — generate_template_v2 already flattened on upload,
    # but re-flatten here so older templates uploaded before flattening
    # shipped don't regress on re-extract.
    from src.core.common.documents.docx_template import DocxTemplateService
    file_content = DocxTemplateService.flatten_word_fields(file_content)
    parsed = await parse_document_v2(filename="original.docx", file_content=file_content)

    template_role = (template.config or {}).get("role", "single")

    with cost_attribution(
        firm_id=firm_id,
        user_id=user_id,
        semantic_id=template_id,
        semantic_id_kind="template_v2",
    ):
        new_spec, template_doc_url = await _run_agent_and_upload_template_docx(
            template_id=template_id,
            parsed_content=parsed.content,
            file_content=file_content,
            template_role=template_role,
            parent_template_spec=parent_template_spec,
            ignored_texts=ignored_texts,
            merges=merges,
            regeneration_instruction=regeneration_instruction,
            previous_spec=previous_spec,
        )

    diff = await TemplateFieldsV2Repository.re_extract_diff_apply(
        template_id=template_id,
        new_fields=[_to_create_dict(f) for f in new_spec],
    )

    # Bump updated_at on the parent row so has_unpublished_changes
    # (computed as updated_at > published_at) flips true if this
    # template was previously published.
    await TemplatesV2Repository.update(
        template_id=template_id,
        template_doc_url=template_doc_url,
    )

    # Surviving names that had non-null params on the prior row are the
    # "preserved_params" set — useful for the FE's "what changed" panel
    # to badge variables whose wizard config carried over.
    preserved_params = [
        row.template_variable
        for row in existing_rows
        if row.params is not None
        and row.template_variable in existing_names
        and row.template_variable in set(diff.updated)
    ]

    return TemplateRegenerateDiffV2(
        template_id=template_id,
        inserted=diff.inserted,
        updated=diff.updated,
        deleted=diff.deleted,
        preserved_params=preserved_params,
        template_doc_url=template_doc_url,
    )


def _row_to_extract(row) -> TemplateFieldV2Extract:
    """Adapter — template_fields_v2 ORM row → TemplateFieldV2Extract.

    Used to build `previous_spec` for the re-extract LLM call so the
    agent preserves baseline entries verbatim. The `template_variable_string`
    is synthesized as `[[<name>]]` (the persistence layer doesn't store
    it; we reconstruct from the variable name + the convention
    template.docx uses).
    """
    params = WizardSourceParams.model_validate(row.params) if row.params else None
    return TemplateFieldV2Extract(
        template_variable=row.template_variable,
        template_index=row.template_index,
        template_property_marker=row.template_property_marker,
        template_property_marker_aliases=row.template_property_marker_aliases or [],
        template_variable_string=f"[[{row.template_variable}]]"
        if row.template_property_marker is not None
        else None,
        template_identifying_text_match=row.template_identifying_text_match,
        description=row.description,
        params=params,
    )
