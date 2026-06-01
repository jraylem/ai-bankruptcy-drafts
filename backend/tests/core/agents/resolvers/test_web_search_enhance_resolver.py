"""Tests for WebSearchEnhanceResolver — opt-in case_vector / Gmail web-search enhancement."""

from unittest.mock import AsyncMock

import pytest

from src.config import settings
from src.core.agents.llm.web_search_enhance import agent as web_search_agent_module
from src.core.agents.resolvers import web_search_enhance_resolver as resolver_module
from src.core.agents.resolvers.web_search_enhance_resolver import (
    WebSearchEnhanceResolver,
)
from src.core.agents.types.sources import (
    CaseVectorSourceParams,
    FieldSource,
    GmailSourceParams,
)
from tests.core.factories import (
    make_agent_config,
    make_resolved_value,
    make_template_field,
)


def _flagged_case_vector_field(
    property_name: str = "court_circuit_and_county",
    marker: str | None = "11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
    text_query: str | None = "Court or agency assigned to a lawsuit under SOFA Q9",
    enable_web_search: bool = True,
):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(
            text_query=text_query,
            enable_web_search=enable_web_search,
        ),
        template_property_marker=marker,
        template_variable_string=f"[[{property_name}]]",
    )


def _unflagged_case_vector_field(property_name: str = "debtor_name"):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.CASE_VECTOR,
        template_property_marker="Quiara Ayanna Vanterpool",
        template_variable_string=f"[[{property_name}]]",
    )


def _gmail_field(property_name: str = "petition_filing_date"):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.GMAIL,
    )


def _flagged_gmail_field(
    property_name: str = "trustee_address",
    marker: str | None = "100 SE 1st Street, Suite 400, Miami, FL 33131",
    subject_query: str | None = "Trustee assignment notice",
    body_query: str | None = "trustee address",
    enable_web_search: bool = True,
):
    return make_template_field(
        property_name=property_name,
        source=FieldSource.GMAIL,
        source_params=GmailSourceParams(
            subject_query=subject_query,
            body_query=body_query,
            enable_web_search=enable_web_search,
        ),
        template_property_marker=marker,
        template_variable_string=f"[[{property_name}]]",
    )


@pytest.mark.unit
async def test_no_op_when_kill_switch_off(monkeypatch):
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", False)
    agent_run = AsyncMock()
    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run", agent_run,
    )

    config = make_agent_config(fields=[_flagged_case_vector_field()])
    rv = make_resolved_value("court_circuit_and_county", "Broward County Circuit Court")
    out = await WebSearchEnhanceResolver.apply(
        agent_config=config,
        case_details=None,
        template_bytes=None,
        resolved_values=[rv],
    )

    assert out == [rv]
    agent_run.assert_not_awaited()


@pytest.mark.unit
async def test_no_op_when_no_flagged_fields(monkeypatch):
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)
    agent_run = AsyncMock()
    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run", agent_run,
    )

    config = make_agent_config(fields=[
        _unflagged_case_vector_field(),
        _gmail_field(),
    ])
    rv = make_resolved_value("debtor_name", "Quiara Ayanna Vanterpool")
    out = await WebSearchEnhanceResolver.apply(
        agent_config=config,
        case_details=None,
        template_bytes=None,
        resolved_values=[rv],
    )

    assert out == [rv]
    agent_run.assert_not_awaited()


@pytest.mark.unit
async def test_skips_unflagged_case_vector_when_only_flagged_should_run(monkeypatch):
    """Flagged field is enhanced; sibling unflagged case_vector and gmail
    fields pass through unchanged in the same merged list."""
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)
    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run",
        AsyncMock(return_value="17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"),
    )

    config = make_agent_config(fields=[
        _flagged_case_vector_field(),
        _unflagged_case_vector_field("debtor_name"),
        _gmail_field(),
    ])
    rvs = [
        make_resolved_value("court_circuit_and_county", "Broward County Circuit Court"),
        make_resolved_value("debtor_name", "Quiara Ayanna Vanterpool"),
        make_resolved_value("petition_filing_date", "April 3, 2026"),
    ]

    out = await WebSearchEnhanceResolver.apply(
        agent_config=config,
        case_details=None,
        template_bytes=None,
        resolved_values=rvs,
    )

    by_name = {rv.property_name: rv for rv in out}
    assert by_name["court_circuit_and_county"].value == "17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"
    assert "enhanced via web search" in by_name["court_circuit_and_county"].reasoning
    assert by_name["debtor_name"].value == "Quiara Ayanna Vanterpool"
    assert by_name["petition_filing_date"].value == "April 3, 2026"


