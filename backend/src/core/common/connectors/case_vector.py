"""Case-vector-backed connectors — read from the per-case `case_file` collection.

Plain case_vector (auto-derived query), reco-chips, multi-select, and
single-select dropdown variants. All consume pgvector chunks from the
case's uploaded documents (petition, schedules, etc.).
"""

from src.core.agents.types.sources import FieldSource

from ._schemas import Connector, ConnectorParam
from ._shared import (
    _DROPDOWN_EXAMPLE_FORMAT_DESC,
    _DROPDOWN_LABEL_DESC,
    _QUERY_TEMPLATE_NOTE,
)


CASE_VECTOR_CONNECTOR = Connector(
    source=FieldSource.CASE_VECTOR.value,
    display_name="Case Vector",
    description=(
        "Search case-specific vector knowledge base. Leave text_query blank "
        "to auto-derive the query from the variable name (default behavior); "
        "set it explicitly for fine-grained control."
    ),
    params=[
        ConnectorParam(
            name="text_query",
            type="string",
            required=False,
            description=(
                "Optional. Explicit text to retrieve relevant case-file chunks "
                "against. Leave blank to auto-derive from the variable name." + _QUERY_TEMPLATE_NOTE
            ),
        ),
        ConnectorParam(
            name="enable_web_search",
            type="boolean",
            required=False,
            description=(
                "Optional. When true, runs a web-search enhancement pass after "
                "case_vector + vision retrieval. Uses the petition-extracted "
                "value as an anchor, looks up small pieces of stable external "
                "context the petition doesn't carry (e.g. resolving a Florida "
                "county name to its judicial circuit number), and reshapes the "
                "result to match template_property_marker. Off by default; "
                "requires a non-empty current value (i.e. case_vector must "
                "first pull SOMETHING — set text_query if the variable name "
                "alone won't retrieve the right chunk)."
            ),
        ),
    ],
)

RECO_CHIPS_FROM_CASE_VECTOR_CONNECTOR = Connector(
    source=FieldSource.RECO_CHIPS_FROM_CASE_VECTOR.value,
    display_name="Recommendation Chips from Case Documents",
    description=(
        "Similarity-search the case's uploaded documents (petition, schedules, etc.), "
        "generate up to 3 short text candidates for the author to click as a starting "
        "point. The author picks one, edits it if needed, and the final text fills "
        "this variable."
    ),
    params=[
        ConnectorParam(
            name="text_query",
            type="string",
            required=True,
            description=(
                "Required similarity query for the case_file collection "
                "(e.g. 'employer occupation income'). Shapes which case-file "
                "chunks the agent sees at generation time." + _QUERY_TEMPLATE_NOTE
            ),
        ),
        ConnectorParam(
            name="label",
            type="string",
            required=True,
            description=(
                "Header shown above the chips at dry-run/draft time "
                "(e.g. 'Employment Description'). Describes what the user is "
                "being asked to provide."
            ),
        ),
        ConnectorParam(
            name="example_sentence",
            type="string",
            required=True,
            description=(
                "Required name-free / date-free skeleton of the sentence the chip "
                "will slot into, used as the authoritative tone / structure / "
                "rhetorical-framing reference (e.g. 'The Debtor is employed in a "
                "capacity where their responsibilities require the handling of "
                "sensitive consumer information, and their employer places "
                "significant trust in them to do so.'). Do NOT include specific "
                "names, dates, or amounts — those come from the source material."
            ),
        ),
    ],
)

