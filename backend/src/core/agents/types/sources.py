"""Source definitions for template-field resolution.

Every template field declares a FieldSource (where its value comes from)
paired with a matching *SourceParams shape (how to query that source).
This module owns the full set of source types, the parameter schemas, and
the runtime GroupDropdownComposite collapsed form.

Date-related enums and the canonical render format live here too, since
they're inputs to SystemGeneratedSourceParams and
DependentOnVariableSourceParams.
"""

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


class FieldSource(str, Enum):
    """Where a template field's value comes from. Each value is paired with a matching *SourceParams shape."""

    GMAIL = "gmail"
    COURT_DRIVE = "court_drive"
    CASE_VECTOR = "case_vector"
    LAW_PRACTICE_VECTOR = "law_practice_vector"
    CONSTANTS = "constants"
    DEPENDENT_ON_VARIABLE = "dependent_on_variable"
    SYSTEM_GENERATED = "system_generated"
    GROUP_DROPDOWN_FROM_GMAIL = "group_dropdown_from_gmail"
    GROUP_DROPDOWN_FROM_COURT_DRIVE = "group_dropdown_from_court_drive"
    RECO_CHIPS_FROM_GMAIL = "reco_chips_from_gmail"
    RECO_CHIPS_FROM_COURT_DRIVE = "reco_chips_from_court_drive"
    RECO_CHIPS_FROM_CASE_VECTOR = "reco_chips_from_case_vector"
    RECO_CHIPS_FROM_DEPENDENT_VARIABLES = "reco_chips_from_dependent_variables"
    DROPDOWN_FROM_GMAIL = "dropdown_from_gmail"
    DROPDOWN_FROM_COURT_DRIVE = "dropdown_from_court_drive"
    DROPDOWN_FROM_CASE_VECTOR = "dropdown_from_case_vector"
    DROPDOWN_FROM_CONSTANTS = "dropdown_from_constants"
    AUTO_DERIVED_FROM_VARIABLE = "auto_derived_from_variable"
    MULTI_SELECT_FROM_CASE_VECTOR = "multi_select_from_case_vector"
    MULTI_SELECT_FROM_GMAIL = "multi_select_from_gmail"
    USER_INPUT_WITH_SUPPORTING_DOCS = "user_input_with_supporting_docs"
    USER_INPUT_PLAIN_TEXT = "user_input_plain_text"
    USER_INPUT_DATE = "user_input_date"
    INHERIT_FROM_PARENT = "inherit_from_parent"


class SystemGeneratedType(str, Enum):
    """Discriminator for SystemGeneratedSourceParams.type — which deterministic value to emit at draft time."""

    CURRENT_DATE = "current_date"


class DerivedValueType(str, Enum):
    """Type of value a DEPENDENT_ON_VARIABLE field derives from its parent; only 'date' is supported today."""

    DATE = "date"


class RuleEffect(str, Enum):
    """Rule applied to a DEPENDENT_ON_VARIABLE parent value (shift by days/months/years, or just reformat)."""

    INCREMENT_BY_DAYS = "increment_by_days"
    DECREMENT_BY_DAYS = "decrement_by_days"
    INCREMENT_BY_MONTHS = "increment_by_months"
    DECREMENT_BY_MONTHS = "decrement_by_months"
    INCREMENT_BY_YEARS = "increment_by_years"
    DECREMENT_BY_YEARS = "decrement_by_years"
    FORMAT_ONLY = "format_only"


_DATE_RULE_EFFECTS = {
    RuleEffect.INCREMENT_BY_DAYS,
    RuleEffect.DECREMENT_BY_DAYS,
    RuleEffect.INCREMENT_BY_MONTHS,
    RuleEffect.DECREMENT_BY_MONTHS,
    RuleEffect.INCREMENT_BY_YEARS,
    RuleEffect.DECREMENT_BY_YEARS,
    RuleEffect.FORMAT_ONLY,
}


DEFAULT_DATE_FORMAT = "%B %-d, %Y"


_SCOPE_TO_CURRENT_CASE_DESCRIPTION = (
    "When true (default), the BE ANDs the current case's number variants into the Gmail query. "
    "Set false for cross-case templates that need to fetch from another case's email thread "
    "(typically combined with {{prior_case_number}}-style query templating)."
)

_QUERY_TEMPLATE_NOTE = " Supports {{variable}} references; substituted at fetch time with the resolved value."


class GmailSourceParams(BaseModel):
    """Parameters for GMAIL source."""
    model_config = ConfigDict(extra="forbid")

    subject_query: str | None = Field(default=None, description="Query to search email subjects." + _QUERY_TEMPLATE_NOTE)
    body_query: str | None = Field(default=None, description="Query to search email body." + _QUERY_TEMPLATE_NOTE)
    scope_to_current_case: bool = Field(
        default=True,
        description=_SCOPE_TO_CURRENT_CASE_DESCRIPTION,
    )
    enable_web_search: bool = Field(
        default=False,
        description=(
            "When true, runs WebSearchEnhanceResolver after the Gmail "
            "retrieval. Uses Anthropic's native web_search tool to fill "
            "missing context the email body doesn't carry (e.g. resolve a "
            "partial address from a notice into a full canonical one, or "
            "reshape a court name to match the docket-number format) and "
            "reshape the result to match `template_property_marker` and the "
            "surrounding docx paragraph. Off by default — opt in per "
            "variable; introduces 1–3s latency and external lookup cost. "
            "Requires a non-empty `current_value` to anchor the search; if "
            "the Gmail search returns empty, enhancement is skipped and "
            "a warning is surfaced to the author."
        ),
    )
    web_search_instruction: str | None = Field(
        default=None,
        description=(
            "Per-field directive for WebSearchEnhanceAgent ONLY. Surfaced "
            "as authoritative in the agent's prompt — overrides marker "
            "shape when in conflict. Use this for steering the search step "
            "(e.g. 'search for Florida judicial circuit by county; ignore "
            "federal court info'). For docx-output formatting rules, use "
            "`output_instruction` on the TemplateField instead. Ignored "
            "unless `enable_web_search=True`."
        ),
    )


