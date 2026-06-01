"""Tests for CaseVectorVisionAgent — multimodal PDF re-extraction."""

from unittest.mock import AsyncMock

import pytest

from src.core.agents.llm import base as agent_base
from src.core.agents.llm.case_vector_vision import CaseVectorVisionAgent
from src.core.agents.llm.case_vector_vision.agent import _VisionExtraction
from src.core.agents.types.resolution import ResolvedTemplateValue
from src.core.agents.types.sources import CaseVectorSourceParams, FieldSource
from tests.core.factories import make_template_field


def _make_field(
    property_name="prior_case_number",
    marker="25-19062",
    text_query: str | None = None,
):
    source_params = (
        CaseVectorSourceParams(text_query=text_query) if text_query is not None else None
    )
    return make_template_field(
        property_name=property_name,
        source=FieldSource.CASE_VECTOR,
        source_params=source_params,
        instruction="filed for bankruptcy within last 8 years",
        template_property_marker=marker,
    )


@pytest.mark.unit
async def test_run_attaches_pdf_document_block_and_text_prompt(monkeypatch):
    captured: dict = {}

    async def fake_invoke_multimodal(cls, content_blocks, run_name, metadata=None):
        captured["content_blocks"] = content_blocks
        captured["run_name"] = run_name
        captured["metadata"] = metadata or {}
        return _VisionExtraction(resolved_values=[
            ResolvedTemplateValue.high_confidence(
                "prior_case_number",
                "25-19062",
                "Page 3 — boxes show prior case 25-19062",
            )
        ])

    monkeypatch.setattr(
        agent_base.Agent,
        "_invoke_multimodal",
        classmethod(fake_invoke_multimodal),
    )

    fields = [_make_field()]
    result = await CaseVectorVisionAgent.run(
        petition_pdf_b64="JVBERi0xLjcgZmFrZQ==",
        fields=fields,
        case_details={"case_number": "26-10700", "chapter": 13},
    )

    assert len(result) == 1
    assert result[0].property_name == "prior_case_number"
    assert result[0].confidence == "high"

    blocks = captured["content_blocks"]
    assert len(blocks) == 2
    document = blocks[0]
    assert document["type"] == "document"
    assert document["source"]["type"] == "base64"
    assert document["source"]["media_type"] == "application/pdf"
    assert document["source"]["data"] == "JVBERi0xLjcgZmFrZQ=="
    text_block = blocks[1]
    assert text_block["type"] == "text"
    assert "prior_case_number" in text_block["text"]
    assert "26-10700" in text_block["text"]  # case_details rendered
    assert "filed for bankruptcy within last 8 years" in text_block["text"]

    assert captured["run_name"] == "CaseVectorVisionAgent"
    assert captured["metadata"] == {"field_count": "1"}


@pytest.mark.unit
async def test_run_returns_empty_list_when_no_fields():
    result = await CaseVectorVisionAgent.run(
        petition_pdf_b64="x",
        fields=[],
        case_details=None,
    )
    assert result == []


@pytest.mark.unit
async def test_run_returns_empty_on_invoke_failure(monkeypatch):
    async def fake_invoke_multimodal(cls, content_blocks, run_name, metadata=None):
        raise RuntimeError("api down")

    monkeypatch.setattr(
        agent_base.Agent,
        "_invoke_multimodal",
        classmethod(fake_invoke_multimodal),
    )

    result = await CaseVectorVisionAgent.run(
        petition_pdf_b64="x",
        fields=[_make_field()],
        case_details=None,
    )
    assert result == []


@pytest.mark.unit
async def test_run_handles_none_invoke_result(monkeypatch):
    monkeypatch.setattr(
        agent_base.Agent,
        "_invoke_multimodal",
        classmethod(AsyncMock(return_value=None)),
    )
    result = await CaseVectorVisionAgent.run(
        petition_pdf_b64="x",
        fields=[_make_field()],
        case_details=None,
    )
    assert result == []


@pytest.mark.unit
async def test_run_threads_text_query_into_prompt_as_authoritative(monkeypatch):
    """Real bug from case 26-10700: a `plaintiff_name` field whose
    text_query said 'Case filed against the debtor under SOFA Q9'
    returned the bankruptcy debtor instead of the actual plaintiff
    (the opposing party in the state-court suit). Vision agent took
    `plaintiff_name` literally and ignored the topical query the user
    typed. Prompt must surface text_query AS authoritative so the
    LLM follows the user's prose, not the variable name."""
    captured: dict = {}

    async def fake_invoke_multimodal(cls, content_blocks, run_name, metadata=None):
        captured["text"] = content_blocks[1]["text"]
        return _VisionExtraction(resolved_values=[])

    monkeypatch.setattr(
        agent_base.Agent,
        "_invoke_multimodal",
        classmethod(fake_invoke_multimodal),
    )

    field = _make_field(
        property_name="plaintiff_name",
        text_query="Case filed against the debtor under SOFA question number 9",
    )
    await CaseVectorVisionAgent.run(
        petition_pdf_b64="x",
        fields=[field],
        case_details=None,
    )

    text = captured["text"]
    # Topical query is rendered into the field block.
    assert "topical query (authoritative)" in text
    assert "Case filed against the debtor under SOFA question number 9" in text
    # Prompt explicitly tells the LLM the topical query overrides the
    # property_name's literal interpretation.
    assert "TOPICAL QUERY IS AUTHORITATIVE" in text
    # Anti-fallback: don't substitute debtor when value is genuinely missing.
    assert "Don't substitute the debtor" in text


@pytest.mark.unit
async def test_run_omits_topical_query_line_when_no_text_query(monkeypatch):
    """When source_params has no text_query (or no source_params at all),
    the prompt skips the `topical query` line so the LLM doesn't see a
    misleading empty hint. The instruction + sample marker still render."""
    captured: dict = {}

    async def fake_invoke_multimodal(cls, content_blocks, run_name, metadata=None):
        captured["text"] = content_blocks[1]["text"]
        return _VisionExtraction(resolved_values=[])

    monkeypatch.setattr(
        agent_base.Agent,
        "_invoke_multimodal",
        classmethod(fake_invoke_multimodal),
    )

    # No text_query, no source_params at all.
    field = _make_field(property_name="prior_case_number")
    await CaseVectorVisionAgent.run(
        petition_pdf_b64="x",
        fields=[field],
        case_details=None,
    )

    text = captured["text"]
    # "TOPICAL QUERY IS AUTHORITATIVE" still appears in the prompt's
    # instructions block (a fixed rule), but the per-field "topical query
    # (authoritative): ..." line should be absent for fields without a
    # text_query.
    assert "topical query (authoritative):" not in text
    # Other field-block lines still render.
    assert "prior_case_number" in text
    assert "filed for bankruptcy within last 8 years" in text
