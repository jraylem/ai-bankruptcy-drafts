"""Templates CRUD routes — list / read / patch field / bundling-config / delete.

Mounted under /api/v3/studio (final paths:
  GET    /api/v3/studio/templates
  GET    /api/v3/studio/templates/{id}
  PATCH  /api/v3/studio/templates/{id}/fields/{field_id}
  PUT    /api/v3/studio/templates/{id}/bundling-config
  DELETE /api/v3/studio/templates/{id}
).

Each route is a thin wrapper over the v2 repositories. The wizard's
per-field save (PATCH /fields/{field_id}) is the load-bearing one —
it's the only endpoint called repeatedly during Phase 1 paralegal
use.
"""

import asyncio
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException

from src.auth.auth import get_current_user_optional
from src.auth.models import User

from src.core.common.storage.r2 import r2_service
from src.core.studio_v2.services.composer.generate import R2_PREFIX_TEMPLATE_V2
from src.core.studio_v2.services.composer.publish import publish_template_v2
from src.core.studio_v2.orchestration.validators import (
    assert_part_of_packet_has_no_user_input_v2,
)
from src.core.studio_v2.repositories import (
    TemplateFieldsV2Repository,
    TemplatesV2Repository,
)
from src.core.studio_v2.types.bundling import TemplateConfigV2, TemplateRole

from .schemas import (
    DeleteTemplateResponse,
    FieldPatchRequest,
    TemplateBundlingConfigRequest,
    TemplateFieldV2Response,
    TemplateV2Response,
)

logger = logging.getLogger(__name__)


async def _serialize_template(
    row,
    *,
    include_fields: bool = False,
    field_counts: tuple[int, int] | None = None,
) -> TemplateV2Response:
    """Build a TemplateV2Response with FRESH presigned R2 URLs.

    Presigned URLs persisted in the DB at upload time expire after 1 hour;
    serving the stored values would 403 on every read past that window.
    We re-sign on every response so the FE always receives a URL valid
    for the next hour, regardless of how long ago the template was
    uploaded. The DB column is left intact for now (cheap audit trail of
    the most recent sign) but is never served back.
    """
    original_url, template_url = await asyncio.gather(
        r2_service.get_presigned_url(
            row.id, "original.docx", prefix=R2_PREFIX_TEMPLATE_V2,
        ),
        r2_service.get_presigned_url(
            row.id, "template.docx", prefix=R2_PREFIX_TEMPLATE_V2,
        ),
    )
    resp = TemplateV2Response.from_row(row)
    resp.original_doc_url = original_url
    resp.template_doc_url = template_url
    if include_fields:
        fields = await TemplateFieldsV2Repository.list_for_template(row.id)
        resp.fields = [TemplateFieldV2Response.from_row(f) for f in fields]
        # When fields are inlined, derive counts client-side from
        # them — avoids a redundant query just to populate the pills.
        # See note in `TemplateFieldsV2Repository.counts_for_templates`
        # — `params is None` is rarely true in practice because the
        # composer-time agent prefills every field. The rail's
        # grouping uses `publishedAt` instead of these counts; this
        # value remains useful only for the per-row pill string.
        resp.total_fields = len(fields)
        resp.configured_fields = sum(1 for f in fields if f.params is not None)
    elif field_counts is not None:
        resp.total_fields, resp.configured_fields = field_counts
    return resp

router = APIRouter(prefix="/studio", tags=["Studio V2 - Templates"])


