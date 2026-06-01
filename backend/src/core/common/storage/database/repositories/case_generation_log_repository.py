"""Async CRUD repository for the CaseGenerationLog ORM model — the v2 draft audit trail."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text

from ..models import CaseGenerationLog
from .base import BaseRepository

logger = logging.getLogger(__name__)


class CaseGenerationLogRepository(BaseRepository):
    """Async CRUD over the CaseGenerationLog table — one row per v2 template-draft attempt."""

    @classmethod
    async def create(
        cls,
        *,
        user_id: str,
        case_id: str,
        draft_template_id: str,
        task_id: str | None = None,
        template_name: str | None = None,
        status: str = "PENDING",
    ) -> CaseGenerationLog:
        """Insert a new log row keyed by (user_id, case_id, draft_template_id)."""
        async with cls._session() as session:
            try:
                log = CaseGenerationLog(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    case_id=case_id,
                    draft_template_id=draft_template_id,
                    template_name=template_name,
                    status=status,
                    task_id=task_id,
                )
                session.add(log)
                await session.commit()
                await session.refresh(log)
                logger.info(
                    "Created case_generation_log: id=%s case=%s template=%s status=%s",
                    log.id, case_id, draft_template_id, status,
                )
                return log
            except Exception as e:
                await session.rollback()
                logger.error(
                    "Failed to create case_generation_log (case=%s template=%s): %s",
                    case_id, draft_template_id, e,
                )
                raise

    @classmethod
    async def update_status(
        cls,
        log_id: str,
        *,
        status: str,
        r2_object_key: str | None = None,
        children: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> CaseGenerationLog | None:
        """Update a log row's status (+ optional terminal-state fields). Returns the refreshed row or None."""
        async with cls._session() as session:
            try:
                sets = ["status = :status", "updated_at = now()"]
                params: dict[str, Any] = {"log_id": log_id, "status": status}

                if r2_object_key is not None:
                    sets.append("r2_object_key = :r2_object_key")
                    params["r2_object_key"] = r2_object_key
                if children is not None:
                    sets.append("children = :children")
                    params["children"] = json.dumps(children)
                if error is not None:
                    sets.append("error = :error")
                    params["error"] = error

                set_clause = ", ".join(sets)
                await session.execute(
                    text(f"UPDATE case_generation_logs SET {set_clause} WHERE id = :log_id"),
                    params,
                )
                await session.commit()

                result = await session.execute(
                    text("SELECT * FROM case_generation_logs WHERE id = :log_id"),
                    {"log_id": log_id},
                )
                row = result.fetchone()
                return CaseGenerationLog(**dict(row._mapping)) if row else None
            except Exception as e:
                await session.rollback()
                logger.error("Failed to update case_generation_log %s: %s", log_id, e)
                raise

    @classmethod
    async def get(cls, log_id: str) -> CaseGenerationLog | None:
        """Fetch a single log by id."""
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text("SELECT * FROM case_generation_logs WHERE id = :log_id"),
                    {"log_id": log_id},
                )
                row = result.fetchone()
                return CaseGenerationLog(**dict(row._mapping)) if row else None
            except Exception as e:
                logger.error("Failed to fetch case_generation_log %s: %s", log_id, e)
                raise

    @classmethod
    async def find_latest_completed(
        cls,
        *,
        user_id: str,
        case_id: str,
        draft_template_id: str,
    ) -> CaseGenerationLog | None:
        """Return the most recent COMPLETED log for the (user, case, template) triple."""
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text(
                        "SELECT * FROM case_generation_logs "
                        "WHERE user_id = :user_id "
                        "  AND case_id = :case_id "
                        "  AND draft_template_id = :draft_template_id "
                        "  AND status = 'COMPLETED' "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {
                        "user_id": user_id,
                        "case_id": case_id,
                        "draft_template_id": draft_template_id,
                    },
                )
                row = result.fetchone()
                return CaseGenerationLog(**dict(row._mapping)) if row else None
            except Exception as e:
                logger.error(
                    "Failed to find_latest_completed (user=%s case=%s template=%s): %s",
                    user_id, case_id, draft_template_id, e,
                )
                raise

    @classmethod
    async def list_for_case(
        cls,
        *,
        user_id: str,
        case_id: str,
        limit: int = 50,
    ) -> list[CaseGenerationLog]:
        """Return the N most recent log rows for a (user, case) — used by the history view."""
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text(
                        "SELECT * FROM case_generation_logs "
                        "WHERE user_id = :user_id AND case_id = :case_id "
                        "ORDER BY created_at DESC LIMIT :limit"
                    ),
                    {"user_id": user_id, "case_id": case_id, "limit": limit},
                )
                rows = result.fetchall()
                return [CaseGenerationLog(**dict(r._mapping)) for r in rows]
            except Exception as e:
                logger.error(
                    "Failed to list_for_case (user=%s case=%s): %s",
                    user_id, case_id, e,
                )
                raise

    @classmethod
    async def list_for_case_all_users(
        cls,
        *,
        case_id: str,
        limit: int = 100,
    ) -> "list[CaseGenerationLog]":
        """Cross-user drafting history for a case.

        Used by the chat agent's `list_drafted_motions` tool so a
        paralegal in any session can see every draft on the case —
        regardless of which firm user kicked it off — and avoid
        double-drafting. Sorted most-recent-first.

        The user-scoped history view continues to use `list_for_case`;
        we deliberately keep these as two separate methods so a future
        access-control tweak to either path doesn't accidentally widen
        or narrow the other.
        """
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text(
                        "SELECT * FROM case_generation_logs "
                        "WHERE case_id = :case_id "
                        "ORDER BY created_at DESC LIMIT :limit"
                    ),
                    {"case_id": case_id, "limit": limit},
                )
                rows = result.fetchall()
                return [CaseGenerationLog(**dict(r._mapping)) for r in rows]
            except Exception as e:
                logger.error(
                    "Failed to list_for_case_all_users (case=%s): %s",
                    case_id, e,
                )
                raise
