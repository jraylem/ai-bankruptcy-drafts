"""Tests for WebEnhanceAgentV2.run — soft-fail contract + happy path.

Mocks `ChatAnthropic` so no real Anthropic round-trip fires. Verifies:
1. Empty current_value / instruction short-circuit (no LLM call).
2. LLM exception → returns current_value unchanged.
3. Response without an <answer> tag → returns current_value unchanged.
4. Happy path → returns the last <answer> tag's content, stripped.
5. List-of-blocks content shape (server-side tool use) is parsed.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.agents.web_enhance import WebEnhanceAgentV2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_current_value_short_circuits():
    """No LLM call when there's nothing to enhance."""
    with patch(
        "src.core.studio_v2.agents.web_enhance.agent.ChatAnthropic",
    ) as chat_mock:
        result = await WebEnhanceAgentV2.run(
            variable_name="x",
            current_value="",
            web_enhance_instruction="confirm circuit number",
        )
    assert result == ""
    chat_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_instruction_short_circuits():
    """No LLM call when the author didn't opt in."""
    with patch(
        "src.core.studio_v2.agents.web_enhance.agent.ChatAnthropic",
    ) as chat_mock:
        result = await WebEnhanceAgentV2.run(
            variable_name="x",
            current_value="anchor",
            web_enhance_instruction="   ",
        )
    assert result == "anchor"
    chat_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_exception_returns_unenhanced():
    """Any LLM error → original value passes through."""
    fake_chain = SimpleNamespace(
        ainvoke=AsyncMock(side_effect=RuntimeError("anthropic down")),
    )
    fake_llm = SimpleNamespace(
        bind_tools=lambda _tools: SimpleNamespace(
            with_config=lambda _cfg: fake_chain,
        ),
    )
    with patch(
        "src.core.studio_v2.agents.web_enhance.agent.ChatAnthropic",
        return_value=fake_llm,
    ):
        result = await WebEnhanceAgentV2.run(
            variable_name="x",
            current_value="17",
            web_enhance_instruction="ordinal please",
        )
    assert result == "17"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_response_without_answer_tag_returns_unenhanced():
    """Missing <answer> tag → fall back to current_value."""
    fake_response = SimpleNamespace(content="I searched but found nothing useful.")
    fake_chain = SimpleNamespace(
        ainvoke=AsyncMock(return_value=fake_response),
    )
    fake_llm = SimpleNamespace(
        bind_tools=lambda _tools: SimpleNamespace(
            with_config=lambda _cfg: fake_chain,
        ),
    )
    with patch(
        "src.core.studio_v2.agents.web_enhance.agent.ChatAnthropic",
        return_value=fake_llm,
    ):
        result = await WebEnhanceAgentV2.run(
            variable_name="circuit",
            current_value="17",
            web_enhance_instruction="ordinal please",
        )
    assert result == "17"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_happy_path_returns_answer_tag_content():
    """Standard success — last <answer> wins, content stripped."""
    fake_response = SimpleNamespace(
        content=(
            "I searched for the Broward county circuit. "
            "<answer>17TH JUDICIAL CIRCUIT, IN AND FOR BROWARD COUNTY, FLORIDA</answer>"
        ),
    )
    fake_chain = SimpleNamespace(
        ainvoke=AsyncMock(return_value=fake_response),
    )
    fake_llm = SimpleNamespace(
        bind_tools=lambda _tools: SimpleNamespace(
            with_config=lambda _cfg: fake_chain,
        ),
    )
    with patch(
        "src.core.studio_v2.agents.web_enhance.agent.ChatAnthropic",
        return_value=fake_llm,
    ):
        result = await WebEnhanceAgentV2.run(
            variable_name="court_district",
            current_value="Broward County",
            web_enhance_instruction="reshape to circuit ordinal format",
            template_property_marker="11TH JUDICIAL CIRCUIT, IN AND FOR MIAMI-DADE COUNTY, FLORIDA",
        )
    assert result == "17TH JUDICIAL CIRCUIT, IN AND FOR BROWARD COUNTY, FLORIDA"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_of_blocks_content_is_parsed():
    """Server-side web-search responses come back as a list of
    content-block dicts; the parser concatenates every text block."""
    fake_response = SimpleNamespace(
        content=[
            {"type": "server_tool_use", "name": "web_search"},
            {"type": "web_search_tool_result", "content": []},
            {"type": "text", "text": "Based on the search, "},
            {"type": "text", "text": "<answer>FINAL VALUE</answer>"},
        ],
    )
    fake_chain = SimpleNamespace(
        ainvoke=AsyncMock(return_value=fake_response),
    )
    fake_llm = SimpleNamespace(
        bind_tools=lambda _tools: SimpleNamespace(
            with_config=lambda _cfg: fake_chain,
        ),
    )
    with patch(
        "src.core.studio_v2.agents.web_enhance.agent.ChatAnthropic",
        return_value=fake_llm,
    ):
        result = await WebEnhanceAgentV2.run(
            variable_name="x",
            current_value="anchor",
            web_enhance_instruction="enrich",
        )
    assert result == "FINAL VALUE"
