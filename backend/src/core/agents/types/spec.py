"""Template spec and composed agent config.

Sits one layer up from sources.py: each TemplateVariable / TemplateField
pairs a FieldSource with its matching *SourceParams, and AgentConfig
bundles the full list for a template. TemplateField.stage is derived
from its source via _STAGE_BY_SOURCE so consumers can filter on stage
without knowing the source-to-stage mapping themselves.
"""

from typing import Literal

from pydantic import BaseModel, Field, computed_field

from .bundling import TemplateBundleRole
from .resolution import ResolverStage
from .sources import AuthorSourceParams, FieldSource, RuntimeSourceParams


_STAGE_BY_SOURCE: dict[FieldSource, ResolverStage] = {
    FieldSource.GMAIL: ResolverStage.LLM_DRAFT,
    FieldSource.COURT_DRIVE: ResolverStage.LLM_DRAFT,
    FieldSource.CASE_VECTOR: ResolverStage.LLM_DRAFT,
    FieldSource.LAW_PRACTICE_VECTOR: ResolverStage.LLM_DRAFT,
    FieldSource.CONSTANTS: ResolverStage.LLM_DRAFT,
    FieldSource.SYSTEM_GENERATED: ResolverStage.SYSTEM_GENERATED,
    FieldSource.DEPENDENT_ON_VARIABLE: ResolverStage.DERIVATIVE,
    FieldSource.GROUP_DROPDOWN_FROM_GMAIL: ResolverStage.USER_INPUT,
    FieldSource.GROUP_DROPDOWN_FROM_COURT_DRIVE: ResolverStage.USER_INPUT,
    FieldSource.RECO_CHIPS_FROM_GMAIL: ResolverStage.USER_INPUT,
    FieldSource.RECO_CHIPS_FROM_COURT_DRIVE: ResolverStage.USER_INPUT,
    FieldSource.RECO_CHIPS_FROM_CASE_VECTOR: ResolverStage.USER_INPUT,
    FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES: ResolverStage.USER_INPUT,
    FieldSource.DROPDOWN_FROM_GMAIL: ResolverStage.USER_INPUT,
    FieldSource.DROPDOWN_FROM_COURT_DRIVE: ResolverStage.USER_INPUT,
    FieldSource.DROPDOWN_FROM_CASE_VECTOR: ResolverStage.USER_INPUT,
    FieldSource.DROPDOWN_FROM_CONSTANTS: ResolverStage.USER_INPUT,
    FieldSource.USER_INPUT_WITH_SUPPORTING_DOCS: ResolverStage.USER_INPUT,
    FieldSource.USER_INPUT_PLAIN_TEXT: ResolverStage.USER_INPUT,
    FieldSource.USER_INPUT_DATE: ResolverStage.USER_INPUT,
    FieldSource.AUTO_DERIVED_FROM_VARIABLE: ResolverStage.AUTO_DERIVED,
    FieldSource.MULTI_SELECT_FROM_CASE_VECTOR: ResolverStage.USER_INPUT,
    FieldSource.MULTI_SELECT_FROM_GMAIL: ResolverStage.USER_INPUT,
    FieldSource.INHERIT_FROM_PARENT: ResolverStage.INHERIT_FROM_PARENT,
}


