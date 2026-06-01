"""Tests for CaseVectorVisionResolver — second-pass case_vector re-extraction."""

from unittest.mock import AsyncMock

import pytest

from src.config import settings
from src.core.agents.llm.case_vector_vision import agent as vision_agent_module
from src.core.agents.resolvers import case_vector_vision_resolver as resolver_module
from src.core.agents.resolvers.case_vector_vision_resolver import (
    CaseVectorVisionResolver,
)
from src.core.agents.types.resolution import ResolvedTemplateValue
from src.core.agents.types.sources import FieldSource
from tests.core.factories import (
    make_agent_config,
    make_resolved_value,
    make_template_field,
)


def _case_vector_field(property_name="prior_case_number"):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.CASE_VECTOR,
        template_property_marker="25-19062",
    )


def _gmail_field(property_name="petition_filing_date"):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.GMAIL,
    )


@pytest.mark.unit
def test_threshold_default_is_medium():
    # The vision fallback's default scope MUST include medium-confidence
    # case_vector resolutions — production hit a confidently-wrong
    # debtor_address when the default was "low" (May 2026). A future env
    # tweak that demotes this back to "low" will fail this test.
    assert settings.CASE_VECTOR_VISION_FALLBACK_THRESHOLD == "medium"


@pytest.mark.unit
async def test_no_op_when_kill_switch_off(monkeypatch):
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_ENABLED", False)
    fetch_pdf = AsyncMock()
    monkeypatch.setattr(resolver_module, "fetch_petition_pdf_bytes", fetch_pdf)

    config = make_agent_config(fields=[_case_vector_field()])
    rv = make_resolved_value("prior_case_number", "", confidence="low")
    out = await CaseVectorVisionResolver.apply(
        agent_config=config,
        case_details=None,
        petition_pdf_url="https://example.com/petition.pdf",
        resolved_values=[rv],
    )

    assert out == [rv]
    fetch_pdf.assert_not_awaited()


@pytest.mark.unit
async def test_no_op_when_no_petition_pdf_url(monkeypatch):
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_ENABLED", True)
    config = make_agent_config(fields=[_case_vector_field()])
    rv = make_resolved_value("prior_case_number", "", confidence="low")
    out = await CaseVectorVisionResolver.apply(
        agent_config=config,
        case_details=None,
        petition_pdf_url=None,
        resolved_values=[rv],
    )
    assert out == [rv]


@pytest.mark.unit
async def test_no_op_when_all_high_confidence(monkeypatch):
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_ENABLED", True)
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_THRESHOLD", "low")
    fetch_pdf = AsyncMock()
    monkeypatch.setattr(resolver_module, "fetch_petition_pdf_bytes", fetch_pdf)

    config = make_agent_config(fields=[_case_vector_field()])
    rv = make_resolved_value("prior_case_number", "25-19062", confidence="high")
    out = await CaseVectorVisionResolver.apply(
        agent_config=config,
        case_details=None,
        petition_pdf_url="https://example.com/petition.pdf",
        resolved_values=[rv],
    )

    assert out == [rv]
    fetch_pdf.assert_not_awaited()


@pytest.mark.unit
async def test_low_threshold_skips_medium_confidence(monkeypatch):
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_ENABLED", True)
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_THRESHOLD", "low")
    fetch_pdf = AsyncMock()
    monkeypatch.setattr(resolver_module, "fetch_petition_pdf_bytes", fetch_pdf)

    config = make_agent_config(fields=[_case_vector_field()])
    rv = make_resolved_value("prior_case_number", "25-19062", confidence="medium")
    out = await CaseVectorVisionResolver.apply(
        agent_config=config,
        case_details=None,
        petition_pdf_url="https://example.com/petition.pdf",
        resolved_values=[rv],
    )

    assert out == [rv]
    fetch_pdf.assert_not_awaited()


