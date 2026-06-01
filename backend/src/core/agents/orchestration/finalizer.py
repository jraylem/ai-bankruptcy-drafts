"""Shared finalizer for the dry-run and draft flows.

Both flows end the same way: download the committed template.docx, run the
reco-chip heal pass, fill the placeholders with resolved values, upload the
filled docx to R2, and surface any warnings the caller needs to present.

This module owns that shared tail. The dry-run and draft services call
finalize_run(...) and wrap its FinalizedRun into their flow-specific
Response type.
"""

import uuid

from pydantic import BaseModel

from src.core.agents.llm.user_input_heal import UserInputHealAgent
from src.core.agents.resolvers.auto_derived_resolver import AutoDerivedResolver
from src.core.agents.types.resolution import ResolvedTemplateValue
from src.core.agents.types.spec import AgentConfig
from src.core.common.documents.docx_template import DocxTemplateService
from src.core.common.storage.r2 import r2_service


class FinalizedRun(BaseModel):
    """Return type of finalize_run, carrying the data the caller needs to build a DryRunResponse or DraftResponse.

    `filled_bytes` is the raw filled docx — kept on the result so the
    bundling engine can extract the parent's produced draft text for
    `extract_from_draft` slot resolution without a second R2 round-trip.
    The pydantic shape carries it as bytes via `arbitrary_types_allowed`.
    """
    model_config = {"arbitrary_types_allowed": True}

    resolved_values: list[ResolvedTemplateValue]
    generated_doc_url: str
    r2_object_key: str
    unresolved: list[str]
    warnings: list[str]
    filled_bytes: bytes | None = None


async def finalize_run(
    template_id: str,
    case_id: str,
    agent_config: AgentConfig,
    all_resolved: list[ResolvedTemplateValue],
    output_prefix: str,
    template_bytes: bytes | None = None,
    resource_key: str | None = None,
) -> FinalizedRun:
    """Run the shared fill/upload/warn tail common to dry-run and draft.

    `output_prefix` is the R2 key prefix ("dry_run" or "draft") that scopes
    the generated docx under the case's folder. `template_bytes` is the
    pre-downloaded template.docx — when provided, the R2 download is
    skipped (the dry_run / draft service downloaded it once upfront so
    the web-search-enhance resolver could use it). When None, finalizer
    falls back to downloading itself.

    `resource_key` (Phase 1 of unfiled-petitions) names the case's R2
    folder for the generated docx upload. Defaults to `case_id` for
    backwards compat — callers passing a UUID will (for legacy cases)
    land the generated docx under a different prefix than the petition.
    Pleading and dry-run services pass the right value via the
    DraftAgentContext's `resource_key`.
    """
    rk = resource_key or case_id
    if template_bytes is None:
        template_bytes = await r2_service.download_file(
            template_id=template_id,
            filename="template.docx",
            prefix="template",
        )

    auto_derived = await AutoDerivedResolver.apply(
        agent_config.template_fields, all_resolved,
    )
    all_resolved = all_resolved + auto_derived

    healed_resolved = await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=all_resolved,
    )

    resolved_dict = {rv.property_name: rv.value for rv in healed_resolved if rv.value}
    filled_bytes, unresolved = DocxTemplateService.fill_template(
        template_bytes=template_bytes,
        template_fields=agent_config.template_fields,
        resolved_values=resolved_dict,
    )

    generated_filename = f"{output_prefix}/{uuid.uuid4()}.docx"
    r2_object_key = await r2_service.upload_file(
        file_content=filled_bytes,
        template_id=rk,
        filename=generated_filename,
        prefix="cases",
    )
    generated_doc_url = await r2_service.get_presigned_url(
        template_id=rk,
        filename=generated_filename,
        prefix="cases",
    )

    return FinalizedRun(
        resolved_values=healed_resolved,
        generated_doc_url=generated_doc_url,
        r2_object_key=r2_object_key,
        unresolved=unresolved,
        warnings=_build_warnings(healed_resolved, unresolved),
        filled_bytes=filled_bytes,
    )


def _build_warnings(
    resolved_values: list[ResolvedTemplateValue],
    unresolved: list[str],
) -> list[str]:
    """Surface unresolved placeholders and low-confidence extractions as human-readable warnings."""
    warnings: list[str] = []
    for placeholder in unresolved:
        warnings.append(f"Unresolved placeholder: {placeholder}")
    for rv in resolved_values:
        if rv.confidence == "low":
            warnings.append(
                f"Low-confidence extraction for '{rv.property_name}': {rv.reasoning}"
            )
    return warnings
