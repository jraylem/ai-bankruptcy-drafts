"""SSE frame rendering — pure-function tests over the wire shape."""

from __future__ import annotations

import json

import pytest

from src.core.agents.llm.chat.events import (
    ContentDelta,
    MessageComplete,
    StreamError,
    ThinkingDelta,
    ToolResult,
    ToolUseInputDelta,
    ToolUseStart,
)
from src.core.components.chat.sse import _event_to_frame, render_sse_response


@pytest.mark.unit
def test_thinking_delta_frame_shape():
    frame = _event_to_frame(ThinkingDelta(delta="hmm"))
    assert frame.startswith("event: thinking_delta\n")
    body = frame.split("data: ", 1)[1].split("\n\n", 1)[0]
    assert json.loads(body) == {"delta": "hmm"}


@pytest.mark.unit
def test_tool_use_start_frame_shape():
    frame = _event_to_frame(ToolUseStart(tool_call_id="c1", tool_name="case_vector_search"))
    assert "event: tool_use_start" in frame
    body = frame.split("data: ", 1)[1].split("\n\n", 1)[0]
    parsed = json.loads(body)
    assert parsed == {"tool_call_id": "c1", "tool_name": "case_vector_search"}


@pytest.mark.unit
def test_tool_result_frame_serializes_result_dict():
    frame = _event_to_frame(ToolResult(
        tool_call_id="c1", tool_name="case_vector_search",
        result={"total": 2, "results": []},
    ))
    body = frame.split("data: ", 1)[1].split("\n\n", 1)[0]
    parsed = json.loads(body)
    assert parsed["result"]["total"] == 2


@pytest.mark.unit
def test_content_delta_and_message_complete_frames():
    cf = _event_to_frame(ContentDelta(delta="hi"))
    assert "event: content_delta" in cf

    mf = _event_to_frame(MessageComplete(message_id="m1", sequence_number=7))
    body = mf.split("data: ", 1)[1].split("\n\n", 1)[0]
    assert json.loads(body) == {"message_id": "m1", "sequence_number": 7}


@pytest.mark.unit
def test_tool_use_input_delta_carries_partial_args():
    f = _event_to_frame(ToolUseInputDelta(tool_call_id="c1", delta='{"query":'))
    body = f.split("data: ", 1)[1].split("\n\n", 1)[0]
    assert json.loads(body) == {"tool_call_id": "c1", "delta": '{"query":'}


@pytest.mark.unit
def test_error_frame_shape():
    f = _event_to_frame(StreamError(message="boom"))
    assert "event: error" in f


@pytest.mark.unit
async def test_render_sse_response_streams_frames_and_surfaces_errors():
    """Generator-raise mid-stream is surfaced as a final `error` frame, not a 500."""

    async def gen():
        yield ContentDelta(delta="a")
        raise RuntimeError("midstream-bug")

    response = await render_sse_response(gen())
    chunks: list[str] = []
    async for raw in response.body_iterator:
        chunks.append(raw if isinstance(raw, str) else raw.decode())
    joined = "".join(chunks)
    assert "event: content_delta" in joined
    assert "event: error" in joined
    assert "midstream-bug" in joined


@pytest.mark.unit
async def test_render_sse_response_renders_clean_stream():
    """Happy path: every event reaches the wire as a `text/event-stream` frame."""

    async def gen():
        yield ThinkingDelta(delta="reasoning")
        yield ContentDelta(delta="hello")
        yield MessageComplete(message_id="m1", sequence_number=1)

    response = await render_sse_response(gen())
    chunks: list[str] = []
    async for raw in response.body_iterator:
        chunks.append(raw if isinstance(raw, str) else raw.decode())
    joined = "".join(chunks)
    assert "event: thinking_delta" in joined
    assert "event: content_delta" in joined
    assert "event: message_complete" in joined
