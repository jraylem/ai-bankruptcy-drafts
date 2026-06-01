"""publish_template_v2 — Phase 3 publish gate.

Snapshots the current working draft (`template_fields_v2` rows +
`templates_v2.config`) into `templates_v2.published_spec` JSONB and
sets `published_at`. Drafts (Phase 3) + the `/v2` chat slash command
(Phase 4) only ever read `published_spec`, so this is the
production-cutover moment for a v2 template.

Pipeline:
1. Load `TemplateV2` row + every `TemplateFieldV2` row.
2. Build a Pydantic list of `TemplateFieldV2` for validator input.
3. Run `validate_for_publish(fields)` → list[str] of error messages.
4. On non-empty errors → raise HTTPException 400 with structured
   payload `{"detail": {"code": "VALIDATION_FAILED", "errors": [...]}}`.
   FE renders each error inline above the Publish CTA.
5. On clean → build `published_spec` JSONB shape (snapshot every
   field's wire-relevant fields + the template's `config`), call
   `TemplatesV2Repository.update_published_snapshot(...)`. The repo
   sets `published_at = now()` atomically with the spec write.
6. Return the refreshed `TemplateV2` row so the FE can update its
   PublishStep state.

Soft-fail boundary: validator DB lookups (constants / attorney
roster) catch their own exceptions and add a generic "try again"
error to the list. The publish call itself wraps the repo update in
a transaction (Repository handles rollback).
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

from ...orchestration.validators import validate_for_publish
from ...repositories import (
    TemplateFieldsV2Repository,
    TemplatesV2Repository,
)
from ...repositories.models import TemplateV2
from ...types.fields import TemplateFieldV2
from ...types.wizard_sources import WizardSourceParams

logger = logging.getLogger(__name__)


async def publish_template_v2(template_id: str) -> TemplateV2:
    """Publish the working draft to `published_spec`.

    Raises HTTPException 400 with `code=VALIDATION_FAILED` + an
    `errors: list[str]` payload when the validator suite produces
    any errors. The FE expects this shape in its `.catch(...)` path.

    Raises HTTPException 404 when the template doesn't exist or has
    been soft-deleted (`is_active = false`).
    """
    template = await TemplatesV2Repository.get(template_id)
    if template is None:
        raise HTTPException(
            status_code=404,
            detail=f"Template {template_id} not found",
        )

    field_rows = await TemplateFieldsV2Repository.list_for_template(template_id)
    pydantic_fields = [_orm_field_to_pydantic(row) for row in field_rows]

    role = (template.config or {}).get("role") if template.config else None
    errors = await validate_for_publish(pydantic_fields, role=role)
    if errors:
        logger.info(
            "publish_template_v2: %d validation error(s) blocked publish for %s",
            len(errors), template_id,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_FAILED",
                "validation_errors": errors,
            },
        )

    published_spec = _build_published_spec(template, pydantic_fields)
    updated = await TemplatesV2Repository.update_published_snapshot(
        template_id=template_id,
        published_spec=published_spec,
    )
    if updated is None:
        # Race: row was active at the start of the call, deleted before
        # the update committed. Treat as 404 from the FE's perspective.
        raise HTTPException(
            status_code=404,
            detail=f"Template {template_id} not found (was deleted mid-publish?)",
        )
    return updated


def _orm_field_to_pydantic(row) -> TemplateFieldV2:
    """Convert a `template_fields_v2` ORM row to the Pydantic
    `TemplateFieldV2` shape the validators expect."""
    params = (
        WizardSourceParams.model_validate(row.params)
        if row.params
        else None
    )
    return TemplateFieldV2(
        id=row.id,
        template_id=row.template_id,
        template_variable=row.template_variable,
        template_property_marker=row.template_property_marker,
        template_property_marker_aliases=row.template_property_marker_aliases or [],
        template_identifying_text_match=row.template_identifying_text_match,
        description=row.description,
        template_index=row.template_index,
        params=params,
    )


def _build_published_spec(
    template: TemplateV2,
    fields: list[TemplateFieldV2],
) -> dict:
    """Snapshot template + fields into the JSONB shape the future
    draft/chat pipelines read.

    Frozen at this moment — every downstream consumer (Phase 3 drafts,
    Phase 4 chat) reads from `published_spec`, NOT from
    `template_fields_v2` rows. Working-draft edits made AFTER publish
    surface as `has_unpublished_changes = true` but do NOT flow into
    in-flight drafts.
    """
    return {
        "template_id": str(template.id),
        "name": template.name,
        "config": template.config or {},
        "fields": [field.model_dump(mode="json") for field in fields],
    }