@pytest.mark.unit
async def test_medium_threshold_includes_medium_confidence(monkeypatch):
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_ENABLED", True)
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_THRESHOLD", "medium")
    monkeypatch.setattr(
        resolver_module,
        "fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"%PDF-1.7"),
    )
    monkeypatch.setattr(
        vision_agent_module.CaseVectorVisionAgent,
        "run",
        AsyncMock(return_value=[
            ResolvedTemplateValue.high_confidence(
                "prior_case_number", "25-19062", "Page 3 — checkbox + form data."
            ),
        ]),
    )

    config = make_agent_config(fields=[_case_vector_field()])
    rv = make_resolved_value("prior_case_number", "wrong", confidence="medium")
    out = await CaseVectorVisionResolver.apply(
        agent_config=config,
        case_details=None,
        petition_pdf_url="https://example.com/petition.pdf",
        resolved_values=[rv],
    )

    assert len(out) == 1
    assert out[0].value == "25-19062"
    assert out[0].confidence == "high"
    assert "corrected via vision" in out[0].reasoning


@pytest.mark.unit
async def test_replaces_only_low_confidence_entries(monkeypatch):
    """High-confidence entries (case_vector OR otherwise) survive untouched."""
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_ENABLED", True)
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_THRESHOLD", "low")
    monkeypatch.setattr(
        resolver_module,
        "fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"%PDF-1.7"),
    )
    monkeypatch.setattr(
        vision_agent_module.CaseVectorVisionAgent,
        "run",
        AsyncMock(return_value=[
            ResolvedTemplateValue.high_confidence(
                "prior_case_number", "25-19062", "Vision says so."
            ),
        ]),
    )

    config = make_agent_config(fields=[
        _case_vector_field("prior_case_number"),
        _case_vector_field("debtor_name"),  # already high confidence
        _gmail_field(),
    ])
    rvs = [
        make_resolved_value("prior_case_number", "", confidence="low"),
        make_resolved_value("debtor_name", "Judith Schwartz", confidence="high"),
        make_resolved_value("petition_filing_date", "January 21, 2026", confidence="high"),
    ]
    out = await CaseVectorVisionResolver.apply(
        agent_config=config,
        case_details=None,
        petition_pdf_url="https://example.com/petition.pdf",
        resolved_values=rvs,
    )

    by_name = {rv.property_name: rv for rv in out}
    assert by_name["prior_case_number"].value == "25-19062"
    assert by_name["debtor_name"].value == "Judith Schwartz"
    assert by_name["debtor_name"].confidence == "high"
    assert by_name["petition_filing_date"].value == "January 21, 2026"


@pytest.mark.unit
async def test_falls_through_when_pdf_fetch_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_ENABLED", True)
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_THRESHOLD", "low")
    monkeypatch.setattr(
        resolver_module,
        "fetch_petition_pdf_bytes",
        AsyncMock(return_value=None),
    )
    agent_run = AsyncMock()
    monkeypatch.setattr(vision_agent_module.CaseVectorVisionAgent, "run", agent_run)

    config = make_agent_config(fields=[_case_vector_field()])
    rv = make_resolved_value("prior_case_number", "", confidence="low")
    out = await CaseVectorVisionResolver.apply(
        agent_config=config,
        case_details=None,
        petition_pdf_url="https://example.com/petition.pdf",
        resolved_values=[rv],
    )

    assert out == [rv]
    agent_run.assert_not_awaited()


@pytest.mark.unit
async def test_falls_through_when_agent_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_ENABLED", True)
    monkeypatch.setattr(settings, "CASE_VECTOR_VISION_FALLBACK_THRESHOLD", "low")
    monkeypatch.setattr(
        resolver_module,
        "fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"%PDF-1.7"),
    )
    monkeypatch.setattr(
        vision_agent_module.CaseVectorVisionAgent,
        "run",
        AsyncMock(return_value=[]),
    )

    config = make_agent_config(fields=[_case_vector_field()])
    rv = make_resolved_value("prior_case_number", "", confidence="low")
    out = await CaseVectorVisionResolver.apply(
        agent_config=config,
        case_details=None,
        petition_pdf_url="https://example.com/petition.pdf",
        resolved_values=[rv],
    )

    assert out == [rv]
