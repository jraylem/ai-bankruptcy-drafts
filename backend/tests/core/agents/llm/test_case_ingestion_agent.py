"""Tests for CaseIngestionAgent — PDF bytes → CaseMetadata.

Differs from DraftAgent in two ways:
  1. Input is a list[HumanMessage] carrying a base64'd document content block,
     not a string prompt.
  2. Error policy RAISES HTTPException instead of returning empty output.
"""

import pytest
from fastapi import HTTPException

from src.core.agents.llm.case_ingestion import CaseIngestionAgent, CaseMetadata


@pytest.mark.unit
async def test_run_returns_metadata_from_invoke(mock_agent_invoke):
    expected = CaseMetadata(
        case_number="26-10700",
        debtors=["John Smith"],
        chapter=13,
        court_district="S.D. Fla.",
    )
    captured = mock_agent_invoke(expected)

    result = await CaseIngestionAgent.run(pdf_bytes=b"%PDF-1.4...", filename="petition.pdf")

    assert result == expected
    assert captured["run_name"] == "CaseIngestionAgent"
    assert captured["metadata"] == {"filename": "petition.pdf"}


@pytest.mark.unit
async def test_run_passes_list_of_messages_not_string_prompt(mock_agent_invoke):
    captured = mock_agent_invoke(
        CaseMetadata(case_number="26-10700", debtors=["John Smith"])
    )

    await CaseIngestionAgent.run(pdf_bytes=b"%PDF-1.4...", filename="petition.pdf")

    prompt = captured["prompt"]
    # Prompt for this agent is a list[HumanMessage], not a string.
    assert isinstance(prompt, list)
    assert len(prompt) == 1
    # The HumanMessage content is a list of content blocks (document + text).
    content = prompt[0].content
    assert any(b.get("type") == "document" for b in content)
    assert any(b.get("type") == "text" for b in content)


@pytest.mark.unit
async def test_run_rejects_empty_pdf_before_invoking_llm(mock_agent_invoke):
    captured = mock_agent_invoke(CaseMetadata(case_number="x", debtors=["y"]))

    with pytest.raises(HTTPException) as exc:
        await CaseIngestionAgent.run(pdf_bytes=b"", filename="petition.pdf")

    assert exc.value.status_code == 400
    assert "Empty PDF" in exc.value.detail
    # Critical: the LLM must NOT be called for an empty PDF
    assert captured == {}


@pytest.mark.unit
async def test_run_raises_502_when_invoke_throws(mock_agent_invoke):
    mock_agent_invoke(RuntimeError("anthropic rate-limited"))

    with pytest.raises(HTTPException) as exc:
        await CaseIngestionAgent.run(pdf_bytes=b"%PDF-1.4...", filename="petition.pdf")

    assert exc.value.status_code == 502
    assert "Case metadata extraction failed" in exc.value.detail


@pytest.mark.unit
async def test_run_raises_422_when_invoke_returns_none(mock_agent_invoke):
    mock_agent_invoke(None)

    with pytest.raises(HTTPException) as exc:
        await CaseIngestionAgent.run(pdf_bytes=b"%PDF-1.4...", filename="petition.pdf")

    assert exc.value.status_code == 422
    assert "Could not extract case metadata" in exc.value.detail