class CourtDriveSourceParams(BaseModel):
    """Parameters for COURT_DRIVE source."""
    model_config = ConfigDict(extra="forbid")

    subject_query: str | None = Field(default=None, description="Query to search email subjects." + _QUERY_TEMPLATE_NOTE)
    body_query: str | None = Field(default=None, description="Query to search email body." + _QUERY_TEMPLATE_NOTE)
    scope_to_current_case: bool = Field(
        default=True,
        description=_SCOPE_TO_CURRENT_CASE_DESCRIPTION,
    )


class VectorSourceParams(BaseModel):
    """Parameters for LAW_PRACTICE_VECTOR source (and a base shape used historically by CASE_VECTOR)."""
    model_config = ConfigDict(extra="forbid")

    text_query: str = Field(description="Query to search vector store." + _QUERY_TEMPLATE_NOTE)


class CaseVectorSourceParams(BaseModel):
    """Optional parameters for the plain CASE_VECTOR source.

    By default the BE auto-derives the search query from the variable name.
    When `text_query` is set, that explicit query is used instead. Supports
    {{variable}} substitution at fetch time, so authors can reach across
    cases (e.g. text_query='Schedule I income {{prior_case_number}}')."""
    model_config = ConfigDict(extra="forbid")

    text_query: str | None = Field(
        default=None,
        description=(
            "Optional. Explicit text to retrieve relevant case-file chunks against. "
            "Leave null to fall back to BE auto-derivation from the variable name." + _QUERY_TEMPLATE_NOTE
        ),
    )
    enable_web_search: bool = Field(
        default=False,
        description=(
            "When true, runs WebSearchEnhanceResolver after the standard "
            "case_vector + vision passes. Uses Anthropic's native web_search "
            "tool to fill missing context the petition PDF doesn't carry "
            "(e.g. resolve a Florida county name to its judicial circuit "
            "number) and reshape the result to match `template_property_marker` "
            "and the surrounding docx paragraph. Off by default — opt in per "
            "variable; introduces 1–3s latency and external lookup cost. "
            "Requires a non-empty `current_value` to anchor the search; if "
            "case_vector + vision return empty, enhancement is skipped and "
            "a warning is surfaced to the author."
        ),
    )
    web_search_instruction: str | None = Field(
        default=None,
        description=(
            "Per-field directive for WebSearchEnhanceAgent ONLY. Surfaced "
            "as authoritative in the agent's prompt — overrides marker "
            "shape when in conflict. Use this for steering the search step "
            "(e.g. 'search for Florida judicial circuit by county; ignore "
            "federal court info'). For docx-output formatting rules, use "
            "`output_instruction` on the TemplateField instead. Ignored "
            "unless `enable_web_search=True`."
        ),
    )


class ConstantsSourceParams(BaseModel):
    """Parameters for CONSTANTS source."""
    model_config = ConfigDict(extra="forbid")

    short_code: str = Field(description="The short_code of the reference data to fetch")


class SystemGeneratedSourceParams(BaseModel):
    """Parameters for SYSTEM_GENERATED source.

    System-generated values are produced deterministically at draft time from
    runtime state (e.g. the server clock) with no external fetch and no LLM
    involvement. The `type` discriminator selects which system value to emit;
    additional fields are type-specific.
    """
    model_config = ConfigDict(extra="forbid")

    type: SystemGeneratedType = Field(description="Which system value to generate")
    format: str = Field(
        default=DEFAULT_DATE_FORMAT,
        description="Python strftime format codes used to render the generated value.",
    )


class DependentOnVariableSourceParams(BaseModel):
    """Parameters for DEPENDENT_ON_VARIABLE source.

    Derives this variable's value from another template variable by applying
    a rule (e.g. DateFiled + 14 days). The parent variable's value is read
    from the already-resolved template values at draft time, the rule is
    applied deterministically in Python, and the result is formatted using
    `format`. No LLM is involved in the math.
    """
    model_config = ConfigDict(extra="forbid")

    dependent_variable: str = Field(description="Name of the parent template variable to derive from")
    derived_value_type: DerivedValueType = Field(description="Type of the derived value; only 'date' is supported today")
    format: str = Field(
        default=DEFAULT_DATE_FORMAT,
        description="Python strftime/strptime format codes used to parse the parent value and render the derived value.",
    )
    rule_effect: RuleEffect = Field(description="The rule to apply to the dependent value")
    rule_effect_value: str | None = Field(
        default=None,
        description=(
            "Numeric amount for the rule effect (e.g. '14' for 14 days). Required unless "
            "rule_effect is 'format_only'; must be a positive integer string."
        ),
    )

    @model_validator(mode="after")
    def _validate_rules(self) -> "DependentOnVariableSourceParams":
        if not self.dependent_variable or not self.dependent_variable.strip():
            raise ValueError("dependent_variable must be a non-empty string")

        if self.derived_value_type == DerivedValueType.DATE:
            if self.rule_effect not in _DATE_RULE_EFFECTS:
                raise ValueError(
                    f"rule_effect '{self.rule_effect.value}' is not valid for derived_value_type 'date'"
                )

            if self.rule_effect == RuleEffect.FORMAT_ONLY:
                if self.rule_effect_value is not None:
                    raise ValueError("rule_effect_value must be null when rule_effect is 'format_only'")
                return self

            if self.rule_effect_value is None or not str(self.rule_effect_value).strip():
                raise ValueError(
                    f"rule_effect_value is required when rule_effect is '{self.rule_effect.value}'"
                )
            try:
                parsed = int(self.rule_effect_value)
            except (TypeError, ValueError):
                raise ValueError(
                    f"rule_effect_value '{self.rule_effect_value}' must be an integer string"
                )
            if parsed <= 0:
                raise ValueError("rule_effect_value must be a positive integer")

        return self