@pytest.mark.unit
async def test_skips_flagged_field_with_empty_current_value_and_surfaces_warning(monkeypatch, caplog):
    """The v1 guardrail: flagged field whose current_value is empty must
    NOT trigger a search (no anchor) AND must surface a clear note in
    the resolved value's reasoning so authors can see they need to fix
    their text_query."""
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)
    agent_run = AsyncMock()
    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run", agent_run,
    )

    config = make_agent_config(fields=[_flagged_case_vector_field()])
    rv = make_resolved_value(
        "court_circuit_and_county", "", reasoning="case_vector returned no chunks",
    )
    with caplog.at_level("WARNING"):
        out = await WebSearchEnhanceResolver.apply(
            agent_config=config,
            case_details=None,
            template_bytes=None,
            resolved_values=[rv],
        )

    assert len(out) == 1
    assert out[0].value == ""
    assert "Web-search enhancement was requested" in out[0].reasoning
    assert "text_query" in out[0].reasoning
    assert any("current_value is empty" in rec.message for rec in caplog.records)
    agent_run.assert_not_awaited()


@pytest.mark.unit
async def test_skips_flagged_field_with_no_marker(monkeypatch, caplog):
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)
    agent_run = AsyncMock()
    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run", agent_run,
    )

    config = make_agent_config(fields=[
        _flagged_case_vector_field(marker=None),
    ])
    rv = make_resolved_value("court_circuit_and_county", "Broward County Circuit Court")
    with caplog.at_level("WARNING"):
        out = await WebSearchEnhanceResolver.apply(
            agent_config=config,
            case_details=None,
            template_bytes=None,
            resolved_values=[rv],
        )

    assert out == [rv]
    assert any("no template_property_marker" in rec.message for rec in caplog.records)
    agent_run.assert_not_awaited()


@pytest.mark.unit
async def test_passes_through_when_agent_returns_unchanged_value(monkeypatch):
    """If the agent returns the same value (or an empty one), the resolved
    value passes through unchanged — no spurious 'enhanced via web search'
    annotation."""
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)
    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run",
        AsyncMock(return_value="Broward County Circuit Court"),
    )

    config = make_agent_config(fields=[_flagged_case_vector_field()])
    rv = make_resolved_value("court_circuit_and_county", "Broward County Circuit Court")
    out = await WebSearchEnhanceResolver.apply(
        agent_config=config,
        case_details=None,
        template_bytes=None,
        resolved_values=[rv],
    )

    assert out == [rv]


@pytest.mark.unit
async def test_passes_through_when_agent_raises(monkeypatch, caplog):
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)
    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run",
        AsyncMock(side_effect=RuntimeError("network down")),
    )

    config = make_agent_config(fields=[_flagged_case_vector_field()])
    rv = make_resolved_value("court_circuit_and_county", "Broward County Circuit Court")
    with caplog.at_level("WARNING"):
        out = await WebSearchEnhanceResolver.apply(
            agent_config=config,
            case_details=None,
            template_bytes=None,
            resolved_values=[rv],
        )

    assert out == [rv]
    assert any("agent raised" in rec.message for rec in caplog.records)


@pytest.mark.unit
async def test_threads_paragraph_when_template_bytes_provided(monkeypatch):
    """When template_bytes is provided, the resolver pulls the surrounding
    paragraph for the placeholder and passes it to the agent as
    `template_paragraph`."""
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)

    # Stub find_paragraph_containing on the resolver's import surface to
    # return a known surrounding-paragraph string for the placeholder.
    monkeypatch.setattr(
        resolver_module.DocxTemplateService,
        "find_paragraph_containing",
        staticmethod(lambda b, p: f"IN THE CIRCUIT COURT OF THE {p}"),
    )

    captured: dict = {}

    async def fake_run(
        variable_name, current_value, template_property_marker,
        template_paragraph, case_details,
        web_search_instruction=None, output_instruction=None,
    ):
        captured["variable_name"] = variable_name
        captured["current_value"] = current_value
        captured["template_property_marker"] = template_property_marker
        captured["template_paragraph"] = template_paragraph
        captured["case_details"] = case_details
        return "17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"

    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run", fake_run,
    )

    config = make_agent_config(fields=[_flagged_case_vector_field()])
    rv = make_resolved_value("court_circuit_and_county", "Broward County Circuit Court")
    case_details = {"case_number": "26-10491", "chapter": 13}
    out = await WebSearchEnhanceResolver.apply(
        agent_config=config,
        case_details=case_details,
        template_bytes=b"<docx>",
        resolved_values=[rv],
    )

    assert captured["variable_name"] == "court_circuit_and_county"
    assert captured["current_value"] == "Broward County Circuit Court"
    assert captured["template_property_marker"].startswith("11 JUDICIAL CIRCUIT")
    assert "[[court_circuit_and_county]]" in captured["template_paragraph"]
    assert "IN THE CIRCUIT COURT OF THE" in captured["template_paragraph"]
    assert captured["case_details"] == case_details
    assert out[0].value == "17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"


