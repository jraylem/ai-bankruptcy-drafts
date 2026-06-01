"""Async repository for the CaseSessionMessage ORM model.

`append` assigns the monotonic `sequence_number` server-side so callers
never have to coordinate. `list_by_session` returns rows ordered by that
sequence — the FE's transcript view depends on this ordering being stable.
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

from ..models import CaseSessionMessage
from .base import BaseRepository

logger = logging.getLogger(__name__)


class CaseSessionMessageRepository(BaseRepository):
    """CRUD for `case_session_messages` rows."""

    @classmethod
    async def append(
        cls,
        *,
        case_session_id: str,
        role: str,
        content: str,
        thinking: str | None = None,
        tool_calls: list | None = None,
        tool_call_id: str | None = None,
        sequence_number: int | None = None,
    ) -> CaseSessionMessage:
        """Append a new message to the session transcript.

        `sequence_number`:
          - When None (default), computed as `max(seq) + 1` inside the
            same transaction. One extra SELECT — fine on the warm path.
          - When provided, used verbatim. Callers pass this when they
            already know the value (e.g. `1` for the welcome message on
            a freshly-created session) to skip the MAX lookup on the
            cold path. Not contention-free under high concurrency, but
            chat is single-streaming-per-session so simultaneous appends
            to the same session aren't an expected case.
        """
        if role not in ("user", "assistant", "tool"):
            raise ValueError(f"Invalid message role: {role!r}")
        new_id = str(uuid.uuid4())
        async with cls._session() as session:
            try:
                if sequence_number is not None:
                    next_seq = sequence_number
                else:
                    next_seq_row = await session.execute(
                        text(
                            "SELECT COALESCE(MAX(sequence_number), 0) + 1 AS next_seq "
                            "FROM case_session_messages "
                            "WHERE case_session_id = :sid"
                        ),
                        {"sid": case_session_id},
                    )
                    next_seq = int(next_seq_row.scalar() or 1)

                await session.execute(
                    text(
                        "INSERT INTO case_session_messages "
                        "(id, case_session_id, sequence_number, role, content, "
                        " thinking, tool_calls, tool_call_id, is_active) "
                        "VALUES (:id, :sid, :seq, :role, :content, :thinking, "
                        "        CAST(:tool_calls AS jsonb), :tool_call_id, TRUE)"
                    ),
                    {
                        "id": new_id,
                        "sid": case_session_id,
                        "seq": next_seq,
                        "role": role,
                        "content": content,
                        "thinking": thinking,
                        "tool_calls": json.dumps(tool_calls) if tool_calls is not None else None,
                        "tool_call_id": tool_call_id,
                    },
                )
                # Bump parent session's updated_at so list-recent ordering works.
                await session.execute(
                    text(
                        "UPDATE case_sessions SET updated_at = NOW() "
                        "WHERE id = :sid AND is_active = true"
                    ),
                    {"sid": case_session_id},
                )
                await session.commit()

                fetched = await session.execute(
                    text("SELECT * FROM case_session_messages WHERE id = :id"),
                    {"id": new_id},
                )
                row = fetched.fetchone()
                if row is None:
                    raise RuntimeError(f"Inserted message {new_id} disappeared")
                return CaseSessionMessage(**dict(row._mapping))
            except Exception as e:
                await session.rollback()
                logger.error(
                    f"Failed to append message to session {case_session_id}: {e}"
                )
                raise

    @classmethod
    async def list_by_session(
        cls,
        *,
        case_session_id: str,
        limit: int = 200,
        before_sequence: int | None = None,
    ) -> list[CaseSessionMessage]:
        """Return active messages for a session, oldest first by sequence_number.

        `before_sequence` is a paging anchor — pass the lowest sequence you've
        already loaded to fetch the next-older page. Returns up to `limit`
        rows.
        """
        async with cls._session() as session:
            try:
                if before_sequence is None:
                    result = await session.execute(
                        text(
                            "SELECT * FROM case_session_messages "
                            "WHERE case_session_id = :sid AND is_active = true "
                            "ORDER BY sequence_number ASC "
                            "LIMIT :limit"
                        ),
                        {"sid": case_session_id, "limit": limit},
                    )
                else:
                    result = await session.execute(
                        text(
                            "SELECT * FROM case_session_messages "
                            "WHERE case_session_id = :sid AND is_active = true "
                            "  AND sequence_number < :before "
                            "ORDER BY sequence_number ASC "
                            "LIMIT :limit"
                        ),
                        {
                            "sid": case_session_id,
                            "before": before_sequence,
                            "limit": limit,
                        },
                    )
                rows = result.fetchall()
                return [CaseSessionMessage(**dict(r._mapping)) for r in rows]
            except Exception as e:
                logger.error(
                    f"Failed to list messages for session {case_session_id}: {e}"
                )
                raise
