"""Tests for ResolvedTemplateValue classmethods."""

import pytest

from src.core.agents.types.resolution import ResolvedTemplateValue, ResolverStage


@pytest.mark.unit
def test_low_confidence_builds_empty_value_with_given_reason():
    rv = ResolvedTemplateValue.low_confidence("debtor_name", "parent was missing")
    assert rv.property_name == "debtor_name"
    assert rv.value == ""
    assert rv.reasoning == "parent was missing"
    assert rv.confidence == "low"


@pytest.mark.unit
def test_high_confidence_builds_populated_value():
    rv = ResolvedTemplateValue.high_confidence(
        "case_number", "26-10700", "extracted from email subject"
    )
    assert rv.property_name == "case_number"
    assert rv.value == "26-10700"
    assert rv.reasoning == "extracted from email subject"
    assert rv.confidence == "high"


@pytest.mark.unit
def test_resolver_stage_enum_values():
    # Stable order matters because _STAGE_BY_SOURCE + pipeline filters rely on it.
    assert {s.value for s in ResolverStage} == {
        "llm_draft",
        "system_generated",
        "derivative",
        "user_input",
        "auto_derived",
        "inherit_from_parent",
    }
