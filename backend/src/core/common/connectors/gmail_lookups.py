"""Gmail-as-multi-select connectors.

Holds the multi-select-from-Gmail variant separately from the email.py
connectors because its param shape (label + instruction + example_formats
+ pick bounds + joiners) diverges from the plain raw-search / dropdown /
chip variants. Splitting it out keeps email.py focused on the small,
shared-shape email connectors.
"""

from src.core.agents.types.sources import FieldSource

from ._schemas import Connector, ConnectorParam
from ._shared import (
    _EMAIL_BODY_PARAM,
    _EMAIL_SUBJECT_PARAM,
    _SCOPE_TO_CURRENT_CASE_PARAM,
)


MULTI_SELECT_FROM_GMAIL_CONNECTOR = Connector(
    source=FieldSource.MULTI_SELECT_FROM_GMAIL.value,
    display_name="Multi-Select from Gmail",
    description=(
        "Pre-fetch a list of options from the case's Gmail correspondence "
        "and present the user a multi-select card UI at dry-run/draft "
        "time. Each option is one string (matching one of "
        "`example_formats`). The user picks K of N; the resolved value "
        "is the Oxford-comma-joined prose string of the picks "
        "(e.g. 'A, B, and C'), ready to drop into a docx slot directly. "
        "UserInputHealAgent then aligns punctuation / suffix labels "
        "against the field's template_property_marker. Use this when "
        "options live in case email threads — e.g. picking creditors "
        "from Proof of Claim filings, picking dockets from clerk "
        "notices."
    ),
    params=[
        ConnectorParam(
            name="label",
            type="string",
            required=True,
            description=(
                "Panel heading shown to the user (e.g. 'Select Creditors "
                "that Altered Plan Terms')."
            ),
        ),
        ConnectorParam(
            name="instruction",
            type="string",
            required=False,
            description=(
                "Optional sub-instruction shown below the label."
            ),
        ),
        _EMAIL_SUBJECT_PARAM,
        _EMAIL_BODY_PARAM,
        _SCOPE_TO_CURRENT_CASE_PARAM,
        ConnectorParam(
            name="example_formats",
            type="string_list",
            required=True,
            description=(
                "One or more example option strings. The DropdownAgent "
                "extracts options matching ANY of these shapes. Use "
                "multiple entries when one source produces options of "
                "distinct shapes. Multi-line entries (`\\n`-separated) "
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
