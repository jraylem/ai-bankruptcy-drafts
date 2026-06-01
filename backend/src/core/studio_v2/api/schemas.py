"""HTTP request/response schemas for the v3 studio router.

Distinct from the composer schemas (`src/core/studio_v2/composer/schemas.py`)
because these wrap the ORM-row reads + the wizard's per-field PATCH
shape. The composer schemas are about parse/generate/regenerate flow;
these are about the templates_v2 + template_fields_v2 row CRUD surface.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.core.studio_v2.services.composer.schemas import MergeOperationV2
from src.core.studio_v2.types.bundling import TemplateConfigV2
from src.core.studio_v2.types.wizard_sources import WizardSourceParams


class FieldPatchRequest(BaseModel):
    """Wizard's atomic per-field save shape."""
    model_config = ConfigDict(extra="forbid")

    params: WizardSourceParams | None = None


class RegenerateTemplateRequest(BaseModel):
    """Body for PUT /templates/{id}/composer/regenerate-template."""
    model_config = ConfigDict(extra="forbid")

    ignored_texts: list[str] | None = None
    merges: list[MergeOperationV2] | None = None
    regeneration_instruction: str | None = None


class TemplateBundlingConfigRequest(BaseModel):
    """Body for PUT /templates/{id}/bundling-config."""
    model_config = ConfigDict(extra="forbid")

    config: TemplateConfigV2


class GenerateTemplateRequest(BaseModel):
    """Reserved — not used directly (the composer endpoint accepts
    multipart form fields). Defined here so docstrings can link to a
    typed shape.
    """
    model_config = ConfigDict(extra="forbid")

    template_name: str
    template_role: str = "single"


class TemplateFieldV2Response(BaseModel):
    """Wire shape for a template_fields_v2 row."""
    model_config = ConfigDict(extra="forbid")

    id: str
    template_id: str
    template_variable: str
    template_property_marker: str | None = None
    template_property_marker_aliases: list[str] = Field(default_factory=list)
    template_identifying_text_match: str | None = None
    description: str | None = None
    template_index: int
    params: WizardSourceParams | None = None
    created_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, row) -> "TemplateFieldV2Response":
        params = (
            WizardSourceParams.model_validate(row.params)
            if row.params
            else None
        )
        return cls(
            id=row.id,
            template_id=row.template_id,
            template_variable=row.template_variable,
            template_property_marker=row.template_property_marker,
            template_property_marker_aliases=row.template_property_marker_aliases or [],
            template_identifying_text_match=row.template_identifying_text_match,
            description=row.description,
            template_index=row.template_index,
            params=params,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class TemplateV2Response(BaseModel):
    """Wire shape for a templates_v2 row.

    `fields` is populated only on `GET /templates/{id}` (the single-row
    fetch); `GET /templates` leaves it as the default empty list to
    keep the listing payload small.

    `has_unpublished_changes` is COMPUTED (`updated_at > published_at`),
    not stored, so the FE always sees a fresh state.
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    firm_id: str | None = None
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    original_doc_url: str | None = None
    template_doc_url: str | None = None
    published_at: datetime | None = None
    has_unpublished_changes: bool = True
    # Field counts — populated by the list endpoint so the FE rail can
    # render configuration progress + publish-state pills without
    # fetching every template's full spec. `total_fields` is the
    # number of `template_fields_v2` rows; `configured_fields` is the
    # subset where `params IS NOT NULL`. Default 0/0 — kept absent
    # from the single-row endpoint by convention (it has the full
    # `fields` list and can compute counts client-side).
    total_fields: int = 0
    configured_fields: int = 0
    created_at: datetime
    updated_at: datetime | None = None
    fields: list[TemplateFieldV2Response] = Field(default_factory=list)

    @classmethod
    def from_row(cls, row) -> "TemplateV2Response":
        has_unpublished_changes = (
            row.published_at is None
            or (row.updated_at is not None and row.updated_at > row.published_at)
        )
        return cls(
            id=row.id,
            firm_id=row.firm_id,
            name=row.name,
            config=row.config or {},
            original_doc_url=row.original_doc_url,
            template_doc_url=row.template_doc_url,
            published_at=row.published_at,
            has_unpublished_changes=has_unpublished_changes,
            created_at=row.created_at,
            updated_at=row.updated_at,
            fields=[],
        )


class DeleteTemplateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str
    deleted: bool
