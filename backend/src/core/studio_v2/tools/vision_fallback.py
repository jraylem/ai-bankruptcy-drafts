"""Vision-fallback tool — Claude-vision call over the case petition
PDF (and, in future iterations, over Gmail image attachments / scanned
PDFs surfaced by the Gmail / case_vector tools).

This tool replaces v1's `CaseVectorVisionResolver` post-processing
pass. v1's model: every dry-run made a SECOND batched vision call
over low-confidence case_vector fields, regardless of whether the
agent had concluded text-only extraction was insufficient. v2's model:
the extractor agent decides AUTONOMOUSLY when to escalate to vision —
either because OCR text on a scanned PDF is gibberish, an attachment
is image-only, or text-extraction returned empty / low-confidence on
a form-layout field (checkboxes, tabular data, signatures).

Per the plan's invariant #2 from Phase 2: there is NO separate
post-processing vision pass in v2; agents reach for vision through
this tool the same way they reach for case_vector_query or
gmail_search.

Reuses v1's `fetch_petition_pdf_bytes` helper via read-only import.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from ..observability import langfuse_callback

logger = logging.getLogger(__name__)


def build_vision_fallback_tool(ctx) -> Any | None:
    """Construct a LangChain-compatible vision-fallback tool bound
    to the case's petition PDF URL.

    Returns `None` when:
    - `ctx.case.petition_pdf_url` is missing (unfiled case, no petition)
    - LangChain Anthropic / fetch helper imports fail
    """
    petition_pdf_url = getattr(ctx.case, "petition_pdf_url", None)
    case_number = getattr(ctx.case, "case_number", None) or "<unknown>"
    case_name = getattr(ctx.case, "case_name", None) or "<unknown>"

    if not petition_pdf_url:
        logger.debug(
            "build_vision_fallback_tool: case %s has no petition_pdf_url; tool unavailable",
            getattr(ctx.case, "id", "<unknown>"),
        )
        return None

    try:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import HumanMessage
        from langchain_core.tools import tool

        from src.core.agents.utils.petition_pdf import fetch_petition_pdf_bytes
        from src.core.common.constants import CLAUDE_MODEL_VISION
        from src.core.common.cost_tracking import (
            CostTrackingCallback,
            build_cost_context_for_agent,
        )
    except ImportError as err:
        logger.warning(
            "build_vision_fallback_tool: dependencies not importable (%s); tool unavailable",
            err,
        )
        return None

    def _extract_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    chunks.append(str(block.get("text", "")))
                elif isinstance(block, str):
                    chunks.append(block)
            return "".join(chunks)
        return str(content)

    @tool
    async def vision_fallback(question: str) -> dict:
        """Read the petition PDF visually and answer a SPECIFIC question.

        Use when text extraction (case_vector_query / gmail_search)
        returned weak or empty results AND the answer requires visual
        layout reasoning — checkboxes, signatures, tabular cells,
        form-field content that pgvector chunks miss.

        Slow + token-expensive; do NOT use as the first lookup. Be
        precise about the question — vague prompts produce vague
        answers (e.g. "Is the box for chapter 7 checked on page 1?"
        works; "tell me about the petition" doesn't).

        Args:
            question: The specific question to answer by reading the
                petition PDF.

        Returns:
            ``{"question": str, "answer": str | None, "error": str | None}``.
            Returns an `error` field rather than raising so the agent
            can decide whether to retry or stop.
        """
        try:
            pdf_bytes = await fetch_petition_pdf_bytes(petition_pdf_url)
        except Exception as err:  # noqa: BLE001
            logger.warning("vision_fallback: PDF fetch failed (%s)", err)
            return {"question": question, "answer": None, "error": str(err)}

        if pdf_bytes is None:
            return {
                "question": question,
                "answer": None,
                "error": "Could not download petition PDF (logged warning).",
            }

        b64 = base64.b64encode(pdf_bytes).decode("ascii")
        content_blocks: list[dict] = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64,
                },
            },
            {
                "type": "text",
                "text": (
                    f"You are reading the bankruptcy petition for case "
                    f"{case_number} ({case_name}). "
                    f"Answer this specific question using ONLY what you can "
                    f"see in the document:\n\n{question}\n\n"
                    f"If the document does not contain the answer, say so "
                    f"explicitly. Be concise."
                ),
            },
        ]
        try:
            cost_ctx = build_cost_context_for_agent(
                kind="agent", agent_name="VisionFallbackToolV2",
            )
            callbacks: list = [CostTrackingCallback(cost_context=cost_ctx)]
            lf_handler = langfuse_callback()
            if lf_handler is not None:
                callbacks.append(lf_handler)
            llm = ChatAnthropic(
                model=CLAUDE_MODEL_VISION,
                max_tokens=2000,
                temperature=0,
            ).with_config({
                "run_name": f"VisionFallbackToolV2:{case_number}",
                "metadata": {
                    "case_number": case_number,
                    "case_name": case_name,
                    "question": question,
                },
                "callbacks": callbacks,
            })
            response = await llm.ainvoke([HumanMessage(content=content_blocks)])
            return {"question": question, "answer": _extract_text(response.content)}
        except Exception as err:  # noqa: BLE001
            logger.warning("vision_fallback: Claude vision call failed (%s)", err)
            return {"question": question, "answer": None, "error": str(err)}

    return vision_fallback
