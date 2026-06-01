"""FE-facing source-connector registry.

Each `Connector` describes one `FieldSource` — what display name to show,
what params the user must fill in, and (optionally) FE-evaluated rules
for conditional visibility / requiredness. The `/template/connectors`
endpoint serves this list verbatim.

Every `source` value and every enum option value in here is pulled
directly from the enums in `agents.types.sources` — so a typo on a
source name or a renamed enum value fails at module import time rather
than silently drifting out of sync with the backend.

Internal layout — connectors are grouped by backend so each per-source
file stays focused on what's actually distinct, while the public
`CONNECTORS` list below preserves the historical FE-facing ordering
(which is asserted via the snapshot test in `tests/core/common/test_connectors.py`).
Reordering this list requires regenerating the snapshot.

  - `_schemas.py` — pydantic models (`Connector`, `ConnectorParam`, etc.)
  - `_shared.py` — shared params + helper builders for near-identical variants
  - `email.py` — Gmail / Court Drive raw, group-dropdown, reco-chips, dropdown
  - `case_vector.py` — case_vector raw + reco-chips + multi-select + dropdown
  - `gmail_lookups.py` — multi_select_from_gmail (diverges from email.py shape)
  - `static.py` — constants, system_generated, dropdown_from_constants, law_practice_vector
  - `derived.py` — dependent_on_variable, auto_derived_from_variable
  - `user_input.py` — plain text / date / supporting-docs / chips-from-deps
  - `bundling.py` — inherit_from_parent (child-side slot marker)
"""

from ._schemas import (
    Connector,
    ConnectorParam,
    ConnectorParamCondition,
    ConnectorParamOption,
)
from .bundling import INHERIT_FROM_PARENT_CONNECTOR
from .case_vector import (
    CASE_VECTOR_CONNECTOR,
    DROPDOWN_FROM_CASE_VECTOR_CONNECTOR,
    MULTI_SELECT_FROM_CASE_VECTOR_CONNECTOR,
    RECO_CHIPS_FROM_CASE_VECTOR_CONNECTOR,
)
from .derived import (
    AUTO_DERIVED_FROM_VARIABLE_CONNECTOR,
    DEPENDENT_ON_VARIABLE_CONNECTOR,
)
from .email import (
    COURT_DRIVE_CONNECTOR,
    DROPDOWN_FROM_COURT_DRIVE_CONNECTOR,
    DROPDOWN_FROM_GMAIL_CONNECTOR,
    GMAIL_CONNECTOR,
    GROUP_DROPDOWN_FROM_COURT_DRIVE_CONNECTOR,
    GROUP_DROPDOWN_FROM_GMAIL_CONNECTOR,
    RECO_CHIPS_FROM_COURT_DRIVE_CONNECTOR,
    RECO_CHIPS_FROM_GMAIL_CONNECTOR,
)
from .gmail_lookups import MULTI_SELECT_FROM_GMAIL_CONNECTOR
from .static import (
    CONSTANTS_CONNECTOR,
    DROPDOWN_FROM_CONSTANTS_CONNECTOR,
    LAW_PRACTICE_VECTOR_CONNECTOR,
    SYSTEM_GENERATED_CONNECTOR,
)
from .user_input import (
    RECO_CHIPS_FROM_DEPENDENT_VARIABLES_CONNECTOR,
    USER_INPUT_DATE_CONNECTOR,
    USER_INPUT_PLAIN_TEXT_CONNECTOR,
    USER_INPUT_WITH_SUPPORTING_DOCS_CONNECTOR,
)


CONNECTORS = [
    GMAIL_CONNECTOR,
    COURT_DRIVE_CONNECTOR,
    CASE_VECTOR_CONNECTOR,
    LAW_PRACTICE_VECTOR_CONNECTOR,
    CONSTANTS_CONNECTOR,
    SYSTEM_GENERATED_CONNECTOR,
    DEPENDENT_ON_VARIABLE_CONNECTOR,
    GROUP_DROPDOWN_FROM_GMAIL_CONNECTOR,
    GROUP_DROPDOWN_FROM_COURT_DRIVE_CONNECTOR,
    RECO_CHIPS_FROM_GMAIL_CONNECTOR,
    RECO_CHIPS_FROM_COURT_DRIVE_CONNECTOR,
    RECO_CHIPS_FROM_CASE_VECTOR_CONNECTOR,
    RECO_CHIPS_FROM_DEPENDENT_VARIABLES_CONNECTOR,
    DROPDOWN_FROM_GMAIL_CONNECTOR,
    DROPDOWN_FROM_COURT_DRIVE_CONNECTOR,
    USER_INPUT_PLAIN_TEXT_CONNECTOR,
    USER_INPUT_DATE_CONNECTOR,
    USER_INPUT_WITH_SUPPORTING_DOCS_CONNECTOR,
    AUTO_DERIVED_FROM_VARIABLE_CONNECTOR,
    MULTI_SELECT_FROM_CASE_VECTOR_CONNECTOR,
    MULTI_SELECT_FROM_GMAIL_CONNECTOR,
    DROPDOWN_FROM_CASE_VECTOR_CONNECTOR,
    DROPDOWN_FROM_CONSTANTS_CONNECTOR,
    INHERIT_FROM_PARENT_CONNECTOR,
]


__all__ = [
    "CONNECTORS",
    "Connector",
    "ConnectorParam",
    "ConnectorParamCondition",
    "ConnectorParamOption",
]
