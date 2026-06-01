"""Email-backed connectors — Gmail + Court Drive variants.

Plain raw-search (Gmail / Court Drive), group-dropdown, reco-chips,
single-select dropdown — every variant whose backend is one of the email
services lives here.
"""

from src.core.agents.types.sources import FieldSource

from ._schemas import Connector
from ._shared import (
    _EMAIL_BODY_PARAM,
    _EMAIL_SUBJECT_PARAM,
    _SCOPE_TO_CURRENT_CASE_PARAM,
    _dropdown_email_connector,
    _group_dropdown_connector,
    _reco_chips_connector,
)


GMAIL_CONNECTOR = Connector(
    source=FieldSource.GMAIL.value,
    display_name="Gmail",
    description="Search emails from Gmail",
    params=[_EMAIL_SUBJECT_PARAM, _EMAIL_BODY_PARAM, _SCOPE_TO_CURRENT_CASE_PARAM],
)

COURT_DRIVE_CONNECTOR = Connector(
    source=FieldSource.COURT_DRIVE.value,
    display_name="Court Drive",
    description="Search court drive documents",
    params=[_EMAIL_SUBJECT_PARAM, _EMAIL_BODY_PARAM, _SCOPE_TO_CURRENT_CASE_PARAM],
)

GROUP_DROPDOWN_FROM_GMAIL_CONNECTOR = _group_dropdown_connector(
    source=FieldSource.GROUP_DROPDOWN_FROM_GMAIL.value,
    display_name="Group Dropdown from Gmail",
    description=(
        "Fetch raw email data from Gmail, extract (left, right) pairs, present the "
        "user a dropdown at dry-run/draft time. Picking one pair fills this variable "
        "(left) and its declared partner variable (right) in a single step."
    ),
    left_label_example="Docket Number",
    right_label_example="Docket Title",
)

GROUP_DROPDOWN_FROM_COURT_DRIVE_CONNECTOR = _group_dropdown_connector(
    source=FieldSource.GROUP_DROPDOWN_FROM_COURT_DRIVE.value,
    display_name="Group Dropdown from Court Drive",
    description=(
        "Fetch raw data from Court Drive, extract (left, right) pairs, present the "
        "user a dropdown at dry-run/draft time. Picking one pair fills this variable "
        "(left) and its declared partner variable (right) in a single step."
    ),
)

RECO_CHIPS_FROM_GMAIL_CONNECTOR = _reco_chips_connector(
    source=FieldSource.RECO_CHIPS_FROM_GMAIL.value,
    display_name="Recommendation Chips from Gmail",
    description=(
        "Fetch raw email data from Gmail, generate up to 3 short text candidates "
        "for the author to click as a starting point. The author picks one, edits "
        "it if needed, and the final text fills this variable."
    ),
)

RECO_CHIPS_FROM_COURT_DRIVE_CONNECTOR = _reco_chips_connector(
    source=FieldSource.RECO_CHIPS_FROM_COURT_DRIVE.value,
    display_name="Recommendation Chips from Court Drive",
    description=(
        "Fetch raw data from Court Drive, generate up to 3 short text candidates "
        "for the author to click as a starting point. The author picks one, edits "
        "it if needed, and the final text fills this variable."
    ),
)

DROPDOWN_FROM_GMAIL_CONNECTOR = _dropdown_email_connector(
    source=FieldSource.DROPDOWN_FROM_GMAIL.value,
    display_name="Dropdown from Gmail",
    description=(
        "Fetch raw email data from Gmail, extract up to 20 distinct options "
        "matching example_format, present a single-select dropdown at "
        "dry-run/draft time. The user's pick is healed for grammar + tone "
        "before filling this variable."
    ),
)

DROPDOWN_FROM_COURT_DRIVE_CONNECTOR = _dropdown_email_connector(
    source=FieldSource.DROPDOWN_FROM_COURT_DRIVE.value,
    display_name="Dropdown from Court Drive",
    description=(
        "Fetch raw data from Court Drive, extract up to 20 distinct options "
        "matching example_format, present a single-select dropdown at "
        "dry-run/draft time. The user's pick is healed for grammar + tone "
        "before filling this variable."
    ),
)