class GroupDropdownSourceParams(BaseModel):
    """Author-facing params declared on the anchor variable in template_spec.

    The anchor's template_variable holds this config; the declared
    right_partner_variable (a sibling in the same template_spec whose
    source is None) receives the right value on pick. At compose time,
    both siblings collapse into a single runtime GroupDropdownComposite.
    """
    model_config = ConfigDict(extra="forbid")

    subject_query: str | None = None
    body_query: str | None = None
    group_label: str = Field(description="Title shown above the dropdown, e.g. 'Docket'")
    left_label: str = Field(description="Column header for the left column, e.g. 'Docket Number'")
    right_label: str = Field(description="Column header for the right column, e.g. 'Docket Title'")
    right_partner_variable: str = Field(description="template_variable name that receives the right value")
    scope_to_current_case: bool = Field(
        default=True,
        description=_SCOPE_TO_CURRENT_CASE_DESCRIPTION,
    )


class RecoChipsEmailSourceParams(BaseModel):
    """Parameters for RECO_CHIPS_FROM_GMAIL and RECO_CHIPS_FROM_COURT_DRIVE.

    The RecoChipsAgent fetches emails using subject_query / body_query, then
    generates up to 3 short text candidates grounded in that source material.
    The FE renders the candidates as clickable chips under `label`; the user
    picks one, optionally edits it, and the final string fills the variable.

    `example_sentence` is the author's name-free skeleton of the sentence
    the chip will slot into. Threaded into the generation prompt as a
    tone/structure reference so chips match the surrounding legal prose
    and establish any premises downstream paragraphs depend on.
    """
    model_config = ConfigDict(extra="forbid")

    subject_query: str | None = None
    body_query: str | None = None
    label: str = Field(description="Header shown above the chips in the FE, e.g. 'Change in Circumstances'")
    example_sentence: str | None = Field(
        default=None,
        description=(
            "Optional name-free / date-free skeleton of the sentence the chip "
            "should resemble in tone and structure, e.g. 'The Debtor is employed "
            "in a capacity where their responsibilities require the handling of "
            "sensitive consumer information, and their employer places significant "
            "trust in them to do so.' Used ONLY for structural / tonal reference; "
            "the agent is instructed NOT to reproduce specific facts from it."
        ),
    )
    scope_to_current_case: bool = Field(
        default=True,
        description=_SCOPE_TO_CURRENT_CASE_DESCRIPTION,
    )


class RecoChipsCaseVectorSourceParams(BaseModel):
    """Parameters for RECO_CHIPS_FROM_CASE_VECTOR.

    Same output shape as RecoChipsEmailSourceParams (label + example_sentence +
    up-to-3 text candidates), but the source material is the per-case
    pgvector `case_file` collection (the debtor's petition / uploaded case
    docs) rather than gmail / court_drive.

    Both `text_query` and `example_sentence` are required — the case-vector
    variant is typically used for narrative legal clauses (employment
    descriptions, change-in-circumstances framing) where the quality of the
    generation and the downstream ChipFitAgent heal both depend on an
    explicit similarity query AND an explicit rhetorical frame. Authors who
    want looser defaults should use a reco-chips-from-email variant instead.
    """
    model_config = ConfigDict(extra="forbid")

    text_query: str = Field(
        description=(
            "Required pgvector similarity query for the case_file collection "
            "(e.g. 'employer occupation income employment Schedule I'). "
            "Shapes which case-file chunks the agent sees." + _QUERY_TEMPLATE_NOTE
        ),
    )
    label: str = Field(description="Header shown above the chips in the FE, e.g. 'Employment Description'")
    example_sentence: str = Field(
        description=(
            "Required name-free / date-free skeleton of the sentence the chip "
            "should resemble in tone and structure, e.g. 'The Debtor is employed "
            "in a capacity where their responsibilities require the handling of "
            "sensitive consumer information, and their employer places significant "
            "trust in them to do so.' The agent treats its interpretive/rhetorical "
            "claims as authoritative and folds in concrete facts from the source; "
            "it is instructed NOT to reproduce specific names/dates/amounts from it."
        ),
    )