@pytest.mark.unit
async def test_degrades_gracefully_when_paragraph_lookup_fails(monkeypatch):
    """If the docx paragraph can't be read, the agent still runs with
    template_paragraph=None — enhancement is best-effort, not fatal."""
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)

    def boom(_b, _p):
        raise RuntimeError("docx parse failed")

    monkeypatch.setattr(
        resolver_module.DocxTemplateService,
        "find_paragraph_containing",
        staticmethod(boom),
    )

    captured: dict = {}

    async def fake_run(
        variable_name, current_value, template_property_marker,
        template_paragraph, case_details,
        web_search_instruction=None, output_instruction=None,
    ):
        captured["template_paragraph"] = template_paragraph
        return "17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"

    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run", fake_run,
    )

    config = make_agent_config(fields=[_flagged_case_vector_field()])
    rv = make_resolved_value("court_circuit_and_county", "Broward County Circuit Court")
    out = await WebSearchEnhanceResolver.apply(
        agent_config=config,
        case_details=None,
        template_bytes=b"<broken-docx>",
        resolved_values=[rv],
    )

    assert captured["template_paragraph"] is None
    assert out[0].value == "17 JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"


# ─── web_search_instruction + output_instruction threading ────────────


def _flagged_case_vector_field_with_directives(
    *,
    web_search_instruction: str | None = None,
    output_instruction: str | None = None,
):
    """Variant of `_flagged_case_vector_field` with extra author directives."""
    field = make_template_field(
        property_name="court_circuit_and_county",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(
            text_query="Court or agency assigned to a lawsuit under SOFA Q9",
            enable_web_search=True,
            web_search_instruction=web_search_instruction,
        ),
        template_property_marker="11 JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
        template_variable_string="[[court_circuit_and_county]]",
    )
    field.output_instruction = output_instruction
    return field


@pytest.mark.unit
async def test_resolver_threads_web_search_instruction_from_source_params(monkeypatch):
    """`CaseVectorSourceParams.web_search_instruction` reaches the agent
    via the `web_search_instruction` kwarg."""
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)

    captured: dict = {}

    async def fake_run(
        variable_name, current_value, template_property_marker,
        template_paragraph, case_details,
        web_search_instruction=None, output_instruction=None,
    ):
        captured["web_search_instruction"] = web_search_instruction
        captured["output_instruction"] = output_instruction
        return "17TH JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"

    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run", fake_run,
    )

    field = _flagged_case_vector_field_with_directives(
        web_search_instruction="search for circuit by county; ignore federal",
    )
    config = make_agent_config(fields=[field])
    rv = make_resolved_value("court_circuit_and_county", "Broward County Circuit Court")
    await WebSearchEnhanceResolver.apply(
        agent_config=config,
        case_details=None,
        template_bytes=None,
        resolved_values=[rv],
    )

    assert captured["web_search_instruction"] == "search for circuit by county; ignore federal"
    assert captured["output_instruction"] is None


@pytest.mark.unit
async def test_resolver_threads_output_instruction_from_field(monkeypatch):
    """`TemplateField.output_instruction` reaches the agent via the
    `output_instruction` kwarg (independent of source_params)."""
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)

    captured: dict = {}

    async def fake_run(
        variable_name, current_value, template_property_marker,
        template_paragraph, case_details,
        web_search_instruction=None, output_instruction=None,
    ):
        captured["web_search_instruction"] = web_search_instruction
        captured["output_instruction"] = output_instruction
        return "11TH JUDICIAL CIRCUIT IN AND FOR MIAMI-DADE COUNTY, FLORIDA"

    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run", fake_run,
    )

    field = _flagged_case_vector_field_with_directives(
        output_instruction="use ordinal form (11TH, 9TH)",
    )
    config = make_agent_config(fields=[field])
    rv = make_resolved_value("court_circuit_and_county", "Miami-Dade County Circuit Court")
    await WebSearchEnhanceResolver.apply(
        agent_config=config,
        case_details=None,
        template_bytes=None,
        resolved_values=[rv],
    )

    assert captured["web_search_instruction"] is None
    assert captured["output_instruction"] == "use ordinal form (11TH, 9TH)"


