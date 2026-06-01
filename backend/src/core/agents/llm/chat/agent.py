"""CaseChatAgent — streaming agentic Claude assistant for v2 case chat.

Runs a ReAct-style loop: stream LLM → if the turn produced tool calls,
execute them, append `ToolMessage` results, stream again. Yields typed
`ChatStreamEvent`s the SSE layer converts to wire frames.

Design notes
------------
- Does NOT inherit from `Agent[TOutput]` — that base is for one-shot
  structured-output calls. Chat is multi-turn streaming with tool use.
- Uses `langchain_anthropic.ChatAnthropic` with extended thinking
  enabled by default (`thinking={"type": "enabled", ...}`) so the FE can
  surface the trace in its collapsible panel.
- Tool dispatch goes through the chat-tool registry. New tools land via
  `@register_tool` and are picked up automatically.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, ClassVar

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.core.common.constants import CLAUDE_MODEL_STANDARD
from src.core.common.cost_tracking import (
    CostTrackingCallback,
    build_cost_context_for_agent,
)

from .events import (
    ChatStreamEvent,
    ContentDelta,
    StreamError,
    ThinkingDelta,
    ToolResult,
    ToolUseInputDelta,
    ToolUseStart,
)
from .prompts import build_system_prompt
from .tools.base import ToolContext
from .tools.registry import get_all_tools, get_tool_by_name

logger = logging.getLogger(__name__)


class CaseChatAgent:
    """Streaming agentic Claude assistant for one (user, case) chat session."""

    MODEL = CLAUDE_MODEL_STANDARD
    MAX_TOKENS = 8000
    THINKING_BUDGET = 4000
    TEMPERATURE = 1.0  # extended thinking requires temperature=1
    MAX_TOOL_ITERATIONS = 6
    # Anthropic-hosted server tool: `web_search_20250305`. The model
    # decides when to call it; Anthropic executes server-side and
    # returns the results inline. No local dispatch — see
    # `_dispatch_tools` and `_chunk_to_events` for how those paths
    # treat this tool differently from registered `BaseChatTool`s.
    WEB_SEARCH_TOOL = {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 5,
    }

    @classmethod
    def _build_llm(cls):
        local_tools = [t.to_langchain_tool() for t in get_all_tools()]
        server_tools = [cls.WEB_SEARCH_TOOL]
        llm = ChatAnthropic(
            model=cls.MODEL,
            max_tokens=cls.MAX_TOKENS,
            temperature=cls.TEMPERATURE,
            thinking={"type": "enabled", "budget_tokens": cls.THINKING_BUDGET},
        )
        bound = local_tools + server_tools
        if bound:
            llm = llm.bind_tools(bound)
        # Attach cost-tracking callback. Pulls firm/case/user from the
        # current `cost_attribution` scope set in chat/service.py, and
        # tags every llm_cost_logs row with kind='chat'. server_tool_use
        # counts roll into the row's web_search-fee surcharge.
        cost_ctx = build_cost_context_for_agent(
            kind="chat", agent_name=cls.__name__,
        )
        llm = llm.with_config(
            {"callbacks": [CostTrackingCallback(cost_context=cost_ctx)]},
        )
        return llm

    @classmethod
    async def stream(
        cls,
        *,
        ctx: ToolContext,
        history: list[BaseMessage],
        user_message: str,
    ) -> AsyncIterator[tuple[ChatStreamEvent | None, AIMessage | None]]:
        """Stream a single user-turn → assistant response.

        Yields `(event, ai_message_or_none)` tuples:
        - `event` is non-None for every streaming delta / tool result.
        - `ai_message_or_none` is non-None at the end of EACH tool-loop
          iteration, carrying that iteration's full `AIMessage` (with
          aggregated thinking + content + tool_calls). The caller is
          expected to persist each one as a separate assistant row so the
          transcript mirrors Anthropic's API structure exactly — every
          `tool_use` block has a sibling `tool_result` block in the
          conversation immediately after it. Persisting only the final
          AIMessage drops the intermediate `tool_use` blocks, which makes
          the next turn's history fail Anthropic's pairing validation.
        """
        llm = cls._build_llm()
        messages: list[BaseMessage] = [
            SystemMessage(build_system_prompt(ctx.case)),
            *history,
            HumanMessage(user_message),
        ]

        try:
            for _ in range(cls.MAX_TOOL_ITERATIONS):
                ai_message: AIMessage | None = None
                async for event, accumulated in cls._stream_one_turn(llm, messages):
                    if event is not None:
                        yield event, None
                    if accumulated is not None:
                        ai_message = accumulated

                if ai_message is None:
                    # Streaming produced nothing — bail safely.
                    yield (
                        StreamError(message="Model produced no output."),
                        None,
                    )
                    return

                # Append a SANITIZED copy of the AIMessage for any
                # subsequent loop iteration. Server-tool content blocks
                # (`server_tool_use`, `web_search_tool_result`) get
                # re-serialized by langchain-anthropic as user-side
                # `tool_result` blocks on resubmission — Anthropic 400s
                # because there's no matching tool_use in the previous
                # (user) message. Server tool execution is one-shot per
                # turn anyway; the visible text the model emitted
                # AFTER the search is what the next iteration needs.
                messages.append(_strip_server_tool_blocks(ai_message))
                # Signal: persist this iteration's assistant turn now.
                # The ORIGINAL `ai_message` (with server-tool blocks
                # intact) goes to the caller so FE rendering and DB
                # persistence still see the web_search invocation.
                yield None, ai_message

                tool_calls = ai_message.tool_calls or []
                # Only LOCAL tool_calls warrant another loop iteration —
                # server tools (e.g. web_search) execute inside the model's
                # turn and don't produce a tool_result we need to feed back.
                # Continuing the loop just because web_search was used
                # forces a second LLM call that 400s on the re-sent
                # server-tool artifacts.
                local_tool_calls = [
                    tc for tc in tool_calls
                    if tc.get("name") not in cls._SERVER_TOOL_NAMES
                ]
                if not local_tool_calls:
                    break

                tool_msgs = await cls._dispatch_tools(tool_calls, ctx)
                for raw_call, tm in zip(tool_calls, tool_msgs):
                    parsed: Any
                    try:
                        parsed = json.loads(tm.content) if isinstance(tm.content, str) else tm.content
                    except Exception:
                        parsed = tm.content
                    yield (
                        ToolResult(
                            tool_call_id=raw_call["id"],
                            tool_name=raw_call["name"],
                            result=parsed,
                        ),
                        None,
                    )
                messages.extend(tool_msgs)
            else:
                logger.warning(
                    "CaseChatAgent: hit MAX_TOOL_ITERATIONS=%d without stop_reason=end_turn",
                    cls.MAX_TOOL_ITERATIONS,
                )
        except Exception as e:
            logger.exception("CaseChatAgent stream failed: %s", e)
            yield StreamError(message=f"Agent error: {e}"), None

    # ─── Internals ──────────────────────────────────────────────────

    @classmethod
    async def _stream_one_turn(
        cls,
        llm: Any,
        messages: list[BaseMessage],
    ) -> AsyncIterator[tuple[ChatStreamEvent | None, AIMessage | None]]:
        """Stream a single round-trip with the LLM.

        Translates AIMessageChunk deltas into our typed `ChatStreamEvent`s
        and assembles the final `AIMessage` (with thinking + content +
        tool_calls aggregated) as the last yield's second element.

        Server-tool inputs (e.g. `web_search`'s query) are NOT emitted
        per-chunk because Anthropic streams them as `input_json_delta`
        events that LangChain doesn't merge back into the original
        `server_tool_use` content block. Instead we wait until the
        accumulated AIMessage is complete and emit one
        `ToolUseInputDelta` per server-tool id with the full input
        JSON pulled from whichever source (`content` or `tool_calls`)
        carried the populated value.
        """
        accumulated: AIMessage | None = None
        seen_tool_starts: set[str] = set()

        async for chunk in llm.astream(messages):
            if accumulated is None:
                accumulated = chunk
            else:
                accumulated = accumulated + chunk

            for ev in cls._chunk_to_events(chunk, seen_tool_starts):
                yield ev, None

        # End-of-stream: surface server-tool inputs (web_search's query
        # etc.) as a single ToolUseInputDelta each. FE's accumulator was
        # left untouched for server-tool ids during streaming, so a one-
        # shot full-JSON delta lands cleanly without JSON-concat issues.
        if accumulated is not None:
            for server_call in extract_server_tool_calls(accumulated):
                tc_id = server_call.get("id", "")
                input_payload = server_call.get("input") or {}
                if not (tc_id and input_payload):
                    continue
                try:
                    yield ToolUseInputDelta(
                        tool_call_id=tc_id,
                        delta=json.dumps(input_payload),
                    ), None
                except Exception:
                    continue

        yield None, accumulated

    @staticmethod
    def _chunk_to_events(
        chunk: Any,
        seen_tool_starts: set[str],
    ) -> list[ChatStreamEvent]:
        """Convert one streamed AIMessageChunk into typed events for the SSE layer."""
        events: list[ChatStreamEvent] = []
        content = getattr(chunk, "content", None)

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "thinking":
                    delta = str(block.get("thinking", "")) or str(block.get("text", ""))
                    if delta:
                        events.append(ThinkingDelta(delta=delta))
                elif btype == "text":
                    delta = str(block.get("text", ""))
                    if delta:
                        events.append(ContentDelta(delta=delta))
                elif btype == "server_tool_use":
                    # Anthropic-hosted web_search invocation. Surface
                    # as ToolUseStart so the FE renders a tool card.
                    # We DO NOT emit the input here — Anthropic streams
                    # `server_tool_use` blocks with an initially-empty
                    # `input` dict and follows up with `input_json_delta`
                    # chunks that LangChain doesn't merge back into the
                    # block. The final input is emitted once at end of
                    # stream by `_stream_one_turn` via
                    # `extract_server_tool_calls` (which reads from
                    # both `content` and `tool_calls`).
                    tc_id = str(block.get("id", "")) or ""
                    tc_name = str(block.get("name", "")) or ""
                    if tc_id and tc_name and tc_id not in seen_tool_starts:
                        seen_tool_starts.add(tc_id)
                        events.append(ToolUseStart(tool_call_id=tc_id, tool_name=tc_name))
                elif btype == "web_search_tool_result":
                    # Anthropic-hosted result for a server_tool_use call.
                    # Forward it as a ToolResult so the card flips to
                    # done + shows result content.
                    tc_id = str(block.get("tool_use_id", "")) or ""
                    if tc_id:
                        events.append(
                            ToolResult(
                                tool_call_id=tc_id,
                                tool_name="web_search",
                                result=block.get("content"),
                            )
                        )
        elif isinstance(content, str) and content:
            events.append(ContentDelta(delta=content))

        for tc_chunk in getattr(chunk, "tool_call_chunks", None) or []:
            tc_id = tc_chunk.get("id") or ""
            tc_name = tc_chunk.get("name") or ""
            tc_args = tc_chunk.get("args") or ""
            is_server_tool = (
                tc_name in CaseChatAgent._SERVER_TOOL_NAMES
                or tc_id.startswith("srvtoolu_")
            )
            if tc_id and tc_name and tc_id not in seen_tool_starts:
                seen_tool_starts.add(tc_id)
                events.append(ToolUseStart(tool_call_id=tc_id, tool_name=tc_name))
            if tc_id and tc_args and not is_server_tool:
                events.append(ToolUseInputDelta(tool_call_id=tc_id, delta=tc_args))

        return events

    # Server-side tools — declared in `bind_tools` but executed by
    # Anthropic, not us. Calling our registry for them would always 404.
    _SERVER_TOOL_NAMES: ClassVar[set[str]] = {"web_search"}

    @classmethod
    async def _dispatch_tools(
        cls,
        tool_calls: list[dict],
        ctx: ToolContext,
    ) -> list[ToolMessage]:
        """Execute every tool call from one assistant turn; build ToolMessage replies.

        Server-managed tools (e.g. `web_search`) are skipped entirely —
        Anthropic already executed them server-side and the result is
        present inline in the assistant message's content blocks.
        """
        tool_msgs: list[ToolMessage] = []
        for call in tool_calls:
            name = call.get("name", "")
            if name in cls._SERVER_TOOL_NAMES:
                continue
            args = call.get("args", {}) or {}
            call_id = call.get("id", "")
            tool_cls = get_tool_by_name(name)
            if tool_cls is None:
                payload = {"error": f"Unknown tool: {name}"}
            else:
                try:
                    payload = await tool_cls.invoke(ctx, **args)
                except Exception as e:
                    logger.exception(
                        "Tool %s raised on call_id=%s: %s", name, call_id, e,
                    )
                    payload = {"error": str(e)}
            tool_msgs.append(
                ToolMessage(
                    content=json.dumps(payload, default=str),
                    tool_call_id=call_id,
                )
            )
        return tool_msgs


def extract_thinking_text(ai_message: AIMessage) -> str | None:
    """Pull the extended-thinking trace out of a completed `AIMessage`, if any."""
    content = ai_message.content
    if not isinstance(content, list):
        return None
    chunks: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "thinking":
            text = block.get("thinking") or block.get("text") or ""
            if text:
                chunks.append(str(text))
    return "".join(chunks) if chunks else None


_SERVER_TOOL_CONTENT_BLOCK_TYPES = frozenset({
    "server_tool_use",
    "web_search_tool_result",
})


def _strip_server_tool_blocks(ai_message: AIMessage) -> AIMessage:
    """Return a copy of `ai_message` with Anthropic-hosted server-tool
    artifacts removed — both the content blocks (`server_tool_use`,
    `web_search_tool_result`) AND any entries in `tool_calls` pointing
    at a server tool.

    Reason: when a single agent iteration uses BOTH a server tool
    (`web_search`) AND a local tool, the agent loop continues to a
    second iteration to process the local tool's result. Re-sending
    the iter-1 AIMessage to Anthropic on iter 2 fails with
    `messages.N.content.M: unexpected tool_use_id found in tool_result
    blocks` — langchain-anthropic re-serializes server-tool artifacts
    in a shape Anthropic's validator doesn't accept on resubmission.

    Stripping is safe across iterations: server-tool execution is
    one-shot per request, and the visible TEXT block that follows the
    web_search result (which IS preserved here) carries the model's
    synthesized takeaway from the search. The model can re-issue the
    search later if it decides it needs another lookup.
    """
    content = ai_message.content
    filtered_content: Any = content
    if isinstance(content, list):
        filtered_content = [
            block for block in content
            if not (
                isinstance(block, dict)
                and block.get("type") in _SERVER_TOOL_CONTENT_BLOCK_TYPES
            )
        ]

    tool_calls = list(ai_message.tool_calls or [])
    filtered_tool_calls = [
        tc for tc in tool_calls
        if (
            tc.get("name") not in CaseChatAgent._SERVER_TOOL_NAMES
            and not str(tc.get("id") or "").startswith("srvtoolu_")
        )
    ]

    content_unchanged = (
        not isinstance(content, list)
        or len(filtered_content) == len(content)
    )
    tool_calls_unchanged = len(filtered_tool_calls) == len(tool_calls)
    if content_unchanged and tool_calls_unchanged:
        return ai_message

    return AIMessage(
        content=filtered_content,
        tool_calls=filtered_tool_calls,
    )


def extract_server_tool_calls(ai_message: AIMessage) -> list[dict]:
    """Extract Anthropic-hosted server-tool invocations from an AIMessage.

    Anthropic surfaces `web_search` and friends as `server_tool_use`
    content blocks. For local tools (`tool_use`), langchain-anthropic
    creates a `tool_call_chunk` carrying the accumulated args; for
    SERVER tools it does NOT — `ai_message.tool_calls` is empty for
    server invocations.

    Instead, langchain-anthropic merges the streamed `input_json_delta`
    chunks into the same content-block-index via `merge_dicts`. The
    `server_tool_use` block ends up with three relevant keys:

    - `input` — stays at the empty `{}` from the initial
      `content_block_start` event (never mutated).
    - `partial_json` — accumulated input JSON as a STRING (delta chunks'
      `partial_json` fields get string-concatenated by `merge_dicts`).
    - `index` — unchanged.

    So the REAL input for server tools lives in `partial_json` and we
    must parse it. We also still consult `tool_calls` as a fallback in
    case a future langchain version starts populating it.

    Returns one entry per server-tool id with `{id, name, input}`.
    """
    content = ai_message.content
    inputs_by_id: dict[str, dict] = {}
    names_by_id: dict[str, str] = {}

    if isinstance(content, list):
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "server_tool_use"):
                continue
            tc_id = str(block.get("id", ""))
            if not tc_id:
                continue
            names_by_id.setdefault(tc_id, str(block.get("name", "")))
            block_input = block.get("input") or {}
            if not block_input:
                # langchain-anthropic accumulates server-tool input deltas
                # as a concatenated JSON string on `partial_json`, not in
                # the original `input` dict. Parse it back.
                partial_json = block.get("partial_json")
                if isinstance(partial_json, str) and partial_json:
                    try:
                        parsed = json.loads(partial_json)
                        if isinstance(parsed, dict):
                            block_input = parsed
                    except (json.JSONDecodeError, TypeError):
                        pass
            existing = inputs_by_id.get(tc_id) or {}
            if block_input and not existing:
                inputs_by_id[tc_id] = block_input
            inputs_by_id.setdefault(tc_id, block_input)

    for tc in ai_message.tool_calls or []:
        tc_id = str(tc.get("id", ""))
        if not tc_id:
            continue
        name = str(tc.get("name", ""))
        is_server = (
            name in CaseChatAgent._SERVER_TOOL_NAMES
            or tc_id.startswith("srvtoolu_")
        )
        if not is_server:
            continue
        names_by_id.setdefault(tc_id, name or "web_search")
        args = tc.get("args") or {}
        existing = inputs_by_id.get(tc_id) or {}
        if args and not existing:
            inputs_by_id[tc_id] = args
        inputs_by_id.setdefault(tc_id, args)

    return [
        {
            "id": tc_id,
            "name": names_by_id.get(tc_id, "web_search") or "web_search",
            "input": inputs_by_id.get(tc_id, {}),
        }
        for tc_id in inputs_by_id
    ]


def extract_visible_text(ai_message: AIMessage) -> str:
    """Pull the visible assistant text out of an `AIMessage` (excluding thinking blocks)."""
    content = ai_message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                if isinstance(block, str):
                    chunks.append(block)
                continue
            if block.get("type") == "text":
                chunks.append(str(block.get("text", "")))
        return "".join(chunks)
    return str(content or "")
