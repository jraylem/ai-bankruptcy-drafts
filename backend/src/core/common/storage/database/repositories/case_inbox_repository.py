"""CRUD + state-machine transitions for the v2 ECF inbox.

State machine:
    ingesting → ready  → accepted (Case row created)
                       → archived (dismissed OR 48h cron timeout)
    ingesting → failed_ingest (R2 upload exhausted retries)

Every transition is a single atomic UPDATE with the source state in the
WHERE clause. Concurrent attempts (two paralegals click Accept) get
rowcount=0 → caller raises 409.

R2 key (`petition_r2_key`) is STABLE for the row's lifetime. Lifecycle
is encoded in `status`, not in the R2 path.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func

from ..models import CaseInbox
from .base import BaseRepository

logger = logging.getLogger(__name__)


class CaseInboxRepository(BaseRepository):
    """Async repository for `case_inbox`."""

    # ─── reads ────────────────────────────────────────────────────────

    @classmethod
    async def list_ready(cls, *, firm_id: str) -> list[CaseInbox]:
        """Main `/inbox` list. firm-scoped, status='ready', ordered newest first."""
        async with cls._session() as session:
            stmt = (
                select(CaseInbox)
                .where(CaseInbox.firm_id == firm_id)
                .where(CaseInbox.status == "ready")
                .order_by(CaseInbox.received_at.desc().nullslast(), CaseInbox.created_at.desc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @classmethod
    async def list_archived(
        cls,
        *,
        firm_id: str,
        q: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CaseInbox]:
        """`/inbox/archived` list. Optional `q` searches case_number / case_name
        via ILIKE. Ordered by archived_at DESC for "most recently archived first"."""
        async with cls._session() as session:
            stmt = (
                select(CaseInbox)
                .where(CaseInbox.firm_id == firm_id)
                .where(CaseInbox.status == "archived")
            )
            if q:
                like = f"%{q}%"
                stmt = stmt.where(
                    (CaseInbox.case_number.ilike(like))
                    | (CaseInbox.case_name.ilike(like))
                )
            stmt = (
                stmt.order_by(CaseInbox.archived_at.desc().nullslast())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @classmethod
    async def get(cls, *, id: str) -> Optional[CaseInbox]:
        """Single-row lookup by id."""
        async with cls._session() as session:
            stmt = select(CaseInbox).where(CaseInbox.id == id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @classmethod
    async def find_by_gmail_message_id(cls, *, message_id: str) -> Optional[CaseInbox]:
        """Dedup probe BEFORE consuming a one-shot PACER link.
        Returns the row regardless of status — any prior attempt counts as 'already processed'.
        Tolerates >1 matching rows (returns the earliest); a DB-level partial UNIQUE
        index on gmail_message_id prevents new duplicates, but legacy rows from before
        the constraint can still exist."""
        async with cls._session() as session:
            stmt = (
                select(CaseInbox)
                .where(CaseInbox.gmail_message_id == message_id)
                .order_by(CaseInbox.created_at.asc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @classmethod
    async def find_by_fingerprint(
        cls, *, firm_id: str, sha256: str,
    ) -> Optional[CaseInbox]:
        """Dedup probe AFTER download — same PDF arriving via different emails.
        Tolerates >1 matching rows (returns the earliest); see find_by_gmail_message_id."""
        async with cls._session() as session:
            stmt = (
                select(CaseInbox)
                .where(CaseInbox.firm_id == firm_id)
                .where(CaseInbox.fingerprint_sha256 == sha256)
                .order_by(CaseInbox.created_at.asc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # ─── writes ───────────────────────────────────────────────────────

    @classmethod
    async def create_ingesting(
        cls,
        *,
        firm_id: Optional[str],
        case_number: Optional[str],
        case_name: Optional[str],
        ssn_last4: Optional[str],
        ssn_extraction_status: str,
        court_district: Optional[str],
        gmail_message_id: Optional[str],
        fingerprint_sha256: Optional[str],
        received_at: Optional[datetime],
        source: str = "gmail_ecf",
        matches_unfiled_case_id: Optional[str] = None,
    ) -> Optional[CaseInbox]:
        """Insert a new row in 'ingesting' state. petition_r2_key is derived
        from the assigned id. Caller next attempts R2 upload, then flips
        status to 'ready' or 'failed_ingest'.

        Returns None when the insert lost a race against another concurrent
        worker (Postgres raised a UniqueViolation against the partial UNIQUE
        index on gmail_message_id or (firm_id, fingerprint_sha256)). The
        caller should treat this identically to a dedup_skip — the winning
        worker's row is the source of truth."""
        async with cls._session() as session:
            try:
                row = CaseInbox(
                    id=str(uuid.uuid4()),
                    firm_id=firm_id,
                    case_number=case_number,
                    case_name=case_name,
                    ssn_last4=ssn_last4,
                    ssn_extraction_status=ssn_extraction_status,
                    court_district=court_district,
                    gmail_message_id=gmail_message_id,
                    fingerprint_sha256=fingerprint_sha256,
                    received_at=received_at,
                    source=source,
                    status="ingesting",
                    petition_r2_key="",  # patched below now that id exists
                    matches_unfiled_case_id=matches_unfiled_case_id,
                )
                row.petition_r2_key = f"case_inbox/{row.id}/petition.pdf"
                session.add(row)
                await session.commit()
                await session.refresh(row)
                return row
            except IntegrityError as e:
                await session.rollback()
                logger.info(
                    "create_ingesting lost dedup race (gmail_msg=%s case=%s); "
                    "another worker won. Treating as dedup_skip.",
                    gmail_message_id, case_number,
                )
                return None
            except Exception as e:
                logger.error(
                    "CaseInboxRepository.create_ingesting failed (gmail_msg=%s case=%s): %s",
                    gmail_message_id, case_number, e,
                )
                raise

    @classmethod
    async def mark_ready(cls, *, id: str) -> int:
        """UPDATE ... SET status='ready' WHERE id=:id AND status='ingesting'.
        Returns rowcount."""
        async with cls._session() as session:
            result = await session.execute(
                text(
                    "UPDATE case_inbox SET status='ready' "
                    "WHERE id=:id AND status='ingesting'"
                ),
                {"id": id},
            )
            await session.commit()
            return result.rowcount or 0

    @classmethod
    async def mark_failed_ingest(cls, *, id: str, error_message: str) -> int:
        """UPDATE ... SET status='failed_ingest', failure_reason=:msg
        WHERE id=:id AND status='ingesting'."""
        async with cls._session() as session:
            result = await session.execute(
                text(
                    "UPDATE case_inbox SET status='failed_ingest', failure_reason=:msg "
                    "WHERE id=:id AND status='ingesting'"
                ),
                {"id": id, "msg": error_message[:2000] if error_message else None},
            )
            await session.commit()
            return result.rowcount or 0

    @classmethod
    async def mark_dismissed_to_archive(cls, *, id: str, user_id: str) -> int:
        """Soft-delete: ready → archived with dismissed_by_user_id populated.
        Discriminates user-dismiss from cron-timeout in the archived view.
        R2 bytes stay at the same key so summon can recover."""
        async with cls._session() as session:
            result = await session.execute(
                text(
                    "UPDATE case_inbox "
                    "SET status='archived', archived_at=now(), "
                    "    dismissed_at=now(), dismissed_by_user_id=:user_id "
                    "WHERE id=:id AND status='ready'"
                ),
                {"id": id, "user_id": user_id},
            )
            await session.commit()
            return result.rowcount or 0

    @classmethod
    async def mark_accepted(
        cls, *, id: str, case_id: str, user_id: str,
    ) -> int:
        """Atomic claim. Tolerates BOTH ready (Accept) and archived (Summon) sources.
        Returns rowcount; 0 → 409 (raced by another firm member or already accepted)."""
        async with cls._session() as session:
            result = await session.execute(
                text(
                    "UPDATE case_inbox "
                    "SET status='accepted', accepted_at=now(), "
                    "    accepted_by_user_id=:user_id, accepted_case_id=:case_id "
                    "WHERE id=:id AND status IN ('ready', 'archived')"
                ),
                {"id": id, "user_id": user_id, "case_id": case_id},
            )
            await session.commit()
            return result.rowcount or 0

    @classmethod
    async def update_matches_unfiled_case_id(
        cls, *, id: str, matches_unfiled_case_id: Optional[str],
    ) -> int:
        """Persist a fresh matcher run's result back to the row.

        Called by the accept/dismiss shared helper after re-running the
        matcher at action time so the column reflects current truth, not
        the (possibly stale) ingest-time hint."""
        async with cls._session() as session:
            result = await session.execute(
                text(
                    "UPDATE case_inbox SET matches_unfiled_case_id = :match "
                    "WHERE id = :id"
                ),
                {"id": id, "match": matches_unfiled_case_id},
            )
            await session.commit()
            return result.rowcount or 0

    @classmethod
    async def archive_stale_ready(cls) -> int:
        """Cron-driven archival of `ready` rows older than 48h. Returns rowcount.
        Leaves dismissed_by_user_id NULL — that's how the archived UI renders
        'timed out Xd ago' instead of 'dismissed by Maria'."""
        async with cls._session() as session:
            result = await session.execute(
                text(
                    "UPDATE case_inbox "
                    "SET status='archived', archived_at=now() "
                    "WHERE status='ready' "
                    "  AND created_at < now() - interval '48 hours'"
                ),
            )
            await session.commit()
            return result.rowcount or 0
