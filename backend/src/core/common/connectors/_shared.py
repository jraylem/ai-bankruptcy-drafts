"""Shared params + helper builders reused across multiple connector files.

Email connectors all carry the same subject/body/scope params; reco-chips
and dropdown-from-email variants are near-identical across gmail vs
court_drive backends. Centralizing the shared pieces here keeps the
per-source files focused on what's actually distinct.
"""

from ._schemas import Connector, ConnectorParam


_QUERY_TEMPLATE_NOTE = (
    " Supports {{variable}} references; substituted at fetch time with the "
    "resolved value of the named variable (must be LLM_DRAFT or "
    "SYSTEM_GENERATED stage)."
)

_EMAIL_SUBJECT_PARAM = ConnectorParam(
    name="subject_query",
    type="string",
    required=False,
    description="Query to search email subjects." + _QUERY_TEMPLATE_NOTE,
)

_EMAIL_BODY_PARAM = ConnectorParam(
    name="body_query",
    type="string",
    required=False,
    description="Query to search email body." + _QUERY_TEMPLATE_NOTE,
)

_SCOPE_TO_CURRENT_CASE_PARAM = ConnectorParam(
    name="scope_to_current_case",
    type="boolean",
    required=False,
    description=(
        "When checked (default), the BE adds the current case's number variants "
        "as an AND clause. Uncheck for cross-case templates that need to reach "
        "into another case's email thread (typically combined with "
        "{{prior_case_number}} in the query)."
    ),
)

_GROUP_LABEL_PARAM = ConnectorParam(
    name="group_label",
    type="string",
    required=True,
    description=(
        "Title shown above the dropdown at dry-run/draft time (e.g. 'Docket'). "
        "Describes what the user is picking — distinct from the left/right column headers."
    ),
)

_RIGHT_PARTNER_PARAM = ConnectorParam(
    name="right_partner_variable",
    type="template_variable_ref",
    required=True,
    description="The sibling template variable (with source unset) that receives the right column's value on pick.",
)


def _reco_chips_connector(
    source: str,
    display_name: str,
    description: str,
) -> Connector:
    """Build one of the near-identical reco_chips_from_* connectors.

    Reco-chips source_params are parallel across the gmail / court_drive
    variants; this helper keeps them DRY.
    """
    return Connector(
        source=source,
        display_name=display_name,
        description=description,
        params=[
            _EMAIL_SUBJECT_PARAM,
            _EMAIL_BODY_PARAM,
            ConnectorParam(
                name="label",
                type="string",
                required=True,
                description=(
                    "Header shown above the chips at dry-run/draft time "
                    "(e.g. 'Change in Circumstances'). Describes what the "
                    "user is being asked to provide."
                ),
            ),
            ConnectorParam(
                name="example_sentence",
                type="string",
                required=False,
                description=(
                    "Optional name-free / date-free skeleton of the sentence the chip "
                    "will slot into, used as a tone / structure / rhetorical-framing "
                    "reference (e.g. 'The Debtor is employed in a capacity where their "
                    "responsibilities require the handling of sensitive consumer "
                    "information, and their employer places significant trust in them "
                    "to do so.'). Do NOT include specific names, dates, or amounts — "
                    "those come from the source material."
                ),
            ),
            _SCOPE_TO_CURRENT_CASE_PARAM,
        ],
    )


_DROPDOWN_LABEL_DESC = (
    "Header shown above the dropdown at dry-run/draft time "
    "(e.g. 'Motion Type'). Describes what the user is being asked to select."
)

_DROPDOWN_EXAMPLE_FORMAT_DESC = (
    "Required example of what each extracted option should look like "
    "(e.g. 'Motion to Modify Plan' or 'Docket 42 — Notice of Appearance'). "
    "Shapes the extraction agent's output. Not used at heal time."
)


def _dropdown_email_connector(
    source: str,
    display_name: str,
    description: str,
) -> Connector:
    """Build one of the near-identical dropdown_from_* email connectors.

    Email variants share the same subject/body query shape and differ only
    in which backend the extraction agent queries.
    """
    return Connector(
        source=source,
        display_name=display_name,
        description=description,
        params=[
            _EMAIL_SUBJECT_PARAM,
            _EMAIL_BODY_PARAM,
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
            _SCOPE_TO_CURRENT_CASE_PARAM,
        ],
    )


def _group_dropdown_connector(
    source: str,
    display_name: str,
    description: str,
    left_label_example: str | None = None,
    right_label_example: str | None = None,
) -> Connector:
    """Build one of the near-identical group_dropdown_from_* connectors.

    `left_label_example` / `right_label_example` optionally append an
    ", e.g. '<example>'" suffix to the column-label descriptions — used
    today to give concrete dockets in the gmail variant while keeping the
    court_drive variant generic. Leave both None for no suffix.
    """
    left_desc = "Column header for the left column of the dropdown (the value this variable receives)"
    if left_label_example:
        left_desc = f"{left_desc}, e.g. '{left_label_example}'"

    right_desc = "Column header for the right column of the dropdown (the value the partner variable receives)"
    if right_label_example:
        right_desc = f"{right_desc}, e.g. '{right_label_example}'"

    return Connector(
        source=source,
        display_name=display_name,
        description=description,
        params=[
            _EMAIL_SUBJECT_PARAM,
            _EMAIL_BODY_PARAM,
            _GROUP_LABEL_PARAM,
            ConnectorParam(name="left_label", type="string", required=True, description=left_desc),
            ConnectorParam(name="right_label", type="string", required=True, description=right_desc),
            _RIGHT_PARTNER_PARAM,
            _SCOPE_TO_CURRENT_CASE_PARAM,
        ],
    )
