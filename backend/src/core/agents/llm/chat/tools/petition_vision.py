"""`petition_vision_lookup` chat tool — visual fallback that reads the petition PDF directly.

When `case_vector_search` returns weak or empty hits and the question requires
visual layout (checkbox state, signature presence, tabular data, form-field
content), this tool feeds the petition PDF to a Claude vision model as a
`document` content block alongside the user's specific question.

Mirrors the pattern in `case_vector_vision/agent.py` but is invoked
synchronously per question rather than batched.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, ClassVar

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.core.agents.utils.petition_pdf import fetch_petition_pdf_bytes
from src.core.common.constants import CLAUDE_MODEL_VISION
from src.core.common.cost_tracking import (
    CostTrackingCallback,
    build_cost_context_for_agent,
)

from .base import BaseChatTool, ToolContext
from .registry import register_tool

logger = logging.getLogger(__name__)


class PetitionVisionInput(BaseModel):
    """Args the model passes to `petition_vision_lookup`."""
    question: str = Field(
        description=(
            "The specific question to answer by reading the petition PDF. "
            "Be precise — e.g. 'Is the box for chapter 7 checked on page 1?', "
            "not 'tell me about the petition'."
        ),
    )


@register_tool
class PetitionVisionLookupTool(BaseChatTool):
    """Visual fallback: ask Claude vision to read the petition PDF directly."""

    name: ClassVar[str] = "petition_vision_lookup"
    description: ClassVar[str] = (
        "Read the petition PDF visually and answer a SPECIFIC question. "
        "Use ONLY when `case_vector_search` returned weak or empty results "
        "AND the question requires visual layout reasoning — checkboxes, "
        "signatures, tabular data, or form-field content that text "
        "extraction would miss. Slow and token-expensive; do not use as the "
        "first lookup. Be precise about the question — vague prompts produce "
        "vague answers."
    )
    input_schema: ClassVar[type[BaseModel]] = PetitionVisionInput

    _MAX_TOKENS = 2000

    @classmethod
    async def invoke(cls, ctx: ToolContext, **kwargs: Any) -> dict:
        args = PetitionVisionInput(**kwargs)
        if not ctx.case.petition_pdf_url:
            return {
                "question": args.question,
                "answer": None,
                "error": "Case has no petition_pdf_url on file.",
            }
        try:
            pdf_bytes = await fetch_petition_pdf_bytes(ctx.case.petition_pdf_url)
        except Exception as e:
            logger.exception(
                "petition_vision_lookup PDF fetch failed for case %s: %s",
                ctx.case.id, e,
            )
            return {"question": args.question, "answer": None, "error": str(e)}
        if pdf_bytes is None:
            return {
                "question": args.question,
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
                    f"{ctx.case.case_number} ({ctx.case.case_name}). "
                    f"Answer this specific question using ONLY what you can "
                    f"see in the document:\n\n{args.question}\n\n"
                    f"If the document does not contain the answer, say so "
                    f"explicitly. Be concise."
                ),
            },
        ]
        try:
            cost_ctx = build_cost_context_for_agent(
                kind="chat", agent_name="PetitionVisionLookupTool",
            )
            llm = ChatAnthropic(
                model=CLAUDE_MODEL_VISION,
                max_tokens=cls._MAX_TOKENS,
                temperature=0,
            ).with_config(
                {"callbacks": [CostTrackingCallback(cost_context=cost_ctx)]},
            )
            response = await llm.ainvoke([HumanMessage(content=content_blocks)])
            answer = cls._extract_text(response.content)
            return {"question": args.question, "answer": answer}
        except Exception as e:
            logger.exception(
                "petition_vision_lookup vision call failed for case %s: %s",
                ctx.case.id, e,
            )
            return {"question": args.question, "answer": None, "error": str(e)}

    @staticmethod
    def _extract_text(content: Any) -> str:
        """Pull the assistant's text out of either a plain string or a content-block list."""
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