@router.get(
    "/templates",
    response_model=list[TemplateV2Response],
)
async def list_templates(
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """List active v2 templates for the current firm. Anonymous
    requests get the full set (Phase 1 — no firm-scoping enforced
    until auth is required).
    """
    firm_id = getattr(current_user, "firm_id", None) if current_user else None
    rows = await TemplatesV2Repository.list(firm_id=firm_id)
    # One grouped count query covers every row's pills — saves N+1.
    counts = await TemplateFieldsV2Repository.counts_for_templates(
        [row.id for row in rows],
    )
    return await asyncio.gather(*(
        _serialize_template(row, field_counts=counts.get(row.id, (0, 0)))
        for row in rows
    ))


@router.get(
    "/templates/{template_id}",
    response_model=TemplateV2Response,
)
async def get_template(
    template_id: str,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Fetch a single v2 template by id with its full field list."""
    row = await TemplatesV2Repository.get(template_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    return await _serialize_template(row, include_fields=True)


@router.patch(
    "/templates/{template_id}/fields/{field_id}",
    response_model=TemplateFieldV2Response,
)
async def patch_template_field(
    template_id: str,
    field_id: str,
    body: FieldPatchRequest,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """The wizard's save action — atomic per-field `params` update.

    The atomic single-row UPDATE prevents the lost-update race that
    would happen if the wizard read the whole spec, mutated one field,
    and wrote back the whole spec.
    """
    template_row = await TemplatesV2Repository.get(template_id)
    if template_row is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    params_dict = body.params.model_dump(mode="json") if body.params else None
    updated = await TemplateFieldsV2Repository.patch_params(
        field_id=field_id,
        params=params_dict,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Field {field_id} not found")
    if updated.template_id != template_id:
        raise HTTPException(
            status_code=400,
            detail=f"Field {field_id} does not belong to template {template_id}",
        )
    # Bump the parent template's updated_at so the FE's
    # `has_unpublished_changes` flag (computed as
    # `updated_at > published_at`) flips after a field edit. Without
    # this, the PublishStep + rail pill stay at "Live" even though
    # the working draft has drifted from the published snapshot.
    await TemplatesV2Repository.touch_updated_at(template_id)
    return TemplateFieldV2Response.from_row(updated)


@router.put(
    "/templates/{template_id}/bundling-config",
    response_model=TemplateV2Response,
)
async def update_template_bundling(
    template_id: str,
    body: TemplateBundlingConfigRequest,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Save the full TemplateConfigV2 (role + companions). Mirrors v1's
    PUT /template/{id}/bundling-config.

    Phase 1 enforces one composer-time validator:
    `assert_part_of_packet_has_no_user_input_v2` — when saving
    `role = part_of_packet`, the spec must not contain any user-input
    fields. The full validator suite gates the Phase 3 publish endpoint.
    """
    template_row = await TemplatesV2Repository.get(template_id)
    if template_row is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

    if body.config.role == TemplateRole.PART_OF_PACKET:
        fields = await TemplateFieldsV2Repository.list_for_template(template_id)
        user_input_offenders = assert_part_of_packet_has_no_user_input_v2(fields)
        if user_input_offenders:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "PART_OF_PACKET_HAS_USER_INPUT",
                    "offending_variables": user_input_offenders,
                    "message": (
                        f"Template {template_id} cannot be set to role=part_of_packet "
                        f"because it contains user-input fields: "
                        f"{', '.join(user_input_offenders)}. Push the user-input "
                        "variable up to the lead template and inherit its resolved "
                        "value via a value_from_parent_bundle slot config."
                    ),
                },
            )

    updated = await TemplatesV2Repository.update(
        template_id=template_id,
        config=body.config.model_dump(mode="json"),
    )
    return await _serialize_template(updated)


@router.delete(
    "/templates/{template_id}",
    response_model=DeleteTemplateResponse,
)
async def delete_template(
    template_id: str,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Soft-delete the template (sets is_active=false). Idempotent —
    returns `deleted: false` when the template was already inactive
    or didn't exist. Cascades to template_fields_v2 via FK ON DELETE
    CASCADE only if we were doing hard deletes; soft-delete leaves
    field rows intact (they're unreachable via the API anyway because
    every read scopes to is_active=true on the parent).
    """
    deleted = await TemplatesV2Repository.soft_delete(template_id)
    return DeleteTemplateResponse(template_id=template_id, deleted=deleted)


@router.post(
    "/templates/{template_id}/publish",
    response_model=TemplateV2Response,
)
async def publish_template(
    template_id: str,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Validate the working draft + snapshot to `published_spec`.

    Empty payload. On clean validation, snapshots every
    `template_fields_v2` row + the template's `config` into
    `templates_v2.published_spec` JSONB and sets `published_at = now()`.
    The returned `TemplateV2Response` has the fresh `published_at` so
    the FE PublishStep can flip its status pill to "Live".

    Validation failure returns HTTP 400 with body shape:
        {
          "detail": {
            "code": "VALIDATION_FAILED",
            "validation_errors": ["...", "..."]
          }
        }
    FE's `apiService.handleError` (api.ts) picks up
    `detail.validation_errors` into the `ApiResponse.validationErrors`
    field, so the PublishStep can render each error string inline
    above the Publish CTA.

    Re-extracting (`PUT .../composer/regenerate-template`) and field
    edits (`PATCH .../fields/{id}`) DO NOT touch `published_spec` —
    the template stays at its last-published state until the
    paralegal explicitly re-publishes.
    """
    updated = await publish_template_v2(template_id)
    return await _serialize_template(updated, include_fields=True)
