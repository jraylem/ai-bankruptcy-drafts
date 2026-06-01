"""Tests for ExtractFromDraftAgentV2.run — failure modes + happy path.
LLM is patched via `_invoke`."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.agents.extract_from_draft import ExtractFromDraftAgentV2
from src.core.studio_v2.agents.extract_from_draft.agent import _ExtractedValueV2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_returns_stripped_value():
    with patch.object(
        ExtractFromDraftAgentV2, "_invoke",
        new=AsyncMock(return_value=_ExtractedValueV2(value="  Jane Doe, Debtor.  ")),
    ):
        out = await ExtractFromDraftAgentV2.run(
            slot_name="debtor_caption",
            draft_text="In re: Jane Doe, Debtor.",
            extract_instruction="Pull the In re caption.",
        )
    assert out == "Jane Doe, Debtor."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_empty_draft_text_skips_llm():
    with patch.object(
        ExtractFromDraftAgentV2, "_invoke", new=AsyncMock(),
    ) as invoke_mock:
        out = await ExtractFromDraftAgentV2.run(
            slot_name="x", draft_text="", extract_instruction="anything",
        )
    invoke_mock.assert_not_called()
    assert out == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_empty_instruction_skips_llm():
    with patch.object(
        ExtractFromDraftAgentV2, "_invoke", new=AsyncMock(),
    ) as invoke_mock:
        out = await ExtractFromDraftAgentV2.run(
            slot_name="x", draft_text="text", extract_instruction="",
        )
    invoke_mock.assert_not_called()
    assert out == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_llm_exception_returns_empty():
    with patch.object(
        ExtractFromDraftAgentV2, "_invoke", side_effect=RuntimeError("boom"),
    ):
        out = await ExtractFromDraftAgentV2.run(
            slot_name="x", draft_text="t", extract_instruction="i",
        )
    assert out == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_llm_none_returns_empty():
    with patch.object(
        ExtractFromDraftAgentV2, "_invoke", new=AsyncMock(return_value=None),
    ):
        out = await ExtractFromDraftAgentV2.run(
            slot_name="x", draft_text="t", extract_instruction="i",
        )
    assert out == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_llm_empty_value_returns_empty():
    with patch.object(
        ExtractFromDraftAgentV2, "_invoke",
        new=AsyncMock(return_value=_ExtractedValueV2(value="")),
    ):
        out = await ExtractFromDraftAgentV2.run(
            slot_name="x", draft_text="t", extract_instruction="i",
        )
    assert out == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_forwards_slot_name_to_metadata():
    """slot_name is sent to LangSmith via _invoke's metadata kwarg."""
    captured_metadata: list[dict] = []

    async def fake_invoke(prompt, run_name, metadata=None):
        captured_metadata.append(metadata or {})
        return _ExtractedValueV2(value="ok")

    with patch.object(
        ExtractFromDraftAgentV2, "_invoke", side_effect=fake_invoke,
    ):
        await ExtractFromDraftAgentV2.run(
            slot_name="my_slot", draft_text="t", extract_instruction="i",
        )
    assert captured_metadata[0]["slot_name"] == "my_slot"
