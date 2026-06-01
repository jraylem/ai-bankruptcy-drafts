"""
Derivative rule executor for template variables whose value is derived from
another variable in the same template.

Runs deterministically after the draft agent has resolved all externally
sourced variables. For each variable with FieldSource.DEPENDENT_ON_VARIABLE,
this module looks up the parent's resolved value, applies the configured
RuleEffect (date arithmetic), and emits a new ResolvedTemplateValue.

Intentionally synchronous and IO-free so the same function can be reused
from both the dry-run flow and the real drafting flow without async plumbing.
"""

from datetime import datetime

from dateutil.relativedelta import relativedelta

from ..types.resolution import ResolvedTemplateValue, ResolverStage
from ..types.sources import DependentOnVariableSourceParams, DerivedValueType, RuleEffect
from ..types.spec import TemplateField


def _apply_date_effect(dt: datetime, effect: RuleEffect, amount: int) -> datetime:
    if effect == RuleEffect.INCREMENT_BY_DAYS:
        return dt + relativedelta(days=amount)
    if effect == RuleEffect.DECREMENT_BY_DAYS:
        return dt - relativedelta(days=amount)
    if effect == RuleEffect.INCREMENT_BY_MONTHS:
        return dt + relativedelta(months=amount)
    if effect == RuleEffect.DECREMENT_BY_MONTHS:
        return dt - relativedelta(months=amount)
    if effect == RuleEffect.INCREMENT_BY_YEARS:
        return dt + relativedelta(years=amount)
    if effect == RuleEffect.DECREMENT_BY_YEARS:
        return dt - relativedelta(years=amount)
    return dt


def _resolve_one(
    field: TemplateField,
    params: DependentOnVariableSourceParams,
    parent_values: dict[str, str],
) -> ResolvedTemplateValue:
    property_name = field.property_name
    parent_name = params.dependent_variable
    parent_value = parent_values.get(parent_name, "")

    if not parent_value:
        return ResolvedTemplateValue.low_confidence(
            property_name,
            f"Parent variable '{parent_name}' was not resolved or was empty.",
        )

    if params.derived_value_type != DerivedValueType.DATE:
        return ResolvedTemplateValue.low_confidence(
            property_name,
            f"Unsupported derived_value_type '{params.derived_value_type.value}'.",
        )

    parse_format = params.format.replace("%-", "%")
    try:
        parsed_dt = datetime.strptime(parent_value, parse_format)
    except ValueError as exc:
        return ResolvedTemplateValue.low_confidence(
            property_name,
            f"Failed to parse '{parent_value}' from '{parent_name}' with format '{params.format}': {exc}",
        )

    amount = int(params.rule_effect_value) if params.rule_effect_value is not None else 0
    shifted = _apply_date_effect(parsed_dt, params.rule_effect, amount)
    rendered = shifted.strftime(params.format)

    if params.rule_effect == RuleEffect.FORMAT_ONLY:
        reasoning = f"Reformatted '{parent_name}' ({parent_value}) as '{params.format}'."
    else:
        reasoning = (
            f"Derived from '{parent_name}' ({parent_value}) "
            f"{params.rule_effect.value} {amount}."
        )

    return ResolvedTemplateValue.high_confidence(property_name, rendered, reasoning)


class DerivativeResolver:
    """Resolve DERIVATIVE-stage fields by deriving values from a parent variable."""

    stage = ResolverStage.DERIVATIVE

    @classmethod
    def apply(
        cls,
        template_fields: list[TemplateField],
        resolved_values: list[ResolvedTemplateValue],
    ) -> list[ResolvedTemplateValue]:
        """Compute derived values for every derivative-stage field.

        Reads parent values out of `resolved_values` (the LLM-extracted values
        from the draft agent plus any system-generated values), applies each
        dependent field's configured rule, and returns a new list of
        ResolvedTemplateValue entries — one per dependent field in
        `template_fields`. Does not mutate `resolved_values`.

        Parents that are unresolved, empty, or unparseable against the configured
        format yield a low-confidence empty value with a reasoning string naming
        the failure. v1 disallows chained dependents at the validation layer, so
        a single left-to-right pass is sufficient.
        """
        parent_values: dict[str, str] = {
            rv.property_name: rv.value for rv in resolved_values if rv.value
        }

        derived: list[ResolvedTemplateValue] = []
        for field in template_fields:
            if field.stage != ResolverStage.DERIVATIVE:
                continue
            params = field.source_params
            if not isinstance(params, DependentOnVariableSourceParams):
                derived.append(
                    ResolvedTemplateValue.low_confidence(
                        field.property_name,
                        "source_params did not match DependentOnVariableSourceParams.",
                    )
                )
                continue
            derived.append(_resolve_one(field, params, parent_values))

        return derived
