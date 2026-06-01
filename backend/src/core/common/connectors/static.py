"""Static-source connectors — values come from server state, not retrieval.

`law_practice_vector` is technically vector-backed but currently a stub;
grouping it here keeps the per-source files balanced. `constants` and
`dropdown_from_constants` read from reference_data; `system_generated`
emits server-clock values.
"""

from src.core.agents.types.sources import FieldSource, SystemGeneratedType

from ._schemas import Connector, ConnectorParam, _options_from_enum
from ._shared import _DROPDOWN_LABEL_DESC, _QUERY_TEMPLATE_NOTE


LAW_PRACTICE_VECTOR_CONNECTOR = Connector(
    source=FieldSource.LAW_PRACTICE_VECTOR.value,
    display_name="Law Practice Vector",
    description="Search law practice vector knowledge base",
    params=[
        ConnectorParam(
            name="text_query",
            type="string",
            required=True,
            description="Query to search law practice vector store." + _QUERY_TEMPLATE_NOTE,
        ),
    ],
)

CONSTANTS_CONNECTOR = Connector(
    source=FieldSource.CONSTANTS.value,
    display_name="Constants",
    description="Fetch value from reference data by short_code",
    params=[
        ConnectorParam(
            name="short_code",
            type="string",
            required=True,
            description="The short_code of the reference data to fetch",
        ),
    ],
)

SYSTEM_GENERATED_CONNECTOR = Connector(
    source=FieldSource.SYSTEM_GENERATED.value,
    display_name="System Generated",
    description=(
        "Value produced deterministically by the server at draft time "
        "(e.g. current date from the server clock). No LLM extraction involved."
    ),
    params=[
        ConnectorParam(
            name="type",
            type="enum",
            required=True,
            description="Which system value to generate.",
            options=_options_from_enum(
                SystemGeneratedType,
                labels={SystemGeneratedType.CURRENT_DATE.value: "Current Date"},
                previews={SystemGeneratedType.CURRENT_DATE.value: "e.g. April 13, 2026"},
            ),
        ),
    ],
)

DROPDOWN_FROM_CONSTANTS_CONNECTOR = Connector(
    source=FieldSource.DROPDOWN_FROM_CONSTANTS.value,
    display_name="Dropdown from Constants",
    description=(
        "Present a single-select dropdown whose options come from a curated "
        "reference_data list (currently the attorney roster under short_code "
        "'ATTORNEYS'). No LLM extraction — options are a direct DB read at "
        "dry-run/draft pause time. The user's pick is healed against the "
        "field's template_property_marker (preferred-format target) before "
        "filling, so a roster entry like 'Chad Van Horn' still heals to "
        "'Chad Van Horn, Esq.' when the template's marker uses the suffix'd "
        "form."
    ),
    params=[
        ConnectorParam(
            name="reference_short_code",
            type="string",
            required=True,
            description=(
                "short_code of the reference_data row whose JSON value holds "
                "the pickable list (e.g. 'ATTORNEYS'). Must match an existing "
                "reference_data entry; the validator rejects unknown codes at "
                "compose time."
            ),
        ),
        ConnectorParam(
            name="label",
            type="string",
            required=True,
            description=_DROPDOWN_LABEL_DESC,
        ),
    ],
)
