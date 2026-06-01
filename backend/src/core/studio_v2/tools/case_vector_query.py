"""Case-vector-query tool — wraps v1's pgvector lookup as a tool the
extractor agent can call autonomously.

Reuses v1's `ToolBox.query_case_specific` via read-only import. Bound
at construction time to `ctx.case.case_file_collection` (the per-case
pgvector collection name), so the agent never sees collection routing.

The agent decides how many chunks to pull (`top_k`, default 5) and
whether to issue follow-up queries with refined phrasing if the
initial result set looks too narrow.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_case_vector_query_tool(ctx) -> Any | None:
    """Construct a LangChain-compatible tool bound to the case's
    pgvector collection.

    Returns `None` when:
    - `ctx.case` has no `case_file_collection` (e.g. unfiled case, no
      petition uploaded yet — pgvector ingestion hasn't run)
    - Import of v1's ToolBox / VectorQueryService raises
    """
    collection_name = getattr(ctx.case, "case_file_collection", None)
    if not collection_name:
        logger.debug(
            "build_case_vector_query_tool: case %s has no case_file_collection; tool unavailable",
            getattr(ctx.case, "id", "<unknown>"),
        )
        return None

    try:
        from langchain_core.tools import tool

        from src.core.common.toolbox import ToolBox
    except ImportError as err:
        logger.warning(
            "build_case_vector_query_tool: dependencies not importable (%s); tool unavailable",
            err,
        )
        return None

    @tool
    async def case_vector_query(query: str, top_k: int = 5) -> dict:
        """Search the case file (petition, schedules, statements, uploaded
        evidence) by semantic similarity. Use when you need to find a
        specific passage about the debtor, a creditor, a vehicle, a date,
        a dollar amount, or any other fact recorded in the bankruptcy
        record.

        Args:
            query: Natural-language search query. Be specific —
                "the debtor's monthly net income from Schedule I" works
                better than "income".
            top_k: How many top-ranked chunks to return (default 5,
                max 20). Increase only when initial results look too
                narrow.

        Returns:
            ``{"results": [{"content": str, "relevance_score": float}, ...],
               "total": int}`` — the same shape v1's draft agent uses.
        """
        capped_k = max(1, min(top_k, 20))
        try:
            result = await ToolBox.query_case_specific(
                collection_name=collection_name,
                query=query,
                k=capped_k,
            )
            return result.model_dump()
        except Exception as err:  # noqa: BLE001 — return error so agent can decide
            logger.warning("case_vector_query: lookup failed (%s)", err)
            return {"results": [], "total": 0, "error": str(err)}

    return case_vector_query
