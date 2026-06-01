"""LangChain `AsyncCallbackHandler` that records LLM cost on every call.

Attached at each agent's edge via `RunnableConfig.callbacks`. LangChain
fires `on_llm_end` once after `.ainvoke()` and once after `.astream()`
completes, handing us the full `LLMResult` whose generations carry the
`AIMessage.usage_metadata` standardized field.

Streaming behavior: LangChain accumulates `AIMessageChunk` deltas into
a final `AIMessageChunk` and emits a single `on_llm_end`. The handler
treats invoke and stream symmetrically.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from .context import CostContext
from .pricing import compute_cost_usd, web_search_fee_usd

if TYPE_CHECKING:
    from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


def _count_server_tool_uses(message: Any) -> int:
    """Count `server_tool_use` content blocks in an AIMessage / chunk.

    Anthropic's hosted web_search is billed flat per use ON TOP of the
    message tokens; we surface the count from the response content so
    the handler can add the surcharge.
    """
    if message is None:
        return 0
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        return 0
    return sum(
        1 for block in content
        if isinstance(block, dict) and block.get("type") == "server_tool_use"
    )


def _extract_usage(message: Any) -> dict[str, int]:
    """Pull a standardized {input, output, cache_read, cache_write} dict
    from `AIMessage.usage_metadata`. Falls back to zeros if missing."""
    meta = getattr(message, "usage_metadata", None) or {}
    if not isinstance(meta, dict):
        return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    details = meta.get("input_token_details") or {}
    if not isinstance(details, dict):
        details = {}
    return {
        "input": int(meta.get("input_tokens", 0) or 0),
        "output": int(meta.get("output_tokens", 0) or 0),
        "cache_read": int(details.get("cache_read", 0) or 0),
        "cache_write": int(details.get("cache_creation", details.get("cache_write", 0)) or 0),
    }


def _model_from_message_or_result(message: Any, response: "LLMResult") -> str:
    """Best-effort: take the response model from AIMessage.response_metadata,
    fall back to llm_output. Anthropic populates response_metadata.model_name
    on every response; older OpenAI flows put it on llm_output.model."""
    rm = getattr(message, "response_metadata", None) or {}
    if isinstance(rm, dict):
        for key in ("model_name", "model"):
            if rm.get(key):
                return str(rm[key])
    llm_output = response.llm_output or {}
    if isinstance(llm_output, dict):
        for key in ("model_name", "model"):
            if llm_output.get(key):
                return str(llm_output[key])
    return ""


class CostTrackingCallback(AsyncCallbackHandler):
    """One instance per LLM call. Construct at the call site with the
    `CostContext` (kind / firm_id / etc.), attach via
    `with_config({"callbacks": [cb]})` or
    `.ainvoke(..., config={"callbacks": [cb]})`.

    Writes a single row to `llm_cost_logs` via
    `LlmCostLogRepository.record(...)`. Repo writes swallow exceptions
    so a Postgres hiccup never bubbles into the LLM caller.
    """

    raise_error: bool = False
    run_inline: bool = True

    def __init__(self, *, cost_context: CostContext) -> None:
        super().__init__()
        self._context = cost_context

    async def on_llm_end(
        self,
        response: "LLMResult",
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        try:
            await self._record(response, run_id)
        except Exception as e:
            # Defensive: should already be swallowed inside _record, but
            # the callback itself must NEVER raise — that propagates
            # back into the LangChain runner and breaks the LLM call.
            logger.exception("CostTrackingCallback.on_llm_end failed: %s", e)

    async def _record(self, response: "LLMResult", run_id: UUID) -> None:
        # Aggregate across all generations (Anthropic typically returns
        # one, but tools / n>1 sampling can return more).
        totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
        server_tool_uses = 0
        model = ""
        for gen_list in response.generations:
            for gen in gen_list:
                message = getattr(gen, "message", None)
                if message is None:
                    continue
                if not model:
                    model = _model_from_message_or_result(message, response)
                usage = _extract_usage(message)
                for k, v in usage.items():
                    totals[k] += v
                server_tool_uses += _count_server_tool_uses(message)

        if model == "" and totals["input"] == 0 and totals["output"] == 0:
            # Nothing useful — skip the write rather than create a zero row.
            return

        cost = compute_cost_usd(
            model=model,
            input_tokens=totals["input"],
            output_tokens=totals["output"],
            cache_read_tokens=totals["cache_read"],
            cache_write_tokens=totals["cache_write"],
        )
        if server_tool_uses > 0:
            cost = (cost + web_search_fee_usd(server_tool_uses)).quantize(Decimal("0.000001"))

        metadata = self._context.to_metadata()
        if server_tool_uses > 0:
            metadata["web_search_uses"] = server_tool_uses

        # Fire-and-forget: a slow Postgres write must NOT block the
        # generator returning to the caller. The repo's `record` is
        # already exception-swallowing.
        asyncio.create_task(
            _record_safely(
                kind=self._context.kind,
                firm_id=self._context.firm_id,
                model=model,
                input_tokens=totals["input"],
                output_tokens=totals["output"],
                cache_read_tokens=totals["cache_read"],
                cache_write_tokens=totals["cache_write"],
                cost_usd=cost,
                run_id=str(run_id),
                semantic_id=self._context.semantic_id,
                semantic_id_kind=self._context.semantic_id_kind,
                metadata=metadata,
            )
        )


async def _record_safely(**kwargs: Any) -> None:
    """Indirection so the repo import doesn't run at module import time
    (avoids any circular-import risk between cost_tracking and storage).
    """
    try:
        from src.core.common.storage.database import LlmCostLogRepository
        await LlmCostLogRepository.record(**kwargs)
    except Exception as e:
        logger.warning("LlmCostLogRepository.record failed: %s", e)
