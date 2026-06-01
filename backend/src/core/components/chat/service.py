"""Glue between the chat router, persistence, and the agent.

Owns: session lookup, history hydration (DB rows → LangChain messages),
agent stream pumping with simultaneous DB write of assistant turns. The
router stays a thin HTTP layer on top.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from fastapi import HTTPException
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)

from src.core.agents.llm.chat.agent import (
    CaseChatAgent,
    extract_server_tool_calls,
    extract_thinking_text,
    extract_visible_text,
)
# Server-side tools (Anthropic-hosted) — these run inside the model's
# turn and produce content-block-only invocations, not local tool calls
# our agent loop dispatches. Used for both persistence merging AND for
# stripping out of cross-turn history rebuilds.
_SERVER_TOOL_NAMES = {"web_search"}
from src.core.agents.llm.chat.events import (
    ChatStreamEvent,
    ContentDelta,
    MessageComplete,
    StreamError,
    ToolResult,
)
from src.core.agents.llm.chat.guardrail import (
    CANNED_REFUSAL,
    screen_user_message,
)
from src.core.agents.llm.chat.tools.base import ToolContext
from src.core.common.cost_tracking import cost_attribution
from src.core.common.storage.database import (
    Case,
    CaseRepository,
    CaseSession,
    CaseSessionMessage,
    CaseSessionMessageRepository,
    CaseSessionRepository,
)

from .schemas import (
    GetOrCreateSessionResponse,
    MessageResponse,
    SessionResponse,
    ToolCallSummary,
)

logger = logging.getLogger(__name__)


WELCOME_MESSAGE = (
    "Hello! I'm your AI Petition Reviewer. I can review bankruptcy petitions "
    "and provide guidance based on Florida bankruptcy rules and best practices."
)


# ─── Session lookup ───────────────────────────────────────────────────


_INITIAL_MESSAGES_LIMIT = 200


async def get_or_create_session(
    *, user_id: str, case_id: str,
) -> GetOrCreateSessionResponse:
    """Resolve the canonical (user, case) session AND return its first
    page of transcript in one round trip.

    Cold-path optimizations:
      - `CaseRepository.get` and `CaseSessionRepository.get_or_create`
        run in parallel via `asyncio.gather` — both depend only on
        case_id, so one round trip wall-time instead of two.
      - On a freshly-created session (`created=True`), skip the
        `list_by_session` lookup entirely — we know the transcript is
        empty — and seed the welcome with `sequence_number=1` so the
        message repo skips its MAX(seq) lookup too.
      - Warm path (`created=False`) keeps the original
        `list_by_session(limit=200)` covering both welcome-needed check
        and FE initial hydration.
    """
    case, (session, created) = await asyncio.gather(
        CaseRepository.get(case_id),
        CaseSessionRepository.get_or_create(user_id=user_id, case_id=case_id),
    )
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    if created:
        seeded = await CaseSessionMessageRepository.append(
            case_session_id=session.id,
            role="assistant",
            content=WELCOME_MESSAGE,
            sequence_number=1,
        )
        rows = [seeded]
    else:
        rows = await CaseSessionMessageRepository.list_by_session(
            case_session_id=session.id, limit=_INITIAL_MESSAGES_LIMIT,
        )
        if not rows:
            # Edge case: existing session with no messages (welcome got
            # deleted, manual DB poke, etc.). Seed lazily so the FE never
            # sees an empty chat.
            seeded = await CaseSessionMessageRepository.append(
                case_session_id=session.id,
                role="assistant",
                content=WELCOME_MESSAGE,
                sequence_number=1,
            )
            rows = [seeded]
    return GetOrCreateSessionResponse(
        session=session_to_response(session),
        messages=[_message_to_response(r) for r in rows],
        has_more=len(rows) == _INITIAL_MESSAGES_LIMIT,
    )


async def load_owned_session(*, user_id: str, session_id: str) -> CaseSession:
    """Fetch a session and verify the caller owns it. 404 on either miss
    so cross-user existence doesn't leak."""
    session = await CaseSessionRepository.get(session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ─── History hydration ────────────────────────────────────────────────


def _message_to_response(row: CaseSessionMessage) -> MessageResponse:
    raw_tool_calls = row.tool_calls
    tool_calls: list[ToolCallSummary] | None = None
    if raw_tool_calls:
        try:
            tool_calls = [
                ToolCallSummary(
                    id=tc.get("id", ""),
                    name=tc.get("name", ""),
                    input=tc.get("input") or tc.get("args") or {},
                )
                for tc in raw_tool_calls
            ]
        except Exception as e:
            logger.warning(
                "Failed to parse tool_calls on message %s: %s", row.id, e,
            )
            tool_calls = None
    return MessageResponse(
        id=row.id,
        case_session_id=row.case_session_id,
        sequence_number=row.sequence_number,
        role=row.role,
        content=row.content or "",
        thinking=row.thinking,
        tool_calls=tool_calls,
        tool_call_id=row.tool_call_id,
        created_at=row.created_at,
    )


def session_to_response(session: CaseSession) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        case_id=session.case_id,
        user_id=session.user_id,
        title=session.title or "Chat",
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


async def list_messages(
    *, session_id: str, limit: int = 200, before_sequence: int | None = None,
) -> list[MessageResponse]:
    rows = await CaseSessionMessageRepository.list_by_session(
        case_session_id=session_id,
        limit=limit,
        before_sequence=before_sequence,
    )
    return [_message_to_response(r) for r in rows]


async def _build_langchain_history(session_id: str) -> list[BaseMessage]:
    """Replay the persisted transcript as LangChain `BaseMessage`s for the agent.

    Thinking blocks are intentionally NOT replayed cross-turn. Anthropic's
    extended-thinking blocks carry a cryptographic `signature` from the
    API response that we don't persist (and shouldn't — it bloats the DB
    and isn't ours to forge). Re-sending an unsigned thinking block
    fails Anthropic's validator with `messages.N.content.0.thinking.signature:
    Field required`. Anthropic only requires thinking blocks to be
    preserved WITHIN a single in-flight tool-use loop — which the agent
    rebuilds live from the LLM's responses — not across user turns.

    Server-tool entries (`web_search`) are ALSO stripped from history:
    Anthropic re-executes server tools fresh each turn, and replaying a
    prior turn's `server_tool_use` tool_call without its corresponding
    `web_search_tool_result` content block (which we'd have to
    reconstruct as an opaque server-tool-result, not a generic
    ToolMessage) risks API rejection. Their omission doesn't hurt
    continuity — the visible answer text from the prior turn already
    carries the useful info.

    Defense in depth: we strip on EITHER `name in _SERVER_TOOL_NAMES`
    OR `id` starting with `srvtoolu_` (Anthropic's server-tool ID
    prefix). Older persisted rows from before tighter persistence
    landed may have empty `name` fields while still carrying the
    `srvtoolu_` ID — the prefix check catches them. And tool rows
    only survive if their `tool_call_id` matches a LOCAL tool_call
    on a preceding assistant row (positive filter); any orphan
    `role="tool"` row from a failed/stale turn gets silently dropped.
    """
    rows = await CaseSessionMessageRepository.list_by_session(
        case_session_id=session_id, limit=1000,
    )
    local_tool_call_ids: set[str] = set()
    messages: list[BaseMessage] = []
    for row in rows:
        if row.role == "user":
            messages.append(HumanMessage(content=row.content or ""))
        elif row.role == "assistant":
            tool_calls = []
            for tc in row.tool_calls or []:
                name = tc.get("name", "")
                tc_id = tc.get("id", "")
                if (
                    name in _SERVER_TOOL_NAMES
                    or tc_id.startswith("srvtoolu_")
                ):
                    continue
                tool_calls.append(
                    {
                        "id": tc_id,
                        "name": name,
                        "args": tc.get("input") or tc.get("args") or {},
                    }
                )
                if tc_id:
                    local_tool_call_ids.add(tc_id)
            messages.append(
                AIMessage(
                    content=row.content or "",
                    tool_calls=tool_calls,
                )
            )
        elif row.role == "tool":
            tc_id = row.tool_call_id or ""
            # Positive filter: keep ONLY tool rows whose call_id matches
            # a LOCAL tool_call we surfaced on a preceding assistant.
            # Anything else — server-tool results, orphans from failed
            # turns, garbled rows — gets silently dropped.
            if tc_id not in local_tool_call_ids:
                continue
            messages.append(
                ToolMessage(
                    content=row.content or "",
                    tool_call_id=tc_id,
                )
            )
    return messages


# ─── Stream orchestration ─────────────────────────────────────────────


async def stream_assistant_turn(
    *,
    user: Any,  # noqa: ANN401 — duck-typed from fastapi auth (has .id)
    session: CaseSession,
    case: Case,
    user_message: str,
) -> AsyncIterator[ChatStreamEvent]:
    """Persist the user's message, run the agent, persist assistant + tool turns,
    and yield typed events the SSE layer will frame.
    """
    # Scope cost attribution for this turn — every nested LLM call
    # (guardrail Haiku, main chat Sonnet, petition_vision sub-tool)
    # picks up firm/case/user/session from this context manager and
    # writes them to llm_cost_logs.
    cost_scope = cost_attribution(
        firm_id=getattr(user, "firm_id", None),
        case_id=case.id,
        user_id=user.id,
        session_id=session.id,
        semantic_id=session.id,
        semantic_id_kind="case_session",
    )
    with cost_scope:
        async for event in _stream_assistant_turn_impl(
            user=user, session=session, case=case, user_message=user_message,
        ):
            yield event


async def _stream_assistant_turn_impl(
    *,
    user: Any,
    session: CaseSession,
    case: Case,
    user_message: str,
) -> AsyncIterator[ChatStreamEvent]:
    # 1. Persist the user turn FIRST so a streaming failure still leaves the
    #    transcript consistent (user said X, but no assistant answer yet).
    await CaseSessionMessageRepository.append(
        case_session_id=session.id,
        role="user",
        content=user_message,
    )

    # 2. Safety pre-screen via Claude Haiku 4.5. Blocks obvious jailbreaks,
    #    explicitly harmful content, and clearly non-legal chitchat —
    #    permissive otherwise so paralegals retain flexibility for
    #    cross-case research, statute lookups, general bankruptcy law.
    #    Short-circuits the expensive Sonnet agent on a hit.
    verdict = await screen_user_message(user_message=user_message, case=case)
    if not verdict.is_allowed:
        refusal_text = (
            (verdict.refusal_message or "").strip() or CANNED_REFUSAL
        )
        persisted = await CaseSessionMessageRepository.append(
            case_session_id=session.id,
            role="assistant",
            content=refusal_text,
        )
        yield ContentDelta(delta=refusal_text)
        yield MessageComplete(
            message_id=persisted.id,
            sequence_number=persisted.sequence_number,
        )
        logger.info(
            "Guardrail blocked user message session=%s category=%s",
            session.id, verdict.category,
        )
        return

    ctx = ToolContext(user_id=user.id, case=case)
    history = await _build_langchain_history(session.id)
    # Drop the trailing user message we just appended — the agent receives
    # it via the `user_message` arg, not the history.
    if history and isinstance(history[-1], HumanMessage) and history[-1].content == user_message:
        history = history[:-1]

    # 2. Persist each iteration's assistant turn AND its tool-result rows
    #    in order. The agent yields an AIMessage at the end of every loop
    #    iteration, so on a multi-step tool-using turn we end up with
    #    multiple `role="assistant"` rows interleaved with `role="tool"`
    #    rows — mirroring Anthropic's API structure (every `tool_use`
    #    block has its `tool_result` block in the very next message).
    #
    #    Persisting only the FINAL assistant message — which is the
    #    earlier shape of this code — drops the intermediate `tool_use`
    #    blocks, so the next turn's history fails Anthropic's pairing
    #    validation with `unexpected tool_use_id found in tool_result blocks`.
    last_persisted_assistant: Any = None
    try:
        async for event, ai_message in CaseChatAgent.stream(
            ctx=ctx, history=history, user_message=user_message,
        ):
            if event is not None:
                if isinstance(event, ToolResult):
                    await _persist_tool_result(session.id, event)
                yield event
            if ai_message is not None:
                last_persisted_assistant = await _persist_assistant_iteration(
                    session.id, ai_message,
                )
    except Exception as e:
        logger.exception("stream_assistant_turn agent error: %s", e)
        yield StreamError(message=f"Agent error: {e}")
        return

    if last_persisted_assistant is None:
        yield StreamError(message="Agent produced no response.")
        return

    yield MessageComplete(
        message_id=last_persisted_assistant.id,
        sequence_number=last_persisted_assistant.sequence_number,
    )


async def _persist_assistant_iteration(
    session_id: str, ai_message: AIMessage,
):
    """Persist one assistant turn (one iteration of the agent loop).

    Merges LOCAL tool calls (from `ai_message.tool_calls`) with
    SERVER tool calls (extracted from `server_tool_use` content blocks)
    into the persisted `tool_calls` JSON so the FE renders a tool card
    on history reload for either kind.

    Server tools are EXCLUDED from `local_calls`: LangChain sometimes
    surfaces them in `ai_message.tool_calls` with empty `args` (the
    real input lives only in the `server_tool_use` content block).
    Keeping both versions duplicates the id, and the FE's `key=id`
    rendering picks the first one — which is the empty-input copy.
    Strip server tools from local_calls and let `extract_server_tool_calls`
    be the single source of truth for their persisted shape.
    """
    local_calls = [
        {
            "id": tc.get("id", ""),
            "name": tc.get("name", ""),
            "input": tc.get("args") or {},
        }
        for tc in (ai_message.tool_calls or [])
        if (
            tc.get("name") not in _SERVER_TOOL_NAMES
            and not str(tc.get("id") or "").startswith("srvtoolu_")
        )
    ]
    server_calls = extract_server_tool_calls(ai_message)
    all_calls = local_calls + server_calls
    tool_calls_payload: list[dict] | None = all_calls if all_calls else None
    return await CaseSessionMessageRepository.append(
        case_session_id=session_id,
        role="assistant",
        content=extract_visible_text(ai_message),
        thinking=extract_thinking_text(ai_message),
        tool_calls=tool_calls_payload,
    )


async def _persist_tool_result(session_id: str, tr: ToolResult) -> None:
    """Persist one tool-result row, keyed by `tool_call_id`."""
    try:
        content_text = (
            tr.result if isinstance(tr.result, str)
            else json.dumps(tr.result, default=str)
        )
    except Exception:
        content_text = str(tr.result)
    await CaseSessionMessageRepository.append(
        case_session_id=session_id,
        role="tool",
        content=content_text,
        tool_call_id=tr.tool_call_id,
    )
