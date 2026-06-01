"""
Canonical vector-query service layer.

Sits between `ToolBox` and the raw pgvector wrapper in
`storage/vectorstore.py`:

  ToolBox.query_*  →  VectorQueryService.*  →  search_collection  →  PGVector

All vector-query routing goes through this class — the real
case-specific pgvector lookup for CASE_VECTOR and email fallbacks, plus
the mocked law-practice KB. Callers outside ToolBox should not reach
past ToolBox; callers outside this file should not import
`search_collection` directly.
"""

from pydantic import BaseModel

from src.core.common.storage.vectorstore import search_collection


class VectorResult(BaseModel):
    """One similarity-search hit, in the shape consumed by the draft agent."""
    content: str
    relevance_score: float


class VectorSearchResult(BaseModel):
    """Envelope returned by every VectorQueryService method."""
    results: list[VectorResult]
    total: int


class VectorQueryService:
    """Canonical query interface for vector stores.

    Do NOT import or instantiate this class directly from application
    code. Call `ToolBox.query_law_practice(...)` or
    `ToolBox.query_case_specific(...)` in `src.core.common.toolbox`.
    """

    @staticmethod
    async def query_law_practice(query: str) -> VectorSearchResult:
        """[MOCK] Law-practice knowledge-base lookup.

        Returns a single placeholder VectorResult until a real
        law-practice pgvector collection is wired up. The
        `[MOCK - Law Practice]` prefix on the content makes the mock
        obvious in LangSmith traces and draft-agent prompts.

        TODO: swap to `VectorQueryService.query_case_specific` against a
        real law-practice collection once its name is decided (likely a
        settings constant, e.g. LAW_PRACTICE_COLLECTION).
        """
        return VectorSearchResult(
            results=[
                VectorResult(
                    content=f"[MOCK - Law Practice] placeholder result for query: {query}",
                    relevance_score=0.95,
                ),
            ],
            total=1,
        )

    @staticmethod
    async def query_case_specific(
        collection_name: str,
        query: str,
        k: int = 5,
    ) -> VectorSearchResult:
        """Similarity search against a case-specific pgvector collection.

        Adapts the `VectorMatch` hits from
        `storage.vectorstore.search_collection` to the shared
        `VectorSearchResult` envelope. This is the only live pgvector
        path in the codebase — used by CASE_VECTOR fields and by the
        Gmail / CourtDrive vector-fallback when a live email query
        returns empty.
        """
        matches = await search_collection(collection_name, query, k=k)
        results = [
            VectorResult(content=m.content, relevance_score=m.score)
            for m in matches
        ]
        return VectorSearchResult(results=results, total=len(results))
