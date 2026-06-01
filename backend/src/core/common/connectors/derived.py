"""Variable-derivation connectors — values flow from another template variable.

`dependent_on_variable` exposes user-configurable rule effects (date math
+ format-only), `auto_derived_from_variable` is read-only — the template
agent emits it whenever an extracted value also appears elsewhere in the
document with a different surrounding context.
"""

from src.core.agents.types.sources import (
    DerivedValueType,
    FieldSource,
    RuleEffect,
)

from ._schemas import Connector, ConnectorParam, ConnectorParamCondition, _options_from_enum


DEPENDENT_ON_VARIABLE_CONNECTOR = Connector(
    source=FieldSource.DEPENDENT_ON_VARIABLE.value,
    display_name="Dependent on Variable",
    description="Derive this variable's value from another template variable by applying a rule (e.g. DateFiled + 14 days).",
    params=[
        ConnectorParam(
            name="dependent_variable",
            type="template_variable_ref",
            required=True,
            description="The parent template variable this value is derived from.",
        ),
        ConnectorParam(
            name="derived_value_type",
            type="enum",
            required=True,
            description="The type of value being derived.",
            options=_options_from_enum(
                DerivedValueType,
                labels={DerivedValueType.DATE.value: "Date"},
                previews={DerivedValueType.DATE.value: "e.g. April 13, 2026"},
            ),
        ),
        ConnectorParam(
            name="rule_effect",
            type="enum",
            required=True,
            description="The rule to apply to the dependent variable's value.",
            options=_options_from_enum(
                RuleEffect,
                labels={
                    RuleEffect.INCREMENT_BY_DAYS.value: "Add days",
                    RuleEffect.DECREMENT_BY_DAYS.value: "Subtract days",
                    RuleEffect.INCREMENT_BY_MONTHS.value: "Add months",
                    RuleEffect.DECREMENT_BY_MONTHS.value: "Subtract months",
                    RuleEffect.INCREMENT_BY_YEARS.value: "Add years",
                    RuleEffect.DECREMENT_BY_YEARS.value: "Subtract years",
                    RuleEffect.FORMAT_ONLY.value: "Reformat only (no shift)",
                },
            ),
            visible_when=ConnectorParamCondition(
                field="derived_value_type",
                equals=DerivedValueType.DATE.value,
            ),
        ),
        ConnectorParam(
            name="rule_effect_value",
            type="string",
            required=False,
            description=(
                "Numeric amount for the rule effect (e.g. '14' for 14 days). "
                "Not used when rule_effect is 'format_only'."
            ),
            visible_when=ConnectorParamCondition(
                field="rule_effect",
                not_in=[RuleEffect.FORMAT_ONLY.value],
            ),
            required_when=ConnectorParamCondition(
                field="rule_effect",
                not_in=[RuleEffect.FORMAT_ONLY.value],
            ),
        ),
    ],
)

AUTO_DERIVED_FROM_VARIABLE_CONNECTOR = Connector(
    source=FieldSource.AUTO_DERIVED_FROM_VARIABLE.value,
    display_name="Auto-Derived from Variable",
    description=(
        "READ-ONLY. The template agent emits this whenever a value (or "
        "substring of a value) extracted as one variable also appears "
        "elsewhere in the document in a different surrounding context. "
        "AutoDeriveAgent extracts the right portion from the parent "
        "variable's already-resolved value at fill time. Parent and "
        "source are not editable."
    ),
    params=[
        ConnectorParam(
            name="dependent_variable",
            type="template_variable_ref",
            required=True,
            description="The parent variable whose resolved value drives this derivation.",
        ),
    ],
)
