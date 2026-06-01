"""Composer routes — parse / generate / regenerate.

Mounted under /api/v3/studio (final paths: /api/v3/studio/composer/parse,
/api/v3/studio/composer/generate-template,
/api/v3/studio/templates/{id}/composer/regenerate-template).

Mirrors v1's `/api/v2/core/template/composer/*` endpoints but emits v2
schemas + persists to v2 tables.
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from src.auth.auth import get_current_user_optional
from src.auth.models import User

from src.core.studio_v2.services.composer import (
    DocumentParseResponseV2,
    MergeOperationV2,
    TemplateGenerateResponseV2,
    TemplateRegenerateDiffV2,
    generate_template_v2,
    parse_document_v2,
    regenerate_template_v2,
)

from .schemas import (
    GenerateTemplateRequest,
    RegenerateTemplateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/studio", tags=["Studio V2 - Composer"])


@router.post(
    "/composer/parse",
    response_model=DocumentParseResponseV2,
)
async def composer_parse(
    document: Annotated[UploadFile, File(description="The .docx file to parse")],
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Flatten an uploaded .docx into a single parsed-text blob +
    metadata for TemplateAgentV2's prompt. Stateless — does NOT
    persist anything. FE turns around and POSTs the content to
    /composer/generate-template.
    """
    if not document.filename or not document.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail="Only .docx uploads are supported",
        )
    content_bytes = await document.read()
    return await parse_document_v2(
        filename=document.filename,
        file_content=content_bytes,
    )


@router.post(
    "/composer/generate-template",
    response_model=TemplateGenerateResponseV2,
)
async def composer_generate_template(
    document: Annotated[UploadFile, File(description="The .docx file to generate from")],
    template_name: Annotated[str, Form(description="Display name for the new template")],
    template_role: Annotated[str, Form(description="single | master | part_of_packet")] = "single",
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Run the full Phase 1 composer flow against an uploaded .docx:
    parse → TemplateAgentV2 → DocxTemplateService.create_template →
    R2 upload → templates_v2 row + template_fields_v2 rows. Returns
    the seeded TemplateSpecV2 the FE renders in the wizard.

    Multipart form: `document` (.docx file) + `template_name` +
    optional `template_role` (default "single"). `parent_template_spec`
    is NOT accepted on this endpoint (Phase 1 composer doesn't have
    the bundle-companions wiring yet — heuristic H3 is deferred to
    Phase 2/3 when bundling lands fully).
    """
    if template_role not in ("single", "master", "part_of_packet"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid template_role={template_role!r}; "
                "must be one of: single, master, part_of_packet"
            ),
        )
    if not document.filename or not document.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail="Only .docx uploads are supported",
        )
    content_bytes = await document.read()
    parsed = await parse_document_v2(
        filename=document.filename,
        file_content=content_bytes,
    )
    return await generate_template_v2(
        template_name=template_name,
        parsed_document=parsed,
        file_content=content_bytes,
        template_role=template_role,
        firm_id=getattr(current_user, "firm_id", None) if current_user else None,
        user_id=getattr(current_user, "id", None) if current_user else None,
    )


@router.put(
    "/templates/{template_id}/composer/regenerate-template",
    response_model=TemplateRegenerateDiffV2,
)
async def composer_regenerate_template(
    template_id: str,
    body: RegenerateTemplateRequest,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Re-extract a v2 template with author-supplied merges /
    ignored_texts / regeneration_instruction. Diffs the new spec
    against existing template_fields_v2 rows preserving wizard-saved
    `params` on kept fields. Returns the diff so the FE can render a
    "what changed" panel.

    **Does NOT touch published_at / published_spec** — re-extract is
    an unpublished change; if the template was previously published,
    the live version stays frozen until the paralegal re-publishes.
    """
    return await regenerate_template_v2(
        template_id=template_id,
        ignored_texts=body.ignored_texts,
        merges=body.merges,
        regeneration_instruction=body.regeneration_instruction,
        firm_id=getattr(current_user, "firm_id", None) if current_user else None,
        user_id=getattr(current_user, "id", None) if current_user else None,
    )
