"""`case_vector_search` chat tool — pgvector retrieval over the case's file corpus.

Wraps `ToolBox.query_case_specific` against the case's `case_file_collection`.
First line of defense when the user asks about facts in the petition,
schedules, or supporting docs.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from src.core.common.toolbox import ToolBox

from .base import BaseChatTool, ToolContext
from .registry import register_tool

logger = logging.getLogger(__name__)


class CaseVectorSearchInput(BaseModel):
    """Args the model passes to `case_vector_search`."""
    query: str = Field(description="Natural-language question or keyword search over the case's file corpus.")
    k: int = Field(default=5, ge=1, le=20, description="How many top results to return.")


@register_tool
class CaseVectorSearchTool(BaseChatTool):
    """Similarity search over the case's pgvector file collection."""

    name: ClassVar[str] = "case_vector_search"
    description: ClassVar[str] = (
        "Search the case's bankruptcy filings, schedules, and supporting "
        "documents by semantic similarity. Use this FIRST for any question "
        "about facts in the case file (creditors, debts, income, property, "
        "exemptions, plan terms, etc.). Returns the top chunks with relevance "
        "scores. If the results look weak (low scores, off-topic, or empty) "
        "and the question is about visual layout (checkboxes, signatures, "
        "tables, form fields), fall back to `petition_vision_lookup`."
    )
    input_schema: ClassVar[type[BaseModel]] = CaseVectorSearchInput

    @classmethod
    async def invoke(cls, ctx: ToolContext, **kwargs: Any) -> dict:
        args = CaseVectorSearchInput(**kwargs)
        try:
            result = await ToolBox.query_case_specific(
                collection_name=ctx.case.case_file_collection,
                query=args.query,
                k=args.k,
            )
            return {
                "query": args.query,
                "total": result.total,
                "results": [
                    {"content": r.content, "relevance_score": r.relevance_score}
                    for r in result.results
                ],
            }
        except Exception as e:
            logger.exception(
                "case_vector_search failed for case %s query=%r: %s",
                ctx.case.id, args.query, e,
            )
            return {"query": args.query, "total": 0, "results": [], "error": str(e)}