MULTI_SELECT_FROM_CASE_VECTOR_CONNECTOR = Connector(
    source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR.value,
    display_name="Multi-Select from Case Documents",
    description=(
        "Pre-fetch a list of options from the case PDFs and present the "
        "user a multi-select card UI at dry-run/draft time. Each option "
        "is one string (matching one of `example_formats`). The user "
        "picks K of N; the resolved value is the Oxford-comma-joined "
        "prose string of the picks (e.g. 'A, B, and C'), ready to drop "
        "into a docx slot directly. UserInputHealAgent then aligns "
        "punctuation / suffix labels against the field's "
        "template_property_marker. Source-agnostic — the strings can "
        "represent assets, creditors, claims, hearings, etc."
    ),
    params=[
        ConnectorParam(
            name="label",
            type="string",
            required=True,
            description=(
                "Panel heading shown to the user (e.g. 'Select Assets for "
                "Reaffirmation')."
            ),
        ),
        ConnectorParam(
            name="instruction",
            type="string",
            required=False,
            description=(
                "Optional sub-instruction shown below the label (e.g. "
                "'Select the assets you want to mention in the motion. "
                "You can select multiple.')."
            ),
        ),
        ConnectorParam(
            name="text_query",
            type="string",
            required=True,
            description=(
                "Topical / section query — drives BOTH passes: "
                "(1) pgvector similarity retrieval over the case_file "
                "collection (DropdownAgent first pass), and "
                "(2) the vision-fallback section locator surfaced to "
                "MultiSelectVisionAgent telling the LLM WHERE in the "
                "petition PDF to look. Write as section + topic prose "
                "so it works for both, e.g. 'Schedule A/B (Real and "
                "Personal Property) — list every real property and every "
                "vehicle the debtor owns; skip household goods'." + _QUERY_TEMPLATE_NOTE
            ),
        ),
        ConnectorParam(
            name="example_formats",
            type="string_list",
            required=True,
            description=(
                "One or more example option strings. The DropdownAgent "
                "extracts options matching ANY of these shapes. Use "
                "multiple entries when one source produces options of "
                "distinct shapes (e.g. vehicles AND properties in one "
                "asset picker). Multi-line entries (`\\n`-separated) "
                "render as multi-line cards in the awaiting-input modal."
            ),
        ),
        ConnectorParam(
            name="min_picks",
            type="number",
            required=False,
            description=(
                "Minimum number of options the user must pick (defaults to 1)."
            ),
        ),
        ConnectorParam(
            name="max_picks",
            type="number",
            required=False,
            description=(
                "Maximum number of options the user may pick. Leave empty "
                "for unbounded."
            ),
        ),
        ConnectorParam(
            name="list_joiner",
            type="string",
            required=False,
            description=(
                "Separator between items for non-Oxford joins (defaults "
                "to ', '). Used as the comma between non-final items "
                "even when oxford=true."
            ),
        ),
        ConnectorParam(
            name="oxford",
            type="boolean",
            required=False,
            description=(
                "When true (default), render 1/2/3+ picks with Oxford-"
                "comma logic ('A', 'A and B', 'A, B, and C'). When false, "
                "join all picks with `list_joiner` literally."
            ),
        ),
    ],
)

DROPDOWN_FROM_CASE_VECTOR_CONNECTOR = Connector(
    source=FieldSource.DROPDOWN_FROM_CASE_VECTOR.value,
    display_name="Dropdown from Case Documents",
    description=(
        "Similarity-search the case's uploaded documents (petition, schedules, "
        "etc.), extract up to 20 distinct options matching example_format, "
        "present a single-select dropdown at dry-run/draft time. The user's "
        "pick is healed for grammar + tone before filling this variable."
    ),
    params=[
        ConnectorParam(
            name="text_query",
            type="string",
            required=True,
            description=(
                "Required similarity query for the case_file collection "
                "(e.g. 'motion type'). Shapes which case-file chunks the "
                "agent sees at extraction time." + _QUERY_TEMPLATE_NOTE
            ),
        ),
        ConnectorParam(
            name="label",
            type="string",
            required=True,
            description=_DROPDOWN_LABEL_DESC,
        ),
        ConnectorParam(
            name="example_format",
            type="string",
            required=True,
            description=_DROPDOWN_EXAMPLE_FORMAT_DESC,
        ),
    ],
)