class CaseVectorQueryEntry(BaseModel):
    """One inline case_vector retrieval composed into a chip generator's source material.

    Lets a `reco_chips_from_dependent_variables` field pull case-file
    chunks directly (e.g. Schedule I/J, Chapter 13 plan) without forcing
    the author to declare a separate `case_vector` variable for each
    retrieval. `text_query` supports `{{variable}}` substitution so
    cross-case retrievals like `"Schedule I {{prior_case_number}}"` work
    with the same helper as gmail/case_vector queries elsewhere.
    """
    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        description=(
            "Human-readable label for this retrieval, e.g. 'Current Schedule I & J'. "
            "Surfaced into the chip generator's prompt so the LLM knows what each "
            "block of source material represents."
        ),
    )
    text_query: str = Field(
        description=(
            "pgvector similarity query against the per-case case_file collection. "
            "Supports {{variable}} references; substituted at chip-generation time "
            "with the resolved value of the named LLM_DRAFT or SYSTEM_GENERATED variable."
        ),
    )


class RecoChipsFromDependentVariablesSourceParams(BaseModel):
    """Parameters for RECO_CHIPS_FROM_DEPENDENT_VARIABLES.

    Generates 3 chip suggestions by composing context from N already-resolved
    variables (instead of fetching from gmail / court_drive / case_vector).
    Replaces the legacy multi-input chip generator that motion-to-extend's
    `change_in_circumstances_explanation` and `prior_dismissal_explanation`
    rely on — those depend on prior-case dismissal reason, schedules, and the
    Chapter 13 plan, which are themselves separate variables in the new spec.

    Stage is USER_INPUT — chips become a PendingRecoChips envelope at the
    pause boundary, the user picks or types, and heal pass tone-matches
    against `example_sentence`. Composition happens at
    `UserInputResolver.apply` time — the fetch handler emits a marker
    FetchedContext only.
    """
    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="Header shown above the chips in the FE, e.g. 'Change in Circumstances'")
    example_sentence: str = Field(
        description=(
            "Required name-free / date-free skeleton of the sentence the chip "
            "should resemble in tone and structure. Used both as the chip-shape "
            "guide AND the heal target after the user picks/types."
        ),
    )
    dependent_variables: list[str] = Field(
        default_factory=list,
        description=(
            "Names of already-resolved variables whose values will be composed as "
            "context for chip generation. Each must reference a variable in the "
            "same template_spec whose stage resolves before USER_INPUT (i.e. "
            "LLM_DRAFT or SYSTEM_GENERATED). Order is preserved when composing the "
            "agent's source-material block."
        ),
    )
    case_vector_queries: list[CaseVectorQueryEntry] = Field(
        default_factory=list,
        description=(
            "Optional inline case_vector retrievals composed into the chip "
            "generator's context — saves authors from declaring a separate "
            "case_vector variable per retrieval. Each entry runs against the "
            "per-case case_file collection at chip-generation time."
        ),
    )
    dependent_chip_variables: list[str] = Field(
        default_factory=list,
        description=(
            "Names of OTHER reco_chips_from_dependent_variables fields whose "
            "GENERATED chip arrays (NOT user picks) feed this generator's context. "
            "Use to align thematically with sibling chips — e.g. dismissal_reason "
            "chips referencing change_in_circumstances chips so the explanations "
            "are consistent. Pass-2 ordering: dependents run AFTER their targets."
        ),
    )
    instruction: str | None = Field(
        default=None,
        description=(
            "Optional extra prompt guidance for the chip-generation LLM, e.g. "
            "'Synthesize 3 plausible dismissal reasons grounded in the trustee's "
            "stated reason and the debtor's prior schedules.'"
        ),
    )


class DropdownEmailSourceParams(BaseModel):
    """Parameters for DROPDOWN_FROM_GMAIL and DROPDOWN_FROM_COURT_DRIVE.

    Extractive single-select: the DropdownAgent queries the email backend,
    extracts up to ~20 distinct option strings matching `example_format`,
    the FE renders them under `label`, and the user clicks one verbatim.
    The picked string then flows through UserInputHealAgent before filling
    the docx — the pick is verbatim at the pick surface but gets grammar-
    fit + legal-tone healed on the server before substitution.

    `example_format` guides *extraction only* (tells the agent what each
    option should LOOK like). Heal uses `template_property_marker` from
    the TemplateField as its preferred-format target — not this field.
    """
    model_config = ConfigDict(extra="forbid")

    subject_query: str | None = None
    body_query: str | None = None
    label: str = Field(description="Header shown above the dropdown in the FE, e.g. 'Motion Type'")
    example_format: str = Field(
        description=(
            "Required example of what each extracted option should look like, "
            "e.g. 'Motion to Modify Plan' or 'Docket 42 — Notice of Appearance'. "
            "Shapes the DropdownAgent's extraction. NOT used at heal time."
        ),
    )
    scope_to_current_case: bool = Field(
        default=True,
        description=_SCOPE_TO_CURRENT_CASE_DESCRIPTION,
    )


class DropdownCaseVectorSourceParams(BaseModel):
    """Parameters for DROPDOWN_FROM_CASE_VECTOR.

    Same output shape as DropdownEmailSourceParams but the source material
    is the per-case pgvector `case_file` collection (the debtor's petition
    / uploaded case docs) instead of gmail / court_drive.

    All fields required — case-vector variants are used for narrative /
    controlled-list picks where quality collapses without an explicit
    similarity query AND an explicit extraction format, same discipline
    as RecoChipsCaseVectorSourceParams.
    """
    model_config = ConfigDict(extra="forbid")

    text_query: str = Field(
        description=(
            "Required pgvector similarity query for the case_file collection "
            "(e.g. 'motion type'). Shapes which case-file chunks the agent "
            "sees at extraction time." + _QUERY_TEMPLATE_NOTE
        ),
    )
    label: str = Field(description="Header shown above the dropdown in the FE, e.g. 'Motion Type'")
    example_format: str = Field(
        description=(
            "Required example of what each extracted option should look like. "
            "Shapes the DropdownAgent's extraction. NOT used at heal time."
        ),
    )


