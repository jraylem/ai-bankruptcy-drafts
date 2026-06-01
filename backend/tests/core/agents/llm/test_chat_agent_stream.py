"""End-to-end behavior of the CaseChatAgent streaming loop.

`ChatAnthropic.astream` is faked at the class level so we can synthesize
the exact chunk sequence we want and assert on the typed events the agent
emits.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from src.core.agents.llm.chat.agent import (
    CaseChatAgent,
    extract_thinking_text,
    extract_visible_text,
)
from src.core.agents.llm.chat.events import (
    ContentDelta,
    MessageComplete,
    StreamError,
    ThinkingDelta,
    ToolResult,
    ToolUseInputDelta,
    ToolUseStart,
)
from src.core.agents.llm.chat.tools.base import ToolContext


def _make_ctx():
    case = SimpleNamespace(
        id="26_10700",
        case_name="In re Doe",
        case_number="26-10700",
        chapter=13,
        court_district="FLSB",
        petition_pdf_url=None,
        case_file_collection="case_file_26_10700",
        gmail_collection="gmail_emails_26_10700",
        courtdrive_collection="courtdrive_emails_26_10700",
    )
    return ToolContext(user_id="user-1", case=case)


class _ScriptedLLM:
    """Drop-in replacement for `llm.bind_tools(...)` returning a streamer.

    `cls` returns objects whose `.astream(messages)` plays back a pre-built
    list of chunks. Multiple turns are supported by indexing into a list of
    chunk-lists — each call to `astream` advances by one turn.
    """

    def __init__(self, turn_chunks: list[list[AIMessageChunk]]):
        self._turns = list(turn_chunks)
        self.calls = 0

    def bind_tools(self, _tools):
        return self

    def with_config(self, _config):
        # Cost-tracking callback attaches here; no-op for the scripted
        # LLM since the tests don't exercise the callback path.
        return self

    async def astream(self, _messages) -> AsyncIterator[AIMessageChunk]:
        if self.calls >= len(self._turns):
            return
        chunks = self._turns[self.calls]
        self.calls += 1
        for c in chunks:
            yield c


def _patch_llm(monkeypatch, llm):
    monkeypatch.setattr(
        "src.core.agents.llm.chat.agent.ChatAnthropic",
        lambda **kwargs: llm,
    )


@pytest.mark.unit
async def test_stream_yields_thinking_and_content_deltas_for_pure_text_turn(monkeypatch):
    """No tool calls — emit thinking deltas + content deltas, then a final AIMessage."""
    turn_chunks = [
        AIMessageChunk(content=[{"type": "thinking", "thinking": "Let me check..."}]),
        AIMessageChunk(content=[{"type": "thinking", "thinking": " the schedule."}]),
        AIMessageChunk(content=[{"type": "text", "text": "There are 12 "}]),
        AIMessageChunk(content=[{"type": "text", "text": "unsecured creditors."}]),
    ]
    _patch_llm(monkeypatch, _ScriptedLLM([turn_chunks]))

    events = []
    final_ai = None
    async for event, ai in CaseChatAgent.stream(
        ctx=_make_ctx(), history=[], user_message="how many unsecured?",
    ):
        if event is not None:
            events.append(event)
        if ai is not None:
            final_ai = ai

    assert any(isinstance(e, ThinkingDelta) for e in events)
    assert "".join(e.delta for e in events if isinstance(e, ThinkingDelta)) == "Let me check... the schedule."
    assert "".join(e.delta for e in events if isinstance(e, ContentDelta)) == "There are 12 unsecured creditors."
    assert final_ai is not None
    assert extract_visible_text(final_ai) == "There are 12 unsecured creditors."
    assert extract_thinking_text(final_ai) == "Let me check... the schedule."


@pytest.mark.unit
async def test_stream_dispatches_tool_then_runs_second_turn(monkeypatch):
    """Turn 1: model emits a tool_use. Agent runs the tool. Turn 2: model emits final text."""

    # Turn 1: streamed chunks with tool_call_chunks (Anthropic shape).
    tool_call_chunk = AIMessageChunk(
        content=[],
        tool_call_chunks=[
            {"id": "call-1", "name": "case_vector_search", "args": '{"query":"unsecured"}', "index": 0},
        ],
    )
    # Final AIMessageChunk so accumulated has full tool_calls when assembled.
    turn1 = [tool_call_chunk]

    # Turn 2: simple text response.
    turn2 = [
        AIMessageChunk(content=[{"type": "text", "text": "Based on the search: 12 creditors."}]),
    ]
    _patch_llm(monkeypatch, _ScriptedLLM([turn1, turn2]))

    # Mock the registry to route the tool call.
    async def fake_invoke(cls, ctx, **kwargs):
        return {"total": 1, "results": [{"content": "Schedule F", "relevance_score": 0.9}]}

    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.case_vector_search.CaseVectorSearchTool.invoke",
        classmethod(fake_invoke),
    )

    events: list = []
    final_ai = None
    async for event, ai in CaseChatAgent.stream(
        ctx=_make_ctx(), history=[], user_message="how many unsecured?",
    ):
        if event is not None:
            events.append(event)
        if ai is not None:
            final_ai = ai

    starts = [e for e in events if isinstance(e, ToolUseStart)]
    input_deltas = [e for e in events if isinstance(e, ToolUseInputDelta)]
    results = [e for e in events if isinstance(e, ToolResult)]

    assert len(starts) == 1
    assert starts[0].tool_name == "case_vector_search"
    assert starts[0].tool_call_id == "call-1"
    assert len(input_deltas) == 1
    assert "unsecured" in input_deltas[0].delta
    assert len(results) == 1
    assert results[0].tool_call_id == "call-1"
    assert results[0].result["total"] == 1

    content = "".join(e.delta for e in events if isinstance(e, ContentDelta))
    assert "12 creditors" in content
    assert final_ai is not None


@pytest.mark.unit
async def test_stream_unknown_tool_returns_error_payload_to_model(monkeypatch):
    """An unknown tool name should produce a ToolResult with an error payload, not crash the stream."""
    tool_call_chunk = AIMessageChunk(
        content=[],
        tool_call_chunks=[
            {"id": "call-1", "name": "not_a_real_tool", "args": '{}', "index": 0},
        ],
    )
    turn2 = [AIMessageChunk(content=[{"type": "text", "text": "I cannot use that tool."}])]
    _patch_llm(monkeypatch, _ScriptedLLM([[tool_call_chunk], turn2]))

    results: list = []
    async for event, _ai in CaseChatAgent.stream(
        ctx=_make_ctx(), history=[], user_message="x",
    ):
        if isinstance(event, ToolResult):
            results.append(event)

    assert len(results) == 1
    assert "Unknown tool" in str(results[0].result)


@pytest.mark.unit
async def test_stream_yields_stream_error_when_llm_raises(monkeypatch):
    class _BoomLLM:
        def bind_tools(self, _tools):
            return self

        def with_config(self, _config):
            return self

        async def astream(self, _messages):
            raise RuntimeError("anthropic 500")
            yield  # unreachable; satisfies async-gen typing

    _patch_llm(monkeypatch, _BoomLLM())

    seen = []
    async for event, _ai in CaseChatAgent.stream(
        ctx=_make_ctx(), history=[], user_message="x",
    ):
        if event is not None:
            seen.append(event)

    assert any(isinstance(e, StreamError) for e in seen)
    assert "anthropic 500" in next(
        e.message for e in seen if isinstance(e, StreamError)
    )


@pytest.mark.unit
def test_message_complete_carries_message_id_and_sequence():
    """Sanity check that the MessageComplete shape is intact (used by router)."""
    mc = MessageComplete(message_id="m1", sequence_number=42)
    assert mc.event == "message_complete"
    assert mc.message_id == "m1"
    assert mc.sequence_number == 42


@pytest.mark.unit
def test_extract_visible_text_string_content_passthrough():
    msg = AIMessage(content="hello world")
    assert extract_visible_text(msg) == "hello world"


@pytest.mark.unit
def test_extract_thinking_text_returns_none_for_text_only_message():
    msg = AIMessage(content=[{"type": "text", "text": "just text"}])
    assert extract_thinking_text(msg) is None


# ─── Anthropic-hosted web_search server tool ──────────────────────────


@pytest.mark.unit
def test_build_llm_binds_web_search_server_tool():
    """`_build_llm` must include Anthropic's hosted web_search server tool
    spec alongside any local tools so Claude can invoke it server-side."""
    captured_tools: list = []

    class _FakeLLM:
        def bind_tools(self, tools):
            captured_tools.extend(tools)
            return self

        def with_config(self, _config):
            return self

    import src.core.agents.llm.chat.agent as agent_module
    original = agent_module.ChatAnthropic
    agent_module.ChatAnthropic = lambda **kwargs: _FakeLLM()
    try:
        CaseChatAgent._build_llm()
    finally:
        agent_module.ChatAnthropic = original

    web = [t for t in captured_tools if isinstance(t, dict) and t.get("type") == "web_search_20250305"]
    assert len(web) == 1, "web_search server tool must be bound to the LLM"
    assert web[0]["name"] == "web_search"
    assert web[0].get("max_uses") == 5


@pytest.mark.unit
def test_chunk_to_events_emits_only_start_for_server_tool_use():
    """`server_tool_use` content blocks surface as ToolUseStart only.
    The input is NOT emitted from per-chunk processing — Anthropic
    streams the input as separate `input_json_delta` chunks that
    LangChain doesn't merge back into the original `server_tool_use`
    block, so emitting per-chunk is unreliable. The single end-of-
    stream emission in `_stream_one_turn` is what carries the input."""
    chunk = AIMessageChunk(content=[
        {
            "type": "server_tool_use",
            "id": "srvtoolu_1",
            "name": "web_search",
            "input": {"query": "Florida 9th circuit court"},
        },
    ])
    seen: set = set()
    events = CaseChatAgent._chunk_to_events(chunk, seen)
    starts = [e for e in events if isinstance(e, ToolUseStart)]
    input_deltas = [e for e in events if isinstance(e, ToolUseInputDelta)]
    assert len(starts) == 1
    assert starts[0].tool_name == "web_search"
    assert starts[0].tool_call_id == "srvtoolu_1"
    # Input deltas are deferred to end-of-stream — no per-chunk emission.
    assert input_deltas == []


@pytest.mark.unit
async def test_stream_one_turn_emits_server_tool_input_delta_at_end(monkeypatch):
    """LangChain hands back a server_tool_use block whose `input` is
    empty (Anthropic streams the input via separate `input_json_delta`
    events that don't get merged into the block). The TRUE input lives
    in `tool_calls[*].args` after accumulation. `_stream_one_turn`
    must emit exactly ONE `ToolUseInputDelta` at end of stream with the
    full input JSON so the live tool card's INPUT panel shows the
    real query rather than `{}`."""
    import json as _json

    # Simulate the streaming shape: server_tool_use block with EMPTY
    # input dict (Anthropic's initial content_block_start payload),
    # AND a tool_call entry with the real args (LangChain's accumulated
    # representation).
    server_chunk = AIMessageChunk(
        content=[
            {
                "type": "server_tool_use",
                "id": "srvtoolu_1",
                "name": "web_search",
                "input": {},  # mirrors Anthropic's initial empty block
            },
            {"type": "text", "text": "Searched the web."},
        ],
        tool_calls=[
            {
                "id": "srvtoolu_1",
                "name": "web_search",
                "args": {"query": "9th judicial circuit court florida"},
            },
        ],
    )
    _patch_llm(monkeypatch, _ScriptedLLM([[server_chunk]]))

    input_deltas: list = []
    async for event, _ai in CaseChatAgent.stream(
        ctx=_make_ctx(), history=[], user_message="what's the circuit?",
    ):
        if isinstance(event, ToolUseInputDelta):
            input_deltas.append(event)

    # Exactly one delta — emitted at end of stream from the accumulated
    # AIMessage, carrying the full input JSON.
    assert len(input_deltas) == 1
    assert input_deltas[0].tool_call_id == "srvtoolu_1"
    assert _json.loads(input_deltas[0].delta) == {
        "query": "9th judicial circuit court florida",
    }


@pytest.mark.unit
def test_extract_server_tool_calls_reads_input_from_tool_calls_when_content_block_input_is_empty():
    """Anthropic's streamed `server_tool_use` content blocks often end
    up with `input={}` after LangChain accumulation. The real input
    lives in `tool_calls[*].args`. `extract_server_tool_calls` must
    union both sources and prefer whichever has the populated input."""
    from src.core.agents.llm.chat.agent import extract_server_tool_calls

    ai = AIMessage(
        content=[
            {
                "type": "server_tool_use",
                "id": "srvtoolu_1",
                "name": "web_search",
                "input": {},  # empty in the content block
            },
            {"type": "text", "text": "answer text"},
        ],
        tool_calls=[
            {
                "id": "srvtoolu_1",
                "name": "web_search",
                "args": {"query": "real query from tool_calls"},
            },
        ],
    )
    out = extract_server_tool_calls(ai)
    assert len(out) == 1
    assert out[0]["id"] == "srvtoolu_1"
    assert out[0]["name"] == "web_search"
    assert out[0]["input"] == {"query": "real query from tool_calls"}


@pytest.mark.unit
def test_extract_server_tool_calls_keeps_content_block_input_when_tool_calls_is_empty():
    """Inverse case: content block carries the input, no entry in
    tool_calls. Helper should still return the populated input."""
    from src.core.agents.llm.chat.agent import extract_server_tool_calls

    ai = AIMessage(
        content=[
            {
                "type": "server_tool_use",
                "id": "srvtoolu_1",
                "name": "web_search",
                "input": {"query": "from content block"},
            },
        ],
        tool_calls=[],
    )
    out = extract_server_tool_calls(ai)
    assert len(out) == 1
    assert out[0]["input"] == {"query": "from content block"}


@pytest.mark.unit
def test_extract_server_tool_calls_parses_partial_json_when_input_empty():
    """Real-world streaming shape: langchain-anthropic does not update
    the `input` dict on `server_tool_use` blocks. Instead, the streamed
    `input_json_delta` chunks accumulate as a concatenated JSON STRING
    on `partial_json` (via `merge_dicts`'s str-concat behavior), and
    `tool_calls` is empty for server tools. The helper must fall back
    to parsing `partial_json`."""
    from src.core.agents.llm.chat.agent import extract_server_tool_calls

    ai = AIMessage(
        content=[
            {
                "type": "server_tool_use",
                "id": "srvtoolu_1",
                "name": "web_search",
                "input": {},
                "partial_json": '{"query": "florida 9th circuit"}',
                "index": 0,
            },
        ],
        tool_calls=[],
    )
    out = extract_server_tool_calls(ai)
    assert len(out) == 1
    assert out[0]["input"] == {"query": "florida 9th circuit"}


@pytest.mark.unit
def test_chunk_to_events_maps_web_search_result_to_tool_result():
    """`web_search_tool_result` content blocks surface as ToolResult
    events so the FE flips the card from 'invoking' to 'done'."""
    chunk = AIMessageChunk(content=[
        {
            "type": "web_search_tool_result",
            "tool_use_id": "srvtoolu_1",
            "content": [{"url": "https://example.gov", "title": "Florida statute X"}],
        },
    ])
    events = CaseChatAgent._chunk_to_events(chunk, set())
    results = [e for e in events if isinstance(e, ToolResult)]
    assert len(results) == 1
    assert results[0].tool_call_id == "srvtoolu_1"
    assert results[0].tool_name == "web_search"


@pytest.mark.unit
async def test_dispatch_tools_skips_web_search_server_tool():
    """`_dispatch_tools` must NOT try to invoke web_search locally —
    Anthropic already executed it server-side and embedded the result
    in the assistant message. Returns no ToolMessage for that call."""
    from src.core.agents.llm.chat.tools.base import ToolContext

    case = SimpleNamespace(
        id="26_10700",
        case_name="In re Doe",
        case_number="26-10700",
        chapter=13,
        court_district="FLSB",
        petition_pdf_url=None,
        case_file_collection="case_file_26_10700",
        gmail_collection="gmail_emails_26_10700",
        courtdrive_collection="courtdrive_emails_26_10700",
    )
    ctx = ToolContext(user_id="user-1", case=case)
    tool_calls = [
        {"id": "srvtoolu_1", "name": "web_search", "args": {"query": "x"}},
    ]
    out = await CaseChatAgent._dispatch_tools(tool_calls, ctx)
    assert out == [], "server tools must not produce ToolMessage rows"


@pytest.mark.unit
def test_strip_server_tool_blocks_drops_server_tool_use_and_web_search_result():
    """Regression: when iter-1 used `web_search`, the AIMessage's
    content carries `server_tool_use` AND `web_search_tool_result`
    blocks. Re-sending that to Anthropic on iter-2 trips a 400 because
    langchain-anthropic re-serializes the result block as a user-side
    `tool_result` whose sibling tool_use lives in the wrong place.
    Stripping is the safe defense — preserve the text + thinking,
    drop the server-tool bookkeeping."""
    from src.core.agents.llm.chat.agent import _strip_server_tool_blocks

    original = AIMessage(
        content=[
            {"type": "thinking", "thinking": "let me search"},
            {"type": "server_tool_use", "id": "srvtoolu_x", "name": "web_search", "input": {"query": "x"}},
            {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_x", "content": [{"url": "https://x"}]},
            {"type": "text", "text": "found it"},
        ],
        tool_calls=[
            {"id": "local-1", "name": "case_vector_search", "args": {"query": "y"}},
            {"id": "srvtoolu_x", "name": "web_search", "args": {"query": "x"}},
            # Defense-in-depth: id starts with srvtoolu_ but name is
            # empty — should still be stripped via the prefix check.
            {"id": "srvtoolu_no_name", "name": "", "args": {"query": "z"}},
        ],
    )
    stripped = _strip_server_tool_blocks(original)
    types = [b.get("type") for b in stripped.content if isinstance(b, dict)]
    assert "server_tool_use" not in types
    assert "web_search_tool_result" not in types
    # Thinking + visible text survive — the model's reasoning + answer
    # context is needed by subsequent loop iterations.
    assert "thinking" in types
    assert "text" in types
    # Local tool_calls preserved so iter-2 can still dispatch them.
    # Server tool_calls (web_search) are stripped — re-sending them
    # to Anthropic on iter 2 triggers the 400 even with content blocks
    # removed, because langchain-anthropic re-serializes them as
    # orphan tool_result entries.
    assert len(stripped.tool_calls) == 1
    assert stripped.tool_calls[0]["id"] == "local-1"
    assert stripped.tool_calls[0]["name"] == "case_vector_search"
    assert stripped.tool_calls[0]["args"] == {"query": "y"}


@pytest.mark.unit
def test_strip_server_tool_blocks_is_noop_when_no_server_blocks_present():
    """Pure-text AIMessages should pass through unchanged — same object."""
    from src.core.agents.llm.chat.agent import _strip_server_tool_blocks

    msg = AIMessage(content=[{"type": "text", "text": "hello"}])
    assert _strip_server_tool_blocks(msg) is msg


@pytest.mark.unit
def test_strip_server_tool_blocks_handles_string_content():
    """Some messages have plain-string content (no blocks). Strip is a no-op."""
    from src.core.agents.llm.chat.agent import _strip_server_tool_blocks

    msg = AIMessage(content="plain string content")
    assert _strip_server_tool_blocks(msg) is msg


@pytest.mark.unit
async def test_stream_does_not_loop_for_pure_server_tool_turn(monkeypatch):
    """If the model used ONLY web_search (server tool) in iter 1, the
    loop must NOT continue. Continuing forces a second LLM call against
    a stripped AIMessage that no longer references the search — both
    wasteful (model has to reconstruct context) and brittle (the 400
    on re-sent server-tool blocks). Pure server-tool turns end cleanly
    after iter 1."""
    # Synth a chunk where the model used web_search server-side AND
    # langchain put it in tool_calls (which is the actual behavior we
    # observed in production traces).
    iter1 = AIMessageChunk(
        content=[
            {"type": "text", "text": "Searched the web; answer is X."},
        ],
        tool_calls=[
            {"id": "srvtoolu_abc", "name": "web_search", "args": {"query": "x"}},
        ],
    )
    # If a second iteration fires, this LLM call would land here. We
    # raise to make the test fail loudly if the loop didn't break.
    iter2 = AIMessageChunk(content=[{"type": "text", "text": "I should not run"}])
    _patch_llm(monkeypatch, _ScriptedLLM([[iter1], [iter2]]))

    iterations_completed = 0
    async for _event, ai_message in CaseChatAgent.stream(
        ctx=_make_ctx(), history=[], user_message="any current Florida statute on X?",
    ):
        if ai_message is not None:
            iterations_completed += 1
    # Loop terminates after iter 1 — no second LLM call.
    assert iterations_completed == 1
