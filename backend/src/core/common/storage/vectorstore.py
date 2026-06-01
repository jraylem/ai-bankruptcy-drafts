"""
Core-owned wrapper around langchain_postgres.PGVector.

Runs in parallel to the legacy src/chatbot/vectorestore.py:
both point at the same Postgres database via settings.VECTORSTORE_URL and write
into the same langchain_pg_collection / langchain_pg_embedding tables, so
collections created here are fully interchangeable with collections created by
chatbot. The difference: this module owns its own SQLAlchemy engine so every
layer core touches (URL -> engine -> pool -> PGVector -> API) lives in
src/core/.
"""

import asyncio
import logging
from typing import Any

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel
from sqlalchemy import create_engine

from src.ai_models import MODEL_EMBEDDINGS
from src.config import settings
from src.core.common.cost_tracking import (
    compute_cost_usd,
    get_current_attribution,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50

vector_engine = create_engine(
    settings.VECTORSTORE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
)

embeddings = OpenAIEmbeddings(
    model=MODEL_EMBEDDINGS,
    api_key=settings.OPENAI_API_KEY,
)

_collection_cache: dict[str, PGVector] = {}


class VectorMatch(BaseModel):
    """A single similarity-search hit returned by search_collection."""
    content: str
    metadata: dict[str, Any]
    score: float


def get_vectorstore(collection_name: str) -> PGVector:
    """Get or initialize a PGVector instance for the given collection name.

    Calling PGVector(...) with a new collection_name auto-creates the matching
    row in langchain_pg_collection if it does not already exist.
    """
    cached = _collection_cache.get(collection_name)
    if cached is not None:
        return cached

    vs = PGVector(
        connection=vector_engine,
        embeddings=embeddings,
        collection_name=collection_name,
    )
    _collection_cache[collection_name] = vs
    logger.info(f"Vectorstore initialized for collection: {collection_name}")
    return vs


async def index_documents(
    collection_name: str,
    documents: list[Document],
    chunk_size: int | None = 500,
    chunk_overlap: int = 50,
) -> int:
    """Embed and store documents in the given pgvector collection.

    Modes:
      - chunk_size is an int: each input Document is split with
        RecursiveCharacterTextSplitter(chunk_size, chunk_overlap) before
        embedding. Metadata from the source Document propagates onto every
        chunk. Use for PDFs / long text where per-chunk retrieval is desired.
      - chunk_size is None: each input Document becomes exactly one row in
        langchain_pg_embedding (one doc -> one embedding -> one row).
        Use for atomic items like emails where a match should return the
        whole item, not a sub-chunk.

    Writes are batched in groups of BATCH_SIZE to stay under embedding
    provider token limits.

    Returns the number of rows written.
    """
    if not documents:
        return 0

    if chunk_size is None:
        rows_to_store = documents
    else:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        rows_to_store = splitter.split_documents(documents)

    if not rows_to_store:
        return 0

    vs = get_vectorstore(collection_name)

    def _add_batch(batch: list[Document]) -> None:
        vs.add_documents(batch)

    stored = 0
    for i in range(0, len(rows_to_store), _BATCH_SIZE):
        batch = rows_to_store[i : i + _BATCH_SIZE]
        await asyncio.to_thread(_add_batch, batch)
        stored += len(batch)
        # Cost tracking: OpenAIEmbeddings via LangChain doesn't return
        # token usage, so estimate locally with tiktoken (best-effort —
        # silently skipped if tiktoken / pricing not available).
        await _record_embedding_cost_safe(
            collection_name=collection_name,
            batch=batch,
        )

    logger.info(
        f"Indexed {stored} rows into collection '{collection_name}' "
        f"(source_documents={len(documents)}, chunk_size={chunk_size})"
    )
    return stored


async def _record_embedding_cost_safe(
    *,
    collection_name: str,
    batch: list[Document],
) -> None:
    """Write one llm_cost_logs row per embedding batch. Always
    exception-safe — cost telemetry must not break indexing."""
    try:
        # Lazy imports to avoid module-load-time cycles (vectorstore is
        # imported very early by services).
        import tiktoken

        from src.core.common.storage.database import LlmCostLogRepository

        try:
            enc = tiktoken.encoding_for_model(MODEL_EMBEDDINGS)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        input_tokens = sum(len(enc.encode(d.page_content or "")) for d in batch)
        if input_tokens <= 0:
            return
        cost = compute_cost_usd(model=MODEL_EMBEDDINGS, input_tokens=input_tokens)
        attribution = get_current_attribution()
        metadata: dict = {
            "collection": collection_name,
            "chunks": len(batch),
        }
        if attribution.case_id:
            metadata["case_id"] = attribution.case_id
        if attribution.user_id:
            metadata["user_id"] = attribution.user_id
        if attribution.session_id:
            metadata["session_id"] = attribution.session_id
        await LlmCostLogRepository.record(
            kind="embeddings",
            firm_id=attribution.firm_id,
            model=MODEL_EMBEDDINGS,
            input_tokens=input_tokens,
            cost_usd=cost,
            metadata=metadata,
        )
    except Exception as e:
        logger.warning("embedding cost tracking failed (non-fatal): %s", e)


async def search_collection(
    collection_name: str,
    query: str,
    k: int = 5,
) -> list[VectorMatch]:
    """Similarity search against a pgvector collection.

    Returns up to k VectorMatch objects ranked by relevance (lower score = more
    similar for PGVector's default L2 / cosine behavior — we invert to "higher
    is better" in the returned score for consumer clarity).
    """
    vs = get_vectorstore(collection_name)

    def _search() -> list[tuple[Document, float]]:
        return vs.similarity_search_with_score(query, k=k)

    raw_hits = await asyncio.to_thread(_search)

    matches: list[VectorMatch] = []
    for doc, distance in raw_hits:
        score = 1.0 - float(distance) if distance is not None else 0.0
        matches.append(
            VectorMatch(
                content=doc.page_content,
                metadata=doc.metadata or {},
                score=score,
            )
        )
    return matches


async def clear_collection(collection_name: str) -> None:
    """Delete every row in the given collection (used by force re-ingest flows)."""
    vs = get_vectorstore(collection_name)

    def _delete() -> None:
        vs.delete_collection()

    await asyncio.to_thread(_delete)
    _collection_cache.pop(collection_name, None)
    logger.info(f"Cleared collection: {collection_name}")