DEFAULT_SUPPORTING_DOC_EXTENSIONS = ["pdf", "docx", "txt", "md", "png", "jpg", "jpeg"]


class UserInputWithSupportingDocsSourceParams(BaseModel):
    """Parameters for USER_INPUT_WITH_SUPPORTING_DOCS.

    Pure user-input form: free-text + uploaded supporting docs. At USER_INPUT
    pause time, the server emits a PendingUserInputWithDocs envelope (label +
    accepted_file_types) with NO pre-pause LLM call — the user types a
    free-form explanation AND attaches supporting documents (PDFs, DOCX,
    TXT/MD, images) pre-uploaded to R2.

    On resume, ExplanationEnhanceAgent reads the user's text in the context
    of the uploaded docs (PDFs/images attached as multimodal content blocks;
    DOCX/TXT/MD parsed to text and inlined into the prompt) and produces one
    polished, corroborated explanation string. That string bypasses
    UserInputHealAgent (the enhancement IS the polish) and fills the
    placeholder directly.
    """
    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        description="Header shown above the textarea + uploader, e.g. 'Letter of Explanation'",
    )
    accepted_file_types: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SUPPORTING_DOC_EXTENSIONS),
        description="Lowercase file extensions the FE should allow and the server will accept.",
    )


class UserInputPlainTextSourceParams(BaseModel):
    """Parameters for USER_INPUT_PLAIN_TEXT.

    Lightweight user-input form for short attorney-authored prose
    (e.g. 'Basis for Objection', 'Recommended Disposition'). At USER_INPUT
    pause time the server emits a PendingUserInputPlainText envelope with
    NO pre-pause LLM call. The user types into a single textarea on the
    FE; the value flows back as a SingleValuePick and is healed against
    `example_output_sentence` (the author-defined skeleton of the desired
    healed output) before filling the placeholder.

    Distinct from USER_INPUT_WITH_SUPPORTING_DOCS — no file uploads, no
    ExplanationEnhanceAgent multimodal pass. Distinct from RECO_CHIPS_*
    — no LLM-generated suggestions to seed the textarea with.
    """
    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        description="Header shown above the textarea, e.g. 'Basis for Objection'.",
    )
    placeholder: str | None = Field(
        default=None,
        description="Optional placeholder text inside the textarea (FE hint for the user).",
    )
    example_output_sentence: str = Field(
        description=(
            "REQUIRED name-free / date-free skeleton of the polished sentence "
            "the heal step should produce. Drives the heal LLM as an explicit "
            "tone + structure target so the user's typed prose comes out in "
            "consistent legal-motion register regardless of how casually they "
            "wrote it. Should NOT contain specific names / dates / amounts — "
            "those come from the user's input."
        ),
    )


class UserInputDateSourceParams(BaseModel):
    """Parameters for USER_INPUT_DATE.

    Author-time declaration that the field's value comes from the user
    picking a date at draft time. The FE renders a calendar widget;
    the picked date is formatted client-side using `format` (strftime)
    and sent back as `SingleValuePick.value` (an already-formatted
    string ready to fill the placeholder verbatim). No heal pass —
    the value is a date string in a known format, not prose.

    Distinct from USER_INPUT_PLAIN_TEXT: that source is for free-form
    prose that runs through UserInputHealAgent. Date inputs don't
    benefit from heal and the FE needs an explicit signal to render
    a calendar (instead of guessing from a date-shaped example).
    """
    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        description="Header shown above the date picker, e.g. 'Date case was dismissed'.",
    )
    placeholder: str | None = Field(
        default=None,
        description="Optional helper text shown next to the picker.",
    )
    format: str = Field(
        default=DEFAULT_DATE_FORMAT,
        description=(
            "strftime format string used to render the picked date into "
            "the docx placeholder. Default `%B %-d, %Y` (e.g. 'April 1, 2026') "
            "matches system_generated.current_date and the dependent_on_variable "
            "default so cross-stage date math reads consistently."
        ),
    )


class DropdownFromConstantsSourceParams(BaseModel):
    """Parameters for DROPDOWN_FROM_CONSTANTS.

    Binds a template field to a curated reference_data list (currently just
    the attorney roster — `reference_short_code="ATTORNEYS"`). At dry-run
    time the FE will render a dropdown of list entries; the user picks one
    and downstream fields can auto-derive child attributes from that pick.

    Picks flow through UserInputHealAgent after selection, same as every
    other dropdown source — the heal step uses the field's
    `template_property_marker` (e.g. the exact attorney-name form the source
    template originally used, like 'Chad Van Horn, Esq.') as the preferred-
    format target, so a roster entry stored as 'Chad Van Horn' still heals
    to the suffix'd form the template expects.

    Schema plumbing ships ahead of the runtime resolver — the actual
    dropdown-emit + auto-derive + heal wiring rides with the virtual-parent /
    tabular plan that comes next. Templates that reference this source
    today will compose cleanly but resolve to empty at draft time until
    that wiring lands.
    """
    model_config = ConfigDict(extra="forbid")

    reference_short_code: str = Field(
        description=(
            "short_code of the reference_data row whose JSON value holds the "
            "pickable list (e.g. 'ATTORNEYS')."
        ),
    )
    label: str = Field(
        description="Header shown above the dropdown in the FE, e.g. 'Signing Attorney'.",
    )


