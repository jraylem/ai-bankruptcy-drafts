"""User-input connectors — values come from the author at dry-run/draft pause.

Plain prose textarea, date picker, supporting-doc upload, and the
deps-driven reco-chip generator (whose context is composed from already-
resolved variables rather than a fresh fetch).
"""

from src.core.agents.types.sources import FieldSource

from ._schemas import Connector, ConnectorParam


RECO_CHIPS_FROM_DEPENDENT_VARIABLES_CONNECTOR = Connector(
    source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES.value,
    display_name="Recommendation Chips from Dependent Variables",
    description=(
        "Generate up to 3 short text candidates by composing context from N "
        "already-resolved variable values (instead of fetching from gmail / "
        "court_drive / case_vector). Use when the chip generator needs to "
        "synthesize from prior agent outputs — e.g. a 'change in circumstances' "
        "reco-chips field that draws on the trustee's dismissal reason and "
        "the prior case's schedules."
    ),
    params=[
        ConnectorParam(
            name="label",
            type="string",
            required=True,
            description=(
                "Header shown above the chips at dry-run/draft time. Describes "
                "what the user is being asked to provide."
            ),
        ),
        ConnectorParam(
            name="example_sentence",
            type="string",
            required=True,
            description=(
                "Required name-free / date-free skeleton of the sentence the chip "
                "will slot into, used as the authoritative tone / structure / "
                "rhetorical-framing reference AND the heal target after the user "
                "picks/types. Do NOT include specific names, dates, or amounts."
            ),
        ),
        ConnectorParam(
            name="dependent_variables",
            type="string_list",
            required=False,
            description=(
                "Names of already-resolved variables whose values will be "
                "composed as context for chip generation. Each must reference a "
                "variable in the same template_spec whose stage is LLM_DRAFT or "
                "SYSTEM_GENERATED (i.e. resolves before the user-input pause). "
                "At least one of dependent_variables, case_vector_queries, or "
                "dependent_chip_variables must be non-empty."
            ),
        ),
        ConnectorParam(
            name="case_vector_queries",
            type="object_list",
            required=False,
            description=(
                "Optional inline case_vector retrievals composed into the chip "
                "generator's source material. Each entry is a {label, text_query} "
                "object; text_query supports {{variable}} substitution at chip-"
                "generation time. Saves authors from declaring a separate "
                "case_vector variable per retrieval (e.g. Schedule I/J)."
            ),
        ),
        ConnectorParam(
            name="dependent_chip_variables",
            type="string_list",
            required=False,
            description=(
                "Names of OTHER reco_chips_from_dependent_variables fields whose "
                "GENERATED chip arrays (NOT user picks) feed this generator's "
                "context for tonal alignment. Targets must also be "
                "reco_chips_from_dependent_variables; cycles are rejected at "
                "compose time."
            ),
        ),
        ConnectorParam(
            name="instruction",
            type="string",
            required=False,
            description=(
                "Optional extra prompt guidance for the chip-generation LLM "
                "(e.g. 'Synthesize 3 plausible dismissal reasons grounded in "
                "the trustee's stated reason and the debtor's prior schedules.')."
            ),
        ),
    ],
)

USER_INPUT_PLAIN_TEXT_CONNECTOR = Connector(
    source=FieldSource.USER_INPUT_PLAIN_TEXT.value,
    display_name="User Input — Plain Text",
    description=(
        "Lightweight prose form. At dry-run/draft time the FE renders a textarea "
        "under `label` (with `placeholder` as the hint and `example_output_sentence` "
        "as the tone target shown below the textarea). The user types short "
        "attorney-authored prose (e.g. 'Basis for Objection'); the value flows "
        "through the grammar/tone heal pass against `example_output_sentence` "
        "before filling this variable. No file uploads, no LLM enhancement step "
        "— distinct from User Input with Supporting Docs."
    ),
    params=[
        ConnectorParam(
            name="label",
            type="string",
            required=True,
            description=(
                "Header shown above the textarea at dry-run/draft time "
                "(e.g. 'Basis for Objection'). Describes what the user is "
                "being asked to write."
            ),
        ),
        ConnectorParam(
            name="placeholder",
            type="string",
            required=False,
            description=(
                "Optional placeholder text inside the textarea — a one-line FE "
                "hint about the expected content. Leave empty when the label is "
                "self-explanatory."
            ),
        ),
        ConnectorParam(
            name="example_output_sentence",
            type="string",
            required=True,
            description=(
                "Required name-free / date-free skeleton of the polished "
                "sentence the heal step should produce. Drives the heal LLM as "
                "an explicit tone + structure target so the user's typed prose "
                "comes out in consistent legal-motion register regardless of "
                "how casually they wrote it. Should NOT contain specific names / "
                "dates / amounts — those come from the user's input."
            ),
        ),
    ],
)

USER_INPUT_DATE_CONNECTOR = Connector(
    source=FieldSource.USER_INPUT_DATE.value,
    display_name="User Input — Date",
    description=(
        "Calendar form. At dry-run/draft time the FE renders a date picker "
        "under `label`; the user picks a date which is rendered using "
        "`format` (strftime) and fills this variable verbatim. No heal pass "
        "— the value is already in its final docx-ready form. Use this when "
        "the variable is a date the user supplies per case (e.g. dismissal "
        "date, hearing date) — distinct from system_generated.current_date "
        "(today) or dependent_on_variable date math."
    ),
    params=[
        ConnectorParam(
            name="label",
            type="string",
            required=True,
            description=(
                "Header shown above the date picker at dry-run/draft time "
                "(e.g. 'Date case was dismissed')."
            ),
        ),
        ConnectorParam(
            name="placeholder",
            type="string",
            required=False,
            description=(
                "Optional helper text shown next to the picker. Leave empty "
                "when the label is self-explanatory."
            ),
        ),
        ConnectorParam(
            name="format",
            type="string",
            required=True,
            description=(
                "strftime format string used to render the picked date into "
                "the docx placeholder. Default `%B %-d, %Y` (e.g. 'April 1, 2026') "
                "matches system_generated.current_date and dependent_on_variable "
                "defaults so cross-stage date math reads consistently."
            ),
        ),
    ],
)

USER_INPUT_WITH_SUPPORTING_DOCS_CONNECTOR = Connector(
    source=FieldSource.USER_INPUT_WITH_SUPPORTING_DOCS.value,
    display_name="User Input with Supporting Docs",
    description=(
        "Pure user-input form. At dry-run/draft time the FE renders a free-text "
        "area plus a file picker; the user types an explanation and uploads "
        "supporting documents (PDFs, DOCX, TXT/MD, images) to "
        "POST /cases/{case_id}/supporting-docs before resuming. On resume the "
        "server reads the user's text in the context of the uploaded docs with "
        "an Opus multimodal call and produces one polished, corroborated "
        "paragraph that fills this variable. Bypasses the standard grammar/tone "
        "heal pass — the enhancement step IS the polish."
    ),
    params=[
        ConnectorParam(
            name="label",
            type="string",
            required=True,
            description=(
                "Header shown above the textarea + uploader at dry-run/draft "
                "time (e.g. 'Letter of Explanation'). Describes what the user "
                "is being asked to write and substantiate."
            ),
        ),
    ],
)