@pytest.mark.unit
async def test_resolver_normalizes_whitespace_only_directives_to_none(monkeypatch):
    """Whitespace-only / empty author directives are normalized to None
    so the prompt builder skips the corresponding block."""
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)

    captured: dict = {}

    async def fake_run(
        variable_name, current_value, template_property_marker,
        template_paragraph, case_details,
        web_search_instruction=None, output_instruction=None,
    ):
        captured["web_search_instruction"] = web_search_instruction
        captured["output_instruction"] = output_instruction
        return "17TH JUDICIAL CIRCUIT IN AND FOR BROWARD COUNTY, FLORIDA"

    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run", fake_run,
    )

    field = _flagged_case_vector_field_with_directives(
        web_search_instruction="   \n  ",
        output_instruction="\t  ",
    )
    config = make_agent_config(fields=[field])
    rv = make_resolved_value("court_circuit_and_county", "Broward County Circuit Court")
    await WebSearchEnhanceResolver.apply(
        agent_config=config,
        case_details=None,
        template_bytes=None,
        resolved_values=[rv],
    )

    assert captured["web_search_instruction"] is None
    assert captured["output_instruction"] is None


# ─── Gmail-sourced fields ─────────────────────────────────────────────


@pytest.mark.unit
async def test_enhances_flagged_gmail_field_with_non_empty_anchor(monkeypatch):
    """A Gmail field with enable_web_search=True and a non-empty current_value
    flows through the same enhancement path as case_vector — the resolver is
    source-agnostic from the anchor value onward."""
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)
    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run",
        AsyncMock(return_value="100 SE 1st Street, Suite 400, Miami, FL 33131"),
    )

    config = make_agent_config(fields=[_flagged_gmail_field()])
    rv = make_resolved_value("trustee_address", "100 SE 1st St, Miami, FL")
    out = await WebSearchEnhanceResolver.apply(
        agent_config=config,
        case_details=None,
        template_bytes=None,
        resolved_values=[rv],
    )

    by_name = {rv.property_name: rv for rv in out}
    assert by_name["trustee_address"].value == "100 SE 1st Street, Suite 400, Miami, FL 33131"
    assert "enhanced via web search" in by_name["trustee_address"].reasoning


@pytest.mark.unit
async def test_skips_flagged_gmail_field_with_empty_current_value_and_surfaces_warning(monkeypatch, caplog):
    """Mirror of the case_vector empty-anchor guardrail. A flagged Gmail
    field whose current_value is empty must NOT trigger a search AND must
    surface the empty-anchor note in the resolved value's reasoning."""
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)
    agent_run = AsyncMock()
    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run", agent_run,
    )

    config = make_agent_config(fields=[_flagged_gmail_field()])
    rv = make_resolved_value(
        "trustee_address", "", reasoning="gmail returned no matching emails",
    )
    with caplog.at_level("WARNING"):
        out = await WebSearchEnhanceResolver.apply(
            agent_config=config,
            case_details=None,
            template_bytes=None,
            resolved_values=[rv],
        )

    assert len(out) == 1
    assert out[0].value == ""
    assert "Web-search enhancement was requested" in out[0].reasoning
    assert any("current_value is empty" in rec.message for rec in caplog.records)
    agent_run.assert_not_awaited()


@pytest.mark.unit
async def test_resolver_threads_web_search_instruction_from_gmail_source_params(monkeypatch):
    """`GmailSourceParams.web_search_instruction` reaches the agent via the
    `web_search_instruction` kwarg — symmetric with the case_vector test
    above."""
    monkeypatch.setattr(settings, "WEB_SEARCH_ENHANCE_ENABLED", True)

    captured: dict = {}

    async def fake_run(
        variable_name, current_value, template_property_marker,
        template_paragraph, case_details,
        web_search_instruction=None, output_instruction=None,
    ):
        captured["web_search_instruction"] = web_search_instruction
        return "100 SE 1st Street, Suite 400, Miami, FL 33131"

    monkeypatch.setattr(
        web_search_agent_module.WebSearchEnhanceAgent, "run", fake_run,
    )

    field = make_template_field(
        property_name="trustee_address",
        source=FieldSource.GMAIL,
        source_params=GmailSourceParams(
            subject_query="Trustee assignment notice",
            body_query="trustee address",
            enable_web_search=True,
            web_search_instruction="prefer USPS-canonicalized street address",
        ),
        template_property_marker="100 SE 1st Street, Suite 400, Miami, FL 33131",
        template_variable_string="[[trustee_address]]",
    )
    config = make_agent_config(fields=[field])
    rv = make_resolved_value("trustee_address", "100 SE 1st St, Miami, FL")
    await WebSearchEnhanceResolver.apply(
        agent_config=config,
        case_details=None,
        template_bytes=None,
        resolved_values=[rv],
    )

    assert captured["web_search_instruction"] == "prefer USPS-canonicalized street address"
