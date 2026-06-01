"""Fire-and-forget audit log for the v2 ECF ingest cron.

Mirrors `LlmCostLogRepository.record` discipline: `record(...)` swallows
ANY exception so observability code can never break the ingest itself.
One row per attempted PACER doc link, written from `run_ingest_cycle`
right after the outcome is decided.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from ..models import CaseIngestionLog
from .base import BaseRepository

logger = logging.getLogger(__name__)

# Canonical outcome vocabulary — kept here so the ingest code, the tests,
# and any future admin UI all reference the same set.
ALL_OUTCOMES = (
    "inserted",
    "gmail_dedup_skip",
    "fingerprint_dedup_skip",
    "dead_link",
    "r2_upload_failed",
    "db_insert_failed",
    "parse_error",
)


class CaseIngestionLogRepository(BaseRepository):
    """Async writes + simple queries for `case_ingestion_logs`."""

    @classmethod
    async def record(
        cls,
        *,
        firm_id: Optional[str],
        outcome: str,
        cycle_id: Optional[str] = None,
        gmail_message_id: Optional[str] = None,
        case_number: Optional[str] = None,
        case_name: Optional[str] = None,
        court_district: Optional[str] = None,
        case_inbox_id: Optional[str] = None,
        error_message: Optional[str] = None,
        pdf_size_bytes: Optional[int] = None,
        elapsed_ms: Optional[int] = None,
    ) -> None:
        """Append one audit row. NEVER raises — wraps every failure in a
        WARNING log so the calling cron loop keeps running."""
        try:
            async with cls._session() as session:
                row = CaseIngestionLog(
                    id=str(uuid.uuid4()),
                    firm_id=firm_id,
                    cycle_id=cycle_id,
                    gmail_message_id=gmail_message_id,
                    case_number=case_number,
                    case_name=case_name,
                    court_district=court_district,
                    outcome=outcome,
                    case_inbox_id=case_inbox_id,
                    error_message=(error_message[:4000] if error_message else None),
                    pdf_size_bytes=pdf_size_bytes,
                    elapsed_ms=elapsed_ms,
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.warning(
                "CaseIngestionLogRepository.record failed (outcome=%s case=%s): %s",
                outcome, case_number, e,
            )

    @classmethod
    async def list_recent(
        cls,
        *,
        firm_id: str,
        outcome: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CaseIngestionLog]:
        """firm-scoped, ordered by created_at DESC. Optional outcome filter."""
        async with cls._session() as session:
            stmt = (
                select(CaseIngestionLog)
                .where(CaseIngestionLog.firm_id == firm_id)
            )
            if outcome:
                stmt = stmt.where(CaseIngestionLog.outcome == outcome)
            stmt = (
                stmt.order_by(CaseIngestionLog.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @classmethod
    async def cycle_summary(
        cls,
        *,
        firm_id: str,
        since: datetime,
        until: datetime,
    ) -> dict:
        """Outcome counts grouped over a time window.

        Returns a dict with every value in ALL_OUTCOMES, defaulting to 0
        for outcomes that didn't appear in the window.
        """
        async with cls._session() as session:
            from sqlalchemy import func, and_
            stmt = (
                select(CaseIngestionLog.outcome, func.count())
                .where(
                    and_(
                        CaseIngestionLog.firm_id == firm_id,
                        CaseIngestionLog.created_at >= since,
                        CaseIngestionLog.created_at < until,
                    )
                )
                .group_by(CaseIngestionLog.outcome)
            )
            result = await session.execute(stmt)
            counts = {outcome: 0 for outcome in ALL_OUTCOMES}
            for row in result.all():
                outcome, n = row[0], row[1]
                if outcome in counts:
                    counts[outcome] = int(n or 0)
            return counts