class TemplateVariable(BaseModel):
    """A template variable extracted from a legal document by the template agent.

    Produced by TemplateAgent.run (agents/template_agent.py), persisted on DraftTemplate.template_spec,
    and consumed by the composer (to build create/fill docx calls) and the dry_run flow
    (to map resolved values back onto the template's placeholder strings).
    """
    template_variable: str = Field(description="The name of the variable in snake_case format")
    template_index: int = Field(description="The order/position of this variable in the document starting from 0")
    source: FieldSource | None = Field(default=None, description="The source to fetch this value")
    source_params: AuthorSourceParams | None = Field(default=None, description="Parameters for the source query")
    template_property_marker: str | None = Field(default=None, description="The exact value to find and replace")
    template_property_marker_aliases: list[str] = Field(
        default_factory=list,
        description=(
            "Alternate orthographic forms of the SAME value found in the document "
            "(e.g. 'Jane S Smith' vs 'Jane S. Smith' — the same debtor, different "
            "punctuation). Each alias is treated as a marker for this variable at "
            "template-creation time, so the placeholder replaces EVERY occurrence "
            "regardless of form. Leave empty when the value only appears in one form."
        ),
    )
    template_variable_string: str | None = Field(default=None, description="The placeholder [[variable_name]]")
    template_identifying_text_match: str | None = Field(
        default=None,
        description=(
            "Surrounding context (full text line or short snippet) where the marker "
            "appears. Used by DocxTemplateService.create_template to disambiguate "
            "placement when multiple variables share the same template_property_marker "
            "value — e.g. a civil case_number vs. a bankruptcy case_number that happen "
            "to share the same literal value in the source doc. For unique-marker "
            "variables this is metadata only."
        ),
    )
    description: str | None = Field(default=None, description="Brief description of what this variable represents")
    instruction: str | None = Field(
        default=None,
        description=(
            "Per-field hint for EXTRACTION-TIME agents (DraftAgent, vision agents, "
            "RecoChipsAgent, DropdownAgent). Tells them what specifically to pull "
            "from the raw source data — e.g. 'extract Document Number from email body', "
            "'use SOFA Q9 not Q3'. NOT used by the heal pass; for output-shaping "
            "rules (tense, predicate-only, anti-double-period) use `output_instruction`."
        ),
    )
    output_instruction: str | None = Field(
        default=None,
        description=(
            "Per-field rules for the FINAL DOCX OUTPUT — the author's directive for "
            "how the resolved value should be shaped (tense / register / predicate-only "
            "/ multi-value formatting / casing / anti-double-period / etc.). Surfaced "
            "as AUTHORITATIVE guidance to every LLM that produces the field's output: "
            "the DraftAgent (LLM_DRAFT-stage extraction for gmail / court_drive / "
            "case_vector / law_practice_vector / constants), the UserInputHealAgent "
            "(reco-chips, dropdown, multi-select, plain-text, supporting-docs, "
            "inherit-from-parent), and the WebSearchEnhanceAgent. Each agent treats it "
            "as overriding any conflicting shape guidance. Examples: 'PAST TENSE ONLY — "
            "circumstance must be resolved-state', 'Predicate-only: drop subject (already "
            "in docx)', 'If multiple emails match, list each on a new line in the format "
            "<subject> — <date>'. Not consumed by purely-deterministic resolvers "
            "(system_generated, dependent_on_variable) since they don't run an LLM."
        ),
    )
    read_only: bool = Field(
        default=False,
        description=(
            "When true, the FE must not let the user change source/source_params or "
            "manually override the resolved value. Set automatically by the template "
            "agent for AUTO_DERIVED_FROM_VARIABLE entries; rejected by the validator "
            "for any other source type."
        ),
    )

    @computed_field
    @property
    def kind(self) -> Literal["physical", "virtual"]:
        """`virtual` when the variable carries no `[[placeholder]]` (it powers
        auto_derive children but never renders directly in the docx);
        `physical` otherwise. Drives FE display affordances and BE composer
        / validator carve-outs for the tabular row pattern."""
        return "virtual" if self.template_variable_string is None else "physical"


class TemplateField(BaseModel):
    """Universal runtime shape for one template variable.

    Carries everything any pipeline stage needs: LLM input (source,
    source_params, instruction), post-draft resolvers (source_params
    for derivative / system_generated), and docx fill
    (template_variable_string). `stage` is derived from `source` via
    _STAGE_BY_SOURCE — consumers filter on `stage` rather than carrying
    their own source-to-stage knowledge.
    """
    property_name: str
    source: FieldSource
    source_params: RuntimeSourceParams | None = None
    instruction: str | None = None
    """Extraction-time hint — see TemplateVariable.instruction for semantics."""
    output_instruction: str | None = None
    """Output-shaping rule passed to every LLM-driven resolver (DraftAgent,
    UserInputHealAgent, WebSearchEnhanceAgent) — see TemplateVariable.output_instruction."""
    template_variable_string: str | None = None
    template_property_marker: str | None = None
    template_identifying_text_match: str | None = None

    @computed_field
    @property
    def stage(self) -> ResolverStage:
        """Return the resolver stage for this field, derived from its source via _STAGE_BY_SOURCE."""
        return _STAGE_BY_SOURCE[self.source]

    @computed_field
    @property
    def kind(self) -> Literal["physical", "virtual"]:
        """Mirrors `TemplateVariable.kind` on the runtime field shape: `virtual`
        when no `[[placeholder]]` exists (this field powers auto_derive
        children but never directly renders in the docx); `physical` otherwise."""
        return "virtual" if self.template_variable_string is None else "physical"


