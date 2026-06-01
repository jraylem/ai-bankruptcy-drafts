"""Async repository for the CaseSession ORM model.

Implements the "one canonical session per (user, case)" contract via
`get_or_create`. The partial unique index on `(user_id, case_id) WHERE
is_active = true` is the source of truth — this repo's job is to handle
the race-free upsert against it.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..models import CaseSession
from .base import BaseRepository

logger = logging.getLogger(__name__)


class CaseSessionRepository(BaseRepository):
    """CRUD for `case_sessions` rows — one per (user, case) chat thread."""

    @classmethod
    async def get_or_create(
        cls,
        *,
        user_id: str,
        case_id: str,
        title: str = "Chat",
    ) -> "tuple[CaseSession, bool]":
        """Return the active session for (user, case), creating one if absent.

        Returns `(session, created)`. `created=True` when this call inserted
        a brand-new row; `created=False` when an existing row was fetched
        (including the race-fallback case where someone else inserted
        between our SELECT and our INSERT). Callers use the flag to skip
        wasted lookups on the cold path — a freshly-created session has
        no prior messages, so no `list_by_session` round trip is needed.

        Idempotent: concurrent callers all end up pointing at the same row
        (the partial unique index rejects a second active insert; on
        conflict we fall back to the SELECT and report `created=False`).
        """
        async with cls._session() as session:
            try:
                existing = await session.execute(
                    text(
                        "SELECT * FROM case_sessions "
                        "WHERE user_id = :user_id AND case_id = :case_id "
                        "  AND is_active = true "
                        "LIMIT 1"
                    ),
                    {"user_id": user_id, "case_id": case_id},
                )
                row = existing.fetchone()
                if row:
                    return CaseSession(**dict(row._mapping)), False

                new_id = str(uuid.uuid4())
                insert_error: IntegrityError | None = None
                try:
                    # is_active = TRUE is explicit on purpose — server_default
                    # covers fresh databases but only takes effect when the
                    # INSERT omits the column. We list it so the partial
                    # unique index `WHERE is_active = true` actually sees the
                    # new row even on DBs that pre-date the server_default.
                    await session.execute(
                        text(
                            "INSERT INTO case_sessions "
                            "(id, case_id, user_id, title, is_active) "
                            "VALUES (:id, :case_id, :user_id, :title, TRUE)"
                        ),
                        {
                            "id": new_id,
                            "case_id": case_id,
                            "user_id": user_id,
                            "title": title,
                        },
                    )
                    await session.commit()
                except IntegrityError as ie:
                    # Could be a real unique-index race (another request
                    # inserted between our SELECT and our INSERT) OR a
                    # genuine integrity failure (FK violation, NULL, etc.).
                    # The follow-up SELECT distinguishes the two: if a row
                    # is now present, it was a race and we adopt it; if
                    # not, the original IntegrityError is the real cause
                    # and we re-raise it.
                    insert_error = ie
                    await session.rollback()

                fetched = await session.execute(
                    text(
                        "SELECT * FROM case_sessions "
                        "WHERE user_id = :user_id AND case_id = :case_id "
                        "  AND is_active = true "
                        "LIMIT 1"
                    ),
                    {"user_id": user_id, "case_id": case_id},
                )
                row = fetched.fetchone()
                if row is None:
                    if insert_error is not None:
                        raise insert_error
                    raise RuntimeError(
                        f"get_or_create returned no row for user={user_id} "
                        f"case={case_id} despite no insert error."
                    )
                logger.info(
                    "Resolved case session id=%s user=%s case=%s",
                    row._mapping["id"], user_id, case_id,
                )
                # `created=True` only when our INSERT succeeded with no
                # IntegrityError. If insert_error is non-None we lost
                # the unique-index race to another concurrent caller;
                # they own the row we just SELECTed, we adopt it as
                # `created=False`.
                created = insert_error is None
                return CaseSession(**dict(row._mapping)), created
            except Exception as e:
                await session.rollback()
                logger.error(
                    f"get_or_create case session user={user_id} case={case_id}: {e}"
                )
                raise

    @classmethod
    async def get(cls, session_id: str) -> CaseSession | None:
        """Fetch one active session by id; returns None if missing or soft-deleted."""
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text(
                        "SELECT * FROM case_sessions "
                        "WHERE id = :session_id AND is_active = true"
                    ),
                    {"session_id": session_id},
                )
                row = result.fetchone()
                return CaseSession(**dict(row._mapping)) if row else None
            except Exception as e:
                logger.error(f"Failed to get case session {session_id}: {e}")
                raise

    @classmethod
    async def update_title(cls, session_id: str, title: str) -> CaseSession | None:
        """Rename a session. No-op if the row is missing or inactive."""
        async with cls._session() as session:
            try:
                await session.execute(
                    text(
                        "UPDATE case_sessions SET title = :title, updated_at = NOW() "
                        "WHERE id = :session_id AND is_active = true"
                    ),
                    {"session_id": session_id, "title": title},
                )
                await session.commit()
                return await cls.get(session_id)
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to rename case session {session_id}: {e}")
                raise

    @classmethod
    async def soft_delete(cls, session_id: str) -> bool:
        """Mark the session inactive — frees up the (user, case) slot for a fresh session."""
        async with cls._session() as session:
            try:
                await session.execute(
                    text(
                        "UPDATE case_sessions SET is_active = false, updated_at = NOW() "
                        "WHERE id = :session_id"
                    ),
                    {"session_id": session_id},
                )
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to soft-delete case session {session_id}: {e}")
                raise
