"""generate_template_v2 — the main composer flow.

Mirrors v1's `generate_template`:
1. Mint a UUID `template_id`.
2. Upload `original.docx` to R2 under `template_v2/{template_id}/`.
3. Run `TemplateAgentV2.run(parsed_content, template_role, parent_spec)`
   → `TemplateAgentV2Output { template_spec: list[TemplateFieldV2Extract] }`.
4. Run `DocxTemplateService.create_template(file_content, template_spec)`
   to place `[[placeholders]]` in the .docx (read-only import of pure
   utility — bridges v2 spec into v1's TemplateVariable shape for the
   placement pass).
5. Drop orphan variables whose placeholders didn't make it into the
   rendered docx (LLM hallucinations + sub-tokens swallowed by longer
   markers).
6. Upload the rendered `template.docx` to R2 under same prefix.
7. Persist `templates_v2` row + `template_fields_v2` rows in one
   atomic flow.
8. Return `TemplateGenerateResponseV2` with presigned URLs + the spec
   (FE renders the wizard against this).

Wrapped in `cost_attribution(..., semantic_id_kind="template_v2")` so
v2 composer spend lands in its own Costs dashboard bucket.
"""

import logging
import uuid

from src.core.agents.types.spec import TemplateVariable as V1TemplateVariable
from src.core.common.cost_tracking import cost_attribution
from src.core.common.documents.docx_template import DocxTemplateService
from src.core.common.storage.r2 import r2_service

from src.core.studio_v2.agents.template import (
    MergeInstructionV2,
    TemplateAgentV2,
    TemplateFieldV2Extract,
)
from src.core.studio_v2.repositories import (
    TemplateFieldsV2Repository,
    TemplatesV2Repository,
)

from .parse import parse_document_v2
from .schemas import (
    DocumentParseResponseV2,
    MergeOperationV2,
    TemplateGenerateResponseV2,
)

logger = logging.getLogger(__name__)

R2_PREFIX_TEMPLATE_V2 = "template_v2"


async def generate_template_v2(
    template_name: str,
    parsed_document: DocumentParseResponseV2,
    file_content: bytes,
    *,
    template_role: str = "single",
    parent_template_spec: list[TemplateFieldV2Extract] | None = None,
    firm_id: str | None = None,
    user_id: str | None = None,
) -> TemplateGenerateResponseV2:
    """Full composer flow for a new template upload.

    `template_role` controls TemplateAgentV2 heuristic H3
    (value_from_parent_bundle suggestions for part_of_packet children).
    Cost attribution wraps the LLM calls so the per-firm Costs
    dashboard can break out v2 composer spend.
    """
    template_id = str(uuid.uuid4())

    # 0. Flatten any Word field codes (`{ DATE }`, content controls, etc.)
    #    so the persisted bytes + the agent's parsed view + every downstream
    #    viewer (Syncfusion, Word, OnlyOffice) all see the SAME frozen
    #    text. Without this, a Word DATE field renders today's value in
    #    Syncfusion's preview while python-docx returns the cached fallback,
    #    breaking the agent's marker / find-and-replace alignment.
    file_content = DocxTemplateService.flatten_word_fields(file_content)
    # Re-parse against the flattened bytes so the agent sees what the
    # persisted source will preview as.
    parsed_document = await parse_document_v2(
        filename=parsed_document.document_id,
        file_content=file_content,
    )

    # 1. Upload original.docx FIRST (so even if the LLM call fails, the
    #    paralegal can re-run regenerate against the persisted bytes).
    await r2_service.upload_file(
        file_content=file_content,
        template_id=template_id,
        filename="original.docx",
        prefix=R2_PREFIX_TEMPLATE_V2,
    )
    original_doc_url = await r2_service.get_presigned_url(
        template_id,
        "original.docx",
        prefix=R2_PREFIX_TEMPLATE_V2,
    )

    # 2. Run the LLM extractor + create_template + upload template.docx.
    with cost_attribution(
        firm_id=firm_id,
        user_id=user_id,
        semantic_id=template_id,
        semantic_id_kind="template_v2",
    ):
        template_spec, template_doc_url = await _run_agent_and_upload_template_docx(
            template_id=template_id,
            parsed_content=parsed_document.content,
            file_content=file_content,
            template_role=template_role,
            parent_template_spec=parent_template_spec,
        )

    # 3. Persist templates_v2 row + template_fields_v2 rows.
    await TemplatesV2Repository.create(
        template_id=template_id,
        name=template_name,
        config={"role": template_role, "companions": []},
        original_doc_url=original_doc_url,
        template_doc_url=template_doc_url,
        firm_id=firm_id,
    )
    if template_spec:
        await TemplateFieldsV2Repository.create_many(
            template_id=template_id,
            fields=[_to_create_dict(f) for f in template_spec],
        )

    return TemplateGenerateResponseV2(
        template_id=template_id,
        name=template_name,
        template_spec=template_spec,
        original_doc_url=original_doc_url,
        template_doc_url=template_doc_url,
    )