class AutoDerivedRuleEffect(str, Enum):
    """Strategy used by `auto_derived_from_variable` to compute its value from the parent.

    EXTRACT_SUBSTRING — the AutoDeriveAgent LLM extracts a substring from the
    parent's resolved value. Used for the tabular row pattern (one parent
    variable feeds N read-only children).

    PLURALIZE_BY_COUNT — deterministic, no LLM. Inspects the parent's joined
    value for an Oxford-comma plurality signal (e.g. ", and ", " and ") and
    emits one of two author-defined values. Used for grammar derivatives
    (`s` suffix, `has`/`have`, `is`/`are`) that agree with a list-style
    parent's pick count.
    """

    EXTRACT_SUBSTRING = "extract_substring"
    PLURALIZE_BY_COUNT = "pluralize_by_count"


class AutoDerivedSourceParams(BaseModel):
    """Parameters for AUTO_DERIVED_FROM_VARIABLE.

    The template agent emits this whenever a value (or substring of a value)
    extracted as one variable also appears elsewhere in the document in a
    different surrounding context — typically the title or header repeating
    part of a body-sentence variable. The auto-derived variable is filled at
    draft/dry-run time by AutoDerivedResolver, which asks AutoDeriveAgent to
    extract the right portion from the parent variable's already-resolved
    value.

    For grammar derivatives (`Creditor{{ s }}`, `{{ HasHave }}`, `{{ IsAre }}`)
    that agree with a list-style parent's pick count, set
    `rule_effect="pluralize_by_count"` and provide `singular_value` /
    `plural_value`. The resolver detects plurality by Oxford-comma signal
    (", and ", " and ") in the parent's joined string — no LLM call needed.
    Caveat: a single legal name containing " and " (e.g. "Smith and Wesson, LLC")
    will false-positive; mitigate by ensuring the multi-select's
    `example_formats` produce an unambiguous Oxford join, OR set the parent
    multi-select's `oxford=false` with a non-overlapping `list_joiner`.

    Author-readonly: the template agent picks both the source AND the
    parent; the FE must not let the user reconfigure these. The companion
    `read_only=true` flag on TemplateVariable signals this to the FE.
    """
    model_config = ConfigDict(extra="forbid")

    dependent_variable: str = Field(
        description="Name of the parent template_variable whose resolved value drives this derivation",
    )
    rule_effect: AutoDerivedRuleEffect = Field(
        default=AutoDerivedRuleEffect.EXTRACT_SUBSTRING,
        description=(
            "Derivation strategy. 'extract_substring' is LLM-driven (default); "
            "'pluralize_by_count' is deterministic and uses singular_value/plural_value."
        ),
    )
    singular_value: str | None = Field(
        default=None,
        description=(
            "Value emitted when the parent represents a single item (1 pick). "
            "REQUIRED when rule_effect='pluralize_by_count'; must be null otherwise. "
            "May be the empty string (e.g. for the 's' suffix in 'Creditor{s}')."
        ),
    )
    plural_value: str | None = Field(
        default=None,
        description=(
            "Value emitted when the parent represents 2+ items (Oxford-comma signal). "
            "REQUIRED when rule_effect='pluralize_by_count'; must be null otherwise."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _drop_dependent_on_variable_bleed(cls, data: Any) -> Any:
        """Drop fields the template agent occasionally copies from the sibling
        DependentOnVariableSourceParams class.

        Both classes share `dependent_variable` and `rule_effect`, so when the
        template-agent LLM is emitting a `pluralize_by_count` payload it
        sometimes also tacks on `derived_value_type` / `format` /
        `rule_effect_value` — fields that belong to the date-math sibling, not
        here. With `extra="forbid"` those three keys would otherwise tank the
        whole template extraction. We strip them with a logged warning so the
        legitimate AutoDerived fields parse cleanly; structurally invalid
        payloads (random typos, missing required fields) still raise.

        Defensive copy: pydantic's smart-union tries each variant on the
        same input dict. Mutating the caller's dict here would corrupt
        downstream attempts (e.g. on legitimate `DependentOnVariableSourceParams`
        payloads, dropping `derived_value_type` from the caller's dict would
        make THAT variant fail too). We copy and return the cleaned version.
        """
        if not isinstance(data, dict):
            return data
        cleaned = dict(data)
        for stale in ("derived_value_type", "format", "rule_effect_value"):
            if stale in cleaned:
                logger.warning(
                    "AutoDerivedSourceParams: dropping spurious '%s' field "
                    "(likely confused with DependentOnVariableSourceParams)",
                    stale,
                )
                cleaned.pop(stale)
        return cleaned

    @model_validator(mode="after")
    def _validate_pluralize_pair(self) -> "AutoDerivedSourceParams":
        if self.rule_effect == AutoDerivedRuleEffect.PLURALIZE_BY_COUNT:
            if self.singular_value is None or self.plural_value is None:
                raise ValueError(
                    "singular_value and plural_value are required when "
                    "rule_effect is 'pluralize_by_count'"
                )
        elif self.singular_value is not None or self.plural_value is not None:
            raise ValueError(
                "singular_value / plural_value are only valid when rule_effect "
                "is 'pluralize_by_count'"
            )
        return self


class MultiSelectFromCaseVectorSourceParams(BaseModel):
    """Parameters for MULTI_SELECT_FROM_CASE_VECTOR.

    Multi-pick variant of `dropdown_from_case_vector`. The DropdownAgent
    queries the case_file collection with `text_query`, extracts up to
    20 distinct option strings matching `example_formats`, and the FE
    presents them as multi-select cards under `label` + `instruction`.
    The user picks K of N; the resolved value is an Oxford-comma-joined
    prose string of the picks (e.g. 'A, B, and C') ready to drop into a
    docx slot directly. UserInputHealAgent runs against the
    `template_property_marker` shape to align punctuation / suffix labels
    without borrowing the marker's literal sample facts.

    Stage is USER_INPUT — emits a `PendingMultiSelect` envelope at the
    pause boundary. Source-agnostic: the strings represent whatever the
    template author wants (assets, creditors, claims, hearings, etc.).
    """
    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        description=(
            "Panel heading shown to user, e.g. 'Select Assets for Reaffirmation'."
        ),
    )
    instruction: str | None = Field(
        default=None,
        description="Optional sub-instruction shown below the label.",
    )
    text_query: str = Field(
        description=(
            "Required topical / section query — drives BOTH passes:\n"
            "  1. pgvector similarity retrieval over the case_file collection "
            "(DropdownAgent first pass).\n"
            "  2. Vision-fallback section locator surfaced to "
            "MultiSelectVisionAgent as a <locator> block telling the LLM "
            "WHERE in the petition PDF to look (which schedule, which "
            "categories to include or exclude).\n"
            "Write as section + topic prose so it works for both passes, "
            "e.g. 'Schedule A/B (Real and Personal Property) — list every "
            "real property and every vehicle the debtor owns; skip "
            "household goods'." + _QUERY_TEMPLATE_NOTE
        ),
    )
    example_formats: list[str] = Field(
        min_length=1,
        description=(
            "One or more example option strings. The DropdownAgent extracts "
            "option strings matching ANY of these shapes. Use multiple entries "
            "when one source produces options of distinct shapes (e.g. vehicles "
            "AND properties in one asset picker). Multi-line entries (with '\\n') "
            "are preserved verbatim and rendered as multi-line cards by the FE."
        ),
    )
    min_picks: int = Field(
        default=1,
        ge=0,
        description="Minimum number of options the user must pick.",
    )
    max_picks: int | None = Field(
        default=None,
        description="Maximum number of options the user may pick; null for unbounded.",
    )
    list_joiner: str = Field(
        default=", ",
        description="Separator between items for non-Oxford joins.",
    )
    oxford: bool = Field(
        default=True,
        description=(
            "When true, render 1/2/3+ picks with Oxford-comma logic "
            "('A', 'A and B', 'A, B, and C'). When false, all picks are "
            "joined with `list_joiner` literally."
        ),
    )

    @model_validator(mode="after")
    def _validate_picks(self) -> "MultiSelectFromCaseVectorSourceParams":
        if self.max_picks is not None and self.max_picks < self.min_picks:
            raise ValueError("max_picks must be >= min_picks when set")
        if not self.text_query.strip():
            raise ValueError("text_query must be a non-empty string")
        if not self.example_formats:
            raise ValueError("example_formats must contain at least one entry")
        for fmt in self.example_formats:
            if not fmt.strip():
                raise ValueError("example_formats entries must be non-empty strings")
        return self


class MultiSelectFromGmailSourceParams(BaseModel):
    """Parameters for MULTI_SELECT_FROM_GMAIL.

    Multi-pick variant whose source material is the case's Gmail inbox
    (rather than the petition pgvector). The DropdownAgent queries Gmail
    using `subject_query` / `body_query`, extracts up to 20 distinct option
    strings matching `example_formats`, and the FE presents them as
    multi-select cards under `label` + `instruction`. The user picks K of N;
    the resolved value is an Oxford-comma-joined prose string of the picks
    (e.g. 'A, B, and C') ready to drop into a docx slot directly.
    UserInputHealAgent runs against the `template_property_marker` shape
    to align punctuation / suffix labels without borrowing the marker's
    literal sample facts.

    Stage is USER_INPUT — emits a `PendingMultiSelect` envelope at the
    pause boundary. NO petition-vision fallback (Gmail has no PDF
    counterpart) — when the live Gmail search returns empty, the
    per-case `gmail_collection` pgvector fallback fires the same way it
    does for plain `gmail` raw lookups.

    Use this when the multi-select options live in case email
    correspondence rather than the petition itself — e.g. picking
    creditors from Proof of Claim filings, picking dockets from clerk
    notices, picking hearings from §341 meeting notices.
    """
    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        description=(
            "Panel heading shown to user, e.g. 'Select Creditors that Altered Plan Terms'."
        ),
    )
    instruction: str | None = Field(
        default=None,
        description="Optional sub-instruction shown below the label.",
    )
    subject_query: str | None = Field(
        default=None,
        description="Query to search email subjects." + _QUERY_TEMPLATE_NOTE,
    )
    body_query: str | None = Field(
        default=None,
        description="Query to search email body." + _QUERY_TEMPLATE_NOTE,
    )
    scope_to_current_case: bool = Field(
        default=True,
        description=_SCOPE_TO_CURRENT_CASE_DESCRIPTION,
    )
    example_formats: list[str] = Field(
        min_length=1,
        description=(
            "One or more example option strings. The DropdownAgent extracts "
            "option strings matching ANY of these shapes. Use multiple entries "
            "when one source produces options of distinct shapes. Multi-line "
            "entries (with '\\n') are preserved verbatim and rendered as "
            "multi-line cards by the FE."
        ),
    )
    min_picks: int = Field(
        default=1,
        ge=0,
        description="Minimum number of options the user must pick.",
    )
    max_picks: int | None = Field(
        default=None,
        description="Maximum number of options the user may pick; null for unbounded.",
    )
    list_joiner: str = Field(
        default=", ",
        description="Separator between items for non-Oxford joins.",
    )
    oxford: bool = Field(
        default=True,
        description=(
            "When true, render 1/2/3+ picks with Oxford-comma logic "
            "('A', 'A and B', 'A, B, and C'). When false, all picks are "
            "joined with `list_joiner` literally."
        ),
    )

    @model_validator(mode="after")
    def _validate_picks(self) -> "MultiSelectFromGmailSourceParams":
        if self.max_picks is not None and self.max_picks < self.min_picks:
            raise ValueError("max_picks must be >= min_picks when set")
        if not (self.subject_query or "").strip() and not (self.body_query or "").strip():
            raise ValueError(
                "at least one of subject_query / body_query must be a non-empty string"
            )
        if not self.example_formats:
            raise ValueError("example_formats must contain at least one entry")
        for fmt in self.example_formats:
            if not fmt.strip():
                raise ValueError("example_formats entries must be non-empty strings")
        return self


