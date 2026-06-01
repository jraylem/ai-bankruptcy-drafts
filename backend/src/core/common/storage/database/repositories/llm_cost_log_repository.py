"""Async CRUD + aggregation repository for `llm_cost_logs`.

This repo's `record(...)` is on the LLM-call hot path, so it's wrapped
in a try/except that NEVER raises — a Postgres hiccup must not break a
chat reply or a draft generation.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from ..models import LlmCostLog
from .base import BaseRepository

logger = logging.getLogger(__name__)


class LlmCostLogRepository(BaseRepository):
    """Async writes + aggregate reads for `llm_cost_logs`."""

    @classmethod
    async def record(
        cls,
        *,
        kind: str,
        firm_id: str | None,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        cost_usd: Decimal,
        run_id: str | None = None,
        semantic_id: str | None = None,
        semantic_id_kind: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Insert one cost row. Swallows ANY exception — the LLM call
        that triggered this MUST proceed regardless of logging outcome.

        `semantic_id` and `semantic_id_kind` should be set together. If
        only one is set, the row still writes but a WARNING is emitted
        so wiring bugs are caught before any aggregation queries break.
        """
        if (semantic_id is None) != (semantic_id_kind is None):
            logger.warning(
                "LlmCostLogRepository.record: semantic_id and semantic_id_kind "
                "must be set together (got semantic_id=%r, semantic_id_kind=%r, kind=%s)",
                semantic_id, semantic_id_kind, kind,
            )
        try:
            async with cls._session() as session:
                log = LlmCostLog(
                    id=str(uuid.uuid4()),
                    firm_id=firm_id,
                    kind=kind,
                    model=model,
                    input_tokens=int(input_tokens or 0),
                    output_tokens=int(output_tokens or 0),
                    cache_read_tokens=int(cache_read_tokens or 0),
                    cache_write_tokens=int(cache_write_tokens or 0),
                    cost_usd=cost_usd,
                    run_id=run_id,
                    semantic_id=semantic_id,
                    semantic_id_kind=semantic_id_kind,
                    log_metadata=metadata or None,
                )
                session.add(log)
                await session.commit()
        except Exception as e:
            logger.warning(
                "LlmCostLogRepository.record failed (kind=%s model=%s): %s",
                kind, model, e,
            )

    @classmethod
    async def aggregate_total(
        cls,
        *,
        firm_id: str | None,
        since: datetime,
        until: datetime,
    ) -> dict:
        """Single-row sum across all kinds for the time range."""
        async with cls._session() as session:
            try:
                clause, params = _firm_clause(firm_id)
                params.update({"since": since, "until": until})
                result = await session.execute(
                    text(
                        "SELECT "
                        "  COALESCE(SUM(cost_usd), 0) AS cost_usd, "
                        "  COALESCE(SUM(input_tokens), 0) AS input_tokens, "
                        "  COALESCE(SUM(output_tokens), 0) AS output_tokens, "
                        "  COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens, "
                        "  COALESCE(SUM(cache_write_tokens), 0) AS cache_write_tokens "
                        "FROM llm_cost_logs "
                        f"WHERE created_at >= :since AND created_at < :until {clause}"
                    ),
                    params,
                )
                row = result.fetchone()
                if row is None:
                    return {"cost_usd": Decimal("0"), "input_tokens": 0, "output_tokens": 0,
                            "cache_read_tokens": 0, "cache_write_tokens": 0}
                m = row._mapping
                return {
                    "cost_usd": Decimal(str(m["cost_usd"] or 0)),
                    "input_tokens": int(m["input_tokens"] or 0),
                    "output_tokens": int(m["output_tokens"] or 0),
                    "cache_read_tokens": int(m["cache_read_tokens"] or 0),
                    "cache_write_tokens": int(m["cache_write_tokens"] or 0),
                }
            except Exception as e:
                logger.error("aggregate_total failed: %s", e)
                raise

    @classmethod
    async def aggregate_by_kind(
        cls,
        *,
        firm_id: str | None,
        since: datetime,
        until: datetime,
    ) -> "list[dict]":
        """Cost + token totals grouped by `kind`, ordered cost-desc."""
        async with cls._session() as session:
            try:
                clause, params = _firm_clause(firm_id)
                params.update({"since": since, "until": until})
                result = await session.execute(
                    text(
                        "SELECT "
                        "  kind, "
                        "  COALESCE(SUM(cost_usd), 0) AS cost_usd, "
                        "  COALESCE(SUM(input_tokens), 0) AS input_tokens, "
                        "  COALESCE(SUM(output_tokens), 0) AS output_tokens "
                        "FROM llm_cost_logs "
                        f"WHERE created_at >= :since AND created_at < :until {clause} "
                        "GROUP BY kind "
                        "ORDER BY SUM(cost_usd) DESC"
                    ),
                    params,
                )
                out: list[dict] = []
                for row in result.fetchall():
                    m = row._mapping
                    out.append({
                        "kind": str(m["kind"]),
                        "cost_usd": Decimal(str(m["cost_usd"] or 0)),
                        "input_tokens": int(m["input_tokens"] or 0),
                        "output_tokens": int(m["output_tokens"] or 0),
                    })
                return out
            except Exception as e:
                logger.error("aggregate_by_kind failed: %s", e)
                raise

    @classmethod
    async def workflow_aggregates(
        cls,
        *,
        firm_id: str | None,
        since: datetime,
        until: datetime,
    ) -> dict:
        """Per-workflow rollups with multiple breakdown units per workflow.

        The new `semantic_id_kind` column (typed scope discriminator) replaces
        the prior JSONB session_id extraction. Aggregations are now indexed
        b-tree lookups on (firm_id, semantic_id_kind, semantic_id).

        Returns:
            {
              'chat': {
                'total_cost_usd': Decimal,   # SUM over semantic_id_kind='case_session'
                                             # FULL-LOADED: includes the main chat
                                             # Sonnet call (kind='chat') AND every
                                             # sub-agent triggered DURING chat
                                             # (case_vector_vision, petition_vision,
                                             # user_input_heal, etc.) that runs
                                             # inside the case_session scope. One
                                             # card = one workflow's true cost; the
                                             # per-agent breakdown lives on the
                                             # "Cost by activity" rail.
                'sessions': int,             # DISTINCT semantic_id
                'messages': int,             # COUNT(*) WHERE kind='chat'
                                             # (one main Sonnet call per user turn)
                'cases': int,                # DISTINCT case_id from log_metadata
              },
              'pleadings': {
                'total_cost_usd': Decimal,   # SUM over semantic_id_kind='pleading_run'
                                             # FULL-LOADED: includes every agent
                                             # (DraftAgent + AutoDerive + Dropdown +
                                             # RecoChips + vision + ...) that fired
                                             # inside the pleading scope
                'runs': int,                 # DISTINCT semantic_id (= task_id)
                'cases': int,                # DISTINCT case_id from log_metadata
              },
              'case_ingest': {
                'total_cost_usd': Decimal,   # SUM over kind IN ('case_ingest','embeddings')
                                             # CaseIngestionAgent + post-create
                                             # embeddings (semantic_id_kind='case')
                'cases': int,                # COUNT(*) WHERE kind='case_ingest'
              },
            }

        Note: case_ingest rows from the CaseIngestionAgent itself (LLM extracts
        the case_number) have semantic_id=NULL because case_id isn't known yet
        at that call site. The post-create indexer rows (kind='embeddings')
        have semantic_id_kind='case' from the nested scope in
        cases/service.py. SUM uses kind-based filtering to capture both.
        """
        async with cls._session() as session:
            try:
                clause, params = _firm_clause(firm_id)
                params.update({"since": since, "until": until})
                result = await session.execute(
                    text(
                        "SELECT "
                        # Chat — scope-based (semantic_id_kind='case_session').
                        # FULL-LOADED: sums every row that fired inside a chat
                        # session, NOT just kind='chat'. A user turn's true cost
                        # includes the main Sonnet call AND any sub-agent the
                        # agent invokes via tool calls (case_vector_vision,
                        # petition_vision_lookup, user_input_heal, etc.). The
                        # per-agent split lives on the "Cost by activity" rail
                        # in the UI; this card is the workflow's headline number.
                        "  COALESCE(SUM(cost_usd) FILTER (WHERE semantic_id_kind = 'case_session'), 0) AS chat_cost, "
                        "  COUNT(DISTINCT semantic_id) FILTER (WHERE semantic_id_kind = 'case_session') AS chat_sessions, "
                        "  COUNT(*) FILTER (WHERE kind = 'chat' AND semantic_id_kind = 'case_session') AS chat_messages, "
                        "  COUNT(DISTINCT log_metadata->>'case_id') FILTER (WHERE semantic_id_kind = 'case_session') AS chat_cases, "
                        # Pleadings — scope-based (semantic_id_kind='pleading_run')
                        # FULL-LOADED: every nested agent shares the scope, so SUM
                        # captures DraftAgent + AutoDerive + Dropdown + RecoChips + ...
                        "  COALESCE(SUM(cost_usd) FILTER (WHERE semantic_id_kind = 'pleading_run'), 0) AS pleadings_cost, "
                        "  COUNT(DISTINCT semantic_id) FILTER (WHERE semantic_id_kind = 'pleading_run') AS pleadings_runs, "
                        "  COUNT(DISTINCT log_metadata->>'case_id') FILTER (WHERE semantic_id_kind = 'pleading_run') AS pleadings_cases, "
                        # Case ingestion — kind-based because CaseIngestionAgent
                        # fires before case_id is known (semantic_id=NULL for that
                        # row); post-create indexers have semantic_id_kind='case'.
                        "  COALESCE(SUM(cost_usd) FILTER (WHERE kind IN ('case_ingest', 'embeddings')), 0) AS case_ingest_cost, "
                        "  COUNT(*) FILTER (WHERE kind = 'case_ingest') AS case_ingest_cases "
                        "FROM llm_cost_logs "
                        f"WHERE created_at >= :since AND created_at < :until {clause}"
                    ),
                    params,
                )
                row = result.fetchone()
                m = row._mapping if row else {}
                return {
                    "chat": {
                        "total_cost_usd": Decimal(str(m.get("chat_cost", 0) or 0)),
                        "sessions": int(m.get("chat_sessions", 0) or 0),
                        "messages": int(m.get("chat_messages", 0) or 0),
                        "cases": int(m.get("chat_cases", 0) or 0),
                    },
                    "pleadings": {
                        "total_cost_usd": Decimal(str(m.get("pleadings_cost", 0) or 0)),
                        "runs": int(m.get("pleadings_runs", 0) or 0),
                        "cases": int(m.get("pleadings_cases", 0) or 0),
                    },
                    "case_ingest": {
                        "total_cost_usd": Decimal(str(m.get("case_ingest_cost", 0) or 0)),
                        "cases": int(m.get("case_ingest_cases", 0) or 0),
                    },
                }
            except Exception as e:
                logger.error("workflow_aggregates failed: %s", e)
                raise

    @classmethod
    async def daily_series(
        cls,
        *,
        firm_id: str | None,
        since: datetime,
        until: datetime,
    ) -> "list[dict]":
        """Per-day cost sums for the sparkline."""
        async with cls._session() as session:
            try:
                clause, params = _firm_clause(firm_id)
                params.update({"since": since, "until": until})
                result = await session.execute(
                    text(
                        "SELECT "
                        "  date_trunc('day', created_at) AS day, "
                        "  COALESCE(SUM(cost_usd), 0) AS cost_usd "
                        "FROM llm_cost_logs "
                        f"WHERE created_at >= :since AND created_at < :until {clause} "
                        "GROUP BY date_trunc('day', created_at) "
                        "ORDER BY day ASC"
                    ),
                    params,
                )
                out: list[dict] = []
                for row in result.fetchall():
                    m = row._mapping
                    out.append({
                        "day": m["day"],
                        "cost_usd": Decimal(str(m["cost_usd"] or 0)),
                    })
                return out
            except Exception as e:
                logger.error("daily_series failed: %s", e)
                raise


def _firm_clause(firm_id: str | None) -> tuple[str, dict[str, Any]]:
    """Return ('AND firm_id = :firm_id', {firm_id: ...}) or empty when null.

    Distinguishes 'firm-scoped' (non-null) from 'system-wide' (null).
    The router always passes a real firm_id; this helper just keeps the
    SQL safe if a system-level caller ever asks for everything.
    """
    if firm_id:
        return "AND firm_id = :firm_id", {"firm_id": firm_id}
    return "", {}


# JSON helper for tests / debug — convert a Decimal-laden row dict to JSON.
def row_to_json(row: dict) -> str:
    return json.dumps({k: str(v) if isinstance(v, Decimal) else v for k, v in row.items()})
