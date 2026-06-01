"""WizardSourceParams — the unified source-binding shape for v2 fields.

Replaces v1's 25-source-type + 19-param-shape sprawl with one
discriminator (`source: SourceKind`) plus a flat set of fields the
relevant source kind reads. Mirrors the FE mock at
bkdrafts-fe/src/components/studio-v2/types.ts (`WizardSourceParams`)
1:1 — the FE and BE share this contract verbatim through the v3 API.

Source kinds (8):
  - gmail            — paralegal writes a natural-language extraction
                       prompt; the v2 extractor agent calls GmailSearch
                       (+ VisionFallback if needed) at resolve time.
  - case_file        — same shape, backed by pgvector + VisionFallback.
  - attorney         — pick a fixed attorney (raw mode) or paralegal
                       picks at draft time (dropdown / multi_select).
  - constants        — firm reference_data row, looked up by
                       constants_short_code. Raw shape only.
  - current_date     — system clock, formatted via date healing.
  - author_input     — paralegal types/picks at draft time. The
                       author_input_kind sub-discriminator chooses
                       between plain_text / date / with_docs.
  - derived_from_variable
                     — DeriveAgent extracts from another variable's
                       resolved raw_context or value, using a
                       natural-language extraction_prompt.
  - value_from_parent_bundle
                     — companion templates inherit from the lead's
                       resolved value; uses parent_bundle_fallback if
                       the lead hasn't filled in yet.

Presentation shape is orthogonal — only meaningful for sources that
accept a shape (gmail / case_file / attorney). Other sources MUST
keep presentation_shape = "raw" (validated by Phase 2 resolver).

Dates always heal to the firm-default format on the BE side; the
date_format field is advisory only and the wizard never writes to it
(Behavior Contract #6 in the plan).
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SourceKind(StrEnum):
    GMAIL = "gmail"
    CASE_FILE = "case_file"
    ATTORNEY = "attorney"
    CONSTANTS = "constants"
    CURRENT_DATE = "current_date"
    AUTHOR_INPUT = "author_input"
    DERIVED_FROM_VARIABLE = "derived_from_variable"
    VALUE_FROM_PARENT_BUNDLE = "value_from_parent_bundle"


class PresentationShape(StrEnum):
    RAW = "raw"
    DROPDOWN = "dropdown"
    CHIP = "chip"
    MULTI_SELECT = "multi_select"


class AuthorInputKind(StrEnum):
    PLAIN_TEXT = "plain_text"
    DATE = "date"
    WITH_DOCS = "with_docs"


class WizardSourceParams(BaseModel):
    """Unified params shape for every v2 template field.

    Frontend wizard saves this shape verbatim via
    `PATCH /api/v3/studio/templates/{id}/fields/{field_id}`. Phase 2's
    WizardResolver dispatches on (source, presentation_shape) to pick
    the right resolver/agent.
    """

    model_config = ConfigDict(extra="forbid")

    source: SourceKind
    presentation_shape: PresentationShape = PresentationShape.RAW

    # Natural-language extraction prompt — used by gmail, case_file,
    # and derived_from_variable sources. Other sources leave it null.
    extraction_prompt: str | None = None

    # How the final inserted value should look. Optional shape hint
    # the LLM extractor + heal agents both consult.
    output_expectation: str | None = None

    # OPTIONAL universal post-resolution web-search enhancement step.
    # When set, every resolved value (regardless of source) is run
    # through `WebEnhanceAgentV2` with this instruction as the
    # author's directive — Claude searches the open web, looks up a
    # missing piece of public/stable context, and reshapes the value
    # to fit the template. On failure the original value passes
    # through unchanged (soft-fail by design). Cost-heavy + slow —
    # leave blank to skip.
    web_enhance_instruction: str | None = None

    # Required when presentation_shape != RAW or source == AUTHOR_INPUT.
    # The prompt the paralegal sees above the picker/input at draft
    # time. Wizard validates required-ness on the FE side.
    label: str | None = None

    # Sample option text the extractor agent uses as a shape reference
    # for dropdown / chip / multi_select sources (NOT {{var}} syntax
    # — concrete sample text per Behavior Contract #1).
    example_format: str | None = None

    # multi_select bounds — ignored for other shapes.
    min_picks: int = Field(default=1, ge=1, le=20)
    max_picks: int = Field(default=5, ge=1, le=20)

    # author_input only — picks the draft-time input widget.
    author_input_kind: AuthorInputKind | None = None

    # constants only — short_code lookup into reference_data.
    constants_short_code: str | None = None

    # attorney + raw shape only — locks the template to one attorney.
    attorney_id: str | None = None

    # BE-advisory only. Every date-shaped value heals to firm default
    # regardless. Kept on the schema for forward compat; wizard never
    # writes to it (Behavior Contract #6).
    date_format: str = "%B %-d, %Y"

    # derived_from_variable only — the parent variable this field
    # derives from.
    dependent_variable: str | None = None

    # value_from_parent_bundle only — used if the lead filing hasn't
    # filled this in yet.
    parent_bundle_fallback: str | None = None

    # Other variable names whose resolved values this extractor needs
    # at resolve time (gmail / case_file only). The Phase 2 pipeline
    # waits for these to resolve first and passes them as a separate
    # dependency_values map distinct from extraction_prompt. NEVER
    # spliced into the prompt as {{var}} syntax. Behavior Contract #3.
    query_dependencies: list[str] = Field(default_factory=list)


def default_wizard_params() -> WizardSourceParams:
    """Construct the wizard's default params (matches FE mock's
    `defaultWizardParams()`). Useful in tests + as a TemplateAgentV2
    fallback when no source-suggestion heuristic fires.
    """
    return WizardSourceParams(source=SourceKind.GMAIL)
