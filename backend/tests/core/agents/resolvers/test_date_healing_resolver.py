"""Tests for DateHealingResolver — normalize common date strings to DEFAULT_DATE_FORMAT."""

import pytest

from src.core.agents.resolvers.date_healing_resolver import DateHealingResolver
from src.core.agents.types.sources import DEFAULT_DATE_FORMAT
from tests.core.factories import make_resolved_value


@pytest.mark.unit
def test_empty_list_passthrough():
    assert DateHealingResolver.apply([]) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "input_value",
    [
        "01/21/2026",         # %m/%d/%Y
        "2026-01-21",         # %Y-%m-%d
        "2026/01/21",         # %Y/%m/%d
        "21-01-2026",         # %d-%m-%Y
        "January 21, 2026",   # %B %d, %Y
        "Jan 21, 2026",       # %b %d, %Y
        "21 January 2026",    # %d %B %Y
        "21 Jan 2026",        # %d %b %Y
    ],
)
def test_all_supported_formats_normalize_to_default(input_value):
    rv = make_resolved_value(value=input_value)
    healed = DateHealingResolver.apply([rv])

    assert len(healed) == 1
    assert healed[0].value == "January 21, 2026"


@pytest.mark.unit
def test_already_normalized_value_is_returned_as_is():
    rv = make_resolved_value(value="January 21, 2026", reasoning="already normal")
    healed = DateHealingResolver.apply([rv])

    # model_copy isn't triggered — same instance / same reasoning string
    assert healed[0] is rv
    assert healed[0].reasoning == "already normal"


@pytest.mark.unit
def test_non_date_value_passes_through_unchanged():
    rv = make_resolved_value(value="John Smith", reasoning="extracted name")
    healed = DateHealingResolver.apply([rv])

    assert healed[0] is rv
    assert healed[0].value == "John Smith"


@pytest.mark.unit
def test_empty_value_passes_through():
    rv = make_resolved_value(value="")
    healed = DateHealingResolver.apply([rv])
    assert healed[0] is rv


@pytest.mark.unit
def test_reasoning_is_annotated_on_rewrite():
    rv = make_resolved_value(value="01/21/2026", reasoning="from subject line")
    healed = DateHealingResolver.apply([rv])

    assert healed[0].value == "January 21, 2026"
    assert "auto-normalized date from '01/21/2026'" in healed[0].reasoning
    assert healed[0].reasoning.startswith("from subject line")  # original preserved


@pytest.mark.unit
def test_returns_new_list_not_original():
    rv = make_resolved_value(value="not a date")
    inp = [rv]
    out = DateHealingResolver.apply(inp)
    assert out is not inp  # fresh list
    assert len(out) == 1


@pytest.mark.unit
def test_default_date_format_is_stable():
    """Guardrail: several consumers assume DEFAULT_DATE_FORMAT is 'Month D, YYYY'."""
    assert DEFAULT_DATE_FORMAT == "%B %-d, %Y"


@pytest.mark.unit
def test_mixed_batch_heals_only_recognized_dates():
    name = make_resolved_value(property_name="name", value="John")
    short = make_resolved_value(property_name="date_short", value="01/21/2026")
    already_ok = make_resolved_value(property_name="date_ok", value="January 21, 2026")
    empty = make_resolved_value(property_name="missing", value="")

    healed = DateHealingResolver.apply([name, short, already_ok, empty])

    assert healed[0].value == "John"
    assert healed[1].value == "January 21, 2026"
    assert healed[2].value == "January 21, 2026"
    assert healed[3].value == ""