class InheritFromParentSourceParams(BaseModel):
    """Marks this variable as a slot — filled by whichever parent attaches
    this child at draft time.

    Configuration for the slot lives on each parent template's BundleCompanion
    entry (in `slot_configurations`), NOT here. This child-side declaration
    just says "I have a slot named X." The same child can be paired with
    many parents and have its slots filled differently for each pairing.

    Phase 1B: source_params accepted at save time; the
    InheritFromParentResolver returns `fallback_value` (or a placeholder
    marker) since no parent context is threaded yet. Phase 2 wires the
    bundling engine to populate parent_context, at which point the
    resolver dispatches per slot kind (parent_variable / extract_from_draft
    / literal) using the parent's per-companion slot_configurations.
    """
    model_config = ConfigDict(extra="forbid")

    fallback_value: str | None = Field(
        default=None,
        description=(
            "Optional placeholder rendered when this child is dry-run "
            "alone (no parent attached). Useful for studio iteration "
            "before bundling lands."
        ),
    )


class GroupDropdownComposite(BaseModel):
    """Runtime composite emitted by build_agent_config — one per group.

    Self-contained for docx fill: both sibling variable names and their
    placeholder strings live inside the composite so DocxTemplateService.fill_template
    can make TWO substitutions from ONE template_fields entry.
    """
    model_config = ConfigDict(extra="forbid")

    subject_query: str | None = None
    body_query: str | None = None
    group_label: str
    left_variable: str
    left_label: str
    left_template_variable_string: str
    right_variable: str
    right_label: str
    right_template_variable_string: str