async def _run_agent_and_upload_template_docx(
    template_id: str,
    parsed_content: str,
    file_content: bytes,
    *,
    template_role: str,
    parent_template_spec: list[TemplateFieldV2Extract] | None = None,
    ignored_texts: list[str] | None = None,
    merges: list[MergeOperationV2] | None = None,
    regeneration_instruction: str | None = None,
    previous_spec: list[TemplateFieldV2Extract] | None = None,
) -> tuple[list[TemplateFieldV2Extract], str]:
    """Run TemplateAgentV2, render the placeholder-marked .docx, upload
    to R2, return (cleaned_spec, presigned_url). Shared by /generate and
    /regenerate.
    """
    merge_instructions = (
        [
            MergeInstructionV2(
                new_variable_name=m.resolve_variable_name(),
                source_variables=m.source_variables,
                description=m.description,
            )
            for m in merges
        ]
        if merges
        else None
    )
    llm_result = await TemplateAgentV2.run(
        parsed_content,
        template_role=template_role,
        parent_template_spec=parent_template_spec,
        ignored_texts=ignored_texts,
        merges=merge_instructions,
        regeneration_instruction=regeneration_instruction,
        previous_spec=previous_spec,
    )

    template_doc_content = DocxTemplateService.create_template(
        file_content=file_content,
        template_spec=_adapt_to_v1_template_variables(llm_result.template_spec),
    )
    cleaned_spec = _drop_orphan_variables_v2(template_doc_content, llm_result.template_spec)

    await r2_service.upload_file(
        file_content=template_doc_content,
        template_id=template_id,
        filename="template.docx",
        prefix=R2_PREFIX_TEMPLATE_V2,
    )
    template_doc_url = await r2_service.get_presigned_url(
        template_id,
        "template.docx",
        prefix=R2_PREFIX_TEMPLATE_V2,
    )
    return cleaned_spec, template_doc_url


def _adapt_to_v1_template_variables(
    spec: list[TemplateFieldV2Extract],
) -> list[V1TemplateVariable]:
    """Adapter — v2 TemplateFieldV2Extract → v1 TemplateVariable shape
    just for `DocxTemplateService.create_template` consumption.

    create_template only reads template_property_marker,
    template_property_marker_aliases, template_variable_string,
    template_identifying_text_match — those are common across v1 + v2.
    All other v1 fields (source, source_params, instruction, etc.) are
    LEFT NULL since create_template doesn't read them.
    """
    return [
        V1TemplateVariable(
            template_variable=f.template_variable,
            template_index=f.template_index,
            template_property_marker=f.template_property_marker,
            template_property_marker_aliases=f.template_property_marker_aliases,
            template_variable_string=f.template_variable_string,
            template_identifying_text_match=f.template_identifying_text_match,
            description=f.description,
            source=None,
            source_params=None,
        )
        for f in spec
    ]


def _drop_orphan_variables_v2(
    template_bytes: bytes,
    template_spec: list[TemplateFieldV2Extract],
) -> list[TemplateFieldV2Extract]:
    """Drop variables whose [[placeholder]] does not appear in the
    rendered template.docx.

    Catches LLM hallucinations + sub-tokens swallowed by longer markers
    (e.g. 'her' extracted as its own variable when it lived inside
    another variable's marker — create_template's longest-first pass
    consumes the parent marker, so '[[her_var]]' never makes it into
    the template docx). Without this filter, the wizard would surface
    dead variables the paralegal can never edit usefully.

    Virtual parents (template_variable_string is None — Rule 16/18) are
    PRESERVED regardless; they never render directly, so absence from
    the docx is expected.
    """
    placeholders_to_check = [
        f.template_variable_string
        for f in template_spec
        if f.template_variable_string is not None
    ]
    if not placeholders_to_check:
        return template_spec

    missing = DocxTemplateService.find_missing_placeholders(
        template_bytes, placeholders_to_check,
    )
    if not missing:
        return template_spec

    surviving: list[TemplateFieldV2Extract] = []
    for f in template_spec:
        if f.template_variable_string in missing:
            logger.info(
                "_drop_orphan_variables_v2: dropping '%s' "
                "(template_variable_string=%s not found in rendered docx)",
                f.template_variable,
                f.template_variable_string,
            )
            continue
        surviving.append(f)
    return surviving


def _to_create_dict(f: TemplateFieldV2Extract) -> dict:
    """Adapter — TemplateFieldV2Extract → dict shape consumed by
    TemplateFieldsV2Repository.create_many. Drops
    template_variable_string (lives in the docx; not persisted on the
    row) and serializes params via Pydantic so JSONB-safe types
    propagate cleanly.
    """
    return {
        "template_variable": f.template_variable,
        "template_property_marker": f.template_property_marker,
        "template_property_marker_aliases": (
            f.template_property_marker_aliases or None
        ),
        "template_identifying_text_match": f.template_identifying_text_match,
        "description": f.description,
        "template_index": f.template_index,
        "params": f.params.model_dump(mode="json") if f.params is not None else None,
    }
