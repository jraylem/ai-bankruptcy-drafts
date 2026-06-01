"""Web-search enhancement agent for case_vector fields.

Runs a single Claude call with the native server-side
`web_search_20250305` tool enabled. Given a `current_value` extracted
from the petition (the anchor), Claude searches the open web for the
small piece of stable context that the petition does NOT carry, then
reshapes the result to match `template_property_marker` and the
surrounding docx paragraph.

Architectural note: this agent does NOT extend the LangChain `Agent`
base class. The base auto-binds `with_structured_output(...)`, which
doesn't compose with native server-side tools. Instead we go through
`ChatAnthropic.bind_tools(...)` directly — that path DOES support
`web_search_20250305` (the tool runs server-side at Anthropic, the
multi-turn dance is internal to the SDK, and LangChain receives the
final assistant turn with the search results already inlined).

Output is parsed by extracting the LAST `<answer>...</answer>` tag
from the concatenated text content. On any failure (SDK error, no
text content, no answer tag) the agent returns `current_value`
unchanged — the resolver treats this as a no-op so the pipeline
never breaks.

LangSmith visibility: `with_config({"run_name": "WebSearchEnhanceAgent",
"tags": [...]})` makes the round-trip appear as its own span,
matching the pattern every other LangChain-stacked agent uses.
"""

import logging
import re
from typing import Any

from langchain_anthropic import ChatAnthropic

from src.core.common.constants import CLAUDE_MODEL_ADVANCED
from src.core.common.cost_tracking import (
    CostTrackingCallback,
    build_cost_context_for_agent,
)

from .prompt_builder import build_web_search_enhance_prompt

logger = logging.getLogger(__name__)


_ANSWER_RE = re.compile(r"<answer>(.*?)</answer>", re.DOTALL | re.IGNORECASE)
_MAX_TOKENS = 4000
_MAX_SEARCHES = 3
_TAGS = ["core", "agent", "web_search_enhance"]
_WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": _MAX_SEARCHES,
}


class WebSearchEnhanceAgent:
    """Enhance one case_vector resolved value via Anthropic's native web search.

    Stateless — `run` builds the chain per-call. Returns the reshaped
    string on success, or the original `current_value` on any failure
    (best-effort agent — never breaks the pipeline).
    """

    @classmethod
    async def run(
        cls,
        variable_name: str,
        current_value: str,
        template_property_marker: str,
        template_paragraph: str | None,
        case_details: dict[str, Any] | None,
        web_search_instruction: str | None = None,
        output_instruction: str | None = None,
    ) -> str:
        """Return the enhanced string, or `current_value` if enhancement failed.

        `web_search_instruction` (from `CaseVectorSourceParams`) and
        `output_instruction` (from `TemplateField`) are author-supplied
        per-field directives — surfaced as authoritative blocks in the
        prompt so they override default marker-shape inference. Each is
        optional; when None or whitespace-only, no block is rendered.
        """
        prompt = build_web_search_enhance_prompt(
            variable_name=variable_name,
            current_value=current_value,
            template_property_marker=template_property_marker,
            template_paragraph=template_paragraph,
            case_details=case_details,
            web_search_instruction=web_search_instruction,
            output_instruction=output_instruction,
        )
        try:
            llm = ChatAnthropic(
                model=CLAUDE_MODEL_ADVANCED,
                max_tokens=_MAX_TOKENS,
            )
            cost_ctx = build_cost_context_for_agent(
                kind="web_search_enhance",
                agent_name="WebSearchEnhanceAgent",
                extra_metadata={"variable_name": variable_name},
            )
            chain = llm.bind_tools([_WEB_SEARCH_TOOL]).with_config({
                "run_name": "WebSearchEnhanceAgent",
                "tags": _TAGS,
                "metadata": {"variable_name": variable_name},
                "callbacks": [CostTrackingCallback(cost_context=cost_ctx)],
            })
            response = await chain.ainvoke(prompt)
        except Exception as e:
            logger.warning(
                "WebSearchEnhanceAgent: LLM call failed for variable '%s' — "
                "returning original current_value. Error: %s",
                variable_name, e,
            )
            return current_value

        final_text = _extract_final_text(response)
        if not final_text:
            logger.warning(
                "WebSearchEnhanceAgent: no text content in response for variable "
                "'%s' — returning original current_value.",
                variable_name,
            )
            return current_value

        answer = _parse_answer(final_text)
        if answer is None:
            logger.warning(
                "WebSearchEnhanceAgent: no <answer> tag found in response for "
                "variable '%s' — returning original current_value. Final text: %r",
                variable_name, final_text[:500],
            )
            return current_value

        return answer


def _extract_final_text(response: Any) -> str:
    """Concatenate every text part of the AIMessage's content.

    LangChain's `ChatAnthropic` may return content as either:
      - a plain string (no tool use, no interleaved blocks), or
      - a list of content-block dicts (tool use is interleaved with
        text — typical for server-side web search).
    Both shapes are handled; non-text blocks (server_tool_use,
    web_search_tool_result) are skipped.
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
        # Defensive: also support the raw-SDK object shape (block.type / block.text)
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _parse_answer(text: str) -> str | None:
    """Return the inside of the LAST <answer>...</answer> match, stripped."""
    matches = list(_ANSWER_RE.finditer(text))
    if not matches:
        return None
    inside = matches[-1].group(1).strip()
    return inside or None