# Union aliases for source_params fields.
#
# Two flavors because group-dropdowns change shape between authoring and
# runtime: the spec persists two sibling variables with GroupDropdownSourceParams
# on the anchor, and compose collapses them into a single GroupDropdownComposite
# on the runtime TemplateField. All other *SourceParams classes are identical
# across both flavors.
AuthorSourceParams = (
    GmailSourceParams
    | CourtDriveSourceParams
    | VectorSourceParams
    | CaseVectorSourceParams
    | ConstantsSourceParams
    | DependentOnVariableSourceParams
    | SystemGeneratedSourceParams
    | GroupDropdownSourceParams
    | RecoChipsEmailSourceParams
    | RecoChipsCaseVectorSourceParams
    | RecoChipsFromDependentVariablesSourceParams
    | DropdownEmailSourceParams
    | DropdownCaseVectorSourceParams
    | DropdownFromConstantsSourceParams
    | UserInputWithSupportingDocsSourceParams
    | UserInputPlainTextSourceParams
    | UserInputDateSourceParams
    | AutoDerivedSourceParams
    | MultiSelectFromCaseVectorSourceParams
    | MultiSelectFromGmailSourceParams
    | InheritFromParentSourceParams
)

RuntimeSourceParams = (
    GmailSourceParams
    | CourtDriveSourceParams
    | VectorSourceParams
    | CaseVectorSourceParams
    | ConstantsSourceParams
    | DependentOnVariableSourceParams
    | SystemGeneratedSourceParams
    | GroupDropdownComposite
    | RecoChipsEmailSourceParams
    | RecoChipsCaseVectorSourceParams
    | RecoChipsFromDependentVariablesSourceParams
    | DropdownEmailSourceParams
    | DropdownCaseVectorSourceParams
    | DropdownFromConstantsSourceParams
    | UserInputWithSupportingDocsSourceParams
    | UserInputPlainTextSourceParams
    | UserInputDateSourceParams
    | AutoDerivedSourceParams
    | MultiSelectFromCaseVectorSourceParams
    | MultiSelectFromGmailSourceParams
    | InheritFromParentSourceParams
)
