"""Tests for DerivativeResolver — pure date-arithmetic logic."""

import pytest

from src.core.agents.resolvers.derivative_resolver import DerivativeResolver
from src.core.agents.types.sources import (
    DerivedValueType,
    FieldSource,
    GmailSourceParams,
    RuleEffect,
)
from tests.core.factories import (
    make_dependent_params,
    make_resolved_value,
    make_template_field,
)


def _derivative_field(
    property_name: str = "response_due",
    dependent_variable: str = "date_filed",
    rule_effect: RuleEffect = RuleEffect.INCREMENT_BY_DAYS,
    rule_effect_value: str | None = "14",
):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.DEPENDENT_ON_VARIABLE,
        source_params=make_dependent_params(
            dependent_variable=dependent_variable,
            rule_effect=rule_effect,
            rule_effect_value=rule_effect_value,
        ),
    )


@pytest.mark.unit
def test_apply_empty_when_no_derivative_fields_in_spec():
    # Only a GMAIL field in the spec — nothing for the derivative resolver to do.
    field = make_template_field(source=FieldSource.GMAIL, source_params=GmailSourceParams())
    out = DerivativeResolver.apply([field], [])
    assert out == []


@pytest.mark.unit
def test_apply_increments_parent_date_by_days():
    parent = make_resolved_value("date_filed", "January 1, 2026")
    field = _derivative_field(rule_effect_value="14")

    result = DerivativeResolver.apply([field], [parent])

    assert len(result) == 1
    rv = result[0]
    assert rv.property_name == "response_due"
    assert rv.value == "January 15, 2026"
    assert rv.confidence == "high"
    assert "date_filed" in rv.reasoning
    assert "increment_by_days" in rv.reasoning


@pytest.mark.unit
def test_apply_decrements_parent_date_by_days():
    parent = make_resolved_value("date_filed", "January 15, 2026")
    field = _derivative_field(
        rule_effect=RuleEffect.DECREMENT_BY_DAYS,
        rule_effect_value="7",
    )

    result = DerivativeResolver.apply([field], [parent])

    assert result[0].value == "January 8, 2026"
    assert result[0].confidence == "high"


@pytest.mark.unit
def test_apply_increments_parent_date_by_months():
    parent = make_resolved_value("date_filed", "January 15, 2026")
    field = _derivative_field(
        rule_effect=RuleEffect.INCREMENT_BY_MONTHS,
        rule_effect_value="3",
    )

    result = DerivativeResolver.apply([field], [parent])

    assert result[0].value == "April 15, 2026"


@pytest.mark.unit
def test_apply_increments_parent_date_by_years():
    parent = make_resolved_value("date_filed", "March 1, 2026")
    field = _derivative_field(
        rule_effect=RuleEffect.INCREMENT_BY_YEARS,
        rule_effect_value="2",
    )

    result = DerivativeResolver.apply([field], [parent])

    assert result[0].value == "March 1, 2028"


@pytest.mark.unit
def test_apply_format_only_reformats_without_shift():
    parent = make_resolved_value("date_filed", "January 1, 2026")
    field = _derivative_field(
        rule_effect=RuleEffect.FORMAT_ONLY,
        rule_effect_value=None,
    )

    result = DerivativeResolver.apply([field], [parent])

    assert result[0].value == "January 1, 2026"
    assert "Reformatted" in result[0].reasoning


@pytest.mark.unit
def test_apply_returns_low_confidence_when_parent_unresolved():
    # No resolved values at all → parent is missing
    field = _derivative_field(dependent_variable="date_filed")

    result = DerivativeResolver.apply([field], [])

    assert len(result) == 1
    assert result[0].confidence == "low"
    assert result[0].value == ""
    assert "date_filed" in result[0].reasoning


@pytest.mark.unit
def test_apply_returns_low_confidence_when_parent_value_empty():
    parent = make_resolved_value("date_filed", "")  # empty string counts as unresolved
    field = _derivative_field(dependent_variable="date_filed")

    result = DerivativeResolver.apply([field], [parent])

    assert result[0].confidence == "low"


@pytest.mark.unit
def test_apply_returns_low_confidence_when_parent_unparseable():
    parent = make_resolved_value("date_filed", "not-a-date")
    field = _derivative_field(dependent_variable="date_filed")

    result = DerivativeResolver.apply([field], [parent])

    assert result[0].confidence == "low"
    assert "Failed to parse" in result[0].reasoning


@pytest.mark.unit
def test_apply_returns_low_confidence_when_source_params_wrong_type():
    parent = make_resolved_value("date_filed", "January 1, 2026")
    # Use a DERIVATIVE-stage field (DEPENDENT_ON_VARIABLE source) with
    # wrong source_params type — the resolver must not blow up.
    field = make_template_field(
        property_name="response_due",
        source=FieldSource.DEPENDENT_ON_VARIABLE,
        source_params=GmailSourceParams(),  # wrong shape
    )

    result = DerivativeResolver.apply([field], [parent])

    assert len(result) == 1
    assert result[0].confidence == "low"
    assert "DependentOnVariableSourceParams" in result[0].reasoning


@pytest.mark.unit
def test_apply_does_not_mutate_input_resolved_values():
    parent = make_resolved_value("date_filed", "January 1, 2026")
    original_snapshot = parent.model_dump()
    field = _derivative_field()

    _ = DerivativeResolver.apply([field], [parent])

    assert parent.model_dump() == original_snapshot


@pytest.mark.unit
def test_apply_emits_one_value_per_derivative_field_in_order():
    parent = make_resolved_value("date_filed", "January 1, 2026")
    f1 = _derivative_field(property_name="fourteen_days", rule_effect_value="14")
    f2 = _derivative_field(
        property_name="one_month",
        rule_effect=RuleEffect.INCREMENT_BY_MONTHS,
        rule_effect_value="1",
    )

    result = DerivativeResolver.apply([f1, f2], [parent])

    assert [rv.property_name for rv in result] == ["fourteen_days", "one_month"]
    assert result[0].value == "January 15, 2026"
    assert result[1].value == "February 1, 2026"
