"""WebEnhanceAgentV2 — Anthropic web-search enhancement for any v2 field.

Architectural note: this agent does NOT extend `StudioV2Agent` /
`Agent`. The base auto-binds `with_structured_output(...)`, which
doesn't compose with native server-side tools like
`web_search_20250305`. Instead we go through `ChatAnthropic.bind_tools(...)`
directly — that path DOES support the server-side tool (the tool runs
at Anthropic, the multi-turn dance is internal to the SDK, and
LangChain receives the final assistant turn with the search results
already inlined). Same architecture as v1's `WebSearchEnhanceAgent`.

Output is parsed by extracting the LAST `<answer>...</answer>` tag
from the concatenated text content. On any failure (SDK error, no
text content, no answer tag, empty answer) the agent returns
`current_value` unchanged — the finalizer treats this as a no-op so
the pipeline never breaks.

Cost attribution kind: `web_enhance_v2` (separate bucket from v1's
`web_search_enhance` for cost dashboard isolation).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_anthropic import ChatAnthropic

from src.core.common.constants import CLAUDE_MODEL_ADVANCED
from src.core.common.cost_tracking import (
    CostTrackingCallback,
    build_cost_context_for_agent,
)

from ...observability import langfuse_callback
from .prompt_builder import build_web_enhance_prompt

logger = logging.getLogger(__name__)


_ANSWER_RE = re.compile(r"<answer>(.*?)</answer>", re.DOTALL | re.IGNORECASE)
_MAX_TOKENS = 4000
_MAX_SEARCHES = 3
_TAGS = ["core", "agent", "studio_v2", "web_enhance"]
_COST_KIND = "web_enhance_v2"
_WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": _MAX_SEARCHES,
}


class WebEnhanceAgentV2:
    """Enhance one resolved value via Anthropic's native web search.

    Stateless — `run` builds the chain per-call. Returns the reshaped
    string on success, or the original `current_value` on any failure.
    Best-effort agent: never raises, never breaks the pipeline.
    """

    @classmethod
    async def run(
        cls,
        *,
        variable_name: str,
        current_value: str,
        web_enhance_instruction: str,
        template_property_marker: str | None = None,
        template_paragraph: str | None = None,
        case_details: dict[str, Any] | None = None,
        output_expectation: str | None = None,
    ) -> str:
        """Return the enhanced string, or `current_value` on any failure.

        Args:
            variable_name: Template variable being enhanced. Surfaces
                in LangSmith / Langfuse trace names.
            current_value: The pipeline's resolved value — the anchor
                the web search starts from. If empty, the agent
                short-circuits and returns it unchanged.
            web_enhance_instruction: Author's directive (the wizard's
                Fine-tune textarea content). Required.
            template_property_marker: Sample shape from the source
                .docx for the placeholder. Optional shape guidance.
            template_paragraph: Surrounding paragraph in the rendered
                template, for tone/grammar reference. Optional.
            case_details: Map of case metadata (debtor, case number,
                chapter, etc.) the agent can cross-reference.
            output_expectation: Author's general output-shape rule
                from the wizard's Fine-tune step. Optional.
        """
        if not current_value or not current_value.strip():
            return current_value
        if not web_enhance_instruction or not web_enhance_instruction.strip():
            return current_value

        prompt = build_web_enhance_prompt(
            variable_name=variable_name,
            current_value=current_value,
            web_enhance_instruction=web_enhance_instruction,
            template_property_marker=template_property_marker,
            template_paragraph=template_paragraph,
            case_details=case_details,
            output_expectation=output_expectation,
        )
        try:
            llm = ChatAnthropic(
                model=CLAUDE_MODEL_ADVANCED,
                max_tokens=_MAX_TOKENS,
            )
            cost_ctx = build_cost_context_for_agent(
                kind=_COST_KIND,
                agent_name="WebEnhanceAgentV2",
                extra_metadata={"variable_name": variable_name},
            )
            callbacks: list[Any] = [CostTrackingCallback(cost_context=cost_ctx)]
            lf_handler = langfuse_callback()
            if lf_handler is not None:
                callbacks.append(lf_handler)
            chain = llm.bind_tools([_WEB_SEARCH_TOOL]).with_config({
                "run_name": f"WebEnhanceAgentV2:{variable_name}",
                "tags": _TAGS,
                "metadata": {"variable_name": variable_name},
                "callbacks": callbacks,
            })
            response = await chain.ainvoke(prompt)
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "WebEnhanceAgentV2: LLM call failed for '%s' (%s); "
                "returning unenhanced value",
                variable_name, err,
            )
            return current_value

        final_text = _extract_final_text(response)
        if not final_text:
            logger.warning(
                "WebEnhanceAgentV2: no text content in response for '%s'; "
                "returning unenhanced value",
                variable_name,
            )
            return current_value

        answer = _parse_answer(final_text)
        if answer is None:
            logger.warning(
                "WebEnhanceAgentV2: no <answer> tag in response for '%s'; "
                "returning unenhanced value. Tail: %r",
                variable_name, final_text[-300:],
            )
            return current_value

        return answer


def _extract_final_text(response: Any) -> str:
    """Concatenate every text part of the AIMessage's content.

    LangChain's `ChatAnthropic` may return content as a plain string
    or a list of content-block dicts (tool use interleaved with
    text — typical for server-side web search). Both shapes are
    handled; non-text blocks are skipped.
    """
    content = getattr(response, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
            continue
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _parse_answer(text: str) -> str | None:
    """Return the inside of the LAST `<answer>...</answer>` match, stripped."""
    matches = list(_ANSWER_RE.finditer(text))
    if not matches:
        return None
    inside = matches[-1].group(1).strip()
    return inside or None
