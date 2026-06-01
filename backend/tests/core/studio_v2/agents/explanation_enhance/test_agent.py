"""Tests for ExplanationEnhanceAgentV2.run — multimodal content
assembly, soft-failure behavior. LLM call patched."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.common.documents.supporting_doc_reader import (
    AttachedImageDoc,
    AttachedPdfDoc,
    InlineTextDoc,
)
from src.core.studio_v2.agents.explanation_enhance import ExplanationEnhanceAgentV2
from src.core.studio_v2.agents.explanation_enhance.agent import _EnhancedExplanationV2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_returns_stripped_polished_text():
    with patch.object(
        ExplanationEnhanceAgentV2, "_invoke",
        new=AsyncMock(return_value=_EnhancedExplanationV2(text="  The Debtor was laid off on March 8, 2026.  ")),
    ):
        out = await ExplanationEnhanceAgentV2.run(
            variable_name="hardship_narrative",
            label="Hardship narrative",
            user_text="i got laid off in march",
            supporting_docs=[],
        )
    assert out == "The Debtor was laid off on March 8, 2026."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_empty_user_text_returns_unchanged_without_llm_call():
    with patch.object(
        ExplanationEnhanceAgentV2, "_invoke", new=AsyncMock(),
    ) as invoke_mock:
        out = await ExplanationEnhanceAgentV2.run(
            variable_name="x", label="x", user_text="", supporting_docs=[],
        )
    invoke_mock.assert_not_called()
    assert out == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_llm_exception_returns_raw_user_text():
    with patch.object(
        ExplanationEnhanceAgentV2, "_invoke", side_effect=RuntimeError("boom"),
    ):
        out = await ExplanationEnhanceAgentV2.run(
            variable_name="x", label="x", user_text="raw text",
            supporting_docs=[],
        )
    assert out == "raw text"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_llm_empty_returns_raw_user_text():
    with patch.object(
        ExplanationEnhanceAgentV2, "_invoke",
        new=AsyncMock(return_value=_EnhancedExplanationV2(text="")),
    ):
        out = await ExplanationEnhanceAgentV2.run(
            variable_name="x", label="x", user_text="fallback",
            supporting_docs=[],
        )
    assert out == "fallback"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_attaches_pdfs_and_images_as_content_blocks():
    """Inline text docs → prompt body; PDFs/images → message content blocks."""
    captured_messages: list = []

    async def fake_invoke(messages, run_name, metadata=None):
        captured_messages.append(messages)
        return _EnhancedExplanationV2(text="polished")

    docs = [
        InlineTextDoc(filename="letter.txt", text="termination notice"),
        AttachedPdfDoc(filename="bill.pdf", base64_data="ZmFrZS1wZGY="),
        AttachedImageDoc(
            filename="check.jpg", media_type="image/jpeg",
            base64_data="ZmFrZS1qcGc=",
        ),
    ]
    with patch.object(
        ExplanationEnhanceAgentV2, "_invoke", side_effect=fake_invoke,
    ):
        await ExplanationEnhanceAgentV2.run(
            variable_name="x", label="x", user_text="hi", supporting_docs=docs,
        )

    msg = captured_messages[0][0]  # one HumanMessage
    content = msg.content
    # First block: text preamble that includes the inline text doc.
    assert content[0]["type"] == "text"
    assert "letter.txt" in content[0]["text"]
    assert "termination notice" in content[0]["text"]
    # Subsequent blocks: PDF + image attachments.
    assert content[1]["type"] == "document"
    assert content[1]["source"]["media_type"] == "application/pdf"
    assert content[1]["source"]["data"] == "ZmFrZS1wZGY="
    assert content[2]["type"] == "image"
    assert content[2]["source"]["media_type"] == "image/jpeg"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_forwards_variable_name_to_metadata():
    captured_metadata: list[dict] = []

    async def fake_invoke(messages, run_name, metadata=None):
        captured_metadata.append(metadata or {})
        return _EnhancedExplanationV2(text="ok")

    with patch.object(
        ExplanationEnhanceAgentV2, "_invoke", side_effect=fake_invoke,
    ):
        await ExplanationEnhanceAgentV2.run(
            variable_name="my_var", label="x", user_text="y",
            supporting_docs=[],
        )
    assert captured_metadata[0]["variable"] == "my_var"
