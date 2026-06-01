"""Tests for ExplanationEnhanceAgent.

Verifies:
  - Prompt composition inlines DOCX/TXT/MD docs into text, attaches PDF + image
    docs as document / image content blocks on a single HumanMessage.
  - Returns the cleaned `text` on success.
  - Returns the user's raw text unchanged on None result or exception.
"""

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from src.core.agents.llm.explanation_enhance import (
    ExplanationEnhanceAgent,
    _EnhancedExplanation,
)
from src.core.common.documents.supporting_doc_reader import (
    AttachedImageDoc,
    AttachedPdfDoc,
    InlineTextDoc,
)


@pytest.mark.unit
async def test_run_inlines_text_docs_and_attaches_binary_docs(monkeypatch):
    captured: list[HumanMessage] = []

    async def fake_invoke(prompt, run_name, metadata=None):
        captured.append(prompt)
        return _EnhancedExplanation(text="  polished paragraph.  ")

    monkeypatch.setattr(ExplanationEnhanceAgent, "_invoke", classmethod(lambda cls, *a, **kw: fake_invoke(*a, **kw)))

    result = await ExplanationEnhanceAgent.run(
        variable_name="letter_of_explanation",
        label="Letter of Explanation",
        user_text="I lost my job in March.",
        supporting_docs=[
            InlineTextDoc(filename="note.txt", text="Employer note: laid off 2026-03-08."),
            AttachedPdfDoc(filename="termination.pdf", base64_data="UERGLUJZVEVT"),
            AttachedImageDoc(
                filename="paystub.png",
                media_type="image/png",
                base64_data="UE5HLUJZVEVT",
            ),
        ],
    )

    assert result == "polished paragraph."

    assert len(captured) == 1
    message_list = captured[0]
    assert isinstance(message_list, list) and len(message_list) == 1
    message = message_list[0]
    assert isinstance(message, HumanMessage)

    content = message.content
    # Order: text preamble, then pdfs, then images.
    assert content[0]["type"] == "text"
    assert "Letter of Explanation" in content[0]["text"]
    assert "I lost my job in March." in content[0]["text"]
    assert "Employer note: laid off 2026-03-08." in content[0]["text"]
    assert "note.txt" in content[0]["text"]

    pdf_block = next(b for b in content if b.get("type") == "document")
    assert pdf_block["source"]["media_type"] == "application/pdf"
    assert pdf_block["source"]["data"] == "UERGLUJZVEVT"

    image_block = next(b for b in content if b.get("type") == "image")
    assert image_block["source"]["media_type"] == "image/png"
    assert image_block["source"]["data"] == "UE5HLUJZVEVT"


@pytest.mark.unit
async def test_run_returns_user_text_when_invoke_raises(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("anthropic down")

    monkeypatch.setattr(
        ExplanationEnhanceAgent,
        "_invoke",
        classmethod(lambda cls, *a, **kw: boom(*a, **kw)),
    )

    result = await ExplanationEnhanceAgent.run(
        variable_name="x",
        label="L",
        user_text="fallback raw text",
        supporting_docs=[],
    )

    assert result == "fallback raw text"


@pytest.mark.unit
async def test_run_returns_user_text_when_result_is_none(monkeypatch):
    async def none_invoke(*args, **kwargs):
        return None

    monkeypatch.setattr(
        ExplanationEnhanceAgent,
        "_invoke",
        classmethod(lambda cls, *a, **kw: none_invoke(*a, **kw)),
    )

    result = await ExplanationEnhanceAgent.run(
        variable_name="x",
        label="L",
        user_text="fallback raw text",
        supporting_docs=[],
    )

    assert result == "fallback raw text"


@pytest.mark.unit
async def test_run_returns_user_text_when_result_text_is_empty(monkeypatch):
    async def empty_invoke(*args, **kwargs):
        return _EnhancedExplanation(text="   ")

    monkeypatch.setattr(
        ExplanationEnhanceAgent,
        "_invoke",
        classmethod(lambda cls, *a, **kw: empty_invoke(*a, **kw)),
    )

    result = await ExplanationEnhanceAgent.run(
        variable_name="x",
        label="L",
        user_text="fallback raw text",
        supporting_docs=[],
    )

    assert result == "fallback raw text"


@pytest.mark.unit
async def test_run_with_no_supporting_docs_still_sends_prompt(monkeypatch):
    captured: list[HumanMessage] = []

    async def fake_invoke(prompt, run_name, metadata=None):
        captured.append(prompt)
        return _EnhancedExplanation(text="polished.")

    monkeypatch.setattr(
        ExplanationEnhanceAgent,
        "_invoke",
        classmethod(lambda cls, *a, **kw: fake_invoke(*a, **kw)),
    )

    result = await ExplanationEnhanceAgent.run(
        variable_name="x",
        label="Letter of Explanation",
        user_text="Just words.",
        supporting_docs=[],
    )

    assert result == "polished."
    content = captured[0][0].content
    # Only the text preamble, no document/image blocks.
    assert len(content) == 1
    assert content[0]["type"] == "text"
    # Prompt mentions the <supporting_text_docs> tag as documentation, but no
    # actual <doc filename="..."> entries should be rendered since no inline docs.
    assert "<doc filename=" not in content[0]["text"]