def root_parent_stage(
    field: "TemplateField | TemplateVariable",
    by_name: "dict[str, TemplateField | TemplateVariable]",
) -> ResolverStage | None:
    """Walk the auto_derived chain to the root parent and return that parent's stage.

    For an `auto_derived_from_variable` field, the value isn't fetched —
    it's extracted from a parent variable's already-resolved value. The
    "effective stage" of an auto_derived field is therefore the stage of
    whichever ancestor in the chain has a real source.

    Returns `None` when:
      - the root parent has no source bound (still null after extraction)
      - the chain references a missing variable
      - a cycle is detected in the chain (cycle validator surfaces this
        as a real error elsewhere — here we just refuse to infinite-loop)

    Non-auto_derived fields short-circuit to their own stage.
    """
    seen: set[str] = set()
    cur = field
    while cur.source == FieldSource.AUTO_DERIVED_FROM_VARIABLE:
        name = getattr(cur, "property_name", None) or getattr(cur, "template_variable", None)
        if name is None or name in seen:
            return None
        seen.add(name)
        params = cur.source_params
        parent_name = getattr(params, "dependent_variable", None) if params is not None else None
        if not parent_name:
            return None
        parent = by_name.get(parent_name)
        if parent is None:
            return None
        cur = parent
    if cur.source is None:
        return None
    return _STAGE_BY_SOURCE.get(cur.source)


def root_parent_is_unbound(
    field: "TemplateField | TemplateVariable",
    by_name: "dict[str, TemplateField | TemplateVariable]",
) -> bool:
    """True iff the auto_derived chain walks to a root whose `source` is None.

    Distinguishes "unbound at the root" (chain is well-formed; the terminal
    parent simply hasn't been mapped to a source yet) from "broken chain"
    (cycle, missing parent). Used by validators to accept placeholder
    references at compose time before the root is bound — `root_parent_stage`
    collapses both cases into `None` and can't distinguish them.

    Returns False for: cycles, missing parents, or roots that have any
    source bound. Returns True for a non-auto_derived input whose own
    source is None (the trivial unbound case).
    """
    seen: set[str] = set()
    cur = field
    while cur.source == FieldSource.AUTO_DERIVED_FROM_VARIABLE:
        name = getattr(cur, "property_name", None) or getattr(cur, "template_variable", None)
        if name is None or name in seen:
            return False
        seen.add(name)
        params = cur.source_params
        parent_name = getattr(params, "dependent_variable", None) if params is not None else None
        if not parent_name:
            return False
        parent = by_name.get(parent_name)
        if parent is None:
            return False
        cur = parent
    return cur.source is None


class AgentConfig(BaseModel):
    """Post-compose artifact that is the single source of truth for drafting.

    Both the draft pipeline (persisted load) and the dry-run pipeline
    (in-memory build) fan out from this object alone. Every variable —
    regardless of resolver stage — lives in `template_fields`.
    """
    template_id: str
    template_fields: list[TemplateField]
    bundle_role: TemplateBundleRole = Field(
        default=TemplateBundleRole.STANDALONE,
        description=(
            "This template's role in the bundling system. STANDALONE templates "
            "draft on their own. PARENT templates carry bundle_companions on "
            "the persistence layer (Phase 2 wires them into the engine). "
            "CHILD_ONLY templates can only run when attached to a parent's "
            "companion at draft time."
        ),
    )
