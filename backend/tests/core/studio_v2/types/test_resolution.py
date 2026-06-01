"""Tests for ResolvedTemplateValueV2 — shape, defaults, raw_context cap."""

import pytest
from pydantic import ValidationError

from src.core.studio_v2.types.resolution import ResolvedTemplateValueV2


@pytest.mark.unit
def test_defaults():
    rv = ResolvedTemplateValueV2(template_variable="x")
    assert rv.value == ""
    assert rv.raw_context == ""
    assert rv.confidence == "high"
    assert rv.note == ""


@pytest.mark.unit
def test_round_trip_with_raw_context():
    rv = ResolvedTemplateValueV2(
        template_variable="vin",
        value="1HGCM82633A123456",
        raw_context="2018 Toyota Camry VIN: 1HGCM82633A123456 mileage 82300",
        confidence="medium",
        note="extracted from vehicle paragraph",
    )
    payload = rv.model_dump()
    assert payload["template_variable"] == "vin"
    assert payload["raw_context"].startswith("2018 Toyota")
    rebuilt = ResolvedTemplateValueV2.model_validate(payload)
    assert rebuilt == rv


@pytest.mark.unit
def test_raw_context_capped_at_2k():
    """Per the plan, raw_context bounds per-row token cost."""
    too_long = "a" * 2001
    with pytest.raises(ValidationError) as exc:
        ResolvedTemplateValueV2(template_variable="x", raw_context=too_long)
    assert "at most 2000" in str(exc.value) or "max_length" in str(exc.value)


@pytest.mark.unit
def test_extra_forbidden():
    with pytest.raises(ValidationError):
        ResolvedTemplateValueV2(template_variable="x", bogus="nope")
