"""HTTP request / response schemas for the v2 composer surface.

Mirrors v1's `src/core/components/engines/template/schemas.py` (minus
the dry-run / agent-config-compose endpoints which don't ship in
Phase 1).
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.core.studio_v2.agents.template import TemplateFieldV2Extract


class DocumentParseResponseV2(BaseModel):
    """Result of `POST /api/v3/studio/composer/parse` — flattened text +
    metadata from an uploaded .docx. The FE turns around and POSTs
    this content to /generate."""
    model_config = ConfigDict(extra="forbid")

    document_id: str
    parsed: bool
    content: str
    metadata: dict[str, Any]


class MergeOperationV2(BaseModel):
    """Author-supplied merge for /regenerate: collapse N existing
    variables into one new variable.

    Mirrors v1's `MergeOperation`. The `new_variable_name` is the
    snake_case identifier the merged variable should carry; the
    `source_variables` are the variables that disappear from the spec
    after the merge.
    """
    model_config = ConfigDict(extra="forbid")

    new_variable_name: str
    source_variables: list[str] = Field(min_length=2)
    description: str | None = None

    def resolve_variable_name(self) -> str:
        return self.new_variable_name


class TemplateGenerateResponseV2(BaseModel):
    """Result of `POST /api/v3/studio/composer/generate-template`."""
    model_config = ConfigDict(extra="forbid")

    template_id: str
    name: str
    template_spec: list[TemplateFieldV2Extract]
    original_doc_url: str
    template_doc_url: str


class TemplateRegenerateDiffV2(BaseModel):
    """Diff returned by `POST /api/v3/studio/templates/{id}/composer/regenerate-template`.

    Mirrors v1's `TemplateRegenerateDiff`. `inserted` / `updated` /
    `deleted` are lists of `template_variable` names so the FE can
    render a "what changed" panel after the paralegal hits Regenerate.
    `preserved_params` lists the variables whose `params` was kept
    verbatim from the prior wizard configuration (only when the
    variable also appears in `updated`).
    """
    model_config = ConfigDict(extra="forbid")

    template_id: str
    inserted: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)
    preserved_params: list[str] = Field(default_factory=list)
    template_doc_url: str
