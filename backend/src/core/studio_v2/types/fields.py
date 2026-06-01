"""TemplateFieldV2 + TemplateSpecV2.

Lives in its own table (`template_fields_v2`); no relation to v1's
TemplateField in `src/core/agents/types/spec.py`. The two systems
share no types and the v1 model is byte-identical throughout
Phases 0-5.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .wizard_sources import WizardSourceParams


class TemplateFieldV2(BaseModel):
    """One template variable in a v2 TemplateSpecV2.

    `template_property_marker` and aliases are composer-set (mirrors
    v1 — see TemplateAgent rule 13 in the plan). `params` is the
    wizard's WizardSourceParams payload that the paralegal edits in
    the wizard or that TemplateAgentV2 pre-populates with a
    source-suggestion default.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    template_id: UUID

    # Variable name in snake_case (e.g. "debtor_name") used as the
    # placeholder identifier inside the .docx as [[debtor_name]].
    template_variable: str

    # The EXACT value the composer should find and replace with the
    # placeholder. Just the value, no surrounding text. None for
    # virtual parents (Rule 16 / 18 — they power their auto-derived
    # children but never render directly).
    template_property_marker: str | None = None

    # Orthographic variants of the same value found elsewhere in the
    # document (e.g. "Jane S Smith" header caption vs "Jane S. Smith"
    # body prose). All forms get replaced by the same placeholder.
    template_property_marker_aliases: list[str] = Field(default_factory=list)

    # Full line/paragraph where the value first appears — human-
    # readable disambiguation for the FE, also used by the composer's
    # find-replace pass to disambiguate same-value-different-role
    # occurrences (e.g. civil_case_number vs bankruptcy_case_number).
    template_identifying_text_match: str | None = None

    # Brief description shown in the wizard sidebar.
    description: str | None = None

    # Document-order index of first appearance. Set by composer; the
    # wizard surfaces fields in this order.
    template_index: int = 0

    # Wizard-saved source binding. None for fields that the composer
    # emitted as virtual parents OR for fields the paralegal hasn't
    # touched yet (TemplateAgentV2's source-suggestion default
    # populates this on initial extract, so null is rare in practice).
    params: WizardSourceParams | None = None


class TemplateSpecV2(BaseModel):
    """Full list of fields for a v2 template, ordered by
    template_index.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: UUID
    fields: list[TemplateFieldV2] = Field(default_factory=list)
