"""Output schemas for TemplateAgentV2.

The agent emits a list of `TemplateFieldV2Extract` dicts. The composer
service translates each one into a `TemplateFieldV2` ORM row
(dropping the `template_variable_string` field, which goes into the
DOCX via `DocxTemplateService.create_template` but is not persisted on
the row).

The shape is DELIBERATELY DIFFERENT from `TemplateFieldV2` in
`src/core/studio_v2/types/fields.py`:
- This is the AGENT'S output shape (composer-time, pre-persistence).
- `TemplateFieldV2` is the persistence shape (lives in
  `template_fields_v2` rows).
- The shape differs by `template_variable_string` (here, not there)
  and `id` / `template_id` (there, not here — the composer assigns
  those when it persists).
"""

from pydantic import BaseModel, ConfigDict, Field

from src.core.studio_v2.types.wizard_sources import WizardSourceParams


class TemplateFieldV2Extract(BaseModel):
    """One template variable as extracted from a legal document.

    Mirrors the structural fields of v1's `TemplateVariable`
    (template_variable, template_index, template_property_marker,
    aliases, template_identifying_text_match, description,
    template_variable_string) but emits a v2 `WizardSourceParams` in
    `params` instead of v1's `source` + `source_params` pair.
    """

    model_config = ConfigDict(extra="forbid")

    template_variable: str = Field(
        description="snake_case name (e.g. debtor_name, case_number)",
    )
    template_index: int = Field(
        description="Document-order index of first appearance, starting from 0",
    )
    template_property_marker: str | None = Field(
        default=None,
        description=(
            "EXACT value to find and replace in the docx. Just the value, "
            "no surrounding text. NULL for virtual parents (Rule 16/18 — "
            "they power their auto-derived children but never render directly)."
        ),
    )
    template_property_marker_aliases: list[str] = Field(
        default_factory=list,
        description=(
            "Alternate orthographic forms of the SAME value (e.g. "
            "'Jane S Smith' vs 'Jane S. Smith'). Every alias becomes an "
            "additional marker for find/replace."
        ),
    )
    template_variable_string: str | None = Field(
        default=None,
        description=(
            "Placeholder string to embed in the docx, e.g. '[[debtor_name]]'. "
            "NULL for virtual parents — they don't render directly."
        ),
    )
    template_identifying_text_match: str | None = Field(
        default=None,
        description=(
            "Full line/paragraph where the marker appears. Used by "
            "DocxTemplateService.create_template to disambiguate placement "
            "when multiple variables share the same marker value."
        ),
    )
    description: str | None = Field(
        default=None,
        description="Brief description of what this variable represents",
    )
    params: WizardSourceParams | None = Field(
        default=None,
        description=(
            "Pre-populated WizardSourceParams per the source-suggestion "
            "heuristics. NULL when the agent has no confident suggestion — "
            "paralegal binds via the wizard. Per heuristic 4, "
            "auto_derived children (Rules 16/18) get "
            "`source=derived_from_variable` + a tailored extraction_prompt "
            "as the default."
        ),
    )
