"""Tests for ExtractorAgentV2._run_loop — the shared tool loop.

We bypass real Anthropic by patching `ChatAnthropic.bind_tools(...).with_config(...).ainvoke`
to return fabricated `AIMessage`s with tool_calls of our choosing.
This exercises the loop's branches: submit_* arrives → parse + return;
real tool call → dispatch + append result; iterations exhaust → None.
"""

from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from src.core.studio_v2.agents.extractors.base import ExtractorAgentV2


class _FakeSubmit(BaseModel):
    """Test submit-tool schema."""

    value: str


class _Agent(ExtractorAgentV2[_FakeSubmit]):
    output_type: ClassVar[type[BaseModel]] = _FakeSubmit
    submit_tool_name: ClassVar[str] = "_FakeSubmit"
    cost_kind: ClassVar[str] = "test_extractor"
    max_iterations: ClassVar[int] = 4


def _make_messages() -> list:
    return [
        SystemMessage(content="system"),
        HumanMessage(content="user"),
    ]


def _stub_llm(responses: list[AIMessage]):
    """Build a LangChain-pipeline-mock whose .ainvoke returns each
    response in turn."""
    pipeline = MagicMock()
    pipeline.ainvoke = AsyncMock(side_effect=responses)
    bound = MagicMock()
    bound.with_config = MagicMock(return_value=pipeline)
    llm = MagicMock()
    llm.bind_tools = MagicMock(return_value=bound)
    return llm


@pytest.mark.unit
@pytest.mark.asyncio
async def test_submit_call_on_first_iteration_returns_parsed_output():
    """Agent calls submit_* immediately — loop returns parsed output."""
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "_FakeSubmit", "args": {"value": "extracted"}, "id": "call-1"},
        ],
    )
    llm = _stub_llm([ai])
    with patch(
        "src.core.studio_v2.agents.extractors.base.ChatAnthropic",
        return_value=llm,
    ):
        result = await _Agent._run_loop(
            messages=_make_messages(),
            tools=[_FakeSubmit],
            agent_name="TestAgent",
        )
    assert result.output is not None
    assert result.output.value == "extracted"
    assert result.tool_call_count == 0
    assert result.iterations == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_real_tool_call_then_submit():
    """Iteration 1: agent calls a real tool → loop dispatches it.
    Iteration 2: agent calls submit_* → loop returns."""
    fake_tool = MagicMock()
    fake_tool.name = "case_vector_query"
    fake_tool.ainvoke = AsyncMock(return_value={"results": [{"content": "chunk", "relevance_score": 0.9}]})

    ai1 = AIMessage(
        content="",
        tool_calls=[
            {"name": "case_vector_query", "args": {"query": "VIN", "top_k": 3}, "id": "call-1"},
        ],
    )
    ai2 = AIMessage(
        content="",
        tool_calls=[
            {"name": "_FakeSubmit", "args": {"value": "1HG..."}, "id": "call-2"},
        ],
    )
    llm = _stub_llm([ai1, ai2])
    with patch(
        "src.core.studio_v2.agents.extractors.base.ChatAnthropic",
        return_value=llm,
    ):
        result = await _Agent._run_loop(
            messages=_make_messages(),
            tools=[fake_tool, _FakeSubmit],
            agent_name="TestAgent",
        )
    assert result.output is not None
    assert result.output.value == "1HG..."
    assert result.tool_call_count == 1
    assert result.iterations == 2
    # Real tool was actually invoked with the args from the LLM.
    fake_tool.ainvoke.assert_awaited_once_with({"query": "VIN", "top_k": 3})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_iterations_exhaust_returns_none():
    """Agent keeps calling a real tool forever — loop caps at max_iterations
    and returns None (caller degrades)."""
    fake_tool = MagicMock()
    fake_tool.name = "case_vector_query"
    fake_tool.ainvoke = AsyncMock(return_value={"results": []})

    looping = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "case_vector_query", "args": {"query": f"q{i}"}, "id": f"c{i}"},
            ],
        )
        for i in range(_Agent.max_iterations + 2)
    ]
    llm = _stub_llm(looping)
    with patch(
        "src.core.studio_v2.agents.extractors.base.ChatAnthropic",
        return_value=llm,
    ):
        result = await _Agent._run_loop(
            messages=_make_messages(),
            tools=[fake_tool, _FakeSubmit],
            agent_name="TestAgent",
        )
    assert result.output is None
    assert result.iterations == _Agent.max_iterations
    assert result.tool_call_count == _Agent.max_iterations


@pytest.mark.unit
@pytest.mark.asyncio
async def test_text_only_response_returns_none():
    """Agent emits no tool_calls (plain text) → caller treats as failure."""
    ai = AIMessage(content="I cannot find that information.")
    llm = _stub_llm([ai])
    with patch(
        "src.core.studio_v2.agents.extractors.base.ChatAnthropic",
        return_value=llm,
    ):
        result = await _Agent._run_loop(
            messages=_make_messages(),
            tools=[_FakeSubmit],
            agent_name="TestAgent",
        )
    assert result.output is None
    assert result.tool_call_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_submit_args_returns_none():
    """submit_* call with args that don't validate against output_type
    → loop returns None."""
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "_FakeSubmit", "args": {"wrong_key": "x"}, "id": "call-1"},
        ],
    )
    llm = _stub_llm([ai])
    with patch(
        "src.core.studio_v2.agents.extractors.base.ChatAnthropic",
        return_value=llm,
    ):
        result = await _Agent._run_loop(
            messages=_make_messages(),
            tools=[_FakeSubmit],
            agent_name="TestAgent",
        )
    assert result.output is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_tool_call_is_safely_ignored():
    """Model calls a tool name we didn't bind — loop reports an error
    via ToolMessage and continues."""
    fake_submit_after = AIMessage(
        content="",
        tool_calls=[
            {"name": "_FakeSubmit", "args": {"value": "ok"}, "id": "c2"},
        ],
    )
    bad_call = AIMessage(
        content="",
        tool_calls=[
            {"name": "imaginary_tool", "args": {}, "id": "c1"},
        ],
    )
    llm = _stub_llm([bad_call, fake_submit_after])
    with patch(
        "src.core.studio_v2.agents.extractors.base.ChatAnthropic",
        return_value=llm,
    ):
        result = await _Agent._run_loop(
            messages=_make_messages(),
            tools=[_FakeSubmit],
            agent_name="TestAgent",
        )
    assert result.output is not None
    assert result.output.value == "ok"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_raise_is_safely_caught():
    """Real tool raises — error is wrapped in ToolMessage; loop continues
    to next iteration which then calls submit_*."""
    fake_tool = MagicMock()
    fake_tool.name = "vision_fallback"
    fake_tool.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))

    ai1 = AIMessage(
        content="",
        tool_calls=[
            {"name": "vision_fallback", "args": {"question": "?"}, "id": "c1"},
        ],
    )
    ai2 = AIMessage(
        content="",
        tool_calls=[
            {"name": "_FakeSubmit", "args": {"value": "fallback"}, "id": "c2"},
        ],
    )
    llm = _stub_llm([ai1, ai2])
    with patch(
        "src.core.studio_v2.agents.extractors.base.ChatAnthropic",
        return_value=llm,
    ):
        result = await _Agent._run_loop(
            messages=_make_messages(),
            tools=[fake_tool, _FakeSubmit],
            agent_name="TestAgent",
        )
    assert result.output is not None
    assert result.output.value == "fallback"
